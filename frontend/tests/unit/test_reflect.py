"""反思分析器自检。

重点验证两件事：
  1. 六个检测器各自能命中预期模式。
  2. **核心纪律**：模型自述绝不被当作证据。
     唯一引用 assumed 的地方是 detect_false_claims，且只用于**指出矛盾**。
"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401

from core.reflect import (  # noqa: E402
    ALL_DETECTORS, ReflectionReport, detect_budget_exhaustion,
    detect_failure_clusters, detect_false_claims, detect_persistent_manifest_gaps,
    detect_repeated_failures, detect_retry_hotspots, reflect,
)
from storage.store import Event  # noqa: E402


def build_events() -> list[Event]:
    """四个 cycle：三个失败（含假成功与重复失败），一个成功。"""
    evs: list[Event] = []
    seq = 0

    def add(kind, cid, goal, **payload):
        nonlocal seq
        seq += 1
        evs.append(Event(kind=kind, cycle_id=cid, goal=goal, seq=seq, payload=payload))

    for cid, goal, sym in (("cyA", "实现 fib", "fib"),
                           ("cyB", "实现 fact", "fib"),
                           ("cyD", "再试 fib", "fib")):
        add("cycle_start", cid, goal)
        add("plan", cid, goal, attempt=2,
            declared=[{"path": f"{sym}.py", "symbols": [sym]}])
        # 模型自述成功 —— 但验证会失败（假成功）
        add("task_result", cid, goal, task_id="t1", ok=True,
            output="已实现并验证通过", error="")
        add("manifest", cid, goal, checked=True, passed=False,
            violations=[{"kind": "declared-missing", "path": "cli.py",
                         "message": "计划要产出 cli.py，但该文件不存在"}],
            actual_files=[{"path": f"{sym}.py", "sha1": "aa"}])
        add("syntax", cid, goal, path=f"{sym}.py", ok=False,
            message="unexpected character after line continuation")
        add("verify", cid, goal, passed=False, detail="AssertionError: got 34", command="x")
        add("cycle_end", cid, goal, status="failed",
            error="达到主循环上限 12 轮，未能完成", attempt=2)

    add("cycle_start", "cyC", "实现 add")
    add("plan", "cyC", "实现 add", attempt=1, declared=[{"path": "add.py", "symbols": ["add"]}])
    add("task_result", "cyC", "实现 add", task_id="t1", ok=True, output="已写 add.py", error="")
    add("manifest", "cyC", "实现 add", checked=True, passed=True, violations=[],
        actual_files=[{"path": "add.py", "sha1": "cc"}])
    add("syntax", "cyC", "实现 add", path="add.py", ok=True, message="")
    add("verify", "cyC", "实现 add", passed=True, detail="PASS", command="x")
    add("cycle_end", "cyC", "实现 add", status="passed", commit="abc123", attempt=1)
    return evs


def main() -> int:
    checks: list[tuple[str, bool]] = []
    evs = build_events()
    report = reflect(evs)

    print("=" * 74)
    print("[1] 汇总")
    print("=" * 74)
    print(f"  cycles={report.cycles_analyzed} summary={report.summary}")
    checks.append(("分析了 4 个 cycle", report.cycles_analyzed == 4))
    checks.append(("通过/失败计数正确",
                   report.summary["passed"] == 1 and report.summary["failed"] == 3))

    kinds = {p.kind for p in report.patterns}
    print(f"\n  命中模式: {sorted(kinds)}")

    print("\n" + "=" * 74)
    print("[2] 六个检测器")
    print("=" * 74)
    checks.append(("repeated_failure 命中", "repeated_failure" in kinds))
    checks.append(("failure_cluster 命中", "failure_cluster" in kinds))
    checks.append(("false_claim 命中", "false_claim" in kinds))
    checks.append(("manifest_gap 命中", "manifest_gap" in kinds))
    checks.append(("retry_hotspot 命中", "retry_hotspot" in kinds))
    checks.append(("budget_exhaustion 命中", "budget_exhaustion" in kinds))

    # 假成功必须是 high
    fc = [p for p in report.patterns if p.kind == "false_claim"]
    checks.append(("假成功标为 high", bool(fc) and fc[0].confidence == "high"))
    print(f"  false_claim confidence = {fc[0].confidence if fc else 'N/A'}")

    # 反复出现 3 次以上应升为 high（这里 2 个 cycle → medium）
    rf = [p for p in report.patterns if p.kind == "repeated_failure"]
    checks.append(("重复失败有证据来源", bool(rf) and all(p.evidence for p in rf)))

    print("\n" + "=" * 74)
    print("[3] 核心纪律：证据必须可溯源，且不采信模型自述")
    print("=" * 74)
    # detector_error 是内部故障，本不该出现；显式检查它不存在，
    # 否则一个崩溃的检测器会被静默吞掉
    checks.append(("没有检测器崩溃", "detector_error" not in kinds))
    all_ev = [e for p in report.patterns for e in p.evidence]
    checks.append(("每条模式都有证据", all(p.evidence for p in report.patterns)))
    checks.append(("证据都带 cycle_id", all(e.cycle_id for e in all_ev)))
    # seq 允许为 0（跨周期聚合保留的是首条来源，可能来自旧事件）；
    # 关键是 label 必须可读、可回溯
    checks.append(("证据 label 均可读",
                   all(e.label() and e.label() != "" for e in all_ev)))

    # false_claim 是唯一允许提到 assumed 的模式，且目的是指出矛盾
    others = [p for p in report.patterns if p.kind != "false_claim"]
    mentions_assumed = [p for p in others if "已实现并验证通过" in p.detail]
    checks.append(("非 false_claim 模式不引用模型自述", not mentions_assumed))

    # 证据 label 可读
    labels = [e.label() for e in all_ev[:5]]
    print(f"  证据样例: {labels}")
    checks.append(("label 非空", all(labels)))

    print("\n" + "=" * 74)
    print("[4] 渲染")
    print("=" * 74)
    md = report.to_markdown()
    checks.append(("markdown 有标题", md.startswith("# 反思报告")))
    checks.append(("markdown 声明未自动应用", "未自动应用" in md))
    checks.append(("markdown 含证据行", "证据：" in md))
    print(f"  markdown 长度: {len(md)}")

    print("\n" + "=" * 74)
    print("[5] 边界：空输入 / 单个成功 cycle")
    print("=" * 74)
    empty = reflect([])
    checks.append(("空输入不崩", empty.cycles_analyzed == 0 and empty.patterns == []))
    print(f"  空输入: cycles={empty.cycles_analyzed} patterns={len(empty.patterns)}")
    print(f"  空输入 markdown: {empty.to_markdown().splitlines()[-1]}")

    only_ok = [e for e in evs if e.cycle_id == "cyC"]
    ok_report = reflect(only_ok)
    checks.append(("全成功时不误报假成功",
                   not any(p.kind == "false_claim" for p in ok_report.patterns)))
    checks.append(("全成功时无重复失败",
                   not any(p.kind == "repeated_failure" for p in ok_report.patterns)))
    print(f"  单个成功 cycle: patterns={[p.kind for p in ok_report.patterns]}")

    print("\n" + "=" * 74)
    print("[6] 检测器失败不应让整份反思为空")
    print("=" * 74)
    # 注意：不能用 `import core.reflect as R` —— core/__init__.py 里
    # `from .reflect import reflect` 会让 `core.reflect` 解析成**函数**而非模块。
    import importlib

    R = importlib.import_module("core.reflect")
    checks.append(("能取到 reflect 模块（未被同名函数遮蔽）",
                   hasattr(R, "ALL_DETECTORS")))
    original = R.ALL_DETECTORS

    def boom(events, snaps):
        raise RuntimeError("模拟检测器崩溃")

    try:
        R.ALL_DETECTORS = (boom, detect_retry_hotspots)
        r2 = reflect(evs)
        has_err = any(p.kind == "detector_error" for p in r2.patterns)
        still_works = any(p.kind == "retry_hotspot" for p in r2.patterns)
        print(f"  记录到 detector_error: {has_err}; 其它检测器仍工作: {still_works}")
        checks.append(("单检测器崩溃被隔离", has_err and still_works))
    finally:
        R.ALL_DETECTORS = original

    print("\n" + "=" * 74)
    print("断言检查")
    print("=" * 74)
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    failed = [n for n, ok in checks if not ok]
    print(f"\n通过 {len(checks) - len(failed)}/{len(checks)}")
    if failed:
        print("失败: " + "; ".join(failed))
    return 1 if failed else 0


raise SystemExit(main())
