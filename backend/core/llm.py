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

from .model_profile import (
    DEFAULT_COUPLING,
    REASONING_REPLAY_ENV,
    REASONING_REPLAY_MODES,
    ModelProfile,
    env_reasoning_replay,
)

# ============================================================
# P19 · 推理模型的 `reasoning_content` 协议兼容
# ============================================================
#: 推理模型（如 `deepseek-flash` 思考模式）在**带 `tools` 的请求**里，要求把上几轮
#: 返回的 `reasoning_content` **原样回灌**；不回灌会直接 400。
#: 本仓库旧代码把它丢掉了 —— 实测错误原文（统筹方 B1-A 批次）正是：
#:
#:     BadRequestError 400: The `reasoning_content` in the thinking mode
#:     must be passed back to the API.
#:
#: ⚠️ 注意方向：**这是"必须回灌"，不是"禁止回灌"**。工单 P19 表 1 写的是"剥掉"，
#: 与错误原文相反；正确做法见 `docs/EVALUATION-REASONING-PROTOCOL.md` §2（带机械证据）。
#: 因此本模块的规定是：
#:   - **带 `tools`**：回灌（否则 400，任何推理模型都撞）；
#:   - **不带 `tools`**：按官方文档无需回灌（传了也会被忽略）⇒ 剥掉，保持请求干净。
#:
#: `AGENT_REASONING_REPLAY` 可取 `auto`（默认，按上面规则）/ `never`（一律剥掉，
#: 供统筹方反向验证工单假设）/ `always`（一律保留），便于灰度与排障。
#:
#: ★ `P22-A`：策略的**默认来源从环境变量改为档位声明**（`ModelProfile.reasoning`）——
#: 加一个推理模型 = 加一份档位，`AGENT_REASONING_REPLAY` 退化为**进程级显式覆盖**
#: （A/B 与排障用）。判定点仍在 `request_messages()`，一处也没有多。
REASONING_CONTENT = "reasoning_content"
REASONING_REPLAY_ENV = REASONING_REPLAY_ENV        # 与 model_profile 同源
REASONING_REPLAY_MODES = REASONING_REPLAY_MODES    # 与 model_profile 同源


def reasoning_replay_mode() -> str:
    """**进程级**回灌策略（只看 `AGENT_REASONING_REPLAY`）。

    保留它是为了向后兼容与进程级排障；带档位的判定请用
    `effective_replay_policy(profile)`。非法值不算数 ⇒ 回落 `auto`
    （**不是**静默变成某一种极端）。
    """
    return env_reasoning_replay() or "auto"


def effective_replay_policy(profile: ModelProfile | None = None) -> str:
    """实际生效的回灌策略（`P22-A`：模型差异收进档位）。

    解析顺序（每一步都可见）：
      ① 进程级 `AGENT_REASONING_REPLAY`（显式覆盖 / 一键关；非法值不算数）；
      ② 档位声明 `profile.reasoning.replay`；
      ③ `auto` —— 中间值，**不是** `never` / `always` 任一极端。
    """
    if profile is None:
        return reasoning_replay_mode()
    return profile.effective_reasoning_replay()


def strip_reasoning_content(messages: list[dict]) -> list[dict]:
    """剥掉消息里的 `reasoning_content`（返回副本，不改调用方的列表）。"""
    out: list[dict] = []
    for m in messages or []:
        if isinstance(m, dict):
            out.append({k: v for k, v in m.items() if k != REASONING_CONTENT})
        else:
            out.append(m)
    return out


def _copy_messages(messages: list[dict]) -> list[dict]:
    return [dict(m) if isinstance(m, dict) else m for m in messages or []]


def _clip_reasoning(messages: list[dict], max_chars: int) -> list[dict]:
    """思考长度上限（档位字段 `max_thinking_chars`）。

    **默认关闭**：`max_chars <= 0` 时**逐字节不动**（返回原列表，连副本都不多造）。
    """
    if max_chars <= 0:
        return messages
    out: list[dict] = []
    for m in messages:
        if (isinstance(m, dict) and isinstance(m.get(REASONING_CONTENT), str)
                and len(m[REASONING_CONTENT]) > max_chars):
            m = {**m, REASONING_CONTENT: m[REASONING_CONTENT][:max_chars]}
        out.append(m)
    return out


