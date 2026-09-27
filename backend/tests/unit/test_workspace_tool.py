"""`list_workspace` 工具的回归测试。

实测事故（见 `docs/CHANGELOG.md` §29）
-------------------------------------
它原来只过滤 `_` 开头的目录，于是把 `.git/` 里的 **249 个文件**全倒给了模型。
后果不只是费 token：模型照单全收，把 `.git/COMMIT_EDITMSG` 之类
写进了本该只含业务文件的交付物里。

判据：与 `core/symbol_index` 的扫描**共用同一份跳过策略**
（`_SKIP_DIRS` + 点号开头的目录/文件），并且截断要**明说**而不是静默。
"""

import asyncio
import json
import os
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401

from tools.code_checks import MAX_LISTED_FILES, list_workspace  # noqa: E402

checks: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    checks.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="ws_tool_")
    ws = os.path.join(tmp, "workspace")
    os.makedirs(ws)
    # 应当被看到的
    for rel in ("a.py", "notes.txt", "sub/b.md"):
        p = os.path.join(ws, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write("x")
    # 应当被跳过的
    for rel in (".git/COMMIT_EDITMSG", ".git/objects/ab/cdef",
                "_tmp/scratch.py", "_debug/log.txt", ".venv/lib/x.py",
                "node_modules/pkg/index.js", ".hidden"):
        p = os.path.join(ws, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write("y")

    old = os.getcwd()
    try:
        os.chdir(tmp)                     # 工具用 os.path.abspath("workspace")
        data = json.loads(asyncio.run(list_workspace()))
    finally:
        os.chdir(old)

    paths = {f["path"] for f in data["files"]}
    print(f"  workspace : {data['workspace']}")
    print(f"  列出      : {sorted(paths)}")
    print(f"  total={data['total']} listed={data['listed']} "
          f"truncated={data['truncated']}")
    print(f"  跳过的目录名: {data['skipped_dir_names']}")

    check("普通文件被列出", {"a.py", "notes.txt", "sub/b.md"} <= paths)
    check("`.git/` 内部文件不外泄（原来是 249 个）",
          not any(p.startswith(".git/") for p in paths))
    check("`_tmp/` 不外泄", not any(p.startswith("_tmp/") for p in paths))
    check("`_debug/` 不外泄", not any(p.startswith("_debug/") for p in paths))
    check("`.venv/` 不外泄", not any(p.startswith(".venv/") for p in paths))
    check("`node_modules/` 不外泄",
          not any(p.startswith("node_modules/") for p in paths))
    check("隐藏文件不外泄", ".hidden" not in paths)
    check("只列出 3 个文件（与目录里该看到的完全一致）", len(paths) == 3)
    check("total 与 listed 都是 3（没有静默截断）",
          data["total"] == 3 and data["listed"] == 3 and data["truncated"] is False)
    check("如实告知跳过了哪些目录名（看不见 ≠ 不存在）",
          ".git" in data["skipped_dir_names"] and "_tmp" in data["skipped_dir_names"])
    check("截断阈值是个明确常量", isinstance(MAX_LISTED_FILES, int)
          and MAX_LISTED_FILES > 0)

    shutil.rmtree(tmp, ignore_errors=True)
    failed = [n for n, ok in checks if not ok]
    print(f"\n通过 {len(checks) - len(failed)}/{len(checks)}")
    return 1 if failed else 0


raise SystemExit(main())
