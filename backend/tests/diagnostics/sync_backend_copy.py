"""把本仓库（上游）的上游代码同步进前端的自带副本 `backend/`。

**默认只预演，不写任何文件**；加 `--apply` 才真正复制（且先备份）。

为什么会有这个脚本
------------------
`bridge/paths.py` 的判据是：`AGENT_BACKEND_DIR` 未设 → 用 `<VueWeb>/backend` 兜底。
用户的真实运行正是这种情况，于是一份 9-25 的旧副本被加载，
**上游的修复全部无效，而服务照常启动**（失败签名与修之前逐字相同）。

**首选是「指过去」而不是「搬过来」**（前端自己的文档也这么写）：

    $env:AGENT_BACKEND_DIR = "<上游 checkout>"

本脚本是兜底：当运行环境不方便设环境变量时，把上游同步进副本。
但它**会再次落后** —— 每次上游改动后都要重跑，所以 `backend_dir_check.py`
应当一起用（后者只读，用来发现"又落后了"）。

用法：

    python tests/diagnostics/sync_backend_copy.py                    # 预演
    python tests/diagnostics/sync_backend_copy.py --apply            # 真同步（先备份）
"""

import argparse
import os
import shutil
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))          # tests/

from _bootstrap import ROOT  # noqa: E402   （上游 checkout）

DEFAULT_FRONTEND = r"D:\PythonProject\SimpleAgent2_Cycle_VueWeb"
UPSTREAM_SUBDIRS = ("core", "tools", "storage", "web")
UPSTREAM_FILES = ("main.py",)
#: 绝不覆盖：这些是**前端那一侧**的文件，不属于上游
NEVER_COPY = ("web/decisions.py",)   # 上游也有同名文件，但内容可能被前端改过 → 需人工确认


def plan(src_root: str, dst_root: str) -> tuple[list[str], list[str]]:
    """返回 (要复制的相对路径, 目的地缺目录提示)。只比较 .py。"""
    todo: list[str] = []
    for sub in UPSTREAM_SUBDIRS:
        d = os.path.join(src_root, sub)
        if not os.path.isdir(d):
            continue
        for root, dirs, names in os.walk(d):
            dirs[:] = [x for x in dirs if x != "__pycache__"]
            for n in names:
                if not n.endswith(".py"):
                    continue
                rel = os.path.relpath(os.path.join(root, n), src_root).replace("\\", "/")
                if rel in NEVER_COPY:
                    continue
                todo.append(rel)
    for f in UPSTREAM_FILES:
        if os.path.isfile(os.path.join(src_root, f)):
            todo.append(f)
    return sorted(todo), []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frontend", default=DEFAULT_FRONTEND)
    ap.add_argument("--apply", action="store_true", help="真正复制（默认只预演）")
    args = ap.parse_args()

    dst = os.path.join(os.path.abspath(args.frontend), "backend")
    if not os.path.isdir(dst):
        print(f"目标不存在：{dst}")
        return 1

    todo, _ = plan(ROOT, dst)
    print("=" * 78)
    print(f"上游: {ROOT}")
    print(f"副本: {dst}")
    print("=" * 78)
    print(f"将复制 {len(todo)} 个 .py（{', '.join(UPSTREAM_SUBDIRS)} + {UPSTREAM_FILES[0]}）")
    for rel in todo[:10]:
        print(f"  {rel}")
    if len(todo) > 10:
        print(f"  …（共 {len(todo)} 个）")
    print(f"\n跳过（需人工确认，不覆盖）: {list(NEVER_COPY)}")

    if not args.apply:
        print("\n[预演] 未写入任何文件。加 --apply 才真正复制（会先备份）。")
        return 0

    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = os.path.join(dst, f"_backup_{stamp}")
    print(f"\n[1/3] 备份副本中将被覆盖的文件 → {backup}")
    copied = 0
    for rel in todo:
        src = os.path.join(ROOT, rel)
        tgt = os.path.join(dst, rel)
        if os.path.isfile(tgt):
            b = os.path.join(backup, rel)
            os.makedirs(os.path.dirname(b), exist_ok=True)
            shutil.copy2(tgt, b)
        print(f"[2/3] 复制 {rel}")
        os.makedirs(os.path.dirname(tgt), exist_ok=True)
        shutil.copy2(src, tgt)
        copied += 1

    print(f"\n[3/3] 完成：复制 {copied} 个文件，备份在 {backup}")
    print("请重启服务（或重新载入后端进程）后，再跑一次：")
    print("    python tests/diagnostics/backend_dir_check.py")
    print("结论应为「加载的这一份与本仓库一致」。")
    return 0


raise SystemExit(main())
