"""LLM 适配器层。

职责边界（重要）：
  - 本层负责「怎么跟某个模型说话」：请求构造、响应解包、JSON 容错、耦合补偿。
  - 工作流层（cycle / pipeline / orchestrator）只调用 `chat()` / `chat_json()`，
    不得包含任何模型特判。

换模型时只需替换 ModelProfile；本文件通常不需要改。
"""

import json
from typing import Any

from openai import AsyncOpenAI

from .model_profile import DEFAULT_COUPLING, ModelProfile


class ModelCapabilityError(RuntimeError):
    """模型不满足流程要求。宁可启动即报错，也不要静默劣化。"""


class LLMClient:
    """OpenAI 兼容协议的模型客户端，由 ModelProfile 驱动。"""

    def __init__(self, profile: ModelProfile | None = None):
        self.profile = profile or ModelProfile()
        self.config = self.profile          # 兼容旧调用方

        problems = self.profile.validate()
        if problems:
            raise ModelCapabilityError(
                "模型接入校验失败：\n  - " + "\n  - ".join(problems)
            )

        self._client = AsyncOpenAI(
            api_key=self.profile.api_key,
            base_url=self.profile.base_url,
            timeout=self.profile.request_timeout,
        )

    # ---------- 基础调用 ----------
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        force_json: bool = False,
    ) -> dict:
        p = self.profile
        kwargs: dict[str, Any] = {
            "model": p.model,
            "messages": messages,
            "temperature": p.limits.temperature,
            "max_tokens": p.limits.max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        # 只有模型声明支持时才发 response_format，否则靠 prompt 约束
        if force_json and p.capabilities.supports_json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        resp = await self._client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        return {
            "content": msg.content,
            "tool_calls": msg.tool_calls or [],
            "finish_reason": resp.choices[0].finish_reason,
        }

    # ---------- 结构化调用（工作流层的标准入口） ----------
    async def chat_json(self, messages: list[dict]) -> dict:
        """要求模型返回 JSON 对象，并按本档位的耦合策略解析。

        把「请求 + 解析 + 修复」封装在适配层，工作流层拿到的是 dict 或 {}。
        """
        reply = await self.chat(messages, force_json=True)
        text = reply.get("content") or ""
        data = extract_json(text, repair=self.profile.coupling.repair_json)
        if not data:
            return {"_parse_failed": True, "_raw": text}
        return data


# ============================================================
# JSON 提取与修复（通用文本处理，不属于任何特定模型）
# ============================================================
def extract_json(text: str, repair: bool = True) -> dict | None:
    """从模型输出里抽出第一个 JSON 对象。

    repair=True 时启用宽松修复：去 markdown 围栏、去尾逗号、去行注释。
    修复失败返回 None，由调用方决定降级策略（不在这里静默造数据）。
    """
    if not text:
        return None

    stripped = text.strip()

    # 去掉 ```json ... ``` 包裹
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 2:
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            stripped = "\n".join(lines)

    raw = _first_balanced_object(stripped)
    if raw is None:
        return None

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        if not repair:
            return None

    # ---- 宽松修复后重试 ----
    fixed = _repair_json_text(raw)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        return None


def _first_balanced_object(text: str) -> str | None:
    """括号匹配找第一个完整对象，正确处理字符串内的括号与转义。"""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _repair_json_text(raw: str) -> str:
    """修复常见的模型输出瑕疵：尾逗号、// 行注释、全角引号。"""
    import re

    text = raw
    # 全角引号 → 半角（仅在非字符串内部做会破坏内容，故只在整体替换明显异常时用）
    text = re.sub(r"//[^\n\"]*$", "", text, flags=re.MULTILINE)   # 行注释
    text = re.sub(r",(\s*[}\]])", r"\1", text)                    # 尾逗号
    return text
