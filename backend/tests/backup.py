"""版本备份：验证 → 提交 → 记录 → 提交记录。

为什么要脚本化
--------------
手工 `git add/commit` 每轮都做、且容易漏步骤（忘了先跑测试、忘了写记录）。
本脚本把流程固定下来：

  1. **先验证**：跑全量单测 + 文档一致性 + 文档审查。任一项失败则**拒绝备份**
     （备份一个坏版本没有意义，反而把故障固化进历史）
  2. 提交到项目仓库（`workspace/` 已在 .gitignore，不会被嵌套仓库污染）
  3. 把本次备份写进 `docs/VERSIONS.md`（详细记录：改了什么、验证结果、回退点）
  4. **再把记录本身提交一次**，并把这次提交作为**备份点**

第 4 步是修出来的：早先记录写在提交**之后**，于是「v1.4 的记录」落在
**v1.5 的提交**里 —— 用打印出的 `git reset --hard <v1.4>` 回退，
恰好会把 v1.4 自己的记录丢掉。备份点必须**自包含**：回退到它，
就能看到它是怎么回事。

用法（在仓库根目录）：
    python tests/backup.py --tag v1.1 --note "多模态接口 + 上下文预算"
    python tests/backup.py --tag v1.2 --note "..." --skip-tests   # 仅紧急
"""

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VERSIONS = os.path.join(ROOT, "docs", "VERSIONS.md")

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)


def run(cmd: list[str], cwd: str = ROOT, check: bool = False) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = (p.stdout or "") + (p.stderr or "")
    if check and p.returncode != 0:
        print(out)
        raise SystemExit(f"命令失败: {' '.join(cmd)}")
    return p.returncode, out


def git(*args: str, cwd: str = ROOT) -> tuple[int, str]:
    from core.checkpoint import resolve_git

    exe = resolve_git()
    if not exe:
        print("找不到 git 可执行文件；无法备份。")
        raise SystemExit(1)
    # core.quotepath=false：让中文文件名按原样输出，而不是被转义成 \350\203...
    return run([exe, "-c", f"safe.directory={os.path.abspath(cwd)}",
                "-c", "core.quotepath=false", *args], cwd=cwd)


def verify() -> tuple[bool, list[str]]:
    """跑全量单测 + 文档一致性。返回 (是否全通过, 摘要行)。"""
    lines: list[str] = []
    ok = True

    py = sys.executable
    suites = [
        ("全量单测", [py, os.path.join(HERE, "run_unit.py")]),
        ("文档一致性", [py, os.path.join(HERE, "unit", "test_doc_consistency.py")]),
        ("文档审查", [py, os.path.join(HERE, "unit", "test_doc_review.py")]),
    ]
    for name, cmd in suites:
        rc, out = run(cmd)
        # 各脚本会把 "通过 N/M" 打到 stdout
        m = re.findall(r"通过\s*(\d+)/(\d+)", out)
        summary = f"{m[-1][0]}/{m[-1][1]}" if m else ("?" if rc else "-")
        passed = (rc == 0)
        ok = ok and passed
        flag = "PASS" if passed else "FAIL"
        lines.append(f"{name} {flag} ({summary})")
        print(f"  [{flag}] {name} {summary}")

    return ok, lines


def counts() -> dict:
    """收集一些可核对的数量，便于日后对比。"""
    sys.path.insert(0, ROOT)
    info: dict = {}
    try:
        from tools import TOOLS_MAP
        info["tools"] = len(TOOLS_MAP)
    except Exception:
        info["tools"] = -1
    try:
        import glob
        info["core_modules"] = len(glob.glob(os.path.join(ROOT, "core", "*.py")))
        info["test_files"] = len(glob.glob(os.path.join(HERE, "unit", "test_*.py")))
    except Exception:
        pass
    return info


