"""进度事件总线：让工作流层能把「正在发生什么」播报出去，而不依赖任何前端。

为什么用 ContextVar 而不是全局单例
-----------------------------------
同一个进程里可能同时跑多个 cycle（Web 端并发提交任务），每个 cycle 的进度
必须只送到它自己的订阅者手里。全局单例做不到这一点，ContextVar 可以：
`asyncio` 的 Task 在创建时复制当前上下文，所以在 `bind_progress()` 之后
创建的协程天然继承同一个接收器，互不串台。

分层纪律
--------
本模块是 `bridge` 的内部件，与上游 `backend/` 无关：

- 没有绑定接收器时，`emit_progress()` 是**纯粹的 no-op**，不产生任何副作用；
- 接收器抛出的异常**绝不能**影响 cycle 成败（唯一例外见下）。

唯一的例外是 `RunCancelled`：它故意继承 `BaseException`，因此能穿过
`except Exception` 的兜底一路向上展开协程栈，实现「协作式取消」——
取消请求由一个正在播报的事件点触发，这是唯一能干净中断模型调用的位置。

注意：上游 `backend/` 里的代码**不 import 本模块**。上游的事件由
`bridge/hooks.py` 在运行时包装出来，所以上游整包替换不会影响这里。
"""

from contextvars import ContextVar
from typing import Any, Callable

# 接收器签名：(kind, payload) -> None
ProgressSink = Callable[[str, dict], None]

_sink: ContextVar[ProgressSink | None] = ContextVar("agent_progress_sink", default=None)


class RunCancelled(BaseException):
    """协作式取消信号。

    继承 `BaseException` 是刻意的：工作流层到处都有 `except Exception` 兜底
    （存储写入失败不能影响 cycle），如果取消信号是 `Exception` 就会被吞掉，
    取消永远不生效。
    """


def bind_progress(sink: ProgressSink):
    """绑定当前上下文的进度接收器，返回可用于还原的 token。"""
    return _sink.set(sink)


def reset_progress(token) -> None:
    _sink.reset(token)


def current_sink() -> ProgressSink | None:
    return _sink.get()


def emit_progress(event_kind: str, **payload: Any) -> None:
    """播报一条进度事件。未绑定接收器时什么都不做。

    ★ 第一个参数叫 **`event_kind`** 而不是 `kind` —— 这是**刻意的防御**，
    与上游 `CodingCycle._emit` 用的是同一招。

    原因：载荷里出现一个叫 `kind` 的键是合法的（上游 `decision_opened` 曾经
    就传 `kind=`）。如果本函数的首参也叫 `kind`，那么

        emit_progress("decision_opened", **{"kind": "repeated_failure"})

    会同时把那个值绑给位置参数与关键字参数：

        TypeError: emit_progress() got multiple values for argument 'kind'

    而这条 TypeError 会被调用方的 `_safe(...)` **吞掉** —— 事件**静默消失**。
    **不报错的失效最难查**，所以把名字让出来。
    """
    sink = _sink.get()
    if sink is None:
        return
    try:
        sink(event_kind, payload)
    except RunCancelled:
        raise
    except Exception:
        # 进度是旁路，坏掉的订阅者不该拖垮 cycle
        pass
