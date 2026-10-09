"""`P22-A`：**模型档位 + 可启用模式（类插件结构）** —— 只做 A（解耦）。

### 工单原文（`DISPATCH.md` ⓪ / `WORK-ORDER.md`【P22】A）

> **只做 A（解耦）**：把模型差异收进档位 —— 是否推理模型 · 回灌策略 ·
> **思考 token 的预算语义** · 思考长度上限 · 是否支持图像 · 上限默认值。
> **验收**：**加一个推理模型 = 加一份档位、代码零改动**；档位缺失时回落到默认
> （**不得静默变成某个极端**）；每个开关都能关，关掉后与基线一致。
> 4. 新增一份**会红**的测试：档位声明的"必回灌"与实现不符 ⇒ 红。

### 本测试怎么把每一条变成机械判据

| 验收 | 判据 |
|---|---|
| 加推理模型 = 加档位、代码零改动 | `register_profile()` 注册一个新档位（**不改任何代码**）⇒ 用假 DeepSeek 端点（缺 `reasoning_content` 就抛官方 400）跑通一道题；并机械证明 `_guess_profile_name` 里没有任何模型名 |
| 档位缺失回落到默认、不是极端 | 未知档位 ⇒ `default` + `fallback=True` + 生效策略 == `auto`（既不是 `never` 也不是 `always`） |
| 每个开关都能关、关掉与基线一致 | 请求体 `sha256`：全关 == 基线；逐个打开 ⇒ 哈希改变（开关不是死的）；再关 ⇒ **回到同一个哈希** |
| 声明 vs 实现不符 ⇒ 红 | `replay_contract_problems()`：真实实现 ⇒ 空；把实现换成"一律剥掉" ⇒ **立刻非空**；恢复 ⇒ 空 |
"""

import asyncio
import hashlib
import inspect
import json
import os
import sys
from types import SimpleNamespace as NS

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import Checker  # noqa: E402

import core.llm as llm_module  # noqa: E402
from core.llm import (  # noqa: E402
    REASONING_CONTENT,
    REASONING_REPLAY_ENV,
    LLMClient,
    effective_replay_policy,
    replay_contract_problems,
    request_messages,
)
from core.model_profile import (  # noqa: E402
    _BUILTIN_PROFILES,
    _guess_profile_name,
    ModelCapabilities,
    ModelLimits,
    ModelProfile,
    ModelReasoning,
    register_profile,
)
from core.task import Task  # noqa: E402
from core.worker import Worker  # noqa: E402

OK = Checker()

#: DeepSeek 官方原文（逐字）—— 拿它当"端点判据"。
DEEPSEEK_400 = ("BadRequestError: Error code: 400 - The `reasoning_content` "
                "in the thinking mode must be passed back to the API.")

NEW_TIER = "acme-reasoner"
NEW_MATCH = ("acme-r1", "acme-think")
NEW_MODEL = "acme-r1"

ENV_KEYS = (
    "ACME_MODEL", "ACME_BASE_URL", "ACME_API_KEY", "ACME_PROFILE",
    "ACME_REASONING", "ACME_REASONING_REPLAY", "ACME_THINKING_MAX_CHARS",
    "ACME_THINKING_IN_MAX_TOKENS", "ACME_CONTEXT_WINDOW",
    REASONING_REPLAY_ENV,
)


def _tc(call_id: str, name: str, arguments: str):
    return NS(id=call_id, function=NS(name=name, arguments=arguments))


class FakeCompletions:
    """假端点。`enforce=True` 时按 DeepSeek 规则验收请求（缺回灌 ⇒ 官方 400）。"""

    def __init__(self, script: list[dict], enforce: bool = True):
        self.script = script
        self.enforce = enforce
        self.requests: list[dict] = []
        self.i = 0

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        if self.enforce and kwargs.get("tools"):
            for m in kwargs.get("messages") or []:
                if (isinstance(m, dict) and m.get("tool_calls")
                        and not m.get(REASONING_CONTENT)):
                    raise RuntimeError(DEEPSEEK_400)
        spec = self.script[min(self.i, len(self.script) - 1)]
        self.i += 1
        msg = NS(content=spec.get("content"),
                 tool_calls=spec.get("tool_calls") or [],
                 reasoning_content=spec.get("reasoning_content"))
        usage = NS(prompt_tokens=10, completion_tokens=20,
                   completion_tokens_details=NS(reasoning_tokens=spec.get("reasoning_tokens", 7)))
        return NS(choices=[NS(message=msg, finish_reason="stop")], usage=usage)