def append_record(tag: str, note: str, verify_lines: list[str],
                  info: dict, files_changed: str) -> None:
    """把一条记录追加到 VERSIONS.md。

    **刻意不在记录里写自己的 hash**：记录是提交内容的一部分，
    写进去就会改变 hash，形成"改一次追一次"的无穷回归。
    取而代之：提交信息以 `{tag}:` 开头，于是

        git log --oneline --grep "^v1.5:"

    就能定位到本条目的提交 —— 稳定、不需要自引用。
    """
    exists = os.path.exists(VERSIONS)
    header = "" if exists else (
        "# 版本备份记录\n\n"
        "每个版本都在**验证通过后**提交。回退点 = 各条目对应的提交；\n"
        "回退命令：`git reset --hard <该提交>`（会丢弃其后所有改动）。\n\n"
        "> **本文件是提交内容的一部分** —— 所以每条记录都在它所描述的那个提交里，\n"
        "> 回退后能直接看到这个版本是怎么回事。\n"
        "> 查找某个版本：`git log --oneline --grep \"^v1.5:\"`\n"
        "> 本文件由 `tests/backup.py` 自动追加，不要手工重排条目。\n\n"
        "---\n"
    )
    entry = [
        "",
        f"## {tag} — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"**改动**：{note}",
        "",
        f"**备份点**：本条目所在的提交（提交信息以 `{tag}:` 开头）",
        "",
        f"**定位命令**：`git log --oneline --grep \"^{tag}:\"`",
        "",
        "**验证**：",
        *[f"- {ln}" for ln in verify_lines],
        "",
        "**规模**："
        f"工具 {info.get('tools', '?')} 个 · "
        f"core 模块 {info.get('core_modules', '?')} 个 · "
        f"测试文件 {info.get('test_files', '?')} 个",
        "",
    ]
    if files_changed:
        entry += ["**本次提交的文件**：", "```", files_changed.strip(), "```", ""]
    entry.append("---")

    with open(VERSIONS, "a", encoding="utf-8") as f:
        if header:
            f.write(header)
        f.write("\n".join(entry) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True, help="版本号，如 v1.1")
    ap.add_argument("--note", required=True, help="本次改了什么（写详细些）")
    ap.add_argument("--skip-tests", action="store_true",
                    help="跳过验证（仅紧急备份，不推荐）")
    args = ap.parse_args()

    print("=" * 70)
    print(f"版本备份 {args.tag}")
    print("=" * 70)

    # ---------- 1. 验证 ----------
    if args.skip_tests:
        print("  [警告] 跳过验证（--skip-tests）")
        verify_lines = ["（跳过验证）"]
    else:
        print("\n[1/5] 验证")
        ok, verify_lines = verify()
        if not ok:
            print("\n验证未通过 —— **拒绝备份**。")
            print("备份一个坏版本会把故障固化进历史，先修好再备份。")
            return 1

    # ---------- 2. 项目仓库就绪？ ----------
    print("\n[2/5] 检查仓库")
    rc, out = git("rev-parse", "--is-inside-work-tree")
    if rc != 0:
        print("  项目根还不是 git 仓库，初始化中…")
        git("init", "-b", "main")
        git("config", "user.name", "SimpleAgent2 Bot")
        git("config", "user.email", "agent@localhost")
        git("config", "core.autocrlf", "false")
    else:
        print("  已是 git 仓库")

    # ---------- 3. 提交代码 ----------
    print("\n[3/5] 提交代码")
    git("add", "-A")
    rc, status = git("status", "--porcelain")
    committed = False
    if not status.strip():
        print("  无改动可提交")
    else:
        rc, files = git("diff", "--cached", "--name-only")
        rc, _ = git("commit", "-m", f"{args.tag}: {args.note}")
        rc, head = git("rev-parse", "--short", "HEAD")
        committed = True
        print(f"  已提交 {head.strip()}")
        print(f"  文件 {len(files.strip().splitlines())} 个")

    # ---------- 4. 记录 ----------
    print("\n[4/5] 写记录")
    rc, files_changed = git("show", "--stat", "--oneline", "HEAD")
    info = counts()
    append_record(args.tag, args.note, verify_lines, info, files_changed)
    print(f"  已追加到 {os.path.relpath(VERSIONS, ROOT)}")

    # ---------- 5. 把记录折进同一个提交：备份点必须自包含 ----------
    # 早先记录写在提交**之后**，于是「v1.4 的记录」落进了 v1.5 的提交 ——
    # 用 `git reset --hard <v1.4>` 回退恰好会丢掉 v1.4 自己的记录。
    # 现在改为：记录写完后 amend 进同一个提交。
    print("\n[5/5] 折进同一个提交（备份点自包含）")
    git("add", "-A")
    rc, status = git("status", "--porcelain")
    if not status.strip():
        print("  无变化可提交")
        rc, ref = git("rev-parse", "--short", "HEAD")
        backup_ref = ref.strip()
    elif committed:
        # 第 3 步刚提交过代码 → 把记录 amend 进去，保持"一次备份 = 一次提交"
        rc, _ = git("commit", "--amend", "--no-edit")
        rc, ref = git("rev-parse", "--short", "HEAD")
        backup_ref = ref.strip()
        print(f"  已 amend 进同一提交 {backup_ref}")
    else:
        # 第 3 步没有代码改动（例如只更新了记录）→ 单独提交记录，不污染上一个备份点
        rc, _ = git("commit", "-m", f"{args.tag}: 备份记录（无代码改动）")
        rc, ref = git("rev-parse", "--short", "HEAD")
        backup_ref = ref.strip()
        print(f"  已单独提交记录 {backup_ref}")

    rc, grep = git("log", "--oneline", "--grep", f"^{args.tag}:")
    print("  定位核对：")
    for line in (grep.strip().splitlines()[:2] or ["(未找到)"]):
        print(f"    {line}")

    print(f"\n备份完成：{args.tag} @ {backup_ref}")
    print(f"回退命令：git reset --hard {backup_ref}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
