"""测试套件自身的卫生检查：**测试必须能真的失败**。

为什么需要它（实测事故，见 `docs/CHANGELOG.md` §29）
----------------------------------------------------
`run_unit.py` 与 `tests/backup.py` 都**只看退出码**。而套件里曾有 5 个文件
（`test_adapter` / `test_check_pipeline` / `test_cycle_manifest` /
`test_manifest` / `test_quality`）**只打印 PASS/FAIL、从不以退出码表达结论**：

  · 它们的 FAIL 在套件里**完全不可见** —— 等于不存在；
  · `test_check_pipeline.py` 更彻底：8 个场景**一条断言都没有**，纯叙述。

这直接解释了一个致命 bug 为什么能活很久：`CodingCycle._emit` 的参数名冲突
让整条人工决策路径 100% 抛异常，而本该照看那条路径的测试恰好是"不会红的测试"。

判据（机器可判定）：每个 `tests/unit/test_*.py` 必须至少满足其一——
  1. 有 `raise SystemExit(...)` / `sys.exit(...)`（以退出码表达结论）；
  2. 有 `assert`（断言失败即非零退出）。
"""

import ast
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401

UNIT = os.path.join(ROOT, "tests", "unit")
checks: list[tuple[str, bool]] = []
SELF = "test_suite_hygiene.py"


def check(name: str, ok: bool) -> None:
    checks.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")


def can_fail(tree: ast.AST) -> tuple[bool, str]:
    """能否以退出码表达失败。返回 (可以, 依据)。"""
    for node in ast.walk(tree):
        # raise SystemExit(...)
        if isinstance(node, ast.Raise):
            exc = node.exc
            if isinstance(exc, ast.Call) and getattr(exc.func, "id", "") == "SystemExit":
                return True, "raise SystemExit"
            if isinstance(exc, ast.Name) and exc.id == "SystemExit":
                return True, "raise SystemExit"
        # sys.exit(...) / exit(...)
        if isinstance(node, ast.Call):
            fn = node.func
            if getattr(fn, "attr", "") == "exit":
                return True, "sys.exit()"
            if isinstance(fn, ast.Name) and fn.id == "exit":
                return True, "exit()"
        # 裸 assert 也会让进程非零退出
        if isinstance(node, ast.Assert):
            return True, "assert"
    return False, "只打印，不以退出码表达结论"


def main() -> int:
    files = sorted(f for f in os.listdir(UNIT)
                   if f.startswith("test_") and f.endswith(".py"))
    print("=" * 74)
    print(f"[1] 每个测试文件都必须能失败（扫 {len(files)} 个）")
    print("=" * 74)

    silent: list[str] = []
    reasons: dict[str, str] = {}
    for name in files:
        path = os.path.join(UNIT, name)
        try:
            tree = ast.parse(open(path, "r", encoding="utf-8").read())
        except SyntaxError as e:
            silent.append(f"{name}（语法错误: {e}）")
            continue
        ok, why = can_fail(tree)
        reasons[name] = why
        if not ok:
            silent.append(name)
            print(f"  FAIL  {name}: {why}")

    print(f"  能以退出码表达结论: {len(files) - len(silent)}/{len(files)}")
    print(f"  只会打印、永不失败的: {silent or '无'}")
    check("没有『只打印不退出』的测试文件", not silent)
    check("确实扫到了测试文件（否则是空转）", len(files) >= 20)
    check("本文件自身也能失败（自指检查）",
          can_fail(ast.parse(open(os.path.abspath(__file__), encoding="utf-8").read()))[0])

    print("\n" + "=" * 74)
    print("[2] 依据分布（提示：只靠 assert 的文件，失败信息不如退出码清晰）")
    print("=" * 74)
    dist: dict[str, int] = {}
    for why in reasons.values():
        dist[why] = dist.get(why, 0) + 1
    for why, n in sorted(dist.items(), key=lambda x: -x[1]):
        print(f"  {why:20s} {n} 个")
    check("至少一半文件用显式退出码（而不是只靠 assert）",
          sum(n for w, n in dist.items() if w != "assert") >= len(files) // 2)

    failed = [n for n, ok in checks if not ok]
    print(f"\n通过 {len(checks) - len(failed)}/{len(checks)}")
    return 1 if failed else 0


raise SystemExit(main())
