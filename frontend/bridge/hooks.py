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
import sys
from typing import Any

from .progress import emit_progress

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
    """挂钩内部一律走这里：进度出问题绝不能影响上游执行。"""
    try:
        return fn(*args, **kwargs)
    except BaseException:  # RunCancelled 要穿出去，见 progress.py
        raise
    except Exception:
        return None


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

    return _emit


def install() -> dict:
    """安装全部挂钩。幂等；重复调用只返回上次的结果。"""
    global _installed, _report
    if _installed:
        return _report

    # 这些 import 必须在 bootstrap.install() 之后（它负责 sys.path）
    from core.checkpoint import CheckpointManager
    from core.coding_cycle import CodingCycle
    from core.cycle import CycleReport
    from core.llm import LLMClient
    from core.orchestrator import Orchestrator
    from core.pipeline import CheckPipeline
    from core.worker import Worker
    from tools import is_error_result

    installed: list[str] = []
    skipped: list[str] = []

    # ---------- 1) 已打点的后端：跳过 cycle 级挂钩，避免重复播报 ----------
    # `_enter` 是「上游文件被加过埋点」的标记。用户可能拿一个改过的后端过来，
    # 那时再挂一层会让同一条事件出现两次。
    pre_instrumented = hasattr(CodingCycle, "_enter")
    if pre_instrumented:
        skipped.append("backend 自带埋点（检测到 CodingCycle._enter），跳过 cycle 级挂钩")

    # ---------- 2) CodingCycle._emit：所有 cycle 级事件的汇聚点 ----------
    if not pre_instrumented:
        _orig_emit = CodingCycle._emit
        # 实现见 make_emit_wrapper（抽出去是为了可测）：按上游真实签名绑定，
        # 不镜像它 —— 镜像就是第二份判据。
        CodingCycle._emit = make_emit_wrapper(_orig_emit)
        installed.append("CodingCycle._emit")

    # ---------- 3) CycleReport.enter：阶段推进 + 尝试边界 ----------
    _orig_enter = CycleReport.enter

    def _enter(self, phase):
        ctx = _cycle_ctx.get()

        # 「进入 PLAN」= 新一轮尝试开始。**必须在 orig_enter 之前播报**：
        # 前端收到 attempt_start 会重置流水线，顺序反了会把刚点亮的 PLAN 抹掉。
        # （上游 `report.attempts = attempt` 在这一步之前已就绪，所以能读到。）
        if ctx is not None and phase.value == "plan":
            attempt = getattr(self, "attempts", 1)
            _safe(emit_progress, "attempt_start", attempt=attempt,
                  max_attempts=ctx.get("max_attempts", 1))
            if attempt > 1:
                _safe(emit_progress, "retry", attempt=attempt,
                      reason=str(ctx.get("last_error") or ""))

        result = _orig_enter(self, phase)

        if ctx is not None:
            _safe(
                emit_progress, "phase",
                cycle_id=ctx.get("cycle_id", ""), goal=ctx.get("goal", ""),
                phase=phase.value, attempt=getattr(self, "attempts", 0),
                transitions=list(self.transitions),
            )
        return result

    CycleReport.enter = _enter
    installed.append("CycleReport.enter")

    # ---------- 4) CodingCycle.run：run_start + 周期上下文 ----------
    _orig_run = CodingCycle.run

    async def _run(self, goal, verify_command=None):
        cycle_placeholder = ctx = {
            "cycle_id": "", "goal": goal,
            "max_attempts": getattr(self, "max_attempts", 1),
        }
        token = _cycle_ctx.set(ctx)
        _safe(
            emit_progress, "run_start", goal=goal,
            backend=getattr(self.checkpoint, "name", "?"),
            max_attempts=ctx["max_attempts"],
            on_decision=getattr(self, "on_decision", "?"),
        )
        try:
            return await _orig_run(self, goal, verify_command)
        finally:
            _cycle_ctx.reset(token)

    CodingCycle.run = _run
    installed.append("CodingCycle.run")

    # ---------- 5) _new_file_artifacts：交付文件 ----------
    _orig_artifacts = CodingCycle._new_file_artifacts

    def _new_file_artifacts(memory):
        paths = _orig_artifacts(memory)
        _safe(emit_progress, "files", touched=list(paths), count=len(paths))
        return paths

    CodingCycle._new_file_artifacts = staticmethod(_new_file_artifacts)
    installed.append("CodingCycle._new_file_artifacts")

    # ---------- 6) 检查点：baseline / rollback ----------
    _orig_commit = CheckpointManager.commit
    _orig_rollback = CheckpointManager.rollback

    def _commit(self, label):
        ckpt = _orig_commit(self, label)
        if "baseline" in (label or ""):
            _safe(emit_progress, "baseline", ref=getattr(ckpt, "ref", "") or "")
        return ckpt

    def _rollback(self, ref):
        ok = _orig_rollback(self, ref)
        _safe(emit_progress, "rollback", ref=ref or "", ok=bool(ok))
        return ok

    CheckpointManager.commit = _commit
    CheckpointManager.rollback = _rollback
    installed.append("CheckpointManager.commit/rollback")

    # ---------- 7) Orchestrator._decide：轮次与决策 ----------
    _orig_decide = Orchestrator._decide

    async def _decide(self, memory):
        round_no = getattr(self, "_bridge_round", 0) + 1
        self._bridge_round = round_no
        _safe(emit_progress, "round_start", round=round_no,
              max_rounds=getattr(self, "max_rounds", 0))
        data = await _orig_decide(self, memory)
        _safe(
            emit_progress, "orchestrator_decision",
            round=round_no,
            status=(data or {}).get("status", "continue"),
            reasoning=str((data or {}).get("reasoning") or "")[:400],
            task_count=len((data or {}).get("tasks") or []),
            final_answer=str((data or {}).get("final_answer") or "")[:400],
        )
        return data

    Orchestrator._decide = _decide
    installed.append("Orchestrator._decide")

    # ---------- 8) Worker.run：任务边界 + 子循环上下文 ----------
    _orig_worker_run = Worker.run

    async def _worker_run(self, task, context):
        ctx = {"task_id": task.id, "step": 0}
        token = _worker_ctx.set(ctx)
        _safe(
            emit_progress, "task_start", task_id=task.id,
            description=(task.description or "")[:200],
            tool_hint=list(task.tool_hint or []),
        )
        try:
            result = await _orig_worker_run(self, task, context)
        finally:
            _worker_ctx.reset(token)
        _safe(
            emit_progress, "task_done", task_id=task.id,
            ok=bool(getattr(result, "ok", False)),
            steps_used=getattr(result, "steps_used", 0),
            output=str(getattr(result, "output", "") or "")[:300],
            error=str(getattr(result, "error", "") or "")[:200],
        )
        return result

    Worker.run = _worker_run
    installed.append("Worker.run")

    # ---------- 9) LLMClient.chat：模型调用（只在子循环里算「步」）----------
    _orig_chat = LLMClient.chat

    async def _chat(self, messages, tools=None, force_json=False):
        ctx = _worker_ctx.get()
        if ctx is None:
            # 编排器的调用不算「子循环步」；它由 _decide 挂钩负责
            return await _orig_chat(self, messages, tools=tools, force_json=force_json)

        ctx["step"] += 1
        step = ctx["step"]
        _safe(emit_progress, "worker_step", task_id=ctx["task_id"], step=step,
              message_count=len(messages))
        reply = await _orig_chat(self, messages, tools=tools, force_json=force_json)
        content = (reply or {}).get("content")
        tool_calls = (reply or {}).get("tool_calls") or []
        _safe(
            emit_progress, "model_reply", task_id=ctx["task_id"], step=step,
            tool_calls=len(tool_calls), content_len=len(content or ""),
            content=str(content or "")[:400],
        )
        return reply

    LLMClient.chat = _chat
    installed.append("LLMClient.chat")

    # ---------- 10) Worker._invoke：工具调用 ----------
    _orig_invoke = Worker._invoke

    async def _invoke(self, name, arguments_json):
        ctx = _worker_ctx.get() or {}
        args = Worker._parse_args(arguments_json) or {}
        _safe(emit_progress, "tool_call", task_id=ctx.get("task_id", ""),
              step=ctx.get("step", 0), tool=name, args=preview_args(name, args))
        result = await _orig_invoke(self, name, arguments_json)
        _safe(emit_progress, "tool_result", task_id=ctx.get("task_id", ""),
              step=ctx.get("step", 0), tool=name,
              ok=not is_error_result(result), preview=str(result)[:400])
        return result

    Worker._invoke = _invoke
    installed.append("Worker._invoke")

    # ---------- 11) CheckPipeline.run_verify：循环内验证回流 ----------
    _orig_run_verify = CheckPipeline.run_verify

    async def _run_verify(self, command):
        res = await _orig_run_verify(self, command)
        _safe(
            emit_progress, "verify_probe",
            passed=bool((res or {}).get("passed")),
            detail=str((res or {}).get("reason") or "")[:300],
            command=command.label()[:400] if hasattr(command, "label") else "",
        )
        return res

    CheckPipeline.run_verify = _run_verify
    installed.append("CheckPipeline.run_verify")

    _installed = True
    _report = {"installed": installed, "skipped": skipped}
    return _report


def report() -> dict:
    return dict(_report)
