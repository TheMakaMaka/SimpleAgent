"""单级诊断：跑完一级后 dump 实际写出的文件内容和完整 verify 结果。

用法（在仓库根目录执行）: python tests/diagnostics/diag_level.py 3
"""

import asyncio
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import WORKSPACE, clean_workspace  # noqa: E402

from core import (  # noqa: E402
    CheckPipeline, CodingCycle, LLMClient, LLMConfig,
    Orchestrator, VerifyCommand, Worker,
)

HERE = os.path.dirname(os.path.abspath(__file__))
LEVELS_PATH = os.path.join(os.path.dirname(HERE), "bench", "levels.json")
LEVELS = {s["level"]: s for s in json.load(open(LEVELS_PATH, encoding="utf-8"))}


async def main():
    level = int(sys.argv[1])
    spec = LEVELS[level]

    clean_workspace()

    verify = VerifyCommand(command=spec["verify"], reason=f"L{level}")
    orch_llm = LLMClient(LLMConfig.from_env(prefix="ORCH"))
    worker_llm = LLMClient(LLMConfig.from_env(prefix="WORKER"))
    worker = Worker(worker_llm)
    orchestrator = Orchestrator(
        orch_llm, worker, max_rounds=6, max_same_task=2,
        pipeline=CheckPipeline(),
        verify_command={"command": verify.command, "reason": verify.reason},
    )
    cycle = CodingCycle(
        orchestrator=orchestrator, worker=worker,
        pipeline=CheckPipeline(), max_attempts=1, verbose=False,
    )

    print("=" * 78)
    print(f"L{level} {spec['name']}")
    print(f"目标: {spec['goal']}")
    print("=" * 78)

    report, memory = await cycle.run(spec["goal"], verify_command=verify)

    print("\n---------- workspace 实际文件 ----------")
    for name in sorted(os.listdir(WORKSPACE)):
        if name.startswith("_"):
            continue
        p = os.path.join(WORKSPACE, name)
        if os.path.isfile(p):
            print(f"\n### {name} ({os.path.getsize(p)} bytes)")
            with open(p, encoding="utf-8") as f:
                print(f.read())

    print("\n---------- verify 原始返回 ----------")
    v = report.verify or {}
    print(json.dumps(v, ensure_ascii=False, indent=2))

    print("\n---------- 直接手工跑一次 verify ----------")
    res = await CheckPipeline().run_verify(verify)
    print(json.dumps(res, ensure_ascii=False, indent=2))

    print(f"\nphase={report.phase.value} error={report.error}")


asyncio.run(main())
