"""构建工作流实例：把「模型档位解析」和「对象装配」收在一处。

为什么单独一层
--------------
`main.py` 与 Web 运行管理器都要构建 Orchestrator。如果两边各写一份，
换模型时就要改两个地方，而且很容易只改一处——「配置只有一个来源」是这个项目
的核心纪律，装配过程同样适用。

本模块**不抛 HTTPException**：它属于工作流装配，不认识 Web 框架。
调用方（`main.py`）负责把 `RuntimeError` 翻译成 HTTP 语义。
"""

from typing import Any

from core import (
    CheckpointManager,
    LLMClient,
    ModelProfile,
    Orchestrator,
    Worker,
    describe_roles,
    get_git_status,
    resolve_role,
)


def resolve_profiles() -> dict[str, ModelProfile]:
    """解析 ORCH / WORKER 两个角色的模型档位。

    走**显式角色表**（`core.config.ROLES`）：未配置的 worker 按角色表声明继承
    orchestrator；其它角色（reviewer / package_optimizer）**不继承**，
    未配置即"未启用"，不会静默顶替成编排器模型。
    """
    cache: dict[str, ModelProfile] = {}
    return {
        "ORCH": resolve_role("orchestrator", resolved=cache),
        "WORKER": resolve_role("worker", resolved=cache),
    }


def validate_profiles(profiles: dict[str, ModelProfile]) -> list[str]:
    """启动自检：模型不满足流程要求就显式失败，而不是静默劣化。"""
    problems: list[str] = []
    for role, prof in profiles.items():
        problems.extend(prof.validate(role=role))
    return problems


def build_orchestrator() -> Orchestrator:
    profiles = resolve_profiles()
    problems = validate_profiles(profiles)
    if problems:
        raise RuntimeError("模型接入校验失败：\n" + "\n".join(problems))

    for role, prof in profiles.items():
        print(f"[模型接入] {role}: {prof.describe()}")

    worker = Worker(LLMClient(profiles["WORKER"]))
    return Orchestrator(LLMClient(profiles["ORCH"]), worker)


def profile_snapshot() -> dict[str, Any]:
    """`/profile` 的数据源：如实暴露生效参数，便于换模型时确认预算。"""
    profiles = resolve_profiles()
    return {
        "checkpoint_backend": {
            "selected": CheckpointManager().name,
            "git": get_git_status(),
        },
        "roles": describe_roles(),
        "models": {
            role: {
                "profile": prof.name,
                "model": prof.model,
                "base_url": prof.base_url,
                "context_window": prof.capabilities.context_window,
                "supports_tool_calls": prof.capabilities.supports_tool_calls,
                "supports_json_mode": prof.capabilities.supports_json_mode,
                "coupling": prof.coupling.notes or "none",
                "limits": {
                    "max_tokens": prof.limits.max_tokens,
                    "max_rounds": prof.limits.max_rounds,
                    "max_steps": prof.limits.max_steps,
                    "max_attempts": prof.limits.max_attempts,
                    "max_errors": prof.limits.max_errors,
                    "max_same_task": prof.limits.max_same_task,
                    "tool_result_chars": prof.limits.tool_result_chars,
                },
                "problems": prof.validate(role=role),
            }
            for role, prof in profiles.items()
        },
    }
