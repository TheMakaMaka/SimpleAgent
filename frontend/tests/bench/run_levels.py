"""难度阶梯跑批：逐步提高任务难度，探测模型边界。

每级都用独立的干净 workspace，逐级跑 CodingCycle，记录：
  是否通过 / 尝试次数 / 任务数 / 耗时 / 失败阶段 / 首个错误

用法（在仓库根目录执行）：
  python tests/bench/run_levels.py            # 跑全部
  python tests/bench/run_levels.py 1 4        # 只跑第 1~4 级

产物落在 tests/output/ 下（logs/ 与 levels_result.json）。
"""

import asyncio
import json
import os
import shutil
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT, clean_workspace, restore_workspace  # noqa: E402

from core import (  # noqa: E402
    CheckPipeline,
    CodingCycle,
    LLMClient,
    LLMConfig,
    Orchestrator,
    VerifyCommand,
    Worker,
)
from core.checkpoint import SNAPSHOT_ROOT  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "tests", "output")
LEVELS_PATH = os.path.join(HERE, "levels.json")
LOG_DIR = os.path.join(OUT_DIR, "logs")
RESULT_PATH = os.path.join(OUT_DIR, "levels_result.json")


def reset_checkpoints():
    shutil.rmtree(SNAPSHOT_ROOT, ignore_errors=True)


def reset_checkpoints():
    shutil.rmtree(SNAPSHOT_ROOT, ignore_errors=True)


def first_error(report) -> str:
    """从 report 里提取最有信息量的失败原因。"""
    if report.error:
        return report.error[:160]
    v = report.verify or {}
    if v.get("detail"):
        return str(v["detail"])[:160]
    for s in report.check_steps or []:
        if not s.get("passed"):
            p = s.get("parsed") or {}
            return f"{p.get('type') or ''} {p.get('message') or p.get('raw') or ''}"[:160]
    return ""


async def run_level(spec: dict) -> dict:
    level = spec["level"]
    clean_workspace()
    reset_checkpoints()

    orch_llm = LLMClient(LLMConfig.from_env(prefix="ORCH"))
    worker_llm = LLMClient(LLMConfig.from_env(prefix="WORKER"))
    worker = Worker(worker_llm)

    verify = VerifyCommand(command=spec["verify"], reason=f"L{level} 验收断言")
    orchestrator = Orchestrator(
        orch_llm, worker,
        max_rounds=12,
        max_same_task=2,
        pipeline=CheckPipeline(),
        verify_command={"command": verify.command, "reason": verify.reason},
    )
    cycle = CodingCycle(
        orchestrator=orchestrator,
        worker=worker,
        pipeline=CheckPipeline(),
        max_attempts=3,
        verbose=False,
    )

    print(f"\n{'=' * 78}")
    print(f"L{level}  {spec['name']}")
    print(f"{'=' * 78}")
    print(f"目标: {spec['goal']}")
    print("-" * 78)

    t0 = time.time()
    try:
        report, memory = await asyncio.wait_for(
            cycle.run(spec["goal"], verify_command=verify), timeout=600
        )
        elapsed = time.time() - t0
    except asyncio.TimeoutError:
        elapsed = time.time() - t0
        print(f"!! 超时（>{600}s）")
        return {
            "level": level, "name": spec["name"], "passed": False,
            "attempts": -1, "tasks": -1, "seconds": round(elapsed, 1),
            "phase": "timeout", "error": "整体超时", "backend": "n/a",
        }

    passed = report.phase.value == "record"
    # 落盘该级完整日志，便于失败后分析
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(os.path.join(LOG_DIR, f"L{level}.json"), "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)

    err = first_error(report)
    flag = "PASS" if passed else "FAIL"
    print(
        f"[{flag}] phase={report.phase.value} attempts={report.attempts} "
        f"tasks={len(memory.records)} 用时={elapsed:.1f}s "
        f"commit={report.commit} rolled_back={report.rolled_back}"
    )
    if err:
        print(f"       原因: {err}")
    print(f"       涉及文件: {report.touched_files}")

    return {
        "level": level, "name": spec["name"], "passed": passed,
        "attempts": report.attempts, "tasks": len(memory.records),
        "seconds": round(elapsed, 1), "phase": report.phase.value,
        "error": err, "backend": cycle.checkpoint.name,
        "touched": report.touched_files,
    }


async def main():
    with open(LEVELS_PATH, encoding="utf-8") as f:
        levels = json.load(f)

    lo, hi = 1, 99
    if len(sys.argv) >= 3:
        lo, hi = int(sys.argv[1]), int(sys.argv[2])
    todo = [s for s in levels if lo <= s["level"] <= hi]

    print(f"将运行 {len(todo)} 个难度等级: {[s['level'] for s in todo]}")
    print(f"workspace 将被清空（原有文件会备份到 _ws_backup 并在结束时还原）")

    results = []
    try:
        for spec in todo:
            results.append(await run_level(spec))
    finally:
        restore_workspace()

    # ---------- 汇总 ----------
    print("\n" + "=" * 78)
    print("难度阶梯结果汇总")
    print("=" * 78)
    print(f"{'级别':<4}{'任务':<28}{'结果':<6}{'尝试':<5}{'任务数':<7}{'耗时':<9}{'失败阶段'}")
    print("-" * 78)
    for r in results:
        print(
            f"L{r['level']:<3}{r['name']:<28}"
            f"{'PASS' if r['passed'] else 'FAIL':<6}"
            f"{r['attempts']:<5}{r['tasks']:<7}{r['seconds']:<9}"
            f"{r['phase']}"
        )
    print("-" * 78)

    passed = [r["level"] for r in results if r["passed"]]
    failed = [r["level"] for r in results if not r["passed"]]
    print(f"通过: {passed}")
    print(f"失败: {failed}")

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"明细已写入 {os.path.relpath(RESULT_PATH, ROOT)}"
          f"，各级 CycleReport 在 {os.path.relpath(LOG_DIR, ROOT)}/ 下")


asyncio.run(main())
