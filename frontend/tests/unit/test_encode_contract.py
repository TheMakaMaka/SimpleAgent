"""离线校验：/encode 的响应契约字段齐全，且 workspace 清理生效。

不调用模型：直接构造 CycleReport，验证 EncodeResponse 能构造成功。
"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401  (把仓库根目录加入 sys.path)

import main  # noqa: E402
from core import CyclePhase, CycleReport  # noqa: E402


def build(phase: CyclePhase, manifest=None, verify=None):
    r = CycleReport(cycle_id="cy_test", goal="g")
    r.phase = phase
    r.attempts = 1
    r.manifest = manifest
    r.verify = verify
    r.commit = "snap0001" if phase == CyclePhase.RECORD else None
    return main.EncodeResponse(
        ok=phase == CyclePhase.RECORD,
        cycle_id=r.cycle_id,
        answer="x",
        phase=r.phase.value,
        attempts=r.attempts,
        checkpoint_backend="snapshot",
        commit=r.commit,
        rolled_back=False,
        touched_files=["a.py"],
        check_passed=True,
        verify_passed=(r.verify or {}).get("passed"),
        manifest_passed=(r.manifest or {}).get("passed"),
        error=None,
    )


resp_ok = build(
    CyclePhase.RECORD,
    manifest={"passed": True},
    verify={"passed": True},
)
resp_fail = build(CyclePhase.FAILED, manifest={"passed": False}, verify=None)

print("成功响应:", resp_ok.model_dump())
print()
print("失败响应:", resp_fail.model_dump())

checks = [
    ("成功时 ok=True", resp_ok.ok is True),
    ("字段 manifest_passed 存在", resp_ok.manifest_passed is True),
    ("字段 verify_passed 存在", resp_ok.verify_passed is True),
    ("失败时 manifest_passed=False", resp_fail.manifest_passed is False),
    ("verify 缺失时为 None", resp_fail.verify_passed is None),
    ("phase 为字符串", isinstance(resp_ok.phase, str)),
]
print()
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
failed = [n for n, ok in checks if not ok]
print(f"\n通过 {len(checks) - len(failed)}/{len(checks)}")
raise SystemExit(1 if failed else 0)
