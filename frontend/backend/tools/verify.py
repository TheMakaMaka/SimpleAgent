"""复合工具：把「检查」和「验证」合并成一次原子调用。

背景：7B 模型自己编排「先 check_syntax 再 run_python」这种多步流程时失误率高，
所以把静态检查和实际执行合成一个工具，降低编排负担。
"""

import asyncio
import json
import os
import subprocess
import uuid

from .parse import parse_traceback_text
from .registry import register, truncate

WORKSPACE_DIR = os.path.abspath("workspace")
TMP_DIR = os.path.abspath(os.path.join(WORKSPACE_DIR, "_tmp"))
os.makedirs(TMP_DIR, exist_ok=True)

TIMEOUT_SECONDS = 60
OUTPUT_LIMIT = 3000


def _clean_env() -> dict:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "PYTHONPATH": WORKSPACE_DIR,
    }
    for k in ("SystemRoot", "TEMP", "TMP", "USERPROFILE", "COMSPEC"):
        if k in os.environ:
            env[k] = os.environ[k]
    return env


def _run_sync(code: str) -> tuple[str, str, int]:
    tmp_name = os.path.join(TMP_DIR, f"{uuid.uuid4().hex}.py")
    with open(tmp_name, "w", encoding="utf-8") as f:
        f.write(code)
    try:
        proc = subprocess.run(
            ["python", tmp_name],
            capture_output=True, text=True,
            timeout=TIMEOUT_SECONDS,
            cwd=WORKSPACE_DIR,
            env=_clean_env(),
            encoding="utf-8", errors="replace",
        )
        return proc.stdout or "", proc.stderr or "", proc.returncode
    finally:
        try:
            os.remove(tmp_name)
        except OSError:
            pass


@register(
    name="check_and_run",
    description=(
        "先做语法检查，再执行代码，返回结构化结果 "
        "{ok, syntax_passed, run_ok, output, parsed_error}。"
        "parsed_error 已含 error_type/message/category/frames，无需再解析 traceback。"
        "需要「验证代码能否跑通」时优先用这个工具，不要自己分两步调用。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "完整可执行的 Python 代码"}
        },
        "required": ["code"],
    },
    profiles=("coding",),
)
async def check_and_run(code: str, expect_exit: int = 0) -> str:
    """先静态检查再执行。

    expect_exit 用于「期望非零退出」的验收（例如断言脚本故意失败）。
    默认 0，即退出码为 0 才算通过。
    """
    if not code or not code.strip():
        return json.dumps(
            {"ok": False, "syntax_passed": False, "message": "代码为空"},
            ensure_ascii=False,
        )

    # 第一步：静态语法检查，不通过就不必执行
    try:
        compile(code, "<submitted>", "exec")
    except SyntaxError as e:
        return json.dumps(
            {
                "ok": False,
                "syntax_passed": False,
                "run_ok": False,
                "parsed_error": {
                    "error_type": "SyntaxError",
                    "message": e.msg,
                    "category": {"kind": "syntax_error"},
                    "frames": [
                        {
                            "file": "<submitted>",
                            "line": e.lineno,
                            "function": "<module>",
                            "code": (e.text or "").rstrip(),
                        }
                    ],
                },
                "hint": "语法错误，请先修正语法再执行。",
            },
            ensure_ascii=False,
        )

    # 第二步：真正执行
    try:
        stdout, stderr, rc = await asyncio.to_thread(_run_sync, code)
    except subprocess.TimeoutExpired:
        return json.dumps(
            {
                "ok": False,
                "syntax_passed": True,
                "run_ok": False,
                "parsed_error": {
                    "error_type": "TimeoutError",
                    "message": f"执行超时（>{TIMEOUT_SECONDS} 秒）",
                    "category": {"kind": "timeout"},
                    "frames": [],
                },
            },
            ensure_ascii=False,
        )
    except Exception as e:
        return json.dumps(
            {
                "ok": False,
                "syntax_passed": True,
                "run_ok": False,
                "parsed_error": {
                    "error_type": type(e).__name__,
                    "message": str(e),
                    "category": {"kind": "unknown"},
                    "frames": [],
                },
            },
            ensure_ascii=False,
        )

    if rc != expect_exit:
        parsed = parse_traceback_text(stderr or stdout)
        if parsed.get("error_type") is None and stderr.strip():
            parsed["message"] = stderr.strip()[:500]
        return json.dumps(
            {
                "ok": False,
                "syntax_passed": True,
                "run_ok": False,
                "exit_code": rc,
                "expected_exit": expect_exit,
                "parsed_error": parsed,
                "raw_output": truncate((stdout + stderr).strip(), 500),
            },
            ensure_ascii=False,
        )

    body = stdout.strip()
    if stderr.strip():
        body += "\n[stderr]\n" + stderr.strip()
    if not body:
        body = "（无输出）"

    return json.dumps(
        {
            "ok": True,
            "syntax_passed": True,
            "run_ok": True,
            "exit_code": rc,
            "expected_exit": expect_exit,
            "output": truncate(body, OUTPUT_LIMIT),
        },
        ensure_ascii=False,
    )
