"""版本记录：给每次备份追加一条「改了什么 / 验证结果 / 怎么退」。

为什么要有它
------------
本项目的"版本"本来只有一个**目录名**（`20260926-093147_v10-warnings-consumer`）。
目录名记不下三件最要紧的事：

    改了什么？   验证过了吗？   怎么退回去？

上游仓库有 `docs/VERSIONS.md` 且纪律是"验证不过拒绝备份"。两侧可追溯性
不对称 —— 这个模块补上本仓库那一侧。

为什么逻辑在这个 Python 模块里、而不是直接写在 `backup.ps1` 里
------------------------------------------------------------
**为了能被测试。** PowerShell 里的字符串拼接没法离线单测，而这个文件的
纪律恰恰是"只增不改"——一条会**静默改写历史**的 bug 必须被钉住。
`backup.ps1` 只负责算出数据、调这里的 CLI。

「只增不改」怎么保证
--------------------
新条目插在**头部之后**（最新在上），旧条目的文本**原样保留**：
实现上就是把文件切成"头部"与"条目"两段，只在中间插入新的一段，
两段都按原字节写回。`tests/unit/test_versions.py` 会拿旧条目逐字比对。

用法
----
    python scripts/versions.py append --label v11 --snapshot 2026... --note "..." \\
        --verify "单测 29/29" --diff "14 改动 / 3 新增 / 2 删除"
    python scripts/versions.py list            # 看已有条目
"""

import argparse
import io
import os
import re
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

#: 默认路径（可在调用里覆盖，便于测试用临时文件）
DEFAULT_PATH = os.path.join(ROOT, "docs", "VERSIONS.md")

#: 头部：第一次创建时写入。之后**永不改动**。
HEADER = """# 版本记录

> **本文件由 `scripts/backup.ps1` 在每次成功备份后自动追加一条，请勿手改。**
>
> 纪律与上游 `docs/VERSIONS.md` 一致：**只增不改**。
> 每条记录四样东西 —— 标签与时间、**改了什么**（机械核对）、**验证结果**、**还原命令**。
>
> 「改了什么」不是人写的总结，而是 `backup.ps1 -Verify -From <上一版>` 的
> **机械 diff**（本机没有 git，这是 `git diff --stat` 的等价物）。
> 所以本文件里的改动清单**不会漏**——手写的一定会漏，这一点已被实测抓到过两次。
>
> 起点说明：本文件自 **v10** 起建立。`v1`…`v9` 只在 `_backups/` 留有目录名，
> 没有机械记录（当时还没做出等价 diff 的手段）。**不追溯补写**——
> 凭记忆补出来的记录不是记录。

---

"""

#: 条目标题的固定形状，用来数条目、也用来防止误伤正文里的 `## `
_ENTRY_RE = re.compile(r"^## `(?P<label>[^`]+)` · (?P<when>.+)$", re.MULTILINE)


def read_text(path: str) -> str:
    if not os.path.isfile(path):
        return ""
    return io.open(path, encoding="utf-8").read()


def split_header(text: str) -> tuple[str, str]:
    """把文件切成（头部, 条目区）。头部 = 第一个条目标题之前的全部内容。

    没有条目时整份都算头部。这样"只增不改"就退化成"在中间插一段"。
    """
    m = _ENTRY_RE.search(text)
    if not m:
        return text, ""
    return text[: m.start()], text[m.start():]


def entries(path: str = DEFAULT_PATH) -> list[tuple[str, str]]:
    """返回 [(label, 该条目的完整文本)]，**按文件顺序**（最新在前）。"""
    _, body = split_header(read_text(path))
    if not body:
        return []
    out: list[tuple[str, str]] = []
    matches = list(_ENTRY_RE.finditer(body))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        out.append((m.group("label"), body[m.start():end]))
    return out


def render_entry(*, label: str, snapshot: str, note: str = "",
                 verify: str = "", diff: str = "", baseline: str = "",
                 changed_files: list[str] | None = None,
                 created_at: str | None = None) -> str:
    """造一条记录。字段缺失时**如实写"未记录"**，不编。"""
    when = created_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    files = changed_files or []
    # 条目正文里的代码块围栏不能和 f-string 冲突，所以用列表拼
    lines = [
        f"## `{label}` · {when}",
        "",
        "| 项 | 值 |",
        "|---|---|",
        f"| 还原点 | `{snapshot}` |",
        f"| 验证结果 | {verify or '—（未记录）'} |",
        f"| 改了什么 | {diff or '—（未记录）'} |",
    ]
    if baseline:
        lines.append(f"| 对比基准 | `{baseline}` |")
    lines += [
        "",
        "**这一版做到了什么**",
        "",
        (note.strip() or "—（本次未填 `-Note`；下次记得填，它比时间戳有用）"),
        "",
    ]
    if files:
        lines += ["**改动清单**（机械核对，取自 `backup.ps1 -Verify`）", "", "```"]
        lines += [f"  {f}" for f in files]
        lines += ["```", ""]
    lines += [
        "**还原**",
        "",
        "```powershell",
        f".\\scripts\\backup.ps1 -Verify  -From {snapshot}",
        f".\\scripts\\backup.ps1 -Restore -From {snapshot}",
        "```",
        "",
        "---",
        "",
    ]
    return "\n".join(lines)


def append_entry(path: str = DEFAULT_PATH, **kw) -> str:
    """追加一条记录（最新在上），**不动任何已有条目**。返回写进去的文本。"""
    text = read_text(path)
    if not text:
        text = HEADER
    header, body = split_header(text)
    if not header.endswith("\n"):
        header += "\n"
    entry = render_entry(**kw)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    io.open(path, "w", encoding="utf-8", newline="").write(header + entry + body)
    return entry


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="版本记录（只增不改）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("append", help="追加一条记录")
    a.add_argument("--path", default=DEFAULT_PATH)
    a.add_argument("--label", required=True)
    a.add_argument("--snapshot", required=True)
    a.add_argument("--note", default="")
    a.add_argument("--verify", default="")
    a.add_argument("--diff", default="")
    a.add_argument("--baseline", default="")
    a.add_argument("--created-at", default=None)
    a.add_argument("--files", default="",
                   help="改动清单，一行一个（换行分隔；用 | 也行）")

    lp = sub.add_parser("list", help="列出已有条目")
    lp.add_argument("--path", default=DEFAULT_PATH)

    args = ap.parse_args(argv)

    if args.cmd == "append":
        raw = args.files.replace("|", "\n")
        files = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        append_entry(
            args.path,
            label=args.label,
            snapshot=args.snapshot,
            note=args.note,
            verify=args.verify,
            diff=args.diff,
            baseline=args.baseline,
            changed_files=files,
            created_at=args.created_at,
        )
        n = len(entries(args.path))
        print(f"[versions] 已追加 `{args.label}`（共 {n} 条）→ "
              f"{os.path.relpath(args.path, ROOT)}")
        return 0

    if args.cmd == "list":
        got = entries(args.path)
        print(f"共 {len(got)} 条（新 → 旧）：")
        for label, txt in got:
            m = _ENTRY_RE.search(txt)
            print(f"  {label}   {m.group('when') if m else '?'}")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
