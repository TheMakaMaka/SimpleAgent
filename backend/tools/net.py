import ipaddress
from urllib.parse import urlparse

import httpx

from .registry import register, err, truncate


def _check_url(url: str) -> None:
    """拒绝指向本地/内网的非 http(s) 与 IP 字面量地址。

    ⚠️ 已知残余风险（未修）：域名在当前时刻解析为公网 IP、但请求时被重新解析到
    内网（DNS rebinding / TOCTOU），本函数拦不住。要彻底防住需在传输层做
    peer-IP 校验（自定义 httpx transport）。当前定位是本地自用工具，
    暴露到公网前必须补上。
    """
    u = urlparse(url)
    if u.scheme not in ("http", "https"):
        raise ValueError("仅支持 http/https")

    host = (u.hostname or "").strip().rstrip(".").lower()
    if not host:
        raise ValueError("URL 缺少主机名")

    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise ValueError("禁止访问本地/内网地址")

    # 关键：ipaddress 对「域名」抛 ValueError，这属于正常情况；
    # 但「私有 IP」也要抛 ValueError——若把两者放在同一个 except 里，
    # 安全判断会被自己的异常处理吞掉（此前正是如此，导致内网地址全部放行）。
    # 因此这里只捕获「不是 IP 字面量」这一种情况。
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return  # 域名，交由后续解析；DNS 层面的风险见上方说明

    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        raise ValueError(f"禁止访问内网/保留地址: {host}")


@register(
    name="fetch_url",
    description="获取指定 URL 的网页文本内容（前 3000 字符）",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "完整的 http/https 网址"}
        },
        "required": ["url"],
        "additionalProperties": False,
    },
    profiles=("general",),
)
async def fetch_url(url: str) -> str:
    try:
        _check_url(url)
    except ValueError as e:
        return err(str(e))

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return truncate(resp.text, 3000)
    except Exception as e:
        return err(f"请求失败: {e}")