"""运行时挂钩：不改上游一行代码，把它的执行过程变成前端能认的事件。

为什么用挂钩而不是往上游里加埋点
--------------------------------
用户的工作流是「把最新版后端复制过来覆盖 `backend/`」。只要埋点写在上游文件里，
这次复制就会把它**静默抹掉**——前端随之失去全部事件。

所以埋点改成运行时包装：上游文件保持原样，`bridge` 在启动时把它的方法包一层。

挂钩点的选择原则：**挑上游本来就存在的"汇聚点"**，而不是挑"我方便的地方"。

| 上游挂钩点 | 一次覆盖的事件 | 为什么它是汇聚点 |
|---|---|---|
| `CodingCycle._emit` | cycle_start / plan / task_result / manifest / syntax / lint / verify / cycle_end / decision_* / rollback_denied | 上游所有 cycle 级事件都从这一个方法出去 |
| `CycleReport.enter` | phase | 阶段推进的唯一出口（`PHASE_ORDER` 校验也在那儿） |
| `CodingCycle.run` | run_start（+ 上下文） | 一轮流程的唯一入口 |
| `CodingCycle._new_file_artifacts` | files | 交付文件的唯一计算处 |
| `CheckpointManager.commit / rollback` | baseline / rollback | 检查点的唯一出口 |
| `Orchestrator._decide` | round_start / orchestrator_decision | 每轮决策的唯一入口 |
| `Worker.run` | task_start / task_done（+ 上下文） | 单个任务的唯一入口 |
| `CheckPipeline.run_verify` | verify_probe | 循环内验证回流的唯一出口 |
| `LLMClient.chat` | worker_step / model_reply | 所有模型调用的唯一出口 |
| `Worker._invoke` | tool_call / tool_result | 所有工具调用的唯一出口 |

**全部失败都不影响上游**：每个包装都兜住自己的异常，进度坏掉不能让 cycle 失败。
唯一的例外是 `RunCancelled`（协作式取消），它继承 `BaseException`，故意穿出去。
"""

import contextvars
import inspect
from typing import Any

from .progress import RunCancelled, emit_progress

#: 当前 worker 上下文：{task_id, step}。判断「这次 chat 是不是子循环发的」靠它。
_worker_ctx: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "bridge_worker_ctx", default=None
)
#: 当前 cycle 上下文：{cycle_id, goal, attempt, transitions, max_attempts}
_cycle_ctx: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "bridge_cycle_ctx", default=None
)

_installed = False
_report: dict[str, Any] = {}


def _safe(fn, *args, **kwargs):
    """挂钩内部一律走这里：**进度与挂钩自身的毛病绝不能影响上游执行**。

    ★ 只放行 `RunCancelled`（协作式取消，刻意继承 `BaseException`，见 `progress.py:34`）。

    改前写的是：

        except BaseException:   # 注释说「RunCancelled 要穿出去」
            raise               # ← 它把**所有**异常都截走并重抛了
        except Exception:       # ← **永远走不到**（死代码）
            return None

    于是 `_safe` **一个异常都没兜住**，而模块抬头明确承诺了"每个包装都兜住自己的异常"。
    实测（判据 H）：`_safe(lambda: 1/0)` 抛出 `ZeroDivisionError`。

    **为什么这条不是"少挡一个异常"**：挂钩自身的任何 bug（`emit_progress` 撞上意外
    payload、`preview_args` 遇到没料到的类型）都会**杀掉用户的整轮运行**，
    而用户看到的 `status=error` 与"模型做不出来"**长得一模一样** ——
    **污染能力画像**（那正是四值结局里 `invalid` 要解决的问题）。

    注意 `except Exception` **不**吞 `KeyboardInterrupt` / `SystemExit`
    （它们是 `BaseException` 但不是 `Exception`）—— 那两个该穿出去。
    """
    try:
        return fn(*args, **kwargs)
    except RunCancelled:
        raise                       # 取消必须穿出去，否则「取消」就失效了
    except Exception:
        return None                 # 其余一律吞掉：挂钩是旁路，坏掉不能拖垮 cycle


