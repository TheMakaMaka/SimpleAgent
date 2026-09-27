"""阶段推进顺序（PHASE_ORDER）的强制校验自检。

背景：PHASE_ORDER 曾经只是声明、无人消费，注释里写的
「CHECK 未通过时不允许进入 VERIFY」并不由它保证。现在由 CycleReport.enter 强制。
"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401

from core import CyclePhase as P  # noqa: E402
from core import CycleReport  # noqa: E402


def fresh():
    return CycleReport(cycle_id="c", goal="g")


def rejects(rep, phase) -> bool:
    try:
        rep.enter(phase)
        return False
    except ValueError:
        return True


def main() -> int:
    print("=" * 72)
    print("阶段推进校验")
    print("=" * 72)

    # 正常推进
    r = fresh()
    for ph in (P.PLAN, P.WRITE, P.CHECK, P.VERIFY, P.RECORD):
        r.enter(ph)
    print("  正常推进:", " -> ".join(r.transitions))

    # 越级 / 倒退 / 跳过 CHECK
    r2 = fresh(); r2.enter(P.PLAN)
    r3 = fresh(); r3.enter(P.PLAN); r3.enter(P.WRITE)
    r4 = fresh()
    r4.enter(P.PLAN); r4.enter(P.WRITE); r4.enter(P.CHECK); r4.enter(P.VERIFY)
    r5 = fresh()
    r5.enter(P.PLAN); r5.enter(P.WRITE); r5.enter(P.CHECK)
    r5.enter(P.VERIFY); r5.enter(P.RECORD)

    # 失败后重启
    r6 = fresh()
    r6.enter(P.PLAN); r6.enter(P.WRITE); r6.enter(P.FAILED); r6.enter(P.PLAN)
    print("  FAILED 后重启:", " -> ".join(r6.transitions))

    # 多次重试（回归项：曾在 PLAN 重复进入时报错）
    r7 = fresh()
    r7.enter(P.PLAN); r7.enter(P.FAILED)
    r7.enter(P.PLAN); r7.enter(P.FAILED)
    r7.enter(P.PLAN)
    print("  连续重试:", " -> ".join(r7.transitions))

    # FAILED 之后不能再次进入 FAILED
    r8 = fresh()
    r8.enter(P.PLAN)
    r8.enter(P.FAILED)

    checks = [
        ("正常顺序通过", r.phase is P.RECORD),
        ("PLAN 越级到 VERIFY 被拦", rejects(r2, P.VERIFY)),
        ("WRITE 跳过 CHECK 到 VERIFY 被拦", rejects(r3, P.VERIFY)),
        ("VERIFY 倒退到 CHECK 被拦", rejects(r4, P.CHECK)),
        ("RECORD 之后再推进被拦", rejects(r5, P.VERIFY)),
        ("FAILED 可从任意阶段进入", r6.phase is P.PLAN),
        ("多次重试不误报", r7.phase is P.PLAN),
        ("FAILED 连续进入被拦", rejects(r8, P.FAILED)),
    ]

    print()
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    failed = [n for n, ok in checks if not ok]
    print(f"\n通过 {len(checks) - len(failed)}/{len(checks)}")
    return 1 if failed else 0


raise SystemExit(main())
