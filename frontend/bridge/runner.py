"""运行管理器：把「一次编码运行」变成可订阅、可回放、可取消的实体。

为什么需要这一层
----------------
`POST /encode` 是**阻塞**的：一次 cycle 动辄 60~300 秒，期间前端什么都看不到。
进度可视化要求「运行」先成为一个可寻址的对象，然后才有资格被订阅。

设计取舍
--------
1. **运行跑在独立线程 + 独立事件循环里。**
   人工决策的 `wait` 模式内部用 `time.sleep` 阻塞（`CodingCycle._wait_for_answer`），
   放在 FastAPI 的事件循环里会把整个服务卡死。每个运行自带一条线程，
   阻塞被限制在它自己身上。

2. **事件流落成每个运行一个 JSONL 文件，而不是内存队列。**
   浏览器刷新 / 断线重连 / 换设备打开同一页面，都应该能补齐历史事件——
   内存队列做不到。文件是唯一真相，SSE 只是它的一个读取器。

3. **取消是协作式的。**
   模型调用没法从外部打断，所以取消请求在下一次进度播报点生效
   （`core.progress.RunCancelled` 继承 `BaseException`，能穿过各处兜底）。
   最坏延迟 ≈ 一次模型调用，这是没有副作用的最小实现。
"""

import asyncio
import json
import os
import secrets
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Iterator

from core import CheckpointManager, CodingCycle, CyclePhase, VerifyCommand
from core.decisions import DecisionManager
from storage import RunStore

from .progress import RunCancelled, bind_progress, reset_progress

from .paths import RUNS_DIR as RUNS_ROOT

# 终态：到达后不再有新事件，SSE 可以收尾
TERMINAL_STATUSES = {"passed", "failed", "relaxed", "cancelled", "error"}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_run_id() -> str:
    return "run_" + datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + secrets.token_hex(3)


# ============================================================
# 事件日志：每个运行一个文件，seq 单调递增
# ============================================================
class EventLog:
    """一个运行的追加型事件日志。

    只有本类会写这个文件，写入点在锁内完成，因此不会出现半行。
    读取（SSE / 轮询）走字节偏移，边写边读是安全的：
    不完整的尾行会被判为「还没写完」，下一次再读。
    """

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._seq = 0
        os.makedirs(os.path.dirname(path), exist_ok=True)

    @property
    def seq(self) -> int:
        return self._seq

    def append(self, kind: str, **payload: Any) -> dict:
        with self._lock:
            self._seq += 1
            record = {
                "seq": self._seq,
                "ts": _now(),
                "kind": kind,
                **payload,
            }
            line = json.dumps(record, ensure_ascii=False, default=str)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            return record

    def read_all(self, after_seq: int = 0) -> list[dict]:
        return [e for e in self._iter_file() if e.get("seq", 0) > after_seq]

    def tail(self, offset: int) -> tuple[list[dict], int]:
        """从字节偏移读增量。返回 (事件列表, 新偏移)。

        只消费**完整的行**：文件可能正被追加，最后一行可能只写了一半。
        """
        if not os.path.exists(self.path):
            return [], offset
        with open(self.path, "rb") as f:
            f.seek(offset)
            chunk = f.read()
        if not chunk:
            return [], offset

        last_nl = chunk.rfind(b"\n")
        if last_nl < 0:
            return [], offset  # 还没有完整的一行
        complete = chunk[: last_nl + 1]
        new_offset = offset + last_nl + 1

        out: list[dict] = []
        for line in complete.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # 脏行跳过，一条坏数据不该毁掉实时流
        return out, new_offset

    def _iter_file(self) -> Iterator[dict]:
        if not os.path.exists(self.path):
            return
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


# ============================================================
# 运行记录
# ============================================================
@dataclass
class RunInfo:
    run_id: str
    goal: str
    status: str = "queued"          # queued|running|passed|failed|relaxed|cancelled|error
    created_at: str = field(default_factory=_now)
    started_at: str = ""
    finished_at: str = ""
    options: dict = field(default_factory=dict)
    phase: str = ""
    attempts: int = 0
    touched_files: list[str] = field(default_factory=list)
    commit: str | None = None
    rolled_back: bool = False
    error: str | None = None
    answer: str = ""
    report: dict | None = None
    summary: dict = field(default_factory=dict)
    event_count: int = 0
    demo: bool = False

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "RunInfo":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


class RunNotFound(KeyError):
    pass