def parse_worker_args(arguments_json):
    """取 `Worker` 类并解析工具参数 —— **整条**都在 `_safe` 的保护范围内。

    ★ 为什么单独包一层（而不是 `_safe(worker_cls()._parse_args, …)`）：
    **参数是在进 `_safe` 之前求值的**，所以 `worker_cls()` 那一步在保护之外 ——
    "取类失败"（上游没有 `core.worker`、或 import 期报错）照样会炸穿。
    求值顺序也是契约的一部分。
    """
    return worker_cls()._parse_args(arguments_json)


def emit_safe(event_kind: str, build, *args):
    """播报一条事件，**payload 的构造也在保护范围内**。

    ★ 这是 `parse_worker_args` 那条教训的**推广**（同一个坑：参数在进 `_safe` 之前求值）：

        _safe(emit_progress, "tool_call", args=preview_args(name, args))
                                          ^^^^^^^^^^^^^^^^^^^^^^^ 在 _safe **之外**求值

    于是 `preview_args` 遇到没料到的类型、`command.label()` 抛错、`list(...)` 碰到
    不可迭代对象 —— 这些**挂钩自己的**毛病照样会杀掉整轮运行。
    把"构造 payload + 播报"整条包进来，才是真的兜住：

        emit_safe("tool_call", _tool_call_payload, name, args, ctx)

    构造失败 ⇒ **这一条事件不发**（少一条事件是可见的、可接受的代价），
    cycle 照常往下跑。
    """
    return _safe(lambda: emit_progress(event_kind, **build(*args)))


# ============================================================
# 预览工具参数（原在 worker 里，现在归 bridge —— 它是给前端看的，不属于工作流）
# ============================================================
def preview_args(name: str, args: dict) -> dict:
    """工具参数摘要：短字段照留，长内容（代码）只给长度与前几行。

    目的不是复现完整调用，而是让人一眼看出「它现在在写哪个文件 / 跑什么」。
    """
    out: dict = {}
    for key, value in (args or {}).items():
        if isinstance(value, str):
            if len(value) <= 200:
                out[key] = value
            else:
                head = "\n".join(value.splitlines()[:6])
                out[key] = f"{head}\n…（共 {len(value)} 字符）"
        elif isinstance(value, (int, float, bool)) or value is None:
            out[key] = value
        else:
            out[key] = str(value)[:200]
    return out


