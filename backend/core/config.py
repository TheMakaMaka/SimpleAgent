"""配置入口（标准参数入口）。

这里是**唯一**的模型与预算配置入口。工作流层不得再出现魔法数字。

角色表是**显式**的（见 `ROLES`）——这是刻意的设计，因为隐式继承在多角色下会
产生难以发现的配置错误：

  两角色时的隐式继承是合理的：未配 `WORKER_*` → 继承 `ORCH_*`。
  但角色数超过两个后，未配置的 `REVIEW` 若也静默继承编排器，
  表现就是「以为请了专业审查员，实际还是同一个模型在审自己」，**且不报错**。

所以规则收紧为：
  - `worker` 明确声明 `inherits_from="orch"`（有意的默认）
  - 其它角色**不继承**，未配置时只给一个 `available=False` 的占位档位，
    由调用方决定是报错还是标记「未启用」
"""

import os
from dataclasses import dataclass

from .model_profile import (
    DEFAULT_COUPLING,
    REASONING_REPLAY_MODES,
    ModelCapabilities,
    ModelCoupling,
    ModelLimits,
    ModelProfile,
    ModelReasoning,
    get_profile,
    profile_names,
    profile_source,
    register_profile,
)

# 向后兼容别名：旧代码写的是 LLMConfig.from_env(...)
LLMConfig = ModelProfile


@dataclass(frozen=True)
class RoleSpec:
    """角色的显式声明。"""

    key: str                      # 环境变量前缀，如 "ORCH"
    name: str                     # 角色标识，如 "orchestrator"
    purpose: str
    inherits_from: str | None = None   # 未配置时继承哪个角色（None = 不继承）
    required: bool = False            # 未配置且无继承时，是否报错
    has_builtin_default: bool = False  # 是否有可用的内置默认档位


# 角色表：新增角色必须在此登记，否则 resolve_role 会明确拒绝。
ROLES: dict[str, RoleSpec] = {
    "orchestrator": RoleSpec(
        key="ORCH", name="orchestrator",
        purpose="拆解任务、在循环内做验证回流",
        required=True,
        # ORCH 有内置默认档位（ollama + qwen2.5:7b），所以"未配置"≠"不可用"。
        # 这与 REVIEW 那种"没配就是没启用"是两件事，必须区分。
        has_builtin_default=True,
    ),
    "worker": RoleSpec(
        key="WORKER", name="worker",
        purpose="用工具执行单个任务（写代码、调工具）",
        # 执行器未单独配置时继承编排器：**有意**的默认，且只对这一对成立
        inherits_from="orchestrator",
        has_builtin_default=True,
    ),
    # 以下角色**无内置默认、不继承**。未配置即"未启用"，绝不静默顶替。
    "reviewer": RoleSpec(
        key="REVIEW", name="reviewer",
        # ★ P5（`TRANSPARENCY2-BACKEND`）：**定位写死为"建议性"**。
        # 为什么强调：声明为"建议性、无自由否决权"的审查**不能当门禁** ——
        # 而 ② 需要机械层的硬否决、③ 需要能否决拆解。
        # 所以**否决权不在这个角色上**：它在**机械关卡**里
        # （`core/pipeline.py` 的 reuse 段 = ② 的机械层；
        #   `core/decompose_review.py` = ③ 的拆解关卡）。
        # 将来若要让模型审查**有否决权**，必须**新增角色**（如 `ARCHITECT`）
        # 或明确改这里的 purpose —— 那是架构级改动，需用户批准。
        purpose="代码审查（**建议性，无自由否决权**）；"
                "有否决权的是机械层关卡（复用性检查 / 拆解合规），不是本角色",
    ),
    "package_optimizer": RoleSpec(
        key="PKGOPT", name="package_optimizer",
        purpose="封装优化：形态识别、参数归纳、候选审核",
    ),
    # 视觉角色：负责图像理解。**独立角色**而非给 worker 加能力——
    # 因为图像模型与代码模型通常不是同一个，且不应强制 worker 必须支持图像。
    "vision": RoleSpec(
        key="VISION", name="vision",
        purpose="图像理解（截图/图表/设计稿 → 结构化描述）",
    ),
}


class RoleNotConfigured(RuntimeError):
    """角色未配置。**这是刻意的显式失败，不是 bug。**"""


def _has_config(prefix: str) -> bool:
    return any(
        os.getenv(f"{prefix}_{k}")
        for k in ("MODEL", "BASE_URL", "API_KEY", "CONTEXT_WINDOW", "PROFILE")
    )


def resolve_profile(prefix: str = "ORCH", fallback: ModelProfile | None = None) -> ModelProfile:
    """解析某个环境变量前缀的模型档位。

    `fallback` 仅在**显式传入**时生效。请优先使用 `resolve_role()`——
    它按角色表决定能否继承，不会因为漏写参数而静默顶替。
    """
    if not _has_config(prefix) and fallback is not None:
        return fallback
    return ModelProfile.from_env(prefix=prefix)


