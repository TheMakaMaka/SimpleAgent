"""验证强制校验真的会拦下失败：给一个不可能满足的验证条件。

期望：verify 不通过 → cycle 进入 failed → 自动回退 → 重试后仍失败。
"""

import asyncio
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

from core import (
    CheckPipeline,
    CodingCycle,
    LLMClient,
    LLMConfig,
    Orchestrator,
    VerifyCommand,
    Worker,
)


async def main():
    orch_llm = LLMClient(LLMConfig.from_env(prefix="ORCH"))
    worker_llm = LLMClient(LLMConfig.from_env(prefix="WORKER"))
    orchestrator = Orchestrator(orch_llm, Worker(worker_llm), max_rounds=6)

    cycle = CodingCycle(
        orchestrator=orchestrator,
        worker=orchestrator.worker,
        pipeline=CheckPipeline(),
        max_attempts=2,
    )

    report, _ = await cycle.run(
        "在 workspace 下创建 counter.py，实现 inc(n) 返回 n+1",
        verify_command=VerifyCommand(
            # 故意不可能满足：inc(n) 不可能等于 n+999
            command=(
                "import counter\n"
                "assert counter.inc(5) == 1004, f'got {counter.inc(5)}'\n"
                "print('PASS')\n"
            ),
            reason="故意注入不可能通过的断言，验证门禁是否生效",
        ),
    )

    print("\n" + "=" * 60)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    print("=" * 60)
    print("phase       :", report.phase.value, "(期望 failed)")
    print("attempts    :", report.attempts, "(期望 2，说明重试了)")
    print("rolled_back :", report.rolled_back, "(期望 True)")
    print("commit      :", report.commit, "(期望 None)")


asyncio.run(main())