# ============================================================
# 安装
# ============================================================
def make_emit_wrapper(orig_emit):
    """给 `CodingCycle._emit` 造包装器：**按上游真实签名绑定，不镜像它**。

    抽成独立函数是为了**可测**：`tests/unit/test_hooks_passthrough.py`
    用不同签名的假 `orig_emit` 直接调它，不必真跑一轮 cycle。

    ★ 为什么要这样（一次真实的 `status=error`）
    ------------------------------------------
    原先写的是 `def _emit(self, kind, cycle_id, goal="", **payload)` ——
    把上游签名原样抄了一份，位置参数就叫 `kind`。于是任何调用点只要写
    `self._emit("decision_opened", cid, kind="repeated_failure", ...)`，
    Python 会把那个值同时绑给位置参数与关键字参数：

        TypeError: _emit() got multiple values for argument 'kind'

    **整轮 run 直接 status=error**。上游踩过一次，并把自己的首参改名
    `event_kind` 做二次防御 —— 但 bridge 这份镜像**不会跟着变**。
    镜像的本质就是"第二份判据"。

    改成 `inspect.signature(orig_emit).bind(...)` 之后有两个好处，都是实测的：

      1. **绑定冲突消失**：调用方写 `kind="y"` 时，上游的 `**payload` 收下它
         （上游第一个位置参数叫 `event_kind`，不再撞名）；
      2. **载荷完整**：`cycle_id`、`goal` 这类位置/缺省参数也会进事件记录。
         纯 `*args, **kwargs` 透传会把它们丢掉 —— 那是"修好 A 弄坏 B"。

    ⚠️ **它治不了上游自己的冲突**：若上游首参仍叫 `kind`，
    `orig_emit(self, *args, **kwargs)` 照样会炸 —— 那只能由上游改名解决
    （外部 checkout 已改；仓库自带的旧副本没改，但它本来也发不出该事件）。
    本函数保证的是**bridge 这一层不再是冲突来源**。
    """
    try:
        sig = inspect.signature(orig_emit)
    except (TypeError, ValueError):        # 内建 / 不可内省
        sig = None

    def _emit(self, *args, **kwargs):
        kind = None
        payload: dict = {}
        if sig is not None:
            try:
                bound = sig.bind(self, *args, **kwargs)
                bound.apply_defaults()
                params = dict(bound.arguments)
                params.pop("self", None)

                # ★ 必须**展开 VAR_KEYWORD**：`BoundArguments.arguments` 会把
                #   `**payload` 收成一个**嵌套字典**挂在 `"payload"` 键下，
                #   而不是摊平。不展开时事件记录会变成
                #       {seq, ts, kind, cycle_id, goal, payload: {...}}
                #   —— 前端读的 `ev.decision_id` 就成了 undefined，而且**不报错**
                #   （只是少显示）。实测被 test_hooks_passthrough.py 的载荷断言抓到。
                for pname, param in sig.parameters.items():
                    if param.kind is inspect.Parameter.VAR_KEYWORD:
                        extra = params.pop(pname, None)
                        if isinstance(extra, dict):
                            params.update(extra)
                    elif param.kind is inspect.Parameter.VAR_POSITIONAL:
                        params.pop(pname, None)

                # 事件名：按名字取。上游改过名（kind → event_kind），两种都认。
                for name in ("event_kind", "kind"):
                    if name in params:
                        kind = params.pop(name)
                        break
                payload = params
            except TypeError:
                # 绑定失败（上游签名与调用不符）→ 不猜，退回最小可用形态
                kind, payload = None, {}
        if kind is None:
            kind = args[0] if args else kwargs.get("event_kind", kwargs.get("kind"))
        if not payload:
            # 绑定不可用时至少保住显式关键字载荷。
            payload = dict(kwargs)
            payload.pop("event_kind", None)
            # 只有在"事件名是从 kwargs['kind'] 取的"情况下才把它从载荷里去掉 ——
            # 那时它已经是事件名，不该再出现一次。正常路径（args[0] 给了事件名）
            # 下 `kind` 是**载荷字段**，必须留着。
            if not args and kwargs.get("kind") == kind:
                payload.pop("kind", None)

        _safe(emit_progress, kind, **payload)

        # 记住失败原因：下一轮 attempt_start 时 `retry` 要带上它，
        # 否则前端只看到"重试了"，看不到"为什么重试"。
        if kind == "cycle_end":
            ctx = _cycle_ctx.get()
            if ctx is not None:
                ctx["last_error"] = payload.get("error") or ""
        return orig_emit(self, *args, **kwargs)

    # 工厂印记：与 `make_hook` 一致 —— 测试与自审查按它判断"这是工厂造的，
    # 不是手写的镜像"（`test_hook_compat.py` 逐个挂钩点查这一点）。
    _emit.__bridge_hook__ = "CodingCycle._emit"
    _emit.__wrapped_orig__ = orig_emit
    return _emit



# ============================================================
# 通用挂钩机械：**透传**，不镜像签名
# ============================================================
#: 全部挂钩点：**(模块:类, 属性名, 中文说明, 是否 staticmethod)**。
#:
#: ★ 这是**唯一名单**：`install()` 按它安装，`tests/unit/test_hook_compat.py`
#:   按它逐个断言"接得住上游签名"。名单分散在两处就会漂 —— 而漂的后果
#:   正是 P5 那个 bug（`run_verify` 镜像了旧签名，每次运行 ~6 秒内必炸）。
HOOK_POINTS: tuple[tuple[str, str, str, bool], ...] = (
    ("core.coding_cycle:CodingCycle", "_emit", "cycle 级事件汇聚点", False),
    ("core.cycle:CycleReport", "enter", "阶段推进 + 尝试边界", False),
    ("core.coding_cycle:CodingCycle", "run", "run_start + 周期上下文", False),
    ("core.coding_cycle:CodingCycle", "_new_file_artifacts", "交付文件", True),
    ("core.checkpoint:CheckpointManager", "commit", "基线检查点", False),
    ("core.checkpoint:CheckpointManager", "rollback", "回退", False),
    ("core.orchestrator:Orchestrator", "_decide", "轮次与决策依据", False),
    ("core.worker:Worker", "run", "任务边界 + 子循环上下文", False),
    ("core.llm:LLMClient", "chat", "模型调用（子循环步）", False),
    ("core.worker:Worker", "_invoke", "工具调用", False),
    ("core.pipeline:CheckPipeline", "run_verify", "循环内验证回流", False),
)


