import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile

from .registry import register

#: `list_workspace` 最多列多少个文件。超出时**明确标 truncated**，
#: 而不是静默截断 —— 静默截断会让模型以为"目录里就这么多"。
MAX_LISTED_FILES = 200


def resolve_ruff() -> str | None:
    """定位 ruff 可执行文件；找不到返回 None。

    不能只用 shutil.which("ruff")：ruff 常被装在**当前解释器所属的 venv** 里，
    而调用本工具的进程 PATH 未必包含该 venv 的 Scripts 目录
    （服务/IDE/CI 进程都可能如此）。这会表现为「明明装了却永远 skipped」，
    和 git 的 PATH 问题同源。

    顺序：当前解释器同目录 → PATH → 常见位置。
    """
    exe_name = "ruff.exe" if os.name == "nt" else "ruff"

    # 1) 与当前解释器同目录（venv/Scripts 或 venv/bin）
    beside = os.path.join(os.path.dirname(sys.executable), exe_name)
    if os.path.isfile(beside):
        return beside

    # 2) PATH
    found = shutil.which("ruff")
    if found:
        return found

    # 3) 常见用户级安装位置
    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\ruff\ruff.exe"),
        os.path.expanduser("~/.local/bin/ruff"),
        "/usr/local/bin/ruff",
        "/opt/homebrew/bin/ruff",
    ]
    for cand in candidates:
        if os.path.isfile(cand):
            return cand
    return None


def _run_cmd(cmd: list[str], timeout: int = 10) -> tuple[int, str, str]:
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace",
        )
        return p.returncode, p.stdout or "", p.stderr or ""
    except FileNotFoundError:
        return -1, "", "command not found"
    except subprocess.TimeoutExpired:
        return -2, "", "timeout"


@register(
    name="check_syntax",
    description=(
        "检查 Python 代码语法是否正确。"
        "返回 {ok: true} 或 {ok: false, error: {type, message, line, text}}。"
        "纯静态检查，不执行代码。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "要检查的 Python 代码"}
        },
        "required": ["code"],
    },
    profiles=("coding",),
)
async def check_syntax(code: str) -> str:
    try:
        ast.parse(code)
        return json.dumps({"ok": True})
    except SyntaxError as e:
        return json.dumps({
            "ok": False,
            "error": {
                "type": "SyntaxError",
                "message": e.msg,
                "line": e.lineno,
                "offset": e.offset,
                "text": (e.text or "").rstrip(),
            },
        }, ensure_ascii=False)


@register(
    name="run_lint",
    description=(
        "对 Python 代码跑 lint 检查（优先 ruff，未安装则返回 skipped）。"
        "返回结构化 issue 列表，issues[].code 是 ruff 规则编号。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "要检查的 Python 代码"}
        },
        "required": ["code"],
    },
    profiles=("coding",),
)
async def run_lint(code: str) -> str:
    ruff = resolve_ruff()
    if not ruff:
        # ok=None 表示「没检查」，不是「检查通过」。
        # 之前返回 ok=True 会让模型误判为 lint 干净（假阴性）。
        return json.dumps(
            {
                "ok": None,
                "issues": [],
                "skipped": "ruff not installed",
                "note": (
                    "lint 未执行，不代表代码已通过检查。"
                    "安装方式: pip install ruff"
                ),
            },
            ensure_ascii=False,
        )

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py",
                                     delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = f.name
    try:
        rc, out, err = _run_cmd([ruff, "check", "--output-format=json", tmp])
        try:
            data = json.loads(out) if out.strip() else []
        except json.JSONDecodeError:
            data = []
        issues = [
            {
                "line": item.get("location", {}).get("row"),
                "col": item.get("location", {}).get("column"),
                "code": item.get("code"),
                "message": item.get("message"),
            }
            for item in data
        ]
        return json.dumps(
            {"ok": len(issues) == 0, "issues": issues},
            ensure_ascii=False,
        )
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


@register(
    name="list_workspace",
    description=(
        "列出 workspace 目录下的所有文件，含相对路径、大小、扩展名。"
        "不确定有哪些文件时先调用此工具。"
    ),
    parameters={"type": "object", "properties": {}, "required": []},
    profiles=("coding",),
)
async def list_workspace() -> str:
    """列出 workspace 里的文件（供模型了解当前目录）。

    ⚠️ 跳过策略与 `core/symbol_index.build_index` **共用同一份常量** ——
    实测事故（CHANGELOG §29）：本函数原来只过滤 `_` 开头的目录，
    于是把 `.git/` 里的 **249 个文件**全倒给了模型。
    后果不只是费 token：模型照单全收，把 `.git/COMMIT_EDITMSG` 之类
    写进了本该只含业务文件的交付物里。

    `os.path.abspath("workspace")` 依赖进程 CWD（既有约束，见 README 已知限制）。
    """
    from core.symbol_index import _SKIP_DIRS

    base = os.path.abspath("workspace")
    files = []
    total = 0
    for root, dirs, names in os.walk(base):
        dirs[:] = [d for d in dirs
                   if d not in _SKIP_DIRS and not d.startswith(".")]
        for name in names:
            if name.startswith("."):
                continue
            total += 1
            if len(files) >= MAX_LISTED_FILES:
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, base).replace("\\", "/")
            try:
                size = os.path.getsize(full)
            except OSError:
                size = 0
            files.append({
                "path": rel,
                "size": size,
                "ext": os.path.splitext(name)[1],
            })
    return json.dumps(
        {
            "ok": True,
            "workspace": base,
            # 被跳过的目录名（让模型知道"看不见"不等于"不存在"）
            "skipped_dir_names": sorted(_SKIP_DIRS),
            "total": total,
            "listed": len(files),
            "truncated": total > len(files),
            "files": files,
        },
        ensure_ascii=False,
    )