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

#: 旧名保留（兼容外部引用）；**实际生效的根**由 `core.runtime.effective_root()` 决定 ——
#: ★ P15：设了任务级目标项目根后，验证必须在**那个根**里跑，
#: 否则「判词描述的是哪份产物」又断了（与 P6 同族）。
WORKSPACE_DIR = os.path.abspath("workspace")

TIMEOUT_SECONDS = 60
OUTPUT_LIMIT = 3000


def _tmp_dir() -> str:
    """临时脚本目录：始终放在**工作区根**下（不往目标项目里丢临时文件）。"""
    from core import runtime

    d = os.path.join(runtime.workspace_root(), "_tmp")
    os.makedirs(d, exist_ok=True)
    return d


def _clean_env() -> dict:
    from core import runtime

    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "PYTHONPATH": runtime.effective_root(),
        # ★ P6 要求 4：**不复用陈旧模块**。这个变量与命令行上的 `-B` 一起
        # 关掉字节码写入；配合 pipeline 在验证前清掉 `__pycache__`，
        # 就不会出现「`.pyc` 比源码新 → import 到上一版代码」这类
        # **判词不描述产物**（实测两个任务报 fail 而归档产物是对的）。
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    for k in ("SystemRoot", "TEMP", "TMP", "USERPROFILE", "COMSPEC"):
        if k in os.environ:
            env[k] = os.environ[k]
    return env


def _run_sync(code: str) -> tuple[str, str, int]:
    from core import runtime

    tmp_name = os.path.join(_tmp_dir(), f"{uuid.uuid4().hex}.py")
    with open(tmp_name, "w", encoding="utf-8") as f:
        f.write(code)
    try:
        proc = subprocess.run(
            ["python", "-B", tmp_name],
            capture_output=True, text=True,
            timeout=TIMEOUT_SECONDS,
            cwd=runtime.effective_root(),
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
            "code": {"type": "string", "description": "完整可执行的 Python 代码"},
            # `expect_exit` 一直是真实参数（验收"期望非零退出"的脚本），
            # 但此前**没写进模型可见 schema** —— 声明漏了实现（U- 类）。
            # P9 收紧形状时补上：否则它会被"未知键"判据拒掉，能力反而丢失。
            "expect_exit": {
                "type": "integer",
                "description": "期望的退出码（默认 0，即退出码 0 才算通过）",
                "default": 0,
            },
        },
        "required": ["code"],
        "additionalProperties": False,
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