def worker_cls():
    """拿 `Worker` 类（**延迟 import**：`bootstrap.install()` 之后才可 import）。

    ★ 为什么要这么一个函数，而不是直接写 `Worker._parse_args(...)`
    ----------------------------------------------------------
    P5b 那次就是这样炸的：`install()` 里写的是

        from core.worker import Worker      # ← **函数内局部 import**

    而 `_around_invoke` 里写的是 `Worker._parse_args(...)` —— 它查的是**模块全局**，
    那里**从来没有** `Worker`。于是：

        NameError: name 'Worker' is not defined

    后果与 P5 一样重：**每一次运行在"模型第一次调用工具"的那一刻死掉**
    （实测事件序 `task_start → worker_step → model_reply → error → run_end`），
    一个文件都还没写出来就结束了。

    ★ 而 ruff **早就报了它**：
        `bridge/hooks.py:438:12: F821 Undefined name `Worker``
    —— 被我自己写的那句 `# noqa: F821（install 时已 import）` 压掉了，
    **而那句理由是错的**（局部 import 不等于模块全局）。
    **一句 noqa 能让门禁闭嘴，但改不了运行期的事实。**
    """
    from core.worker import Worker

    return Worker


def phase_id(phase: Any) -> str:
    """阶段标识：`CyclePhase.PLAN` → `"plan"`。

    上游给的是枚举；给字符串时也照用 —— **不许因为"它不是枚举"就静默不发**。
    """
    value = getattr(phase, "value", None)
    return str(value if value is not None else (phase or ""))


def bind_arguments(orig, args: tuple, kwargs: dict) -> dict:
    """按**上游真实签名**把这次调用解成"参数名 → 值"。

    拿不到（内建/签名不可内省）或**绑不上**（上游签名与调用不符）时返回 `{}`：
    **不猜**。调用照旧原样透传给上游，由上游自己报错 —— 那一层不是 bridge 该修的。
    """
    try:
        sig = inspect.signature(orig)
    except (TypeError, ValueError):
        return {}
    try:
        bound = sig.bind(*args, **kwargs)
    except TypeError:
        return {}
    out = dict(bound.arguments)
    # ★ 展开 VAR_KEYWORD（与 `make_emit_wrapper` 同一条纪律）：
    #   不展开时 `**payload` 会变成嵌套字典挂在 `"payload"` 下，而调用方
    #   按名字读的是摊平后的键 —— 读不到、也不报错。
    for pname, param in sig.parameters.items():
        if param.kind is inspect.Parameter.VAR_KEYWORD:
            extra = out.pop(pname, None)
            if isinstance(extra, dict):
                out.update(extra)
        elif param.kind is inspect.Parameter.VAR_POSITIONAL:
            out.pop(pname, None)
    return out


def make_sync_hook(orig, around, *, label: str = ""):
    """同步目标的透传包装器：`around(named, call)`，`call()` 返回原方法的结果。"""

    def wrapper(*args, **kwargs):
        named = bind_arguments(orig, args, kwargs)
        return around(named, lambda: orig(*args, **kwargs))

    wrapper.__name__ = getattr(orig, "__name__", "wrapper")
    wrapper.__qualname__ = getattr(orig, "__qualname__", wrapper.__name__)
    wrapper.__doc__ = getattr(orig, "__doc__", None)
    wrapper.__bridge_hook__ = label or wrapper.__name__   # 供测试/自审查识别
    wrapper.__wrapped_orig__ = orig
    return wrapper


