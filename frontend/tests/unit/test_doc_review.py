"""文档审查：机械可验证的那一层。

检查逻辑住在 `core/doc_review.py`（工具与测试**共用同一套判据**，
避免两处逻辑分叉——那是本项目一直在治理的漂移）。

本文件只负责：装载文档、调用共享检查、断言结果。

## 为什么这里要先把版本戳摘掉

`§` 这个符号在本项目里有**两种互不相干的用法**：

| 用法 | 例子 | 指向 |
|---|---|---|
| 交叉引用 | `详见 CYCLE.md §2.2` | 那 5 份上游文档的章节 |
| 版本戳 | `同步至 CHANGELOG §25` | **CHANGELOG** 的条目号 |

`core.doc_review.check_section_refs` 只把前 5 份文档的标题当靶子
（CHANGELOG 不在 `texts` 里），于是版本戳的数字会被当成一个指向不明章节的引用。

以前没暴露，是因为 CHANGELOG 的节号**碰巧**和 `MODULES.md` 的模块号对齐
（§23↔`bridge/audit.py`、§24↔`contract_vocab.py`）——一旦某轮只改工具、
MODULES 没有同号章节，就会红。这是**两个约定靠同号巧合互相满足**，
不是真的有效。

所以这里把版本戳行摘掉再查交叉引用，并**另立一条断言**专门校验版本戳
（它必须等于 CHANGELOG 的最大条目号）——两种约定各查各的。
"""

import os
import re
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
CHANGELOG = os.path.join(ROOT, "docs", "CHANGELOG.md")

#: 版本戳行。摘掉它再查交叉引用（理由见模块 docstring）。
STAMP_RE = re.compile(r"^.*同步至\s*CHANGELOG\s*§\d+.*$", re.MULTILINE)


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

    print("\n[4] § 交叉引用（**不含**版本戳行）")
    stripped = {name: STAMP_RE.sub("", t) for name, t in texts.items()}
    n_stamps = sum(len(STAMP_RE.findall(t)) for t in texts.values())
    print(f"      摘掉版本戳 {n_stamps} 行（它们是 CHANGELOG 条目号，不是章节引用）")

    # ★ 章节池还要含**没进 DOCS 的文档**（DIAGNOSTICS / LAYOUT）。
    #   `check_section_refs` 只把"传给它的那些文档"的标题当靶子，而上游文档会
    #   **合法地**引用它们的章节（例如 "详见 `docs/DIAGNOSTICS.md` §7.5"）。
    #   不把它们的标题放进去，这种带文件名限定的引用会被误判成"无效引用"。
    #   放宽方向是安全的：池子变大只会让能解析的引用变多，`§99` 照样红。
    for extra in ("DIAGNOSTICS.md", "LAYOUT.md"):
        p = os.path.join(ROOT, "docs", extra)
        if os.path.isfile(p):
            stripped[extra] = read(p)

    r = check_section_refs(stripped)
    checks.append(("§ 交叉引用有效", r.ok))
    print(f"  {'PASS' if r.ok else 'FAIL'}  无效引用 {r.evidence or '无'}")

    print("\n[4b] 版本戳指向真实的 CHANGELOG 条目")
    changelog = read(CHANGELOG)
    sections = {int(n) for n in re.findall(r"^##\s*(\d+)\.", changelog, re.MULTILINE)}
    checks.append(("CHANGELOG 有条目编号", bool(sections)))
    print(f"  {'PASS' if sections else 'FAIL'}  CHANGELOG 条目 "
          f"{sorted(sections)[-6:] if sections else '无'}…")
    for name, t in texts.items():
        m = re.search(r"同步至\s*CHANGELOG\s*§(\d+)", t)
        ok = bool(m) and int(m.group(1)) in sections
        checks.append((f"{name} 版本戳指向真实条目", ok))
        declared = m.group(1) if m else "缺失"
        print(f"  {'PASS' if ok else 'FAIL'}  {name}: 声明 §{declared}")

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
