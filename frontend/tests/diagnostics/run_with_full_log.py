"""完整编码流程日志：把一轮 CodingCycle 的全过程完整记录下来。

用途：需要向人展示/复盘"流程到底怎么跑的"时用，不参与自动化断言。
日志同时打到 stdout 和 tests/output/full_cycle_log.txt。

用法（在仓库根目录执行）: python tests/diagnostics/run_with_full_log.py
"""

import asyncio
import io
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402

from core import (  # noqa: E402
    CheckPipeline,
    CodingCycle,
    LLMClient,
    LLMConfig,
    Orchestrator,
    VerifyCommand,
    Worker,
)

LOG_PATH = os.path.join(ROOT, "tests", "output", "full_cycle_log.txt")

GOAL = (
    "在 workspace 下创建 sum_1_to_100.py，实现 sum_1_to_100() 函数返回 1 到 100 的和，"
    "并在文件末尾用 print 输出该函数的结果"
)

VERIFY = VerifyCommand(
    command=(
        "import sum_1_to_100\n"
        "assert sum_1_to_100.sum_1_to_100() == 5050, "
        "f'期望 5050，实际 {sum_1_to_100.sum_1_to_100()}'\n"
        "print('PASS: sum_1_to_100() == 5050')\n"
    ),
    reason="直接调用函数并断言结果等于 5050",
)


class Tee(io.TextIOBase):
    """同时写终端和日志文件。"""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            st.write(s)
            st.flush()
        return len(s)

    def flush(self):
        for st in self.streams:
            st.flush()


async def main():
    log_file = open(LOG_PATH, "w", encoding="utf-8")
    real_stdout = sys.stdout
    sys.stdout = Tee(real_stdout, log_file)

    try:
        t0 = time.time()
        print("=" * 78)
        print("完整编码流程日志")
        print("=" * 78)
        print(f"目标        : {GOAL}")
        print(f"验证命令    : {VERIFY.command.strip()}")
        print(f"验证依据    : {VERIFY.reason}")
        print(f"开始时间    : {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 78)

        orch_llm = LLMClient(LLMConfig.from_env(prefix="ORCH"))
        worker_llm = LLMClient(LLMConfig.from_env(prefix="WORKER"))
        print(f"编排模型    : {orch_llm.config.model} @ {orch_llm.config.base_url}")
        print(f"执行模型    : {worker_llm.config.model} @ {worker_llm.config.base_url}")

        worker = Worker(worker_llm)
        # 验证命令与流水线交给主循环，使验证结论能在循环内回流
        orchestrator = Orchestrator(
            orch_llm, worker,
            max_rounds=8,
            max_same_task=2,
            pipeline=CheckPipeline(),
            verify_command={"command": VERIFY.command, "reason": VERIFY.reason},
        )

        cycle = CodingCycle(
            orchestrator=orchestrator,
            worker=worker,
            pipeline=CheckPipeline(),
            max_attempts=2,
        )

        report, memory = await cycle.run(GOAL, verify_command=VERIFY)

        print("\n" + "=" * 78)
        print("最终 CycleReport")
        print("=" * 78)
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))

        print("\n" + "=" * 78)
        print("汇总")
        print("=" * 78)
        print(f"最终阶段      : {report.phase.value}")
        print(f"尝试次数      : {report.attempts}")
        print(f"检查点后端    : {cycle.checkpoint.name}")
        print(f"提交          : {report.commit}")
        print(f"已回退        : {report.rolled_back}")
        print(f"涉及文件      : {report.touched_files}")
        print(f"任务记录数    : {len(memory.records)}")
        print(f"检查点引用    : {cycle.checkpoint.current_ref()}")
        print(f"耗时          : {time.time() - t0:.1f} 秒")
        print(f"日志已保存到  : {LOG_PATH}")
        print("=" * 78)
    finally:
        sys.stdout = real_stdout
        log_file.close()


asyncio.run(main())
