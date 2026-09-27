"""记忆渲染的预算与优先级自检。

修的两个坑：
  1. 验证结论原本在 prompt **最末尾** —— 一旦被截断，最该看到的信息先丢
  2. 原本按**条数**硬截断（最近 12 条），更早的记录静默消失
"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401

from core.memory import SharedMemory  # noqa: E402
from core.model_profile import ModelLimits  # noqa: E402
from core.task import Task, TaskResult  # noqa: E402


def build(n_ok: int = 30, n_fail: int = 3, verify_failed: bool = True) -> SharedMemory:
    m = SharedMemory(goal="实现一个大模块")
    i = 0
    for _ in range(n_ok):
        t = Task(id=f"t{i}", description=f"第{i}步：写一段较长的实现描述" * 3)
        m.record(t, TaskResult(task_id=t.id, ok=True, output="完成" * 40, steps_used=1))
        i += 1
    for _ in range(n_fail):
        t = Task(id=f"t{i}", description=f"第{i}步：出错的步骤" * 2)
        m.record(t, TaskResult(task_id=t.id, ok=False, output="",
                               error="AssertionError: got 34", steps_used=2))
        i += 1
    m.set_verify(not verify_failed,
                 "AssertionError: got 34" if verify_failed else "PASS",
                 "assert f(10) == 55", "fp")
    return m


def main() -> int:
    checks: list[tuple[str, bool]] = []

    print("=" * 74)
    print("[1] 预算从 context_window 推导")
    print("=" * 74)
    for cw in (2048, 8192, 32768, 131072):
        lim = ModelLimits.from_context_window(cw)
        print(f"  ctx={cw:<7} prompt_chars={lim.orchestrator_prompt_chars:<7} "
              f"tool_chars={lim.tool_result_chars}")
    a = ModelLimits.from_context_window(8192).orchestrator_prompt_chars
    b = ModelLimits.from_context_window(131072).orchestrator_prompt_chars
    checks.append(("窗口越大预算越大", b > a))
    checks.append(("预算有下限（不会太小）", a >= 2000))
    checks.append(("可显式覆盖",
                   ModelLimits.from_context_window(8192, orchestrator_prompt_chars=1)
                   .orchestrator_prompt_chars == 1))

    print("\n" + "=" * 74)
    print("[2] 验证结论排在最前（截断时最该看到的不丢）")
    print("=" * 74)
    m = build()
    full = m.summary_for_orchestrator(char_budget=10 ** 6)
    tiny = m.summary_for_orchestrator(char_budget=400)
    print(f"  无限制 {len(full)} 字符；预算 400 -> {len(tiny)} 字符")
    checks.append(("完整渲染以验证结论开头", full.strip().startswith("【验证结论】")))
    checks.append(("极小预算下验证结论仍在开头",
                   tiny.strip().startswith("【验证结论】")))
    checks.append(("极小预算下结论内容完整",
                   "目标尚未达成" in tiny or "status=done" in tiny))
    checks.append(("极小预算确实变短了", len(tiny) < len(full)))

    print("\n" + "=" * 74)
    print("[3] 截断必须明说丢了多少（不再静默）")
    print("=" * 74)
    # 两种省略提示都要认：
    #   "省略较早的 N 条记录"    —— 进到了「已完成任务」段但没填满
    #   "因 prompt 预算不足，省略了 N 条任务记录" —— 预算在到达该段前就耗尽
    def says_truncated(text: str) -> bool:
        return ("省略较早的" in text) or ("省略了" in text and "预算不足" in text)

    checks.append(("省略时给出提示", says_truncated(tiny)))
    print(f"  tiny 含提示: {says_truncated(tiny)}")
    print(f"    {(tiny.splitlines()[-1] if tiny.splitlines() else '')[:56]}")
    # 预算足够大时不应出现省略提示
    checks.append(("预算充足时无误导性省略提示", not says_truncated(full)))

    print("\n" + "=" * 74)
    print("[4] 优先级顺序：失败 > 事实 > 产物 > 已完成")
    print("=" * 74)
    m2 = build()
    m2.add_fact("Python 3.10 不支持 match-case 以外的 3.11 语法")
    m2.artifacts["a1"] = __import__("core.task", fromlist=["Artifact"]).Artifact(
        key="a1", kind="file", path="mod.py")
    mid = m2.summary_for_orchestrator(char_budget=700)
    lines = mid.splitlines()
    pos_fail = next((i for i, l in enumerate(lines) if l.startswith("失败任务")), 999)
    pos_fact = next((i for i, l in enumerate(lines) if l.startswith("关键事实")), 999)
    pos_art = next((i for i, l in enumerate(lines) if l.startswith("已有产物")), 999)
    pos_done = next((i for i, l in enumerate(lines) if l.startswith("已完成任务")), 999)
    print(f"  位置: 失败={pos_fail} 事实={pos_fact} 产物={pos_art} 已完成={pos_done}")
    checks.append(("失败先于事实/产物/已完成", pos_fail < pos_fact and pos_fail < pos_done))
    checks.append(("事实先于已完成", pos_fact < pos_done))
    checks.append(("产物先于已完成", pos_art < pos_done))
    checks.append(("顺序单调", pos_fail <= pos_fact <= pos_art <= pos_done))

    print("\n" + "=" * 74)
    print("[5] 已完成任务按时间倒序填充（最近的一定在预算内）")
    print("=" * 74)
    # 用足够装下几条但不装全部的预算
    small = build(n_ok=50, n_fail=0, verify_failed=False)
    txt = small.summary_for_orchestrator(char_budget=800)
    has_last = "t49" in txt
    has_first = "t0:" in txt
    print(f"  含最新记录 t49: {has_last}；含最早记录 t0: {has_first}")
    checks.append(("最新的记录一定在", has_last))

    print("\n" + "=" * 74)
    print("[6] max_records 仍可显式限制（向后兼容语义）")
    print("=" * 74)
    limited = full_count = small.summary_for_orchestrator(char_budget=10 ** 6,
                                                          max_records=5)
    shown = sum(1 for l in limited.splitlines()
                if l.startswith("  [") and "t" in l)
    print(f"  max_records=5 时显示 {shown} 条（含省略提示）")
    checks.append(("max_records 生效", "省略较早的" in limited))

    print("\n" + "=" * 74)
    print("[7] 空记忆不崩")
    print("=" * 74)
    empty = SharedMemory(goal="空目标")
    out = empty.summary_for_orchestrator(char_budget=200)
    print(f"  输出: {out!r}")
    checks.append(("空记忆输出含目标", "空目标" in out))
    checks.append(("空记忆长度合理", len(out) < 200))

    print("\n" + "=" * 74)
    print("断言检查")
    print("=" * 74)
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    failed = [n for n, ok in checks if not ok]
    print(f"\n通过 {len(checks) - len(failed)}/{len(checks)}")
    if failed:
        print("失败项:")
        for f in failed:
            print(f"  - {f}")
    return 1 if failed else 0


raise SystemExit(main())
