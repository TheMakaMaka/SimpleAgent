"""`P22-A` 机械取证：**模型档位 + 可启用模式（类插件结构）**。

不是单元测，而是把本轮的四条验收逐条打成原始回显（评估文档 §4 引用的就是这里）：

  [1] 档位面：内置档位清单 + 每份档位的 P22-A 字段（`tier()` 可机读）；
  [2] ★ **加一个推理模型 = 加一份档位、代码零改动**：运行时 `register_profile()`
      注册一个新档位 ⇒ `from_env()` 自动选中 ⇒ 用假 DeepSeek 端点跑通一道题；
      并机械证明选档函数里没有任何模型名；
  [3] ★ **关掉开关 == 基线**：请求体 `sha256` 双向对照（关 ⇒ 同哈希；开 ⇒ 变哈希）；
  [4] ★ **声明 vs 实现**：真实实现 ⇒ 空；换成"一律剥掉"的坏实现 ⇒ **立刻非空**；
  [5] `/profile` 契约面：`model_tiers` + `models[*].tier` + `replay_contract_problems`；
  [6] 反空洞：进程级一键关 ⇒ 同一个假端点复现官方 400。
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
)
from core.model_profile import (  # noqa: E402
    _BUILTIN_PROFILES,
    _guess_profile_name,
    ModelCapabilities,
    ModelLimits,
    ModelProfile,
    ModelReasoning,
    profile_names,
    profile_source,
    register_profile,
)
from core.task import Task  # noqa: E402
from core.worker import Worker  # noqa: E402

OK = Checker()
DEEPSEEK_400 = ("BadRequestError: Error code: 400 - The `reasoning_content` "
                "in the thinking mode must be passed back to the API.")

ENV_KEYS = ("ACME_MODEL", "ACME_API_KEY", "ACME_BASE_URL", REASONING_REPLAY_ENV)
TOOLS = [{"type": "function", "function": {"name": "noop", "parameters": {}}}]
MSGS = [
    {"role": "system", "content": "s"},
    {"role": "user", "content": "u"},
    {"role": "assistant", "content": None,
     "tool_calls": [{"id": "c0", "type": "function",
                     "function": {"name": "noop", "arguments": "{}"}}],
     REASONING_CONTENT: "思考片段"},
]


def _tc(call_id, name, arguments):
    return NS(id=call_id, function=NS(name=name, arguments=arguments))


class FakeCompletions:
    def __init__(self, script, enforce=True):
        self.script, self.enforce = script, enforce
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
                   completion_tokens_details=NS(reasoning_tokens=7))
        return NS(choices=[NS(message=msg, finish_reason="stop")], usage=usage)


class FakeClient:
    def __init__(self, script, enforce=True):
        self.completions = FakeCompletions(script, enforce=enforce)
        self.chat = NS(completions=self.completions)


def _install_fake(script, enforce=True) -> FakeClient:
    fake = FakeClient(script, enforce=enforce)
    llm_module.AsyncOpenAI = lambda **_kw: fake  # type: ignore[assignment]
    return fake


def _hash(reqs) -> str:
    return hashlib.sha256(
        json.dumps(reqs, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]


def _one_request(profile, tools=TOOLS):
    fake = _install_fake([{"content": "ok", REASONING_CONTENT: "思考"}], enforce=False)
    asyncio.run(LLMClient(profile).chat([dict(m) for m in MSGS], tools=tools))
    return fake.completions.requests[-1]


def _profile(**reasoning_kw) -> ModelProfile:
    return ModelProfile(
        name="tier-test", model="tier-test-model",
        capabilities=ModelCapabilities(context_window=65536),
        limits=ModelLimits(max_tokens=8192),
        reasoning=ModelReasoning(**reasoning_kw),
    )


async def _run_worker(profile):
    return await Worker(LLMClient(profile)).run(
        Task(id="t1", description="查看系统信息", expected_output="一句话结论"),
        context="")


WORKER_SCRIPT = [
    {"reasoning_content": "先看看系统信息", "content": None,
     "tool_calls": [_tc("c1", "get_system_info", "{}")]},
    {"reasoning_content": "看完了，给结论", "content": "完成", "tool_calls": []},
]


def main() -> int:
    saved = {k: os.environ.get(k) for k in ENV_KEYS}
    for k in ENV_KEYS:
        os.environ.pop(k, None)
    new_tier = "acme-reasoner"
    try:
        # ================= [1] 档位面 =================
        print("=" * 74)
        print("[1] 档位面：registry + 每份档位的 P22-A 字段")
        print("=" * 74)
        print(f"  profile_names() = {profile_names()}")
        print(f"  sources         = "
              f"{ {n: profile_source(n) for n in profile_names()} }")
        for name in profile_names():
            t = _BUILTIN_PROFILES[name].tier()
            print(f"  [{name}] reasoning={t['is_reasoning_model']} "
                  f"replay={t['reasoning_replay']} "
                  f"thinking_in_maxtok={t['thinking_counts_in_max_tokens']} "
                  f"cap={t['max_thinking_chars']} image={t['supports_image_input']} "
                  f"ctx={t['context_window']} max_tokens={t['limits']['max_tokens']}")
        OK.check("registry 非空且含内置 reasoner 档位", "reasoner" in profile_names())
        for key in ("is_reasoning_model", "reasoning_replay",
                    "thinking_counts_in_max_tokens", "max_thinking_chars",
                    "supports_image_input", "context_window", "limits", "modes"):
            OK.check(f"tier() 暴露 P22-A 字段 `{key}`",
                     key in _BUILTIN_PROFILES["reasoner"].tier())

        # ================= [2] 加档位、代码零改动 =================
        print("\n" + "=" * 74)
        print("[2] ★ 加一个推理模型：运行时注册一份档位（不改代码）⇒ 跑通一道题")
        print("=" * 74)
        register_profile(ModelProfile(
            name=new_tier, model="acme-r1",
            capabilities=ModelCapabilities(context_window=65536),
            limits=ModelLimits(max_tokens=4096),
            reasoning=ModelReasoning(is_reasoning_model=True, replay="auto"),
            match=("acme-r1", "acme-think"),
        ))
        os.environ.update({"ACME_MODEL": "acme-r1", "ACME_API_KEY": "fake-key"})
        prof = ModelProfile.from_env("ACME")
        print(json.dumps(prof.tier(), ensure_ascii=False, indent=2))
        print(f"  _guess_profile_name('acme-r1') = {_guess_profile_name('acme-r1')}")
        src = inspect.getsource(_guess_profile_name)
        print(f"  选档函数里有具体模型名吗: qwen={'qwen' in src} "
              f"deepseek={'deepseek' in src} acme={'acme' in src}")
        OK.check("新档位只靠 match 被选中（零代码改动）",
                 _guess_profile_name("acme-r1") == new_tier)
        OK.check("选档函数里没有任何具体模型名（数据驱动）",
                 not any(m in src for m in ("qwen", "deepseek", "acme")))

        fake = _install_fake(WORKER_SCRIPT)
        res = asyncio.run(_run_worker(prof))
        reqs = fake.completions.requests
        asst = [m for m in reqs[1]["messages"] if isinstance(m, dict) and m.get("tool_calls")]
        print(f"  worker: ok={res.ok} requests={len(reqs)} "
              f"回灌={asst[0].get(REASONING_CONTENT)!r}")
        OK.check("用新档位跑通一道题（不再 400）", res.ok is True and len(reqs) >= 2)
        OK.check("带 tools 的后续请求按档位声明回灌", bool(asst))

        # ================= [3] 开关双向（sha256） =================
        print("\n" + "=" * 74)
        print("[3] ★ 关掉开关 == 基线；打开 ⇒ 哈希必变（同一个模型/预算，只变档位）")
        print("=" * 74)
        rows = [
            ("基线（全关：False / auto / cap=0）", _profile()),
            ("推理模式=True", _profile(is_reasoning_model=True)),
            ("推理模式=False（关）", _profile(is_reasoning_model=False)),
            ("覆盖 replay=never（非推理档位）", _profile(replay="never")),
            ("覆盖 replay=always（非推理档位）", _profile(replay="always")),
            ("thinking_cap=2（开）", _profile(max_thinking_chars=2)),
            ("thinking_cap=0（关）", _profile(max_thinking_chars=0)),
        ]
        base_hash = None
        for label, p in rows:
            h = _hash([_one_request(p)])
            if base_hash is None:
                base_hash = h
            kept = REASONING_CONTENT in _one_request(p)["messages"][-1]
            print(f"  {label:34s} sha256={h} kept={kept} "
                  f"{'== 基线' if h == base_hash else '!= 基线'}")
            OK.check(f"[{label}] 能构造出请求体（策略={effective_replay_policy(p)}）",
                     bool(h))
        OK.check("★ 推理模式关/开（auto 下）都 == 基线哈希（声明不改报文）",
                 _hash([_one_request(_profile(is_reasoning_model=True))]) == base_hash
                 and _hash([_one_request(_profile(is_reasoning_model=False))]) == base_hash)
        OK.check("★ 覆盖 replay=never ⇒ 哈希改变（开关有牙）",
                 _hash([_one_request(_profile(replay="never"))]) != base_hash)
        OK.check("★ thinking_cap=2 ⇒ 哈希改变；cap=0 ⇒ 回到基线",
                 _hash([_one_request(_profile(max_thinking_chars=2))]) != base_hash
                 and _hash([_one_request(_profile(max_thinking_chars=0))]) == base_hash)
        os.environ[REASONING_REPLAY_ENV] = "never"
        h_env = _hash([_one_request(_profile(is_reasoning_model=True))])
        print(f"  AGENT_REASONING_REPLAY=never       sha256={h_env} "
              f"(== replay=never 的哈希: "
              f"{h_env == _hash([_one_request(_profile(replay='never'))])})")
        OK.check("★ 进程级一键关可复现（与档位 never 同哈希）",
                 h_env == _hash([_one_request(_profile(replay="never"))]))
        os.environ.pop(REASONING_REPLAY_ENV, None)
        OK.check("★ 取消一键关 ⇒ 回到基线哈希",
                 _hash([_one_request(_profile(is_reasoning_model=True))]) == base_hash)

        # ================= [4] 声明 vs 实现（会红） =================
        print("\n" + "=" * 74)
        print("[4] ★ 声明 vs 实现：真实实现 == 空；坏实现 ⇒ 立刻非空")
        print("=" * 74)
        reasoner = _profile(is_reasoning_model=True, replay="auto")
        print(f"  真实实现: {replay_contract_problems(reasoner)}")
        original = llm_module.request_messages
        llm_module.request_messages = (  # type: ignore[assignment]
            lambda messages, tools=None, profile=None:
            llm_module.strip_reasoning_content(messages))
        red = replay_contract_problems(reasoner)
        print(f"  坏实现（一律剥掉）: {json.dumps(red, ensure_ascii=False)}")
        llm_module.request_messages = original  # type: ignore[assignment]
        print(f"  恢复后: {replay_contract_problems(reasoner)}")
        OK.check("★ 判据会红（坏实现下非空）", bool(red))
        OK.check("★ 判据不恒红（恢复后为空）",
                 replay_contract_problems(reasoner) == [])

        # ================= [5] /profile 契约面 =================
        print("\n" + "=" * 74)
        print("[5] /profile：model_tiers + models[*].tier + replay_contract_problems")
        print("=" * 74)
        import main as app_module  # noqa: E402

        d = asyncio.run(app_module.profile())
        print(f"  model_tiers = {json.dumps(d.get('model_tiers'), ensure_ascii=False)}")
        for role, row in d.get("models", {}).items():
            t = row.get("tier") or {}
            print(f"  models[{role}].tier = profile={t.get('profile')} "
                  f"reasoning={t.get('is_reasoning_model')} "
                  f"replay={t.get('reasoning_replay')} fallback={t.get('fallback')} "
                  f"modes={t.get('modes')}")
            print(f"  models[{role}].replay_contract_problems = "
                  f"{row.get('replay_contract_problems')}")
        OK.check("★ /profile 暴露 model_tiers", "model_tiers" in d)
        OK.check("★ /profile 每角色的 models 项带 tier",
                 all("tier" in row for row in d.get("models", {}).values()))
        OK.check("★ /profile 暴露「声明 vs 实现」判据（不是只在测试里活着）",
                 all("replay_contract_problems" in row
                     for row in d.get("models", {}).values()))

        # ================= [6] 反空洞：一键关 ⇒ 官方 400 =================
        print("\n" + "=" * 74)
        print("[6] 反空洞：AGENT_REASONING_REPLAY=never ⇒ 同一个假端点复现 400")
        print("=" * 74)
        os.environ[REASONING_REPLAY_ENV] = "never"
        _install_fake(WORKER_SCRIPT)
        raised = ""
        try:
            asyncio.run(_run_worker(prof))
        except RuntimeError as e:  # noqa: PERF203
            raised = str(e)
        os.environ.pop(REASONING_REPLAY_ENV, None)
        print(f"  实测异常: {raised[:120]}")
        OK.check("关掉回灌 ⇒ 假端点抛官方 400 原文",
                 "must be passed back" in raised)
    finally:
        _BUILTIN_PROFILES.pop(new_tier, None)
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return OK.report()


raise SystemExit(main())
