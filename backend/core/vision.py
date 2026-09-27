"""视觉适配器：把图像变成模型可读的输入。

定位
----
与 `llm.py` 同级——**适配层**。工作流层不关心图像怎么编码、用哪个模型看，
只调用 `describe_image()`。

关键纪律（与全项目一致）
------------------------
**能力不满足时显式失败，不静默丢图。**
模型未声明 `supports_image_input` 时直接抛错，而不是把图丢掉、让模型
凭文本瞎猜——那会产出一个"看起来有依据"的幻觉答案。

只读
----
本地图片读取走**白名单目录**（与 `doc_access` 同一思路）：
只允许 `VISION_IMAGE_ROOTS` 指定的目录，默认 `assets` 与 `workspace`。
不接受绝对路径与 `..`，避免被诱导读系统文件。
"""

import base64
import os
from dataclasses import dataclass
from typing import Literal

from .llm import LLMClient, ModelCapabilityError

# 支持判定的图片类型（按扩展名）
_MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

DEFAULT_IMAGE_ROOTS = ("assets", "workspace")
MAX_IMAGE_BYTES = 8 * 1024 * 1024      # 单图上限
MAX_IMAGES = 8                          # 一次请求的图片数上限（还受 profile 约束）

Detail = Literal["auto", "low", "high"]


class VisionError(ModelCapabilityError):
    """视觉请求无法完成。**显式失败**——不静默降级。"""


@dataclass
class ImageInput:
    """一张待理解的图像。三种来源互斥。"""

    path: str = ""            # 本地路径（相对仓库根，走白名单）
    url: str = ""             # http(s) 直链
    data_uri: str = ""        # 已是 data:image/...;base64,...
    detail: Detail = "auto"
    label: str = ""           # 可选：告诉模型这是什么（如 "错误截图"）

    def kind(self) -> str:
        if self.path:
            return "path"
        if self.url:
            return "url"
        if self.data_uri:
            return "data_uri"
        return "empty"


