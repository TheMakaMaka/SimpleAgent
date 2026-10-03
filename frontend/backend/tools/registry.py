"""工具注册表：注册、schema 生成、**按 profile 过滤**。

为什么要有 profile 过滤
-----------------------
工具分两类，用途完全不同：

  编码工具      run_python / write_file / check_syntax / review_code …
                子循环干活的家伙，必须可见
  通用种子工具  get_weather / calculate / fetch_url / get_system_info …
                原初工具，代表未来**通用 agent** 的能力

后者**不该出现在编码 profile 里**——但也不该删除。它们是种子。
所以正确做法是：**保留全部工具 + 声明它属于哪个 profile + 按 profile 过滤**。

这也顺带解决 `tool_hint` 无强制力的问题：过滤后模型根本看不到不该用的工具，
不需要靠"提示"约束它。

（这是 `CYCLE.md` 插件化的最小版本；`risk` / `stage` 等声明留待后续。）
"""

import json
from typing import Awaitable, Callable, Iterable

TOOLS_MAP: dict[str, dict] = {}

# profile 名 → 该 profile 的默认工具集语义
PROFILE_CODING = "coding"     # 编码流程（当前唯一在跑的 profile）
PROFILE_GENERAL = "general"   # 通用 agent（未来）
PROFILE_ANY = "any"           # 两个 profile 都该有（如 read_file）


def register(
    name: str,
    description: str,
    parameters: dict,
    profiles: Iterable[str] = (PROFILE_ANY,),
):
    """注册一个工具。

    `profiles` 声明该工具属于哪些 profile：
      - `("any",)`            两个 profile 都暴露（默认，保持向后兼容）
      - `("coding",)`         只在编码流程暴露
      - `("general",)`        只在通用 agent 暴露（编码流程隐藏）
      - `("coding","general")` 都暴露
    """
    profile_set = tuple(profiles) or (PROFILE_ANY,)

    def deco(fn: Callable[..., Awaitable[str]]):
        TOOLS_MAP[name] = {
            "function": fn,
            "description": description,
            "parameters": parameters,
            "profiles": profile_set,
        }
        return fn
    return deco


def _belongs(info: dict, profile: str | None) -> bool:
    if not profile or profile == PROFILE_ANY:
        return True
    profiles = info.get("profiles") or (PROFILE_ANY,)
    return PROFILE_ANY in profiles or profile in profiles


def tool_schemas(profile: str | None = None) -> list[dict]:
    """生成给模型的工具 schema。

    `profile=None` 返回全部（诊断/兼容用）；传具体 profile 则过滤。
    """
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": info["description"],
                "parameters": info["parameters"],
            },
        }
        for name, info in TOOLS_MAP.items()
        if _belongs(info, profile)
    ]


def tool_names(profile: str | None = None) -> list[str]:
    return [n for n, i in TOOLS_MAP.items() if _belongs(i, profile)]


def hidden_names(profile: str) -> list[str]:
    """在当前 profile 下被隐藏的工具——用于诊断，让"隐藏了什么"可见。"""
    return [n for n, i in TOOLS_MAP.items() if not _belongs(i, profile)]


def describe_profiles() -> dict:
    """诊断用：每个工具属于哪些 profile。"""
    out: dict[str, list[str]] = {}
    for name, info in TOOLS_MAP.items():
        for p in info.get("profiles") or (PROFILE_ANY,):
            out.setdefault(p, []).append(name)
    return out


def err(msg: str) -> str:
    """旧格式错误（兼容用，新工具应返回结构化 JSON）。"""
    return f"Error: {msg}"


def truncate(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...（已截断，共 {len(text)} 字符）"


def is_error_result(result: str) -> bool:
    """
    统一判断工具结果是否失败。
    优先解析结构化 JSON（新协议），回退到字符串匹配（旧工具）。
    """
    try:
        data = json.loads(result)
        if isinstance(data, dict) and "ok" in data:
            return data["ok"] is False
    except (json.JSONDecodeError, TypeError):
        pass
    return result.startswith("Error:") or "错误：" in result
