"""文档审查：机械可验证的那一层。

检查逻辑住在 `core/doc_review.py`（工具与测试**共用同一套判据**，
避免两处逻辑分叉——那是本项目一直在治理的漂移）。

本文件只负责：装载文档、调用共享检查、断言结果。
"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401

from core.doc_review import (  # noqa: E402
    check_code_blocks, check_imports, check_module_refs, check_profile_fields,
    check_section_refs, importable_modules,
)

DOCS = {
    "README.md": os.path.join(ROOT, "README.md"),
    "CYCLE.md": os.path.join(ROOT, "CYCLE.md"),
    "ARCHITECTURE.md": os.path.join(ROOT, "docs", "ARCHITECTURE.md"),
    "MODULES.md": os.path.join(ROOT, "docs", "MODULES.md"),
    "OPERATIONS.md": os.path.join(ROOT, "docs", "OPERATIONS.md"),
}


def read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main() -> int:
    checks: list[tuple[str, bool]] = []
    texts = {name: read(path) for name, path in DOCS.items()}
    mods = importable_modules()

    print("=" * 74)
    print(f"[0] 可校验模块 {len(mods)} 个（判据来自 core/doc_review.py，与工具共用）")
    print("=" * 74)

    print("\n[1] python 代码块语法")
    for name, t in texts.items():
        r = check_code_blocks(t)
        checks.append((f"{name} 代码块语法合法", r.ok))
        print(f"  {'PASS' if r.ok else 'FAIL'}  {name}: {r.detail}"
              + (f"  错误 {r.evidence}" if r.evidence else ""))

    print("\n[2] import 指向真实符号")
    for name, t in texts.items():
        r = check_imports(t, mods)
        checks.append((f"{name} import 引用存在", r.ok))
        print(f"  {'PASS' if r.ok else 'FAIL'}  {name}: "
              f"不存在 {r.evidence or '无'}")

    print("\n[3] 「模块.符号」引用")
    for name, t in texts.items():
        r = check_module_refs(t, mods)
        checks.append((f"{name} 模块.符号引用存在", r.ok))
        print(f"  {'PASS' if r.ok else 'FAIL'}  {name}: "
              f"不存在 {r.evidence or '无'}")

    print("\n[4] § 交叉引用")
    # 章节号池要含**被引用但不在正文检查范围**的文档：
    # 上游文档里合法地写着"见 `docs/CHANGELOG.md` §7"，
    # 不把 CHANGELOG 的章节号放进池子，这类引用就等于从没被校验过。
    extra_refs = {}
    for extra in ("CHANGELOG.md", "VERSIONS.md", "FRONTEND_CONTRACT.md",
                  "PENDING_DECISIONS.md"):
        p = os.path.join(ROOT, "docs", extra)
        if os.path.exists(p):
            extra_refs[extra] = read(p)
    print(f"  章节号池额外纳入: {sorted(extra_refs)}")
    r = check_section_refs(texts, extra_refs)
    checks.append(("§ 交叉引用有效", r.ok))
    print(f"  {'PASS' if r.ok else 'FAIL'}  无效引用 {r.evidence or '无'}")
    # 版本戳不是引用：它必须**不**被当成引用（否则会假失败）
    stamp_refs = [ln for t in texts.values() for ln in t.splitlines()
                  if "同步至 CHANGELOG §" in ln]
    checks.append(("版本戳行存在（否则上面那条检查有盲区）", bool(stamp_refs)))
    print(f"  版本戳行: {len(stamp_refs)} 处（已排除在引用校验外）")

    print("\n[5] /profile 字段名")
    try:
        import asyncio

        import main as app_module

        prof = asyncio.run(app_module.profile())
        r = check_profile_fields(texts, set(prof))
        checks.append(("/profile 字段名存在", r.ok))
        print(f"  {'PASS' if r.ok else 'FAIL'}  {r.detail}"
              + (f"  不存在 {r.evidence}" if r.evidence else ""))
    except Exception as e:  # noqa: BLE001
        checks.append(("/profile 可调用", False))
        print(f"  FAIL  无法调用 /profile: {e}")

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