def make_async_hook(orig, around, *, label: str = ""):
    """异步目标：同上，`around` 是 `async def`，内部 `await call()`。"""

    async def wrapper(*args, **kwargs):
        named = bind_arguments(orig, args, kwargs)

        async def call():
            return await orig(*args, **kwargs)

        return await around(named, call)

    wrapper.__name__ = getattr(orig, "__name__", "wrapper")
    wrapper.__qualname__ = getattr(orig, "__qualname__", wrapper.__name__)
    wrapper.__doc__ = getattr(orig, "__doc__", None)
    wrapper.__bridge_hook__ = label or wrapper.__name__
    wrapper.__wrapped_orig__ = orig
    return wrapper


def make_hook(orig, around, *, label: str = ""):
    """**同步还是异步，问上游** —— 不手写这个判断（手写就是又一份镜像）。

    ★ 这里刻意**不用 `functools.wraps`**：它会把 `__wrapped__` 指回原方法，
    于是 `inspect.signature(包装器)` 会**报告上游的签名**（看起来像镜像），
    而实际能力是"什么都收"。外部工具（含统筹方的 `hook-compat.py`）
    按签名判断兼容性时，看到的必须是**真相**：`(*args, **kwargs)`。
    """
    maker = make_async_hook if inspect.iscoroutinefunction(orig) else make_sync_hook
    return maker(orig, around, label=label)


def resolve(spec: str):
    """`"core.pipeline:CheckPipeline"` → 类对象。延迟 import（bootstrap 之后才行）。"""
    import importlib

    mod_name, _, attr = spec.partition(":")
    return getattr(importlib.import_module(mod_name), attr)


# ---------- 各挂钩点的"围绕逻辑"（都只读 named，不碰签名） ----------

def _around_enter(named: dict, call):
    report = named.get("self")
    phase = named.get("phase")
    pid = phase_id(phase)
    ctx = _cycle_ctx.get()

    # 「进入 PLAN」= 新一轮尝试开始。**必须在 orig 之前播报**：
    # 前端收到 attempt_start 会重置流水线，顺序反了会把刚点亮的 PLAN 抹掉。
    # （上游 `report.attempts = attempt` 在这一步之前已就绪，所以能读到。）
    if ctx is not None and pid == "plan":
        attempt = getattr(report, "attempts", 1)
        _safe(emit_progress, "attempt_start", attempt=attempt,
              max_attempts=ctx.get("max_attempts", 1))
        if attempt > 1:
            _safe(emit_progress, "retry", attempt=attempt,
                  reason=str(ctx.get("last_error") or ""))

    result = call()

    if ctx is not None:
        def _phase_payload(report, pid, ctx):
            return {
                "cycle_id": ctx.get("cycle_id", ""), "goal": ctx.get("goal", ""),
                "phase": pid, "attempt": getattr(report, "attempts", 0),
                # ★ `list(...)` 也搬进来：它碰到不可迭代对象会抛，而那在 `_safe` 之外
                "transitions": list(getattr(report, "transitions", None) or []),
            }

        emit_safe("phase", _phase_payload, report, pid, ctx)
    return result


async def _around_run(named: dict, call):
    self = named.get("self")
    goal = named.get("goal", "")
    ctx: dict = {
        "cycle_id": "", "goal": goal,
        "max_attempts": getattr(self, "max_attempts", 1),
    }
    token = _cycle_ctx.set(ctx)
    _safe(
        emit_progress, "run_start", goal=goal,
        backend=getattr(getattr(self, "checkpoint", None), "name", "?"),
        max_attempts=ctx["max_attempts"],
        on_decision=getattr(self, "on_decision", "?"),
    )
    try:
        return await call()
    finally:
        _cycle_ctx.reset(token)


def _around_artifacts(named: dict, call):
    paths = call()

    def _files_payload(paths):
        touched = list(paths or [])
        return {"touched": touched, "count": len(touched)}

    emit_safe("files", _files_payload, paths)
    return paths


