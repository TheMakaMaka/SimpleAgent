"""测试公共引导：把仓库根目录加入 sys.path。

测试脚本可以位于 tests/ 的任意子目录，导入 `core` / `tools` 前先 import 本模块：

    from _bootstrap import ROOT, WORKSPACE   # noqa: F401

同时也提供统一的 workspace 清理与断言小工具，避免每个脚本各写一份。
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))   # tests/
ROOT = os.path.dirname(HERE)                        # 仓库根目录
WORKSPACE = os.path.join(ROOT, "workspace")
OUTPUT_DIR = os.path.join(HERE, "output")

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# 扫描/清理 workspace 时保留的内部目录
KEEP_DIRS = {"_debug", "_tmp", "__pycache__"}


def clean_workspace(keep_existing: bool = False) -> None:
    """清空 workspace 里由模型产出的文件，保留内部调试目录。

    keep_existing=True 时把原有文件备份到 tests/output/_ws_backup 并返回还原函数。
    """
    os.makedirs(WORKSPACE, exist_ok=True)
    if not keep_existing:
        for name in os.listdir(WORKSPACE):
            if name in KEEP_DIRS:
                continue
            p = os.path.join(WORKSPACE, name)
            shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)
        return

    backup = os.path.join(OUTPUT_DIR, "_ws_backup")
    shutil.rmtree(backup, ignore_errors=True)
    os.makedirs(backup, exist_ok=True)
    for name in os.listdir(WORKSPACE):
        if name in KEEP_DIRS:
            continue
        shutil.move(os.path.join(WORKSPACE, name), os.path.join(backup, name))

    def restore() -> None:
        for name in os.listdir(backup):
            src = os.path.join(backup, name)
            dst = os.path.join(WORKSPACE, name)
            if os.path.exists(dst):
                shutil.rmtree(dst, ignore_errors=True) if os.path.isdir(dst) else os.remove(dst)
            shutil.move(src, dst)
        shutil.rmtree(backup, ignore_errors=True)

    return restore


def restore_workspace() -> None:
    """把 clean_workspace(keep_existing=True) 备份的文件还原回 workspace。"""
    backup = os.path.join(OUTPUT_DIR, "_ws_backup")
    if not os.path.isdir(backup):
        return
    for name in os.listdir(backup):
        src = os.path.join(backup, name)
        dst = os.path.join(WORKSPACE, name)
        if os.path.exists(dst):
            shutil.rmtree(dst, ignore_errors=True) if os.path.isdir(dst) else os.remove(dst)
        shutil.move(src, dst)
    shutil.rmtree(backup, ignore_errors=True)


class Checker:
    """极简断言收集器，让脚本结束时统一打印 PASS/FAIL。"""

    def __init__(self) -> None:
        self.results: list[tuple[str, bool]] = []

    def check(self, name: str, ok: bool) -> None:
        self.results.append((name, bool(ok)))

    def report(self) -> int:
        print("\n" + "=" * 70)
        print("断言检查")
        print("=" * 70)
        for name, ok in self.results:
            print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        failed = [n for n, ok in self.results if not ok]
        print("-" * 70)
        print(f"通过 {len(self.results) - len(failed)}/{len(self.results)}")
        if failed:
            print("失败项: " + ", ".join(failed))
        return 1 if failed else 0
