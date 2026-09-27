"""端到端跑一轮真实编码流程（走本地 Ollama），确认正向路径可通。

用法（在仓库根目录执行）: python tests/diagnostics/cycle_e2e.py
"""

import asyncio
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import clean_workspace  # noqa: E402

from core import (  # noqa: E402
    CheckPipeline,
    CodingCycle,
    LLMClient,
    LLMConfig,
    Orchestrator,
    VerifyCommand,
    Worker,
)


async def main():
    clean_workspace()
    orch_llm = LLMClient(LLMConfig.from_env(prefix="ORCH"))
    worker_llm = LLMClient(LLMConfig.from_env(prefix="WORKER"))
    orchestrator = Orchestrator(orch_llm, Worker(worker_llm), max_rounds=8)

    cycle = CodingCycle(
        orchestrator=orchestrator,
        worker=orchestrator.worker,
        pipeline=CheckPipeline(),
        max_attempts=2,
    )

    report, memory = await cycle.run(
        "在 workspace 下创建 math_utils.py，实现 fib(n) 返回斐波那契数列第 n 项（fib(1)=1, fib(2)=1）",
        verify_command=VerifyCommand(
            command=(
                "import math_utils\n"
                "assert math_utils.fib(1) == 1, math_utils.fib(1)\n"
                "assert math_utils.fib(2) == 1, math_utils.fib(2)\n"
                "assert math_utils.fib(10) == 55, math_utils.fib(10)\n"
                "print('PASS')\n"
            ),
            reason="直接调用 fib 并断言数列值",
        ),
    )

    print("\n" + "=" * 60)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    print("=" * 60)
    print("phase      :", report.phase.value)
    print("commit     :", report.commit)
    print("touched    :", report.touched_files)
    print("rolled_back:", report.rolled_back)


asyncio.run(main())