def _apply_replay_policy(
    messages: list[dict],
    tools: list[dict] | None,
    mode: str,
    max_thinking_chars: int = 0,
) -> list[dict]:
    """回灌/剥掉的**唯一实现**（`request_messages` 只是它的取参外壳）。"""
    if mode == "never":
        return strip_reasoning_content(messages)
    if mode == "always":
        return _clip_reasoning(_copy_messages(messages), max_thinking_chars)
    # auto：带 tools ⇒ 回灌（DeepSeek 协议要求）；不带 tools ⇒ 剥掉
    kept = _copy_messages(messages) if tools else strip_reasoning_content(messages)
    return _clip_reasoning(kept, max_thinking_chars)


def request_messages(
    messages: list[dict],
    tools: list[dict] | None = None,
    profile: ModelProfile | None = None,
) -> list[dict]:
    """组装**真正发给 API** 的消息 —— `reasoning_content` 回灌/剥掉的**唯一判定点**。

    为什么收成一个函数：回灌与否是"跟模型怎么说话"，属于适配层职责；
    散在 worker / orchestrator 各写一遍，迟早漏一处，而漏掉的那处会 400
    （这正是 P19 的成因：旧代码在适配层把字段丢了，调用点无从补）。

    `P22-A`：`profile` 省略时与旧行为**逐字节一致**（`AGENT_REASONING_REPLAY` 或
    `auto`）；给了档位则以**档位声明**为准（进程级变量仍可显式覆盖）。
    """
    if profile is None:
        return _apply_replay_policy(messages, tools, reasoning_replay_mode())
    return _apply_replay_policy(
        messages,
        tools,
        profile.effective_reasoning_replay(),
        profile.reasoning.max_thinking_chars,
    )


def replay_contract_problems(profile: ModelProfile | None = None) -> list[str]:
    """★ `P22-A` 的**声明 vs 实现**判据（**会红**）。

    把样本消息喂进**真实**的 `request_messages`，检查它是否按档位声明处理
    `reasoning_content`；不一致即返回非空列表。

    为什么需要它：档位是"声明"，`request_messages` 是"实现"。本项目反复栽在
    「声明了但没接上」——所以声明必须由机械判据与实现对照，而不是靠人看。
    """
    if profile is None:
        return []
    problems = list(profile.reasoning.problems())
    declared = profile.effective_reasoning_replay()
    sample = [{
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": "c0", "type": "function",
            "function": {"name": "noop", "arguments": "{}"},
        }],
        REASONING_CONTENT: "样本思考",
    }]
    kept_tools = REASONING_CONTENT in request_messages(
        sample, tools=[{"type": "function"}], profile=profile)[0]
    kept_none = REASONING_CONTENT in request_messages(
        sample, tools=None, profile=profile)[0]
    # 三种声明各自的期望行为（与 P19 协议同一张表）
    want_tools = declared in ("auto", "always")
    want_none = declared == "always"
    if profile.reasoning.is_reasoning_model and not kept_tools:
        problems.append(
            f"档位声明是推理模型（replay={declared!r}），但带 tools 的请求没有回灌 "
            f"{REASONING_CONTENT} ⇒ 实测会 400（P19）"
        )
    if kept_tools != want_tools:
        problems.append(
            f"声明 replay={declared!r} 时带 tools 应 kept={want_tools}，实现 kept={kept_tools}"
        )
    if kept_none != want_none:
        problems.append(
            f"声明 replay={declared!r} 时不带 tools 应 kept={want_none}，实现 kept={kept_none}"
        )
    return problems


