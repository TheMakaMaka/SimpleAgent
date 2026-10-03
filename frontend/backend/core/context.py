"""Cycle 级上下文：用 ContextVar 传递当前 cycle 的目标文件。

为什么用 ContextVar 而不是构造参数：
CodingCycle 在构造 Orchestrator 之后才知道本轮涉及哪些文件，直接传参会形成
「先建 orchestrator 再建 cycle」的循环依赖。ContextVar 让内层按需读取，
且天然隔离并发任务。
"""

from contextvars import ContextVar

_cycle_files: ContextVar[list[str] | None] = ContextVar("cycle_files", default=None)
_declared_files: ContextVar[list | None] = ContextVar("declared_files", default=None)


def set_cycle_files(files: list[str]):
    return _cycle_files.set(list(files or []))


def get_cycle_files() -> list[str] | None:
    return _cycle_files.get()


def reset_cycle_files(token) -> None:
    try:
        _cycle_files.reset(token)
    except (ValueError, LookupError):
        pass


# ---------- 文件清单（manifest）的声明 ----------
def set_declared_files(raw) -> object:
    """由编排器在 run() 中设置，供 CHECK 阶段读取。"""
    return _declared_files.set(raw)


def get_declared_files():
    return _declared_files.get()


def reset_declared_files(token) -> None:
    try:
        _declared_files.reset(token)
    except (ValueError, LookupError):
        pass
