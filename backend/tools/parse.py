import json
import re
from typing import Any

from .registry import register


def _split_error_line(line: str) -> tuple[str, str]:
    if ":" in line:
        t, m = line.split(":", 1)
        return t.strip(), m.strip()
    return line.strip(), ""


def _classify(error_type: str, message: str) -> dict:
    if error_type == "ModuleNotFoundError":
        sym = (re.search(r"No module named '([^']+)'", message) or [None, None])[1]
        return {"kind": "missing_module", "symbol": sym}
    if error_type == "ImportError":
        sym = (re.search(r"cannot import name '([^']+)'", message) or [None, None])[1]
        return {"kind": "import_error", "symbol": sym}
    if error_type == "NameError":
        sym = (re.search(r"name '([^']+)' is not defined", message) or [None, None])[1]
        return {"kind": "undefined_name", "symbol": sym}
    if error_type == "AttributeError":
        mm = re.search(r"'([^']+)' object has no attribute '([^']+)'", message)
        return {
            "kind": "attribute_error",
            "object": mm.group(1) if mm else None,
            "attribute": mm.group(2) if mm else None,
        }
    if error_type == "TypeError":
        return {"kind": "type_error"}
    if error_type == "ValueError":
        return {"kind": "value_error"}
    if error_type == "KeyError":
        return {"kind": "key_error"}
    if error_type == "IndexError":
        return {"kind": "index_error"}
    if error_type == "ZeroDivisionError":
        return {"kind": "zero_division"}
    if error_type == "FileNotFoundError":
        return {"kind": "file_not_found"}
    if error_type == "PermissionError":
        return {"kind": "permission_error"}
    if error_type == "SyntaxError":
        return {"kind": "syntax_error"}
    if error_type == "IndentationError":
        return {"kind": "indentation_error"}
    if error_type in ("AssertionError",):
        return {"kind": "assertion_error"}
    if error_type in ("TimeoutError", "subprocess.TimeoutExpired"):
        return {"kind": "timeout"}
    return {"kind": "unknown"}


def parse_traceback_text(raw: str) -> dict[str, Any]:
    """核心：原始 traceback 字符串 → 结构化 dict。"""
    if not raw or not raw.strip():
        return {"error_type": None, "message": "", "category": {"kind": "empty"}, "frames": []}

    lines = [l for l in raw.splitlines() if l.strip()]

    error_line = lines[-1]
    for line in reversed(lines):
        if line.startswith(("During handling", "The above exception")):
            continue
        error_line = line
        break

    error_type, error_message = _split_error_line(error_line)

    frames = []
    for i, line in enumerate(lines):
        m = re.match(r'\s*File "(.+)", line (\d+), in (.+)', line)
        if m:
            code = lines[i + 1].strip() if i + 1 < len(lines) else ""
            frames.append({
                "file": m.group(1),
                "line": int(m.group(2)),
                "function": m.group(3),
                "code": code,
            })

    return {
        "error_type": error_type,
        "message": error_message,
        "category": _classify(error_type, error_message),
        "frames": frames[-3:],
    }


@register(
    name="parse_python_error",
    description=(
        "把原始 Python traceback 字符串解析成结构化 JSON，"
        "包含 error_type、message、category、frames。"
        "看到原始 traceback 时优先调用此工具，不要自己逐行阅读。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "raw": {"type": "string", "description": "原始 traceback 文本"}
        },
        "required": ["raw"],
        "additionalProperties": False,
    },
    profiles=("coding",),
)
async def parse_python_error(raw: str) -> str:
    result = parse_traceback_text(raw)
    return json.dumps(result, ensure_ascii=False)