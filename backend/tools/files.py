import json
import os

from core import runtime

from .registry import register, err, truncate

BASE_DIR = os.path.abspath("workspace")
os.makedirs(BASE_DIR, exist_ok=True)

_PROTECTED = {".env", "main.py", "agent.py", "pyproject.toml", "requirements.txt"}


#: 工具与 **verify 代码**的工作目录都是 workspace 根，所以路径**不该**带这个前缀。
#: 工具仍然容忍它（兼容既有习惯），但会**在返回值里明说被去掉了** ——
#: 实测事故（CHANGELOG §29）：提示词例子曾经 `path`/`description` 带前缀而
#: `verify` 不带，模型照抄前缀写 verify，于是 `open('workspace/x.txt')` 必然
#: FileNotFoundError，一轮 cycle 直接失败。
#:
#: ★ P14（2026-10-03）：`workspace/` 的约定**对外显式化**，不再只活在
#: 这一行常量上 —— `/profile.runtime` 会连同三个绝对根一起说明它。
_WORKSPACE_PREFIX = "workspace/"


def had_workspace_prefix(filename: str) -> bool:
    """调用方是否写了 `workspace/` 前缀（用于回一句纠正提示）。"""
    return (filename or "").replace("\\", "/").lstrip("/").startswith(_WORKSPACE_PREFIX)


def _report_label(path: str) -> str:
    """给报告/归档用的相对标签。

    输出根下的产物统一带 `outputs/` 前缀，这样 `runtime.resolve_write()`
    能把同一个标签解析回同一个文件（写与查同源，不会各算一套）。
    """
    out = runtime.output_root()
    eff = runtime.effective_root()
    if runtime.is_within(path, out) and not runtime.is_within(path, eff):
        rel = os.path.relpath(path, out).replace("\\", "/")
        return "outputs" if rel == "." else f"outputs/{rel}"
    return runtime.relative_label(path)


def _root_hint() -> str:
    return (
        f"目标根: {runtime.effective_root()}"
        f"（来源 {runtime.effective_root_source()}）；"
        f"输出根: {runtime.output_root()}（交付物写这里，用 `outputs/` 前缀）"
    )


@register(
    name="read_file",
    description=(
        "读取文件内容（大文件返回预览摘要）。路径相对**目标项目根**"
        "（设了任务级 project_root 就是它，否则是 workspace）；"
        "`outputs/` 前缀指向输出根。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "filename": {"type": "string", "description": "相对目标根的路径（或 outputs/ 前缀）"}
        },
        "required": ["filename"],
        "additionalProperties": False,
    },
    profiles=("coding",),
)
async def read_file(filename: str) -> str:
    try:
        path = runtime.resolve_read(filename)
    except runtime.ScopeError as e:
        # ★ 结构化拒绝（P15）：越界**不静默失败**，给出可机判字段
        return runtime.scope_error_result("read_file", e)

    if not os.path.exists(path):
        return err(f"文件不存在: {filename}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return err(f"读取失败: {e}")

    if len(content) > 2000:
        preview = content[:1500]
        info = f"文件 {filename} 共 {len(content)} 字符，以下是前 1500 字符：\n{preview}..."
        # JSON 时给一点结构提示
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                info = (
                    f"文件 {filename} 是 JSON，顶层字段: {', '.join(data.keys())}\n"
                    f"总字符数 {len(content)}。"
                )
        except Exception:
            pass
        return info

    return f"文件 {filename} 内容：\n{content}"


@register(
    name="write_file",
    description=(
        "把文本写入文件（会覆盖同名文件）。相对路径以**目标项目根**为根"
        "（设了任务级 project_root 就是它，否则是 workspace）；"
        "交付物请用 `outputs/` 前缀写到**输出根**。"
        "超出目标根/输出根的路径会被**结构化拒绝**（不会静默写到别处）。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "filename": {"type": "string", "description": "相对目标根的路径（或 outputs/ 前缀）"},
            "content": {"type": "string", "description": "要写入的完整内容"},
        },
        "required": ["filename", "content"],
        "additionalProperties": False,
    },
    profiles=("coding",),
)
async def write_file(filename: str, content: str) -> str:
    try:
        path = runtime.resolve_write(filename)
    except runtime.ScopeError as e:
        # ★ P15 要求 5：越界写 ⇒ 结构化拒绝（可机判字段 + 不允许静默失败）
        return runtime.scope_error_result("write_file", e)

    base = os.path.basename(path)
    if base in _PROTECTED:
        return err(f"禁止写入受保护文件: {base}")

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        return err(f"写入失败: {e}")

    # 返回相对根的路径，干净、统一
    rel_path = _report_label(path)
    msg = f"OK:FILE|{rel_path}|{len(content)}|已写入 {rel_path}（{len(content)} 字符）"
    if had_workspace_prefix(filename):
        # 就地纠正：别让模型把 `workspace/` 带进 verify 代码
        msg += (f"\n注意：你写的是 `{filename}`，已按目标根解析为 `{rel_path}`。"
                f"后续（尤其是 verify 里的 import / open）请直接用 `{rel_path}`。")
    if rel_path.startswith("outputs/"):
        msg += f"\n（这是**交付物**，落在输出根 {runtime.output_root()}）"
    return msg
