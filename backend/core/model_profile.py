"""模型接入的标准参数入口。

设计原则（重要，决定了后续能不能换模型）：
  - **机制**留在工作流层（cycle / pipeline / checkpoint），它们不得包含任何
    针对特定模型的补偿。
  - **策略与数字**集中在适配层，即本模块。换模型时只改这里。

三层结构：
  ModelProfile
    ├── 标识 name / base_url / model        —— 接入信息
    ├── 能力 capabilities                   —— 流程对模型的要求，不满足应显式报错
    ├── 预算 limits                         —— 从 context_window 推导出的各项预算
    └── 耦合 coupling                       —— 该模型特有的、无法抽象的补偿

ModelCoupling 存在的意义：把「为了让某个模型跑通而写的补丁」集中到一处，
使其可以整体丢弃，而不是散落在工作流里腐烂。
空实现（DEFAULT_COUPLING）即"不做任何补偿"，新模型默认走这条路径。
"""

import os
import sys
from dataclasses import dataclass, field, replace
from typing import Callable

PROFILE_ENV = "AGENT_MODEL_PROFILE"


# ============================================================
# 1. 能力声明：流程对模型的要求
# ============================================================
@dataclass
class ModelCapabilities:
    """流程需要的模型能力。启动时校验，不满足就显式失败。

    宁可启动即报错，也不要静默劣化——静默劣化是换模型时最难查的故障。
    """

    supports_tool_calls: bool = True
    supports_json_mode: bool = False      # 支持 response_format={"type":"json_object"}
    supports_system_role: bool = True
    context_window: int = 8192

    # ---------- 多模态 ----------
    # 是否接受图像输入。False 时视觉请求会**显式失败**，而不是静默丢图。
    supports_image_input: bool = False
    # 单次请求的图像数量上限（多数服务有硬限制，如 10 或 20）
    max_images_per_request: int = 1
    # 是否支持图像细节档位（OpenAI 的 detail: low/high/auto）
    supports_image_detail: bool = False