def _around_commit(named: dict, call):
    ckpt = call()
    label = named.get("label") or ""
    if "baseline" in str(label):
        _safe(emit_progress, "baseline", ref=getattr(ckpt, "ref", "") or "")
    return ckpt


def _around_rollback(named: dict, call):
    ok = call()
    _safe(emit_progress, "rollback", ref=named.get("ref") or "", ok=bool(ok))
    return ok


async def _around_decide(named: dict, call):
    self = named.get("self")
    round_no = getattr(self, "_bridge_round", 0) + 1
    self._bridge_round = round_no
    _safe(emit_progress, "round_start", round=round_no,
          max_rounds=getattr(self, "max_rounds", 0))
    data = await call()
    _safe(
        emit_progress, "orchestrator_decision",
        round=round_no,
        status=(data or {}).get("status", "continue"),
        reasoning=str((data or {}).get("reasoning") or "")[:400],
        task_count=len((data or {}).get("tasks") or []),
        final_answer=str((data or {}).get("final_answer") or "")[:400],
    )
    return data


async def _around_worker_run(named: dict, call):
    task = named.get("task")
    ctx = {"task_id": getattr(task, "id", ""), "step": 0}
    token = _worker_ctx.set(ctx)
    def _task_start_payload(task, ctx):
        return {
            "task_id": ctx["task_id"],
            "description": str(getattr(task, "description", "") or "")[:200],
            # ★ `list(...)` 同样搬进来（tool_hint 万一不是可迭代对象）
            "tool_hint": list(getattr(task, "tool_hint", None) or []),
        }

    emit_safe("task_start", _task_start_payload, task, ctx)
    try:
        result = await call()
    finally:
        _worker_ctx.reset(token)
    _safe(
        emit_progress, "task_done", task_id=ctx["task_id"],
        ok=bool(getattr(result, "ok", False)),
        steps_used=getattr(result, "steps_used", 0),
        output=str(getattr(result, "output", "") or "")[:300],
        error=str(getattr(result, "error", "") or "")[:200],
    )
    return result


async def _around_chat(named: dict, call):
    ctx = _worker_ctx.get()
    if ctx is None:
        # 编排器的调用不算「子循环步」；它由 _decide 挂钩负责
        return await call()

    ctx["step"] += 1
    step = ctx["step"]
    messages = named.get("messages") or []
    _safe(emit_progress, "worker_step", task_id=ctx.get("task_id", ""), step=step,
          message_count=len(messages))
    reply = await call()
    content = (reply or {}).get("content")
    tool_calls = (reply or {}).get("tool_calls") or []
    _safe(
        emit_progress, "model_reply", task_id=ctx.get("task_id", ""), step=step,
        tool_calls=len(tool_calls), content_len=len(content or ""),
        content=str(content or "")[:400],
    )
    return reply


async def _around_invoke(named: dict, call):
    from tools import is_error_result

    ctx = _worker_ctx.get() or {}
    name = named.get("name", "")
    arguments_json = named.get("arguments_json")
    # 走 `parse_worker_args`（内部才取类）：**整条**都在 `_safe` 的保护范围内 ——
    # 连"取类失败"那一步也不许炸穿（挂钩自己的异常不能拖垮上游的工具调用）。
    args = _safe(parse_worker_args, arguments_json) or {}
    def _tool_call_payload(name, args, ctx):
        return {"task_id": ctx.get("task_id", ""), "step": ctx.get("step", 0),
                "tool": name, "args": preview_args(name, args)}

    emit_safe("tool_call", _tool_call_payload, name, args, ctx)
    result = await call()
    _safe(emit_progress, "tool_result", task_id=ctx.get("task_id", ""),
          step=ctx.get("step", 0), tool=name,
          ok=not is_error_result(result), preview=str(result)[:400])
    return result


