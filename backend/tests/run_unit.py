"""统一跑单元测试（全部离线，不需要模型）。

用法（在仓库根目录执行）:
    python tests/run_unit.py

诊断脚本和难度基准需要真实模型，故意不放在这里，见 tests/README.md。
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
UNIT_DIR = os.path.join(HERE, "unit")

sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    scripts = sorted(f for f in os.listdir(UNIT_DIR) if f.startswith("test_") and f.endswith(".py"))
    if not scripts:
        print("没有找到单元测试")
        return 1

    # 统一 UTF-8，避免 Windows 控制台默认 GBK 导致断言信息乱码
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")

    results: list[tuple[str, bool]] = []
    print(f"发现 {len(scripts)} 个单元测试\n")

    for name in scripts:
        path = os.path.join(UNIT_DIR, name)
        print("=" * 74)
        print(f"运行 {name}")
        print("=" * 74)
        proc = subprocess.run(
            [sys.executable, path],
            cwd=ROOT,                     # 统一从仓库根目录运行，保证相对路径一致
            env=env,
            text=True, encoding="utf-8", errors="replace",
        )
        ok = proc.returncode == 0
        results.append((name, ok))
        print(f"→ {name}: {'PASS' if ok else 'FAIL'}\n")

    print("=" * 74)
    print("汇总")
    print("=" * 74)
    for name, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    failed = [n for n, ok in results if not ok]
    print("-" * 74)
    print(f"通过 {len(results) - len(failed)}/{len(results)}")
    if failed:
        print("失败: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
