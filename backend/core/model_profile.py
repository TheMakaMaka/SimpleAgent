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
from dataclasses import dataclass, field
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

        {prefix}_MODEL            模型名（用于匹配内置档位）
        {prefix}_BASE_URL         接入地址
        {prefix}_API_KEY
        {prefix}_CONTEXT_WINDOW   仅给这一个数字，其余预算自动推导
        {prefix}_MAX_TOKENS / _MAX_ROUNDS / _MAX_STEPS / _MAX_ATTEMPTS /
        {prefix}_MAX_ERRORS / _MAX_SAME_TASK / _TEMPERATURE / _TIMEOUT
        {prefix}_COUPLING         default | qwen | none
        """
        model = os.getenv(f"{prefix}_MODEL", "qwen2.5:7b")
        profile_name = os.getenv(f"{prefix}_PROFILE") or _guess_profile_name(model)
        base = _BUILTIN_PROFILES.get(profile_name, _BUILTIN_PROFILES["default"])

        ctx = int(os.getenv(f"{prefix}_CONTEXT_WINDOW", str(base.capabilities.context_window)))

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

        limits = ModelLimits.from_context_window(ctx, **overrides)

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

        return cls(
            name=profile_name,
            model=model,
            base_url=os.getenv(f"{prefix}_BASE_URL", base.base_url),
            api_key=os.getenv(f"{prefix}_API_KEY", base.api_key),
            request_timeout=float(os.getenv(f"{prefix}_TIMEOUT", str(base.request_timeout))),
            capabilities=capabilities,
            limits=limits,
            coupling=coupling,
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
        return problems

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
    ),
}


def _guess_profile_name(model: str) -> str:
    m = (model or "").lower()
    if "qwen" in m:
        return "qwen"
    return "default"


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def register_profile(profile: ModelProfile) -> None:
    """注册自定义档位，供 {prefix}_PROFILE 引用。"""
    _BUILTIN_PROFILES[profile.name] = profile


def get_profile(name: str) -> ModelProfile:
    return _BUILTIN_PROFILES.get(name, _BUILTIN_PROFILES["default"])
