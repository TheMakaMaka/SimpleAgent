import json
import os

from .registry import register, err, truncate

BASE_DIR = os.path.abspath("workspace")
os.makedirs(BASE_DIR, exist_ok=True)

_PROTECTED = {".env", "main.py", "agent.py", "pyproject.toml", "requirements.txt"}


#: 工具与 **verify 代码**的工作目录都是 workspace 根，所以路径**不该**带这个前缀。
#: 工具仍然容忍它（兼容既有习惯），但会**在返回值里明说被去掉了** ——
#: 实测事故（CHANGELOG §29）：提示词例子曾经 `path`/`description` 带前缀而
#: `verify` 不带，模型照抄前缀写 verify，于是 `open('workspace/x.txt')` 必然
#: FileNotFoundError，一轮 cycle 直接失败。
_WORKSPACE_PREFIX = "workspace/"


def _safe_path(filename: str) -> str:
    normalized = filename.replace("\\", "/").lstrip("/")
    if normalized.startswith(_WORKSPACE_PREFIX):
        normalized = normalized[len(_WORKSPACE_PREFIX):]
    target = os.path.abspath(os.path.join(BASE_DIR, normalized))
    if target != BASE_DIR and not target.startswith(BASE_DIR + os.sep):
        raise ValueError(f"非法路径: {filename}")
    return target


def had_workspace_prefix(filename: str) -> bool:
    """调用方是否写了 `workspace/` 前缀（用于回一句纠正提示）。"""
    return (filename or "").replace("\\", "/").lstrip("/").startswith(_WORKSPACE_PREFIX)


@register(
    name="read_file",
    description="读取 workspace 目录下的文件内容。大文件返回预览摘要。",
    parameters={
        "type": "object",
        "properties": {
            "filename": {"type": "string", "description": "相对 workspace 的文件路径"}
        },
        "required": ["filename"],
    },
    profiles=("coding",),
)
async def read_file(filename: str) -> str:
    try:
        path = _safe_path(filename)
    except ValueError as e:
        return err(str(e))

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
    description="把文本写入 workspace 目录下的文件（会覆盖同名文件）",
    parameters={
        "type": "object",
        "properties": {
            "filename": {"type": "string", "description": "相对 workspace 的文件路径"},
            "content": {"type": "string", "description": "要写入的完整内容"},
        },
        "required": ["filename", "content"],
    },
    profiles=("coding",),
)
async def write_file(filename: str, content: str) -> str:
    try:
        path = _safe_path(filename)
    except ValueError as e:
        return err(str(e))

    base = os.path.basename(path)
    if base in _PROTECTED:
        return err(f"禁止写入受保护文件: {base}")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        return err(f"写入失败: {e}")

    # 返回相对 BASE_DIR 的路径，干净、统一
    rel_path = os.path.relpath(path, BASE_DIR).replace("\\", "/")
    msg = f"OK:FILE|{rel_path}|{len(content)}|已写入 {rel_path}（{len(content)} 字符）"
    if had_workspace_prefix(filename):
        # 就地纠正：别让模型把 `workspace/` 带进 verify 代码
        msg += (f"\n注意：你写的是 `{filename}`，已按 workspace 根解析为 `{rel_path}`。"
                f"工具与 verify 代码的工作目录**就是 workspace 根**，"
                f"后续（尤其是 verify 里的 import / open）请直接用 `{rel_path}`，"
                f"不要带 `workspace/` 前缀。")
    return msg