def _int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def response_usage(resp: Any) -> dict:
    """从响应里抽出用量，**含 `reasoning_tokens`**（它先吃掉 `max_tokens` 预算）。

    推理模型的 `reasoning_tokens` 可能挂在 `usage.completion_tokens_details`
    （OpenAI 兼容面）或 `usage.reasoning_tokens`（部分网关）—— 两处都取，
    取不到就是 0，**不假装**。
    """
    usage = getattr(resp, "usage", None)
    details = getattr(usage, "completion_tokens_details", None)
    reasoning = getattr(details, "reasoning_tokens", None)
    if reasoning is None:
        reasoning = getattr(usage, "reasoning_tokens", None)
    return {
        "prompt_tokens": _int_or_zero(getattr(usage, "prompt_tokens", 0)),
        "completion_tokens": _int_or_zero(getattr(usage, "completion_tokens", 0)),
        "reasoning_tokens": _int_or_zero(reasoning),
    }


def aggregate_usage(named_clients: list[tuple[str, Any]],
                    profile: ModelProfile | None = None) -> dict:
    """把若干 `LLMClient.usage` 汇总进报告（同一个 client 只算一次，不重复计数）。

    报告要能回答"**这次的 `max_tokens` 有多少被思考吃掉**"——没有它，
    换推理模型时读数会被误读成"模型答得短/不行"。

    `P22-A`：可传档位，把**生效的回灌策略**与**预算语义声明**一并写进读数 ——
    否则"换了档位之后读数变了"会被误读成"模型变强/变弱"。
    """
    per_role: dict[str, dict] = {}
    seen: set[int] = set()
    total = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0}
    for role, client in named_clients:
        if client is None or id(client) in seen:
            continue
        seen.add(id(client))
        u = getattr(client, "usage", None)
        if not isinstance(u, dict):
            continue
        row = {k: _int_or_zero(u.get(k)) for k in total}
        per_role[role] = row
        for k in total:
            total[k] += row[k]
    total["reasoning_share"] = (
        round(total["reasoning_tokens"] / total["completion_tokens"], 4)
        if total["completion_tokens"] else 0.0
    )
    return {
        "policy": effective_replay_policy(profile),
        "policy_declared": profile.reasoning.replay if profile is not None else None,
        "model": profile.model if profile is not None else None,
        "thinking_counts_in_max_tokens": (
            profile.reasoning.counts_in_max_tokens if profile is not None else None),
        "total": total,
        "by_role": per_role,
        "note": "`reasoning_tokens` 先吃掉 `max_tokens` 预算（推理档位声明 "
                "`counts_in_max_tokens`）；它为空只说明响应里没给，不冒充 0 用量",
    }


class ModelCapabilityError(RuntimeError):
    """模型不满足流程要求。宁可启动即报错，也不要静默劣化。"""


class LLMClient:
    """OpenAI 兼容协议的模型客户端，由 ModelProfile 驱动。"""

    def __init__(self, profile: ModelProfile | None = None):
        self.profile = profile or ModelProfile()
        self.config = self.profile          # 兼容旧调用方

        #: ★ P19：本次进程内累计用量（含 `reasoning_tokens`）。
        #: 由 `aggregate_usage()` 汇总进 `CycleReport.model_usage`。
        self.usage: dict[str, int] = {
            "calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
            "reasoning_tokens": 0,
        }

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
            # ★ P19：只在这一层决定 `reasoning_content` 回不回灌（带 tools 必须回灌）。
            # ★ P22-A：策略来自**档位**（`profile.reasoning`），进程级变量可显式覆盖。
            "messages": request_messages(messages, tools, profile=p),
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
        usage = response_usage(resp)
        self.usage["calls"] += 1
        for _k in ("prompt_tokens", "completion_tokens", "reasoning_tokens"):
            self.usage[_k] += usage[_k]
        return {
            "content": msg.content,
            "tool_calls": msg.tool_calls or [],
            "finish_reason": resp.choices[0].finish_reason,
            # ★ P19：把思考过程作为**事实**带回来（供诊断/报告），
            # 但它是否回灌由 `request_messages` 统一裁决，调用方不必也不该自己判断。
            "reasoning_content": getattr(msg, "reasoning_content", None),
            "usage": usage,
            "reasoning_tokens": usage["reasoning_tokens"],
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
