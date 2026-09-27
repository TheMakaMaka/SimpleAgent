"""显式角色表自检。

核心验证：**多角色下不会静默顶替**。
早期实现用 `resolve_profile(prefix, fallback)`,未配置的 REVIEW 会继承 ORCH,
表现为"以为请了专业审查员,实际还是同一个模型在审自己",且不报错。
"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401

from core.config import (  # noqa: E402
    ROLES, RoleNotConfigured, describe_roles, resolve_profile, resolve_role,
    resolve_roles, role_available,
)


def clear_env() -> None:
    for spec in ROLES.values():
        for k in ("MODEL", "BASE_URL", "API_KEY", "CONTEXT_WINDOW", "PROFILE"):
            os.environ.pop(f"{spec.key}_{k}", None)


def main() -> int:
    checks: list[tuple[str, bool]] = []

    print("=" * 74)
    print("[1] 未配置任何变量时的行为")
    print("=" * 74)
    clear_env()
    roles = {r["role"]: r for r in describe_roles()}
    for name, r in roles.items():
        print(f"  {name:<18} available={str(r['available']):<5} source={r['source']}")

    checks.append(("orchestrator 有内置默认 → 可用",
                   roles["orchestrator"]["available"] is True
                   and roles["orchestrator"]["source"] == "内置默认"))
    checks.append(("worker 继承 orchestrator",
                   roles["worker"]["available"] is True
                   and roles["worker"]["source"] == "继承 orchestrator"))

    # ★ 最关键的一条
    checks.append(("reviewer 未配置即未启用（不静默继承）",
                   roles["reviewer"]["available"] is False
                   and roles["reviewer"]["model"] is None))
    checks.append(("package_optimizer 同样未启用",
                   roles["package_optimizer"]["available"] is False))

    pc: dict = {}
    try:
        rv = resolve_role("reviewer", resolved=pc)
        checks.append(("reviewer 直接解析必须报错", False))
        print(f"  !! reviewer 竟然解析成功: {rv.model}")
    except RoleNotConfigured as e:
        checks.append(("reviewer 直接解析必须报错", True))
        print(f"  reviewer 拒绝: {str(e)[:56]}")

    # 批量解析：未启用返回 None 而不是抛异常（便于 /profile 如实展示）
    out = resolve_roles("orchestrator", "worker", "reviewer")
    checks.append(("批量解析未启用返回 None",
                   out["reviewer"] is None and out["orchestrator"] is not None))
    print(f"  批量: { {k: (v.model if v else '未启用') for k,v in out.items()} }")

    # 但必需角色缺失必须抛
    os.environ["ORCH_MODEL"] = "x"
    checks.append(("role_available 反映可用性",
                   role_available("orchestrator") and not role_available("reviewer")))

    print("\n" + "=" * 74)
    print("[2] 显式配置优先")
    print("=" * 74)
    clear_env()
    os.environ["ORCH_MODEL"] = "orch-model"
    os.environ["WORKER_MODEL"] = "worker-model"
    os.environ["REVIEW_MODEL"] = "review-model"
    roles2 = {r["role"]: r for r in describe_roles()}
    for name in ("orchestrator", "worker", "reviewer"):
        print(f"  {name:<14} model={roles2[name]['model']} source={roles2[name]['source']}")
    checks.append(("orchestrator 用显式配置", roles2["orchestrator"]["model"] == "orch-model"))
    checks.append(("worker 用显式配置（不继承）", roles2["worker"]["model"] == "worker-model"))
    checks.append(("reviewer 配了就启用", roles2["reviewer"]["model"] == "review-model"))

    print("\n" + "=" * 74)
    print("[3] 只配 ORCH 时 worker 继承（有意的默认），reviewer 仍拒绝")
    print("=" * 74)
    clear_env()
    os.environ["ORCH_MODEL"] = "only-orch"
    pc2: dict = {}
    o = resolve_role("orchestrator", resolved=pc2)
    w = resolve_role("worker", resolved=pc2)
    print(f"  orchestrator={o.model}  worker={w.model}")
    checks.append(("worker 继承到 only-orch", w.model == "only-orch"))
    try:
        resolve_role("reviewer")
        checks.append(("reviewer 仍拒绝（不继承 ORCH）", False))
    except RoleNotConfigured:
        checks.append(("reviewer 仍拒绝（不继承 ORCH）", True))
    print("  reviewer 仍被拒绝 ✓")

    print("\n" + "=" * 74)
    print("[4] 未知角色 / 向后兼容")
    print("=" * 74)
    try:
        resolve_role("nonexistent_role")
        checks.append(("未知角色报错", False))
    except RoleNotConfigured as e:
        checks.append(("未知角色报错", "未知角色" in str(e)))
        print(f"  未知角色: {str(e)[:56]}")

    # resolve_profile 保留（向后兼容），但不再是推荐入口
    clear_env()
    prof = resolve_profile("ORCH")
    checks.append(("resolve_profile 仍可用（向后兼容）", prof is not None))
    print(f"  resolve_profile('ORCH') -> {prof.model}")

    clear_env()
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