# ============================================================
# 2. 预算参数：从 context_window 推导
# ============================================================
@dataclass
class ModelLimits:
    """所有"数字类"参数的唯一入口。

    提供 from_context_window() 工厂：接入新模型时只给一个上下文长度，
    其余预算按比例推导，避免到处散落魔法数字。
    """

    max_tokens: int = 4096                # 单次生成上限
    max_errors: int = 3                   # 连续工具报错上限
    max_steps: int = 15                   # 单个子任务步数上限
    max_rounds: int = 15                  # 主循环轮次上限
    max_same_task: int = 2                # 同一任务最多尝试次数
    max_attempts: int = 2                 # 一个 cycle 最多尝试次数
    temperature: float = 0.1

    # 字符级预算（不是 token，是回灌上下文的截断长度）
    tool_result_chars: int = 1500
    # 编排器 prompt 的字符预算。**不是 token**——按"1 token ≈ 4 字符"粗估后
    # 取窗口的约 1/6，给工具 schema 与模型输出留空间。
    # 设为 0 表示"不限制"（不推荐：会让 prompt 无限增长直到超窗）。
    orchestrator_prompt_chars: int = 6000

    @classmethod
    def from_context_window(cls, context_window: int, **overrides) -> "ModelLimits":
        """按上下文窗口推导一组自洽的默认预算。

        比例是经验值，可以整体替换；重点是**只有一个地方需要调**。
        """
        cw = max(2048, int(context_window))

        # 单次生成预算：窗口的一半，但不超过 4096。
        # 说明：4096 是原先实测可用的值（ctx=8192 时），这里刻意保持不回退；
        # 只有在窗口更大时才允许上浮。需要更大生成预算的模型请显式覆盖 MAX_TOKENS。
        max_tokens = min(cw // 2, 4096)

        # 上下文越大，允许的迭代越多（但设上限，避免无限烧钱）
        if cw <= 8192:
            rounds, steps, attempts = 15, 15, 2
        elif cw <= 32768:
            rounds, steps, attempts = 20, 20, 3
        else:
            rounds, steps, attempts = 30, 25, 3

        # 回灌截断：至少 800 字符，约为窗口的 1/6（粗略按 1 token≈4 字符估）
        tool_chars = max(800, min(cw // 6, 8000))

        # 编排器 prompt 预算：与回灌同量级，但下限更高（要装下目标 + 结论 + 若干任务）
        prompt_chars = max(2000, min(cw // 6, 24000))

        params = dict(
            max_tokens=max_tokens,
            max_rounds=rounds,
            max_steps=steps,
            max_attempts=attempts,
            tool_result_chars=tool_chars,
            orchestrator_prompt_chars=prompt_chars,
        )
        params.update(overrides)
        return cls(**params)


# ============================================================
# 3. 模型耦合：该模型特有的补偿
# ============================================================
@dataclass
class ModelCoupling:
    """针对特定模型的补偿策略。

    这里的每一项都属于「为了让某个模型跑通而加的补丁」。它们**不属于工作流**：
    工作流只负责调度与校验，不应该知道某个模型爱说"首先我"。

    新模型默认使用 DEFAULT_COUPLING（全空），即不做任何补偿。
    """

    # 该模型表示"我要开始写计划了"的句式特征；空元组 = 不识别
    plan_hints: tuple[str, ...] = ()
    # JSON 输出不合规时，是否启用宽松修复（去围栏、括号匹配、尾逗号）
    repair_json: bool = True
    # 该模型惯用的错误文本前缀；空元组 = 不做文本嗅探（只信结构化判断）
    #
    # 预留项：当前工作流只依赖结构化协议（tools.registry.is_error_result），
    # 不使用本字段做判定。保留是为了将来某个模型确实需要文本兜底时，
    # 补偿逻辑有地方可放，而不是散回工作流层。matches_error_prefix() 同理。
    error_prefixes: tuple[str, ...] = ()
    # 模型名里出现这些片段时，认为它适合被工具调用回灌截断
    notes: str = ""

    def looks_like_plan(self, text: str) -> bool:
        if not text or not self.plan_hints:
            return False
        return any(h in text for h in self.plan_hints)

    def matches_error_prefix(self, text: str) -> bool:
        if not text or not self.error_prefixes:
            return False
        return any(text.startswith(p) for p in self.error_prefixes)


# 空耦合：不做任何模型特判。工作流只依赖结构化协议。
DEFAULT_COUPLING = ModelCoupling()

# qwen 系（当前实测使用）的补偿档：集中在此，换模型可直接丢弃本段
QWEN_COUPLING = ModelCoupling(
    plan_hints=("我将", "首先我", "接下来我", "我打算", "计划如下"),
    repair_json=True,
    error_prefixes=("Error:", "错误：", "执行异常", "失败："),
    notes="7B 量级：倾向先写计划再调用工具，JSON 偶有不规范",
)


# ============================================================
# 3.5 推理档位与可启用模式（P22-A · 类插件结构）
# ============================================================
#: `reasoning_content` 回灌策略的取值。与进程级 `AGENT_REASONING_REPLAY`
#: （显式覆盖 / 一键关）共用同一套取值。
REASONING_REPLAY_MODES = ("auto", "never", "always")
#: 进程级覆盖变量名：显式设置时优先于档位声明（便于 A/B 与排障）。
REASONING_REPLAY_ENV = "AGENT_REASONING_REPLAY"


@dataclass
class ModelReasoning:
    """推理模型的档位（`P22-A`）。

    设计目标：**加一个推理模型 = 加一份档位，代码零改动**。
    所以这里只放"数据"；协议路径由 `core/llm.py` 按这些字段统一裁决。

    ★ 每一项都**可以关**，关掉即回到基线行为：

      · `is_reasoning_model=False` ⇒ 与普通模型走同一条路径；
      · `replay="never"`           ⇒ 不回灌（`P19` 之前的行为，仅供排障/反向验证）；
      · `max_thinking_chars=0`     ⇒ 思考长度不限（该约束关闭）。
    """

    #: 是否是推理模型：决定走哪条协议路径
    is_reasoning_model: bool = False
    #: 回灌策略：`auto`（带 tools 回灌 / 不带剥掉）| `never` | `always`
    replay: str = "auto"
    #: 预算语义：思考 token 是否计入 `max_tokens`（推理模型为 True）。
    #: **本轮只声明**：换算规则属 `B1`，写进档位而不是散在代码里。
    counts_in_max_tokens: bool = True
    #: 思考长度上限（字符）；`0` = 不限（约束关闭）
    max_thinking_chars: int = 0

    def problems(self) -> list[str]:
        """档位声明自身的自洽性（**声明 vs 协议**）。空列表 = 自洽。

        ★ 这条是**会红**的判据：声明为推理模型却把回灌关掉，
        带 `tools` 的后续请求必然 400（`P19` 的实测原文）。
        """
        out: list[str] = []
        if self.replay not in REASONING_REPLAY_MODES:
            out.append(
                f"reasoning.replay={self.replay!r} 不在 {REASONING_REPLAY_MODES}"
            )
        if self.is_reasoning_model and self.replay == "never":
            out.append(
                "reasoning.is_reasoning_model=True 与 reasoning.replay='never' 冲突："
                "带 tools 的后续请求必须回灌 reasoning_content，否则 API 400"
            )
        if self.max_thinking_chars < 0:
            out.append("reasoning.max_thinking_chars 不能为负（0 表示不限）")
        return out

    def modes(self) -> dict[str, bool]:
        """可启用模式的当前状态（**每一项都能关**）。"""
        return {
            "reasoning_model": bool(self.is_reasoning_model),
            "reasoning_replay": self.replay != "never",
            "thinking_cap": self.max_thinking_chars > 0,
        }


def env_reasoning_replay() -> str | None:
    """进程级覆盖值；未设置或非法都返回 `None`（**不静默变成某个极端**）。"""
    raw = (os.environ.get(REASONING_REPLAY_ENV) or "").strip().lower()
    return raw if raw in REASONING_REPLAY_MODES else None


# ============================================================
# 4. 完整档位
# ============================================================
@dataclass
class ModelProfile:
    """一个模型接入所需的全部标准参数。"""

    name: str = "default"
    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen2.5:7b"
    api_key: str = "ollama"
    request_timeout: float = 120.0

    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    limits: ModelLimits = field(default_factory=ModelLimits)
    coupling: ModelCoupling = field(default_factory=lambda: DEFAULT_COUPLING)

    # ---------- P22-A：档位（数据驱动，加模型不改代码） ----------
    #: 推理档位：协议路径 / 回灌策略 / 预算语义 / 思考上限
    reasoning: ModelReasoning = field(default_factory=ModelReasoning)
    #: 模型名匹配片段：`_guess_profile_name` 按它选档 ⇒ 新增模型 = 加一条档位
    match: tuple[str, ...] = ()
    #: 档位缺失而回落到 `default` 时为 True —— 让"回落"**可见**，不是静默
    fallback: bool = False
    #: 回落到哪一份档位（`fallback=False` 时为空串）
    fallback_to: str = ""

    def __post_init__(self) -> None:
        # 保证 context_window 至少能容下单次生成预算。
        # 修正会改变用户配置的实际值，因此必须**可见**——否则 /profile 显示的值
        # 与 .env 里配的值不一致，排查时会误以为配置没生效。
        if self.capabilities.context_window < self.limits.max_tokens:
            import sys

            before = self.capabilities.context_window
            self.capabilities.context_window = self.limits.max_tokens
            print(
                f"[配置修正] {self.name}: context_window {before} 小于 "
                f"max_tokens {self.limits.max_tokens}，已抬升为 "
                f"{self.capabilities.context_window}",
                file=sys.stderr,
            )

    # ---------- 构造 ----------
    @classmethod
    def from_env(cls, prefix: str = "LLM") -> "ModelProfile":
        """从环境变量构造。这是**唯一**的预算入口。

        {prefix}_MODEL            模型名（用于匹配档位的 `match` 片段）
        {prefix}_BASE_URL         接入地址
        {prefix}_API_KEY
        {prefix}_CONTEXT_WINDOW   仅给这一个数字，其余预算自动推导
        {prefix}_MAX_TOKENS / _MAX_ROUNDS / _MAX_STEPS / _MAX_ATTEMPTS /
        {prefix}_MAX_ERRORS / _MAX_SAME_TASK / _TEMPERATURE / _TIMEOUT
        {prefix}_COUPLING         default | qwen | none
        {prefix}_REASONING / _REASONING_REPLAY（auto|never|always）/
        {prefix}_THINKING_IN_MAX_TOKENS / _THINKING_MAX_CHARS
                                  P22-A 推理档位的逐项覆盖（**每项都能关**）
        """
        raw_model = (os.getenv(f"{prefix}_MODEL") or "").strip()
        explicit_profile = (os.getenv(f"{prefix}_PROFILE") or "").strip()
        # 先用既有默认模型名猜档位；档位自己声明了默认模型名时以档位为准 ——
        # 这样"加一份档位"就足以让一个新模型名跑起来，不必改这里的默认值。
        model = raw_model or "qwen2.5:7b"
        profile_name = explicit_profile or _guess_profile_name(model)
        registered = profile_name in _BUILTIN_PROFILES
        base = _BUILTIN_PROFILES.get(profile_name, _BUILTIN_PROFILES["default"])
        if not registered:
            # 档位缺失 ⇒ 回落 default，但必须**可见**（不得静默变成某个极端）
            print(
                f"[配置] {prefix}_PROFILE={profile_name!r} 未登记，"
                f"回落 {base.name!r} 档位（回灌策略取 default，不是 never/always）",
                file=sys.stderr,
            )
        if not raw_model:
            model = base.model

        ctx_env = (os.getenv(f"{prefix}_CONTEXT_WINDOW") or "").strip()
        ctx = int(ctx_env) if ctx_env else base.capabilities.context_window

        # 预算覆盖项（未设置则用推导值）
        overrides = {}
        numeric = {
            "MAX_TOKENS": ("max_tokens", int),
            "MAX_ROUNDS": ("max_rounds", int),
            "MAX_STEPS": ("max_steps", int),
            "MAX_ATTEMPTS": ("max_attempts", int),
            "MAX_ERRORS": ("max_errors", int),
            "MAX_SAME_TASK": ("max_same_task", int),
            "TEMPERATURE": ("temperature", float),
            "TOOL_RESULT_CHARS": ("tool_result_chars", int),
        }
        for env_key, (fld, cast) in numeric.items():
            raw = os.getenv(f"{prefix}_{env_key}")
            if raw is not None and raw.strip():
                try:
                    overrides[fld] = cast(raw)
                except ValueError:
                    pass

        limits = (
            # 显式给了窗口 ⇒ 按窗口推导（保持既有行为）
            ModelLimits.from_context_window(ctx, **overrides) if ctx_env
            # ★ P22-A：档位声明的"上限默认值"就是默认；显式覆盖仍生效。
            #   复制一份，避免把内置档位的 limits 对象共享出去被就地改坏。
            else replace(base.limits, **overrides)
        )

        # 耦合档：可显式指定，默认继承内置档位
        coupling_key = (os.getenv(f"{prefix}_COUPLING") or "").strip().lower()
        if coupling_key == "none":
            coupling = DEFAULT_COUPLING
        elif coupling_key == "qwen":
            coupling = QWEN_COUPLING
        elif coupling_key == "default":
            coupling = DEFAULT_COUPLING
        else:
            coupling = base.coupling

        capabilities = ModelCapabilities(
            supports_tool_calls=base.capabilities.supports_tool_calls,
            supports_json_mode=_env_bool(f"{prefix}_JSON_MODE", base.capabilities.supports_json_mode),
            supports_system_role=base.capabilities.supports_system_role,
            context_window=ctx,
            # 多模态：由环境变量声明。未声明则视为不支持——
            # 这样"以为能识图其实不能"会变成显式失败，而不是静默丢图。
            supports_image_input=_env_bool(
                f"{prefix}_VISION", base.capabilities.supports_image_input),
            max_images_per_request=int(
                os.getenv(f"{prefix}_MAX_IMAGES",
                          str(base.capabilities.max_images_per_request))),
            supports_image_detail=_env_bool(
                f"{prefix}_IMAGE_DETAIL", base.capabilities.supports_image_detail),
        )

        # ★ P22-A：推理档位。每一项都能被环境变量覆盖/关掉 ——
        # 加档位不改代码，排障时也不必改代码。
        replay_env = (os.getenv(f"{prefix}_REASONING_REPLAY") or "").strip().lower()
        reasoning = ModelReasoning(
            is_reasoning_model=_env_bool(
                f"{prefix}_REASONING", base.reasoning.is_reasoning_model),
            replay=replay_env or base.reasoning.replay,
            counts_in_max_tokens=_env_bool(
                f"{prefix}_THINKING_IN_MAX_TOKENS",
                base.reasoning.counts_in_max_tokens),
            max_thinking_chars=int(os.getenv(
                f"{prefix}_THINKING_MAX_CHARS",
                str(base.reasoning.max_thinking_chars))),
        )

        return cls(
            name=profile_name,
            model=model,
            base_url=os.getenv(f"{prefix}_BASE_URL", base.base_url),
            api_key=os.getenv(f"{prefix}_API_KEY", base.api_key),
            request_timeout=float(os.getenv(f"{prefix}_TIMEOUT", str(base.request_timeout))),
            capabilities=capabilities,
            limits=limits,
            coupling=coupling,
            reasoning=reasoning,
            match=base.match,
            fallback=not registered,
            fallback_to="" if registered else base.name,
        )

    # ---------- 校验 ----------
    def validate(self, role: str = "LLM") -> list[str]:
        """返回问题列表；空列表表示可用。

        在启动时调用，把"模型不满足流程要求"变成显式错误。
        """
        problems: list[str] = []
        if not self.capabilities.supports_tool_calls:
            problems.append(
                f"[{role}] 模型 {self.model} 声明不支持 tool_calls，"
                "本流程的子任务执行依赖工具调用，无法运行。"
            )
        if self.limits.max_tokens >= self.capabilities.context_window:
            problems.append(
                f"[{role}] max_tokens({self.limits.max_tokens}) "
                f">= context_window({self.capabilities.context_window})，"
                "单次生成会立刻撑满上下文。"
            )
        if self.capabilities.context_window < 2048:
            problems.append(
                f"[{role}] context_window({self.capabilities.context_window}) 过小，"
                "不足以容纳工具 schema 与任务上下文。"
            )
        # 只有"要用视觉"的角色才校验图像能力；普通角色声明了不支持也无妨
        if role == "vision" and not self.capabilities.supports_image_input:
            problems.append(
                f"[{role}] 模型 {self.model} 未声明 supports_image_input，"
                "无法承担图像理解任务。"
            )
        # ★ P22-A：档位声明自身的自洽性（声明 vs 协议）。会红。
        problems.extend(f"[{role}] {p}" for p in self.reasoning.problems())
        return problems

    # ---------- P22-A：档位视图 ----------
    def effective_reasoning_replay(self) -> str:
        """实际生效的回灌策略。解析顺序（每一步都可见）：

        ① 进程级 `AGENT_REASONING_REPLAY`（显式覆盖 / 一键关；非法值不算数）；
        ② 档位声明 `reasoning.replay`；
        ③ 默认 `auto` —— 中间值，**不是** `never` / `always` 任一极端。
        """
        env = env_reasoning_replay()
        if env:
            return env
        declared = self.reasoning.replay
        return declared if declared in REASONING_REPLAY_MODES else "auto"

    def tier(self) -> dict:
        """把"模型差异"作为一个**可机读的档位**暴露（`/profile` 直接转发）。

        覆盖 `P22-A` 点名的全部字段：是否推理模型 · 回灌策略 · 思考 token 的
        预算语义 · 思考长度上限 · 是否支持图像 · 上限默认值。
        `fallback` 让"档位缺失回落到默认"成为**可见事实**，而不是静默行为。
        """
        return {
            "profile": self.name,
            "model": self.model,
            "fallback": self.fallback,
            "fallback_to": self.fallback_to or None,
            "match": list(self.match),
            "is_reasoning_model": self.reasoning.is_reasoning_model,
            "reasoning_replay": self.effective_reasoning_replay(),
            "reasoning_replay_declared": self.reasoning.replay,
            "reasoning_replay_env": os.environ.get(REASONING_REPLAY_ENV) or None,
            "thinking_counts_in_max_tokens": self.reasoning.counts_in_max_tokens,
            "max_thinking_chars": self.reasoning.max_thinking_chars,
            "supports_image_input": self.capabilities.supports_image_input,
            "max_images_per_request": self.capabilities.max_images_per_request,
            "context_window": self.capabilities.context_window,
            "limits": {
                "max_tokens": self.limits.max_tokens,
                "max_rounds": self.limits.max_rounds,
                "max_steps": self.limits.max_steps,
                "tool_result_chars": self.limits.tool_result_chars,
            },
            "modes": self.reasoning.modes(),
            "problems": self.reasoning.problems(),
        }

    def describe(self) -> str:
        c, l = self.capabilities, self.limits
        vision = (
            f"img={c.max_images_per_request}"
            + ("+detail" if c.supports_image_detail else "")
            if c.supports_image_input else "img=no"
        )
        return (
            f"{self.name} | model={self.model} | ctx={c.context_window} | "
            f"maxtok={l.max_tokens} | rounds={l.max_rounds} | steps={l.max_steps} | "
            f"attempts={l.max_attempts} | tool_chars={l.tool_result_chars} | "
            f"json={c.supports_json_mode} | {vision} | "
            f"reasoning={'yes' if self.reasoning.is_reasoning_model else 'no'} | "
            f"coupling={self.coupling.notes or 'none'}"
        )


# ============================================================
# 内置档位
# ============================================================
_BUILTIN_PROFILES: dict[str, ModelProfile] = {
    "default": ModelProfile(
        name="default",
        capabilities=ModelCapabilities(context_window=8192, supports_json_mode=False),
        limits=ModelLimits.from_context_window(8192),
        coupling=DEFAULT_COUPLING,
    ),
    "qwen": ModelProfile(
        name="qwen",
        model="qwen2.5:7b",
        capabilities=ModelCapabilities(context_window=8192, supports_json_mode=True),
        limits=ModelLimits.from_context_window(8192),
        coupling=QWEN_COUPLING,
        # 数据驱动选档：`_guess_profile_name` 不再知道任何具体模型名。
        match=("qwen",),
    ),
    # ★ P22-A：推理模型档位 —— **加一个推理模型 = 加这一条**（代码零改动）。
    #   实测来源（P19）：`deepseek-flash` 思考模式返回 `reasoning_content`，
    #   带 `tools` 的后续请求必须回灌，否则 400。
    "reasoner": ModelProfile(
        name="reasoner",
        model="deepseek-reasoner",
        capabilities=ModelCapabilities(context_window=65536, supports_json_mode=False),
        limits=ModelLimits.from_context_window(65536, max_tokens=8192),
        coupling=DEFAULT_COUPLING,
        reasoning=ModelReasoning(
            is_reasoning_model=True,
            replay="auto",              # 带 tools 回灌 / 不带剥掉（协议要求）
            counts_in_max_tokens=True,  # 思考先吃掉 max_tokens 预算
            max_thinking_chars=0,       # 约束关闭（B2 才启用）
        ),
        match=("deepseek-reasoner", "deepseek-r1", "deepseek-flash"),
    ),
}

#: 通过 `register_profile()` 注册的档位名（区别于内置档位）。
_REGISTERED_PROFILES: set[str] = set()


def _guess_profile_name(model: str) -> str:
    """按**档位自己声明的** `match` 片段选档（数据驱动）。

    刻意不在这里写任何具体模型名 —— 否则"加一个模型"就变成了改代码，
    而 `P22-A` 的验收正是「加一个推理模型 = 加一份档位、代码零改动」。
    匹配不到时回落 `default`（**不是** `never` / `always` 任一极端）。
    """
    m = (model or "").lower()
    for name, prof in _BUILTIN_PROFILES.items():
        if name == "default":
            continue
        if any(frag and frag.lower() in m for frag in prof.match):
            return name
    return "default"


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def register_profile(profile: ModelProfile) -> None:
    """注册自定义档位，供 `{prefix}_PROFILE` 引用。

    ★ 这是 `P22-A`「加一个推理模型 = 加一份档位、代码零改动」的入口：
    档位自带 `match` 片段，所以连"按模型名选档"那一步也不需要改代码。
    """
    _BUILTIN_PROFILES[profile.name] = profile
    _REGISTERED_PROFILES.add(profile.name)


def profile_names() -> list[str]:
    """已登记档位名（`/profile` 暴露插件面用）。"""
    return list(_BUILTIN_PROFILES)


def profile_source(name: str) -> str:
    """档位来源：`builtin` / `registered` / `missing`（可机判）。"""
    if name not in _BUILTIN_PROFILES:
        return "missing"
    return "registered" if name in _REGISTERED_PROFILES else "builtin"


def get_profile(name: str) -> ModelProfile:
    return _BUILTIN_PROFILES.get(name, _BUILTIN_PROFILES["default"])