# ============================================================
# 管理器
# ============================================================
class RunManager:
    """全局唯一实例（`run_manager()`）。运行状态跨请求存活。"""

    def __init__(self, root: str = RUNS_ROOT):
        self.root = os.path.abspath(root)
        os.makedirs(self.root, exist_ok=True)
        self._lock = threading.Lock()
        self._logs: dict[str, EventLog] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._cancel: dict[str, threading.Event] = {}
        self._mem: dict[str, RunInfo] = {}
        self._load_existing()

    # ---------- 磁盘布局 ----------
    def _dir(self, run_id: str) -> str:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in run_id)
        return os.path.join(self.root, safe)

    def _meta_path(self, run_id: str) -> str:
        return os.path.join(self._dir(run_id), "meta.json")

    def _log_path(self, run_id: str) -> str:
        return os.path.join(self._dir(run_id), "events.jsonl")

    def _log(self, run_id: str) -> EventLog:
        with self._lock:
            log = self._logs.get(run_id)
            if log is None:
                log = EventLog(self._log_path(run_id))
                self._logs[run_id] = log
            return log

    # ---------- 启动时恢复历史 ----------
    def _load_existing(self) -> None:
        if not os.path.isdir(self.root):
            return
        for name in os.listdir(self.root):
            path = os.path.join(self.root, name, "meta.json")
            if not os.path.isfile(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    info = RunInfo.from_dict(json.load(f))
            except (OSError, json.JSONDecodeError, TypeError):
                continue
            # 进程重启后，之前「正在跑」的运行已经不可能再跑了
            if not info.terminal:
                info.status = "cancelled"
                info.error = "服务重启，运行已中断"
                info.finished_at = info.finished_at or _now()
                self._write_meta(info)
            self._mem[info.run_id] = info

    # ---------- meta 读写 ----------
    def _write_meta(self, info: RunInfo) -> None:
        os.makedirs(self._dir(info.run_id), exist_ok=True)
        path = self._meta_path(info.run_id)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(info.to_dict(), f, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, path)

    def _save(self, info: RunInfo) -> None:
        with self._lock:
            info.event_count = self._logs[info.run_id].seq if info.run_id in self._logs else info.event_count
            self._mem[info.run_id] = info
        self._write_meta(info)

    # ---------- 查询 ----------
    def get(self, run_id: str) -> RunInfo | None:
        with self._lock:
            info = self._mem.get(run_id)
        if info is not None:
            return info
        path = self._meta_path(run_id)
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                info = RunInfo.from_dict(json.load(f))
        except (OSError, json.JSONDecodeError, TypeError):
            return None
        with self._lock:
            self._mem[run_id] = info
        return info

    def require(self, run_id: str) -> RunInfo:
        info = self.get(run_id)
        if info is None:
            raise RunNotFound(run_id)
        return info

    def list_runs(self, limit: int = 50) -> list[RunInfo]:
        items = list(self._mem.values())
        items.sort(key=lambda r: r.created_at, reverse=True)
        return items[: max(1, limit)]

    def events(self, run_id: str, after_seq: int = 0, limit: int = 2000) -> list[dict]:
        self.require(run_id)
        out = self._log(run_id).read_all(after_seq)
        return out[:limit]

    def tail(self, run_id: str, offset: int) -> tuple[list[dict], int]:
        self.require(run_id)
        return self._log(run_id).tail(offset)

    # ---------- 取消 ----------
    def cancel(self, run_id: str) -> tuple[bool, str]:
        info = self.get(run_id)
        if info is None:
            return False, "运行不存在"
        if info.terminal:
            return False, f"运行已处于终态: {info.status}"
        with self._lock:
            flag = self._cancel.setdefault(run_id, threading.Event())
        flag.set()
        self._log(run_id).append("cancel_requested", run_id=run_id)
        return True, "已请求取消；将在下一个进度点生效"

    def is_cancelled(self, run_id: str) -> bool:
        with self._lock:
            flag = self._cancel.get(run_id)
        return bool(flag and flag.is_set())

    # ---------- 启动 ----------
    def start(
        self,
        goal: str,
        verify_command: str | None = None,
        max_attempts: int = 2,
        on_decision: str = "auto",
        max_consecutive_failures: int = 2,
        session_id: str = "default",
        approval_base_url: str = "",
        demo: bool = False,
    ) -> RunInfo:
        run_id = _new_run_id()
        info = RunInfo(
            run_id=run_id,
            goal=goal,
            status="queued",
            options={
                "verify_command": verify_command or "",
                "max_attempts": max_attempts,
                "on_decision": on_decision,
                "max_consecutive_failures": max_consecutive_failures,
                "session_id": session_id,
                "approval_base_url": approval_base_url,
                "demo": demo,
            },
            demo=demo,
        )
        self._log(run_id).append(
            "queued", run_id=run_id, goal=goal, demo=demo,
            options=info.options,
        )
        self._save(info)

        with self._lock:
            self._cancel[run_id] = threading.Event()

        thread = threading.Thread(
            target=self._run_thread,
            args=(run_id,),
            name=f"agent-run-{run_id}",
            daemon=True,
        )
        with self._lock:
            self._threads[run_id] = thread
        thread.start()
        return info

    # ---------- 执行 ----------
    def _run_thread(self, run_id: str) -> None:
        info = self.require(run_id)
        log = self._log(run_id)
        info.status = "running"
        info.started_at = _now()
        self._save(info)

        def sink(kind: str, payload: dict) -> None:
            # 协作式取消：唯一的生效点，见模块 docstring
            if self.is_cancelled(run_id):
                raise RunCancelled(run_id)
            log.append(kind, run_id=run_id, **payload)

        token = bind_progress(sink)
        try:
            if info.demo:
                from .demo import run_demo_cycle

                summary = run_demo_cycle(sink, run_id=run_id, goal=info.goal)
                self._finish(
                    info,
                    status=summary.pop("status", "passed"),
                    phase=summary.get("phase") or "record",
                    attempts=summary.get("attempts") or 1,
                    touched_files=summary.get("touched_files") or [],
                    commit=summary.get("commit"),
                    rolled_back=bool(summary.get("rolled_back")),
                    error=summary.get("error"),
                    answer=summary.get("answer") or "",
                    report=summary.get("report"),
                    summary=summary.get("summary") or {},
                )
                return

            result = asyncio.run(self._execute(run_id, info, log))
            self._finish(info, **result)
        except RunCancelled:
            log.append("cancelled", run_id=run_id, message="已按请求取消本次运行")
            self._finish(info, status="cancelled", error="运行被取消",
                         summary={"cancelled": True})
        except Exception as e:  # 装配失败 / 模型不可用 → 如实报告，不假装成功
            import traceback

            detail = f"{type(e).__name__}: {e}"
            log.append("error", run_id=run_id, message=detail,
                       traceback=traceback.format_exc()[-2000:])
            self._finish(info, status="error", error=detail,
                         summary={"exception": type(e).__name__})
        finally:
            reset_progress(token)
            with self._lock:
                self._threads.pop(run_id, None)
            print(f"[run {run_id}] 结束: {info.status}", flush=True)

    async def _execute(self, run_id: str, info: RunInfo, log: EventLog) -> dict:
        from .actions import build_cycle

        options = info.options
        cycle = build_cycle(
            max_attempts=int(options.get("max_attempts") or 2),
            on_decision=str(options.get("on_decision") or "auto"),
            max_consecutive_failures=int(options.get("max_consecutive_failures") or 2),
            base_url=str(options.get("approval_base_url") or ""),
        )

        raw_verify = (options.get("verify_command") or "").strip()
        verify = VerifyCommand(command=raw_verify, reason="调用方指定的验证命令") if raw_verify else None

        # 注意：上游 CodingCycle.run 不接受 cycle_id（它自己生成）。
        # 前端按 run_id 订阅，事件里带的 cycle_id 是上游生成的——两者不同名，
        # 但都在事件流里，关联时按 run_id 找即可。
        report, memory = await cycle.run(info.goal, verify_command=verify)

        ok_count = sum(1 for r in memory.records if r.result.ok)
        summary = {
            "tasks_total": len(memory.records),
            "tasks_ok": ok_count,
            "tasks_failed": len(memory.records) - ok_count,
            "check_steps": len(report.check_steps or []),
            "tool_calls": sum(
                len(getattr(r.result, "artifacts", []) or []) for r in memory.records
            ),
        }

        status_map = {
            CyclePhase.RECORD.value: "passed",
            CyclePhase.FAILED.value: "failed",
        }
        status = status_map.get(report.phase.value, "failed")
        # 人工放宽验收：保留为独立终态，不要混进 passed
        if report.error and "放宽验收" in report.error:
            status = "relaxed"

        RunStore(str(options.get("session_id") or "default")).append_run(
            goal=info.goal,
            ok=status == "passed",
            answer=f"run={run_id} commit={report.commit}",
            records=memory.records,
        )

        return {
            "status": status,
            "phase": report.phase.value,
            "attempts": report.attempts,
            "touched_files": list(report.touched_files or []),
            "commit": report.commit,
            "rolled_back": report.rolled_back,
            "error": report.error,
            "answer": (
                f"cycle 通过校验，检查点 {report.commit}"
                if status == "passed"
                else (report.error or "cycle 未通过校验")
            ),
            "report": report.to_dict(),
            "summary": summary,
        }

    def _finish(self, info: RunInfo, **fields: Any) -> None:
        info.status = fields.get("status", info.status)
        info.finished_at = _now()
        for key in ("phase", "attempts", "touched_files", "commit",
                    "rolled_back", "error", "answer", "report", "summary"):
            if key in fields and fields[key] is not None:
                setattr(info, key, fields[key])
        # 事件数在关闭前刷新一次，前端拿到的计数才准确
        log = self._logs.get(info.run_id)
        if log is not None:
            info.event_count = log.seq
        info.touched_files = list(info.touched_files or [])
        info.summary = dict(info.summary or {})
        info.summary.setdefault("events", info.event_count)
        self._save(info)
        log = self._logs.get(info.run_id)
        if log is not None:
            # ★ P3（`TRANSPARENCY2-UI`）：把**结局四值 + 判据来源 + 审查独立性**
            #   一并放进 `run_end`。
            #
            #   为什么不让前端自己去翻报告：界面是**事件驱动**的，实时流与历史回放
            #   共用同一条路（`store/run.ts`）。放进报告而不放进事件，就会出现
            #   "实时看得到、回放看不到"这种最难查的差异。
            #
            #   字段名照抄上游 `core/outcome.py:89 build_verdict()` 与
            #   `core/cycle.py:145-146`（`outcome` / `outcome_reason` / `verdict`），
            #   **不改名、不重算** —— 前端只呈现，不做第二个体检口径。
            verdict = self._verdict_of(info)
            log.append(
                "run_end", run_id=info.run_id, status=info.status,
                phase=info.phase, attempts=info.attempts, error=info.error or "",
                commit=info.commit or "", rolled_back=info.rolled_back,
                touched_files=info.touched_files, summary=info.summary,
                **verdict,
            )

    @staticmethod
    def _verdict_of(info: RunInfo) -> dict:
        """从报告里取结局四值那一组事实（取不到就**什么都不加**）。

        `{}` 与"给个默认值"是**两件事**：字段缺席时前端显示「后端未产出」，
        而不是显示一个我编的 `fail`。所以这里绝不补默认值。
        """
        rep = info.report if isinstance(info.report, dict) else {}
        out: dict = {}
        verdict = rep.get("verdict")
        if isinstance(verdict, dict):
            for src, dst in (("outcome", "outcome"), ("outcome_kind", "outcome_kind"),
                             ("reason", "outcome_reason"),
                             ("criterion_source", "criterion_source"),
                             ("criterion_trust", "criterion_trust"),
                             ("criterion_independent", "criterion_independent"),
                             ("note", "outcome_note")):
                if verdict.get(src) is not None:
                    out[dst] = verdict[src]
        # 报告顶层的 `outcome` / `outcome_reason`（`core/cycle.py:145-146`）是同一件事，
        # 有的后端版本只填这两个 —— 缺 `verdict` 时补上。
        for key in ("outcome", "outcome_reason"):
            if key in rep and key not in out and rep[key] is not None:
                out[key] = rep[key]
        return out

    # ---------- 决策（供 SPA 内联作答） ----------
    def pending_decisions(self, run_id: str | None = None) -> list[dict]:
        mgr = DecisionManager()
        items = mgr.pending()
        out = []
        for d in items:
            if run_id and d.cycle_id != run_id:
                continue
            out.append({
                "id": d.id, "kind": d.kind, "cycle_id": d.cycle_id,
                "question": d.question, "context": d.context,
                "default": d.default, "created_at": d.created_at,
                "expires_at": d.expires_at, "status": d.status,
                "options": [o.to_dict() for o in d.options],
            })
        return out

    def answer_decision(self, decision_id: str, value: str, by: str = "webui") -> tuple[bool, str]:
        return DecisionManager().answer(decision_id, value, by=by)


# ============================================================
# 单例
# ============================================================
_manager: RunManager | None = None
_manager_lock = threading.Lock()


def run_manager() -> RunManager:
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = RunManager()
        return _manager