class FakeClient:
    def __init__(self, script: list[dict], enforce: bool = True):
        self.completions = FakeCompletions(script, enforce=enforce)
        self.chat = NS(completions=self.completions)


def _install_fake(script: list[dict], enforce: bool = True) -> FakeClient:
    fake = FakeClient(script, enforce=enforce)
    llm_module.AsyncOpenAI = lambda **_kw: fake  # type: ignore[assignment]
    return fake


def _worker_script() -> list[dict]:
    """第 1 轮：带 reasoning + 一个工具调用；第 2 轮：带 reasoning + 纯文本收尾。"""
    return [
        {"reasoning_content": "先看看系统信息", "content": None,
         "tool_calls": [_tc("c1", "get_system_info", "{}")]},
        {"reasoning_content": "看完了，给结论", "content": "完成", "tool_calls": []},
    ]


def _hash_requests(reqs: list[dict]) -> str:
    """请求体的**逐字节**指纹（消息顺序、键、值全在内）。"""
    return hashlib.sha256(
        json.dumps(reqs, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]


TOOLS = [{"type": "function", "function": {"name": "noop", "parameters": {}}}]
MSGS = [
    {"role": "system", "content": "s"},
    {"role": "user", "content": "u"},
    {"role": "assistant", "content": None,
     "tool_calls": [{"id": "c0", "type": "function",
                     "function": {"name": "noop", "arguments": "{}"}}],
     REASONING_CONTENT: "思考片段"},
]


def _one_request(profile: ModelProfile | None, messages=MSGS, tools=TOOLS) -> dict:
    """发**一次**请求并返回它（`enforce=False`，只取报文，不判协议）。"""
    fake = _install_fake([{"content": "ok", "reasoning_content": "思考"}], enforce=False)
    client = LLMClient(profile if profile is not None else ModelProfile())
    asyncio.run(client.chat(list(messages), tools=tools))
    return fake.completions.requests[-1]


def _msg_body(profile: ModelProfile | None, messages=MSGS, tools=TOOLS) -> list[dict]:
    return _one_request(profile, messages, tools)["messages"]


def _reasoning_profile(**kw) -> ModelProfile:
    """固定模型/预算，**只**变推理档位 —— 这样"报文变了"只可能来自档位。"""
    return ModelProfile(
        name="reasoner-test",
        model="tier-test-model",
        capabilities=ModelCapabilities(context_window=65536),
        limits=ModelLimits(max_tokens=8192),
        reasoning=ModelReasoning(**kw),
    )


async def _run_worker(profile: ModelProfile):
    return await Worker(LLMClient(profile)).run(
        Task(id="t1", description="查看系统信息", expected_output="一句话结论"),
        context="")


def main() -> int:
    saved = {k: os.environ.get(k) for k in ENV_KEYS}
    for k in ENV_KEYS:
        os.environ.pop(k, None)
    try:
        # ================= [1] 档位字段齐全（P22-A 的六个字段都可机读） =========
        print("=" * 74)
        print("[1] 档位面：P22-A 点名的字段都在 `tier()` 里（可机读）")
        print("=" * 74)
        p = ModelProfile()
        tier = p.tier()
        required = {
            "is_reasoning_model", "reasoning_replay", "thinking_counts_in_max_tokens",
            "max_thinking_chars", "supports_image_input", "context_window",
            "limits", "modes", "fallback",
        }
        missing = sorted(required - set(tier))
        print(f"  tier keys = {sorted(tier)}")
        OK.check(f"★ 档位字段齐全（缺 {missing or '无'}）", not missing)
        OK.check("默认档位不是推理模型、策略为 auto",
                 tier["is_reasoning_model"] is False and tier["reasoning_replay"] == "auto")
        OK.check("★ 默认状态下 P22-A 新增的两个开关都关着"
                 "（推理模式 / 思考上限）；回灌策略是中性的 auto",
                 tier["modes"]["reasoning_model"] is False
                 and tier["modes"]["thinking_cap"] is False
                 and tier["reasoning_replay"] == "auto"
                 and set(tier["modes"]) == {"reasoning_model", "reasoning_replay",
                                            "thinking_cap"})
        builtin_tier = _BUILTIN_PROFILES["reasoner"].tier()
        OK.check("内置 reasoner 档位声明为推理模型（数据，不是代码）",
                 builtin_tier["is_reasoning_model"] is True)
        OK.check("内置 reasoner 档位的上限默认值生效（max_tokens=8192，"
                 "不是通用推导的 4096）",
                 builtin_tier["limits"]["max_tokens"] == 8192
                 and builtin_tier["context_window"] == 65536)

        # ================= [2] 加推理模型 = 加档位、代码零改动 =================
        print("\n" + "=" * 74)
        print("[2] ★ 加一个推理模型：**只注册一份档位**（不改代码）⇒ 跑通一道题")
        print("=" * 74)
        register_profile(ModelProfile(
            name=NEW_TIER,
            model=NEW_MODEL,
            capabilities=ModelCapabilities(context_window=65536),
            limits=ModelLimits(max_tokens=4096),
            reasoning=ModelReasoning(is_reasoning_model=True, replay="auto"),
            match=NEW_MATCH,
        ))
        OK.check("★ 新档位只靠 `match` 就被选中（`_guess_profile_name` 零改动）",
                 _guess_profile_name(NEW_MODEL) == NEW_TIER
                 and _guess_profile_name(NEW_MATCH[1]) == NEW_TIER)
        src = inspect.getsource(_guess_profile_name)
        OK.check("★ `_guess_profile_name` 里没有任何具体模型名（数据驱动）",
                 "qwen" not in src and "deepseek" not in src and "acme" not in src)

        os.environ.update({"ACME_MODEL": NEW_MODEL, "ACME_API_KEY": "fake-key"})
        prof = ModelProfile.from_env("ACME")
        print(f"  from_env('ACME') -> profile={prof.name} model={prof.model} "
              f"tier={json.dumps(prof.tier()['modes'], ensure_ascii=False)}")
        OK.check("★ 新模型名自动落到新档位（没有 ORCH_PROFILE 也不需要改代码）",
                 prof.name == NEW_TIER and prof.fallback is False)
        OK.check("新档位被识别为推理模型且策略来自档位",
                 prof.reasoning.is_reasoning_model
                 and effective_replay_policy(prof) == "auto")

        fake = _install_fake(_worker_script())
        res = asyncio.run(_run_worker(prof))
        reqs = fake.completions.requests
        asst = [m for m in reqs[1]["messages"]
                if isinstance(m, dict) and m.get("tool_calls")]
        print(f"  worker: ok={res.ok} steps={res.steps_used} requests={len(reqs)}")
        print(f"  第 2 次请求回灌字段 = {asst[0].get(REASONING_CONTENT)!r}")
        OK.check("★ 用新档位真的跑通一道题（不再是 400）", res.ok is True and len(reqs) >= 2)
        OK.check("★ 新档位下带 tools 的后续请求回灌了 reasoning_content",
                 bool(asst) and asst[0].get(REASONING_CONTENT) == "先看看系统信息")

        # ================= [3] 档位缺失 ⇒ 回落默认，且不是任何极端 =============
        print("\n" + "=" * 74)
        print("[3] 档位缺失：回落 `default` + `fallback=True`，策略是 auto（不是极端）")
        print("=" * 74)
        os.environ["ACME_PROFILE"] = "no-such-tier"
        fallback = ModelProfile.from_env("ACME")
        ft = fallback.tier()
        print(f"  fallback={ft['fallback']} profile={ft['profile']} "
              f"replay={ft['reasoning_replay']} (declared={ft['reasoning_replay_declared']})")
        OK.check("★ 未登记档位 ⇒ fallback=True 且写明回落到谁（回落**可见**）",
                 ft["fallback"] is True and ft["fallback_to"] == "default")
        OK.check("★ 回落策略 == auto（既不是 never 也不是 always）",
                 ft["reasoning_replay"] == "auto")
        ok_unknown = ModelProfile.from_env("ACME").tier()["reasoning_replay"] == "auto"
        os.environ.pop("ACME_PROFILE", None)
        os.environ["ACME_MODEL"] = "totally-unknown-model"
        unknown = ModelProfile.from_env("ACME")
        print(f"  未知模型名 -> profile={unknown.name} replay={unknown.tier()['reasoning_replay']}")
        OK.check("★ 未知模型名也回落 default/auto（不静默变成极端）",
                 ok_unknown and unknown.name == "default"
                 and unknown.tier()["reasoning_replay"] == "auto")
        os.environ["ACME_MODEL"] = NEW_MODEL

        # ================= [4] 每个开关都能关，关掉后与基线**逐字节**一致 =========
        print("\n" + "=" * 74)
        print("[4] 开关双向：关 == 基线（同一 sha256）；打开 ⇒ 哈希必须变")
        print("=" * 74)
        # 所有对比档位共用同一模型名/预算，**只**变推理档位 ——
        # 这样"哈希变了"只可能来自档位，不会与"换了模型名"混在一起。
        baseline_profile = _reasoning_profile()          # 全部开关关闭（auto / 无上限）
        base_hash = _hash_requests([_one_request(baseline_profile)])
        base_expected = [dict(m) for m in MSGS]          # 基线 = 原样（带 tools 回灌）
        OK.check("★ 基线请求体 == 手写期望（没有多/少任何键）",
                 _msg_body(baseline_profile) == base_expected)
        print(f"  基线 sha256 = {base_hash}")

        reasoner_auto = _reasoning_profile(is_reasoning_model=True, replay="auto")
        h_auto = _hash_requests([_one_request(reasoner_auto)])
        OK.check("推理档位 + auto：报文与基线**逐字节相同**（协议路径本就一致）",
                 h_auto == base_hash)

        off_again = _reasoning_profile(is_reasoning_model=False)
        OK.check("★ 关掉「推理模式」⇒ 回到同一个基线哈希",
                 _hash_requests([_one_request(off_again)]) == base_hash)

        # `replay=never`：非推理档位下"关掉回灌"是合法的开关
        # （推理档位 + never 是自相矛盾的声明，由 [5] 的 validate 判据拦下）
        never_on = _reasoning_profile(replay="never")
        h_never = _hash_requests([_one_request(never_on)])
        OK.check("★ 覆盖值 `replay=never` 有效：报文变了（reasoning_content 被剥掉）",
                 h_never != base_hash
                 and REASONING_CONTENT not in _msg_body(never_on)[-1])
        OK.check("★ 取消覆盖（auto）⇒ 回到**同一个**基线哈希",
                 _hash_requests([_one_request(_reasoning_profile(replay="auto"))]) == base_hash)

        cap_on = _reasoning_profile(is_reasoning_model=True, max_thinking_chars=2)
        kept = _msg_body(cap_on)[-1].get(REASONING_CONTENT)
        h_cap = _hash_requests([_one_request(cap_on)])
        OK.check("★ 开关 `thinking_cap` 有效：截断到上限（2 字符）",
                 kept == "思考" and h_cap != base_hash)
        OK.check("★ 关回去（cap=0）⇒ 回到同一个基线哈希",
                 _hash_requests([_one_request(_reasoning_profile(max_thinking_chars=0))])
                 == base_hash)

        # `always` 与 `auto` 只在**不带 tools** 时不同 ⇒ 用不带 tools 的请求证明它有效
        no_tools_base = _hash_requests([_one_request(baseline_profile, tools=None)])
        always_on = _reasoning_profile(is_reasoning_model=True, replay="always")
        no_tools_always = _hash_requests([_one_request(always_on, tools=None)])
        OK.check("★ 覆盖值 `replay=always` 有效：不带 tools 时也保留（与 auto 不同）",
                 no_tools_always != no_tools_base
                 and REASONING_CONTENT in _msg_body(always_on, tools=None)[-1])

        # 进程级一键关（AGENT_REASONING_REPLAY）：必须压过档位声明，且**可见**
        os.environ[REASONING_REPLAY_ENV] = "never"
        env_tier = reasoner_auto.tier()
        h_env = _hash_requests([_one_request(reasoner_auto)])
        OK.check("★ 进程级一键关压过档位声明，且 tier 里如实标注",
                 env_tier["reasoning_replay"] == "never"
                 and env_tier["reasoning_replay_declared"] == "auto"
                 and env_tier["reasoning_replay_env"] == "never")
        OK.check("★ 一键关后报文 == never 的报文（可复现，不是新状态）",
                 h_env == h_never)
        os.environ.pop(REASONING_REPLAY_ENV, None)
        OK.check("★ 取消一键关 ⇒ 又回到基线哈希",
                 _hash_requests([_one_request(reasoner_auto)]) == base_hash)

        # 逐 role 的环境开关（{prefix}_REASONING=0）：把推理模式关掉
        os.environ["ACME_REASONING"] = "0"
        off = ModelProfile.from_env("ACME")
        OK.check("★ `{prefix}_REASONING=0` 能关掉推理模式（档位可被环境覆盖）",
                 off.reasoning.is_reasoning_model is False
                 and off.tier()["modes"]["reasoning_model"] is False)
        os.environ.pop("ACME_REASONING", None)
        os.environ["ACME_THINKING_MAX_CHARS"] = "3"
        OK.check("★ `{prefix}_THINKING_MAX_CHARS` 能开/关思考上限",
                 ModelProfile.from_env("ACME").tier()["max_thinking_chars"] == 3)
        os.environ.pop("ACME_THINKING_MAX_CHARS", None)

        # ================= [5] ★ 声明 vs 实现不符 ⇒ 红（会红的判据） ============
        print("\n" + "=" * 74)
        print("[5] ★ 声明 vs 实现：真实实现 == 绿；换成坏实现 ⇒ **立刻红**")
        print("=" * 74)
        OK.check("真实实现下，推理档位声明与实现一致（空列表）",
                 replay_contract_problems(reasoner_auto) == [])
        original = llm_module.request_messages

        def broken(messages, tools=None, profile=None):
            """坏实现：一律剥掉 —— 正是 P19 的旧代码形状。"""
            return llm_module.strip_reasoning_content(messages)

        llm_module.request_messages = broken  # type: ignore[assignment]
        red = replay_contract_problems(reasoner_auto)
        print(f"  坏实现下的判据输出: {red}")
        OK.check("★ 实现违反『必回灌』声明 ⇒ 判据非空（这是会红的那条）", bool(red))
        llm_module.request_messages = original  # type: ignore[assignment]
        OK.check("★ 换回真实实现 ⇒ 判据恢复为空（不是恒红）",
                 replay_contract_problems(reasoner_auto) == [])

        conflict = ModelProfile(
            name="conflict", model="x",
            reasoning=ModelReasoning(is_reasoning_model=True, replay="never"))
        print(f"  冲突档位的 validate(): {conflict.validate(role='ORCH')}")
        OK.check("★ 声明自相矛盾（推理模型 + never）⇒ validate() 非空",
                 bool(conflict.validate(role="ORCH"))
                 and bool(conflict.reasoning.problems()))
        OK.check("纯函数面：`request_messages` **没有**档位时与旧行为一致",
                 request_messages([dict(MSGS[-1])], TOOLS)[0].get(REASONING_CONTENT)
                 == "思考片段")

        # ================= [6] 反空洞：env never ⇒ 假端点 400 ==================
        print("\n" + "=" * 74)
        print("[6] 反空洞：一键关 ⇒ 同一个假端点必须复现官方 400")
        print("=" * 74)
        os.environ[REASONING_REPLAY_ENV] = "never"
        _install_fake(_worker_script())
        raised = ""
        try:
            asyncio.run(_run_worker(prof))
        except RuntimeError as e:  # noqa: PERF203
            raised = str(e)
        os.environ.pop(REASONING_REPLAY_ENV, None)
        print(f"  实测异常: {raised[:110]}")
        OK.check("★ 关掉回灌 ⇒ 假端点抛官方 400（说明前面的跑通不是空转）",
                 "must be passed back" in raised)
    finally:
        _BUILTIN_PROFILES.pop(NEW_TIER, None)
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return OK.report()


raise SystemExit(main())