async def _around_run_verify(named: dict, call):
    """★ P5：这里**不许**镜像签名。

    上游 v1.23 给 `run_verify` 加了一个可选参数
    （`core/pipeline.py:361`：`async def run_verify(self, command, files=None)`），
    并在 `core/orchestrator.py:246` 用**两个位置参数**调用它。
    旧实现写的是 `async def _run_verify(self, command)` —— 于是：

        TypeError: install.<locals>._run_verify() takes 2 positional arguments
                   but 3 were given

    **每一次运行 ~6 秒内失败，验证整条链停摆**。这与 D9 是同一类：
    在一处学到了"要透传"，没推广到另外九个挂钩点。
    """
    command = named.get("command")
    res = await call()
    def _probe_payload(res, command):
        try:
            label = command.label()[:400] if hasattr(command, "label") else ""
        except Exception:               # noqa: BLE001 —— 取不到命令原文不影响判定
            label = ""
        return {"passed": bool((res or {}).get("passed")),
                "detail": str((res or {}).get("reason") or "")[:300],
                "command": label}

    emit_safe("verify_probe", _probe_payload, res, command)
    return res


#: 属性名 → 围绕逻辑。**按 (模块:类, 属性名) 精确匹配**；`_emit` 走专用工厂。
_AROUND: dict[tuple[str, str], Any] = {
    ("core.cycle:CycleReport", "enter"): _around_enter,
    ("core.coding_cycle:CodingCycle", "run"): _around_run,
    ("core.coding_cycle:CodingCycle", "_new_file_artifacts"): _around_artifacts,
    ("core.checkpoint:CheckpointManager", "commit"): _around_commit,
    ("core.checkpoint:CheckpointManager", "rollback"): _around_rollback,
    ("core.orchestrator:Orchestrator", "_decide"): _around_decide,
    ("core.worker:Worker", "run"): _around_worker_run,
    ("core.llm:LLMClient", "chat"): _around_chat,
    ("core.worker:Worker", "_invoke"): _around_invoke,
    ("core.pipeline:CheckPipeline", "run_verify"): _around_run_verify,
}


def install() -> dict:
    """安装全部挂钩。幂等；重复调用只返回上次的结果。

    ★ 这里**不再逐个手写包装器**：按 `HOOK_POINTS` 表遍历，
    每个点用 `make_hook`（同步/异步问上游）+ 自己的围绕逻辑。
    手写十个签名 = 十份会漂的镜像（P5 就是这么来的）。
    """
    global _installed, _report
    if _installed:
        return _report

    from core.coding_cycle import CodingCycle

    installed: list[str] = []
    skipped: list[str] = []

    # ---------- 1) 已打点的后端：跳过 cycle 级挂钩，避免重复播报 ----------
    # `_enter` 是「上游文件被加过埋点」的标记。用户可能拿一个改过的后端过来，
    # 那时再挂一层会让同一条事件出现两次。
    pre_instrumented = hasattr(CodingCycle, "_enter")
    if pre_instrumented:
        skipped.append("backend 自带埋点（检测到 CodingCycle._enter），跳过 cycle 级挂钩")

    for spec, attr, why, is_static in HOOK_POINTS:
        if pre_instrumented and spec.endswith("CodingCycle") and attr in ("_emit", "run",
                                                                        "_new_file_artifacts"):
            continue
        cls = resolve(spec)
        orig = cls.__dict__.get(attr)
        if orig is None:                       # 继承来的：取实际生效的那个
            orig = getattr(cls, attr)
        if is_static:
            orig = orig.__func__ if isinstance(orig, staticmethod) else orig

        if attr == "_emit":
            wrapped = make_emit_wrapper(orig)
        else:
            around = _AROUND.get((spec, attr))
            if around is None:
                # 表里有点、却没有围绕逻辑：**宁可跳过也不装一个空壳** ——
                # 空壳会让人以为"这个点挂着"，而它什么也不发。
                skipped.append(f"{spec}.{attr}（缺围绕逻辑，未安装）")
                continue
            wrapped = make_hook(orig, around, label=f"{spec}.{attr}")

        setattr(cls, attr, staticmethod(wrapped) if is_static else wrapped)
        installed.append(f"{spec.split(':')[-1]}.{attr}")

    _installed = True
    _report = {"installed": installed, "skipped": skipped, "points": len(HOOK_POINTS)}
    return _report


def report() -> dict:
    return dict(_report)