def role_available(role: str) -> bool:
    """该角色是否可用。

    "可用" = 显式配置 / 有继承来源 / 有内置默认。
    只有**无默认且无继承**的角色（reviewer、package_optimizer）在未配置时不可用。
    """
    spec = ROLES.get(role)
    if spec is None:
        return False
    if _has_config(spec.key):
        return True
    if spec.inherits_from:
        return role_available(spec.inherits_from)
    return spec.has_builtin_default


def resolve_role(
    role: str,
    *,
    required: bool | None = None,
    resolved: dict[str, ModelProfile] | None = None,
) -> ModelProfile:
    """按**角色名**解析档位。

    与 `resolve_profile` 的区别：继承关系来自角色表，而不是调用方随手传的
    `fallback`。这样"未配置"只会走三条明确路径：

      1. 角色表声明了 `inherits_from` → 继承（仅 worker→orchestrator）
      2. 声明了 `has_builtin_default` → 用内置默认档位（orchestrator/worker）
      3. 都没有 → 抛 `RoleNotConfigured`（reviewer/package_optimizer 即此类）

    第 3 条正是防"以为请了审查员，其实是同一个模型审自己"的关键：
    它**不会**静默顶替成编排器模型。
    """
    spec = ROLES.get(role)
    if spec is None:
        raise RoleNotConfigured(
            f"未知角色 {role!r}；已登记的角色: {sorted(ROLES)}"
        )

    cache = resolved if resolved is not None else {}

    if _has_config(spec.key):
        prof = ModelProfile.from_env(prefix=spec.key)
        cache[role] = prof
        return prof

    # 未配置：优先角色表声明的继承
    if spec.inherits_from:
        parent = cache.get(spec.inherits_from) or resolve_role(
            spec.inherits_from, resolved=cache
        )
        print(
            f"[配置] {role} 未单独配置，按角色表继承 {spec.inherits_from}"
            f"（模型 {parent.model}）"
        )
        cache[role] = parent
        return parent

    if spec.has_builtin_default:
        prof = ModelProfile.from_env(prefix=spec.key)
        print(
            f"[配置] {role} 未配置，使用内置默认档位"
            f"（模型 {prof.model} @ {prof.base_url}）"
        )
        cache[role] = prof
        return prof

    must = spec.required if required is None else required
    if must:
        raise RoleNotConfigured(
            f"角色 {role} 未配置（需要 {spec.key}_* 环境变量）。"
            f"用途：{spec.purpose}"
        )
    raise RoleNotConfigured(
        f"角色 {role} 未启用（未设置任何 {spec.key}_* 环境变量，且无内置默认）。"
        f"用途：{spec.purpose}"
    )


def resolve_roles(*names: str) -> dict[str, ModelProfile | None]:
    """批量解析。**未启用返回 None，不抛异常**——便于在 /profile 里如实展示。

    必需角色缺失才会抛 `RoleNotConfigured`。
    """
    cache: dict[str, ModelProfile] = {}
    out: dict[str, ModelProfile | None] = {}
    for name in names:
        spec = ROLES.get(name)
        if spec is None:
            out[name] = None
            continue
        try:
            out[name] = resolve_role(name, resolved=cache)
        except RoleNotConfigured:
            if spec.required:
                raise
            out[name] = None
    return out


def describe_roles() -> list[dict]:
    """诊断用：每个角色的启用状态、来源与是否可用。"""
    prof_cache: dict[str, ModelProfile] = {}
    out: list[dict] = []
    for name, spec in ROLES.items():
        configured = _has_config(spec.key)
        entry = {
            "role": name,
            "env_prefix": spec.key,
            "purpose": spec.purpose,
            "configured": configured,
            "inherits_from": spec.inherits_from,
            "has_builtin_default": spec.has_builtin_default,
            "available": False,
            "model": None,
            "source": "未启用",
        }
        try:
            prof = resolve_role(name, resolved=prof_cache)
            entry["available"] = True
            entry["model"] = prof.model
            entry["source"] = (
                f"{spec.key}_*" if configured
                else (f"继承 {spec.inherits_from}" if spec.inherits_from
                      else "内置默认")
            )
        except RoleNotConfigured:
            pass
        out.append(entry)
    return out


__all__ = [
    "DEFAULT_COUPLING",
    "LLMConfig",
    "ModelCapabilities",
    "ModelCoupling",
    "ModelLimits",
    "ModelProfile",
    "ModelReasoning",
    "REASONING_REPLAY_MODES",
    "ROLES",
    "RoleNotConfigured",
    "RoleSpec",
    "describe_roles",
    "get_profile",
    "profile_names",
    "profile_source",
    "register_profile",
    "resolve_profile",
    "resolve_role",
    "resolve_roles",
    "role_available",
]
