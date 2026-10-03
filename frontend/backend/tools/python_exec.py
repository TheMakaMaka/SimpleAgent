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
os.makedirs(WORKSPACE_DIR, exist_ok=True)

TIMEOUT_SECONDS = 60
OUTPUT_LIMIT = 4000


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
    name="run_python",
    description=(
        "执行一段完整 Python 代码，返回结构化 JSON："
        "{ok: true, output} 或 {ok: false, exit_code, error: {type, category, frames}, raw_output}。"
        "代码必须自包含（含 import 与 print），超时 60 秒。"
        "需要运行代码、验证算法时使用。"
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
async def run_python(code: str) -> str:
    if not code or not code.strip():
        return json.dumps({
            "ok": False,
            "error": {"type": "ValueError", "message": "代码为空"},
        })

    try:
        stdout, stderr, rc = await asyncio.to_thread(_run_sync, code)
    except subprocess.TimeoutExpired:
        return json.dumps({
            "ok": False,
            "error": {
                "type": "TimeoutError",
                "message": f"执行超时（>{TIMEOUT_SECONDS} 秒）",
                "category": {"kind": "timeout"},
            },
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "ok": False,
            "error": {"type": type(e).__name__, "message": str(e)},
        }, ensure_ascii=False)

    if rc != 0:
        parsed = parse_traceback_text(stderr or stdout)
        if parsed.get("error_type") is None and stderr.strip():
            parsed["message"] = stderr.strip()[:500]
        return json.dumps({
            "ok": False,
            "exit_code": rc,
            "error": parsed,
            "raw_output": truncate((stdout + stderr).strip(), 500),
        }, ensure_ascii=False)

    body = stdout.strip()
    if stderr.strip():
        body += "\n[stderr]\n" + stderr.strip()
    if not body:
        body = "（无输出）"

    return json.dumps({
        "ok": True,
        "output": truncate(body, OUTPUT_LIMIT),
    }, ensure_ascii=False)