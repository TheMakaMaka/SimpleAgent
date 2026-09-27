"""动作装配：把「请求参数」翻成「可执行对象」。

`main.py`（旧接口）与 `server.runner`（新运行管理器）都要按同一套规则构建
`CodingCycle`。规则只写一份，避免两边预算/开关悄悄跑偏。
"""

import os

from core import CheckPipeline, CodingCycle

from .factory import build_orchestrator


def approval_base_url() -> str:
    """决策链接的前缀。手机要用，必须是手机可达的地址（不是 127.0.0.1）。

    例：AGENT_APPROVAL_BASE_URL=http://192.168.1.10:8000
    """
    return (os.getenv("AGENT_APPROVAL_BASE_URL") or "http://127.0.0.1:8000").rstrip("/")


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(int(value), high))


def build_cycle(
    max_attempts: int = 2,
    on_decision: str = "auto",
    max_consecutive_failures: int = 2,
    base_url: str = "",
) -> CodingCycle:
    """构建一轮编码流程。

    与 `POST /encode` 完全同构：同一套钳制范围、同一套决策模式白名单。
    """
    orchestrator = build_orchestrator()
    return CodingCycle(
        orchestrator=orchestrator,
        worker=orchestrator.worker,
        pipeline=CheckPipeline(),
        max_attempts=clamp(max_attempts, 1, 5),
        on_decision=on_decision if on_decision in ("auto", "notify", "wait") else "auto",
        max_consecutive_failures=clamp(max_consecutive_failures, 1, 10),
        approval_base_url=base_url or approval_base_url(),
    )