def image_roots() -> tuple[str, ...]:
    """允许读取本地图片的目录。可用 VISION_IMAGE_ROOTS 覆盖（冒号/分号分隔）。"""
    raw = (os.getenv("VISION_IMAGE_ROOTS") or "").strip()
    if not raw:
        return DEFAULT_IMAGE_ROOTS
    sep = ";" if ";" in raw else ":"
    return tuple(p.strip() for p in raw.split(sep) if p.strip())


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resolve_local_image(rel_path: str) -> str:
    """把本地图片路径解析成绝对路径并做白名单校验。"""
    if not rel_path or not rel_path.strip():
        raise VisionError("图片路径为空")

    raw = rel_path.strip().replace("\\", "/")
    if os.path.isabs(raw) or (len(raw) > 1 and raw[1] == ":"):
        raise VisionError(f"只接受相对仓库根的图片路径: {rel_path}")

    parts = [p for p in raw.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise VisionError(f"禁止路径穿越: {rel_path}")

    root = _project_root()
    target = os.path.abspath(os.path.join(root, *parts))

    allowed = False
    for r in image_roots():
        base = os.path.abspath(os.path.join(root, r))
        if target == base or target.startswith(base + os.sep):
            allowed = True
            break
    if not allowed:
        raise VisionError(
            f"不在允许的图片目录内: {rel_path}（允许 {list(image_roots())}）"
        )
    if not os.path.isfile(target):
        raise VisionError(f"图片不存在: {rel_path}")

    size = os.path.getsize(target)
    if size > MAX_IMAGE_BYTES:
        raise VisionError(f"图片过大: {size} 字节 > {MAX_IMAGE_BYTES}")

    ext = os.path.splitext(target)[1].lower()
    if ext not in _MIME_BY_EXT:
        raise VisionError(
            f"不支持的图片类型 {ext or '(无扩展名)'}；"
            f"支持 {sorted(_MIME_BY_EXT)}"
        )
    return target


def _to_data_uri(image: ImageInput) -> str:
    """把 ImageInput 规范化成 data URI（OpenAI 兼容格式）。"""
    if image.data_uri:
        if not image.data_uri.startswith("data:image/"):
            raise VisionError("data_uri 必须以 data:image/ 开头")
        return image.data_uri

    if image.url:
        if not image.url.startswith(("http://", "https://")):
            raise VisionError(f"只接受 http(s) 图片直链: {image.url}")
        return image.url          # 直链直接交给服务端抓取

    if image.path:
        target = _resolve_local_image(image.path)
        ext = os.path.splitext(target)[1].lower()
        mime = _MIME_BY_EXT[ext]
        with open(target, "rb") as f:
            blob = f.read()
        return f"data:{mime};base64,{base64.b64encode(blob).decode('ascii')}"

    raise VisionError("ImageInput 三种来源（path/url/data_uri）必须给一个")


def build_vision_message(
    prompt: str,
    images: list[ImageInput],
    client: LLMClient | None = None,
) -> dict:
    """构造一条含图像的用户消息（OpenAI 兼容 content 数组）。

    纯函数，不做能力校验——校验在 `ensure_vision_capable()`。
    """
    if not images:
        raise VisionError("至少需要一张图像")
    if len(images) > MAX_IMAGES:
        raise VisionError(f"图像数量 {len(images)} 超过上限 {MAX_IMAGES}")

    content: list[dict] = []
    if prompt:
        content.append({"type": "text", "text": prompt})

    for i, img in enumerate(images, 1):
        uri = _to_data_uri(img)
        block: dict = {"type": "image_url", "image_url": {"url": uri}}
        # detail 是 OpenAI 的扩展字段，不是所有实现都接受。
        # **保守默认：只在模型显式声明支持时才下发**——
        # 未声明的实现收到它会直接报错，那属于"自己制造故障"。
        supports_detail = bool(
            client is not None
            and getattr(client.profile.capabilities, "supports_image_detail", False)
        )
        if supports_detail and img.detail and img.detail != "auto":
            block["image_url"]["detail"] = img.detail
        if img.label:
            content.append({"type": "text", "text": f"[图 {i}] {img.label}"})
        content.append(block)

    return {"role": "user", "content": content}


def ensure_vision_capable(client: LLMClient, images: list[ImageInput]) -> None:
    """在发请求前校验能力与数量。**显式失败，不静默丢图。**"""
    caps = client.profile.capabilities
    if not caps.supports_image_input:
        raise VisionError(
            f"模型 {client.profile.model} 未声明 supports_image_input。"
            f"设置 {client.profile.name.upper()}_VISION=true 或换用支持视觉的模型。"
            "（不静默丢图：那会让模型凭文本臆测，产出看似有据的幻觉）"
        )
    if len(images) > caps.max_images_per_request:
        raise VisionError(
            f"一次请求 {len(images)} 张图，超过模型声明上限 "
            f"{caps.max_images_per_request}（可用 MAX_IMAGES 调整声明）"
        )


async def describe_image(
    prompt: str,
    images: list[ImageInput],
    client: LLMClient | None = None,
    system: str = "",
) -> str:
    """用视觉模型理解图像，返回文本结果。

    `client` 省略时按 `vision` 角色解析档位（见 core/config.py 的 ROLES）。
    """
    if client is None:
        from .config import resolve_role

        client = LLMClient(resolve_role("vision"))

    ensure_vision_capable(client, images)

    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append(build_vision_message(prompt, images, client=client))

    reply = await client.chat(messages)
    return (reply.get("content") or "").strip()


def describe() -> dict:
    """诊断用：视觉角色是否启用、允许的目录、上限。"""
    from .config import ROLES, role_available

    spec = ROLES.get("vision")
    return {
        "role_configured": role_available("vision") if spec else False,
        "env_prefix": spec.key if spec else None,
        "image_roots": list(image_roots()),
        "max_image_bytes": MAX_IMAGE_BYTES,
        "max_images": MAX_IMAGES,
        "supported_types": sorted(_MIME_BY_EXT),
        "note": "未配置 VISION_* 时该角色为「未启用」，调用会显式失败。",
    }
