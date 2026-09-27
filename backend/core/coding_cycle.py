"""一轮编码流程：把「规划 → 写码 → 检查 → 验证 → 记录」封成一个整体。

与旧流程的关键差异：
  - 验证结论**在编排循环内部**回流，主循环能立刻知道自己是否已经达成目标，
    不再盲目地重复制造"再验证一次"的任务。
  - check 阶段仍由程序在 cycle 层把门，语法不过关不允许进入 verify。
  - 每个 cycle 结束自动打检查点；未通过校验则回退，避免错误累积。
"""

from datetime import datetime
import os

from .checkpoint import WORKSPACE_DIR, CheckpointManager
from .context import (
    reset_cycle_files, reset_declared_files, set_cycle_files, set_declared_files,
)
from .cycle import PHASE_ORDER, CyclePhase, CycleReport, VerifyCommand
from .decisions import DecisionManager, FAILURE_OPTIONS, ROLLBACK_OPTIONS
from .notify import build_notifier
from .symbol_index import build_index
from .manifest import parse_declared
from .memory import SharedMemory
from .orchestrator import Orchestrator
from .pipeline import CheckPipeline
from .task import Artifact
from .worker import Worker
from storage.store import Event, Storage, default_storage


class CodingCycle:
    def __init__(
        self,
        orchestrator: Orchestrator,
        worker: Worker,
        pipeline: CheckPipeline | None = None,
        checkpoint_prefer: str = "git",
        max_attempts: int = 2,
        verbose: bool = True,
        storage: Storage | None = None,
        persist: bool = True,
        decisions: "DecisionManager | None" = None,
        notifier=None,
        approval_base_url: str = "",
        max_consecutive_failures: int = 2,
        on_decision: str = "auto",
    ):
        self.orchestrator = orchestrator
        self.worker = worker
        self.pipeline = pipeline or CheckPipeline()
        self.checkpoint = CheckpointManager(prefer=checkpoint_prefer)
        self.max_attempts = max(1, max_attempts)
        self.verbose = verbose
        # 事件持久化：默认开启。写入失败**绝不能**影响 cycle 成败，
        # 所以全部落在 self._emit 里兜住异常。
        self.persist = persist
        self.storage = (storage or default_storage()) if persist else None

        # ---------- 人工决策 ----------
        # on_decision: auto   = 命中决策点时自动选保守动作（旧行为，测试友好）
        #              notify = 命中时落盘 + 推送，然后自动选保守动作
        #              wait   = 命中时落盘 + 推送，并**阻塞等待**人工作答
        self.on_decision = on_decision
        self.decisions = decisions or DecisionManager()
        self.notifier = notifier or build_notifier()
        self.approval_base_url = approval_base_url.rstrip("/")
        self.max_consecutive_failures = max(1, int(max_consecutive_failures))
        self._consecutive_failures = 0

        # 本次 cycle 之前 workspace 里已存在的文件；用于区分「目标文件」与历史文件
        self._prior_files: list[str] = []

        # 当前 cycle_id：结构化上下文压缩需要按 cycle 分组事件
        self._current_cycle_id: str = ""

    # ---------- 事件 ----------
    def _emit(self, event_kind: str, cycle_id: str, goal: str = "", **payload) -> None:
        """所有 cycle 级事件的**唯一**汇聚点。

        ⚠️ **参数名即接口**（实测踩过大坑，见 `docs/CHANGELOG.md` §29）：
        前端 bridge 用 `install()` 把本方法替换成一个同签名的包装器来挂钩子，
        而它的包装器把第一个参数也叫 `kind`。于是只要**某个 payload 键与参数同名**，
        调用点就会在**绑定参数阶段**抛
        `TypeError: _emit() got multiple values for argument 'kind'` ——
        连函数体都进不去。

        现状：`payload` 里**禁止**出现 `kind` / `cycle_id`；
        `goal` 是唯一被允许的（它是签名里的记录字段，不是 payload 键）。
        这条由 `tests/unit/test_frontend_contract.py` 用 AST 扫全部调用点守着。

        第一个参数刻意叫 `event_kind` 而不是 `kind`：这样即使将来 payload 里
        真出现 `kind`，**我这侧**也不会撞（但包装器仍会，所以那条禁令仍然有效）。
        """
        if not self.storage:
            return
        try:
            self.storage.append_event(
                Event(kind=event_kind, cycle_id=cycle_id, goal=goal, payload=payload)
            )
        except Exception as e:
            # 存储是旁路，绝不能因为它让 cycle 失败
            self._log(f"[storage] 写入事件失败（已忽略）: {e}")

    def _emit_snapshot(self, cycle_id: str, goal: str) -> None:
        """cycle 结束后压缩并保存快照。压缩是纯函数，不经过模型。"""
        if not self.storage:
            return
        try:
            from .compress import reduce_cycle

            events = self.storage.get_events()
            snap = reduce_cycle(events, cycle_id)
            snap.cycle_id = cycle_id
            snap.goal = goal
            self.storage.save_snapshot(cycle_id, snap.to_dict())
        except Exception as e:
            self._log(f"[storage] 压缩快照失败（已忽略）: {e}")

    # ---------- 人工决策 ----------
    def _build_context(self, report: CycleReport, goal: str, extra: dict | None = None) -> dict:
        """给审批页的结构化上下文。

        复用我们已经做好的东西：manifest 的声明/实际、验证失败细节、
        事件流压缩出的失败记录。这样手机上看到的是**结构化事实**，
        不是一句含糊的"失败了"。
        """
        ctx: dict = {
            "goal": goal,
            "cycle_id": report.cycle_id,
            "attempt": report.attempts,
            "phase": report.phase.value,
            "error": report.error or "",
            "touched": list(report.touched_files or []),
        }
        m = report.manifest or {}
        if m:
            ctx["declared"] = [d.get("path") for d in (m.get("declared") or [])]
            ctx["violations"] = [
                {"kind": v.get("kind"), "path": v.get("path") or v.get("from"),
                 "message": v.get("message")}
                for v in (m.get("violations") or [])[:6]
            ]
        v = report.verify or {}
        if v:
            ctx["verify"] = {"passed": v.get("passed"), "detail": str(v.get("detail") or "")[:300]}
        if extra:
            ctx.update(extra)
        return ctx

    def _ask(
        self,
        kind: str,
        report: CycleReport,
        goal: str,
        question: str,
        options: list,
        default: str,
        extra: dict | None = None,
    ) -> str:
        """开一个决策点并等待作答。

        返回最终生效的动作。无论配置如何，**本方法不会抛异常**，
        也永远不会让流程无限期挂死（notify 失败即不等待）。
        """
        decision = self.decisions.open(
            kind=kind,
            cycle_id=report.cycle_id,
            question=question,
            options=options,
            context=self._build_context(report, goal, extra),
            default=default,
        )
        self._emit(
            "decision_opened", report.cycle_id, goal=goal,
            decision_id=decision.id, decision_kind=kind, question=question,
            options=[o.value for o in options], default=default,
        )
        self._log(f"[决策] 已挂起待人工决策: {decision.id} — {question}")

        if self.on_decision == "auto":
            # 旧行为：不推送、不等待，直接采用保守默认动作（测试友好）
            return default

        link = f"{self.approval_base_url}/decisions/{decision.id}" \
            if self.approval_base_url else f"/decisions/{decision.id}"
        result = self.notifier.send(decision, link)
        self._emit(
            "decision_notified", report.cycle_id, goal=goal,
            decision_id=decision.id, channel=result.channel, ok=result.ok,
            detail=result.detail,
        )
        self._log(
            f"[决策] 推送通道={result.channel} ok={result.ok} "
            f"{('· ' + result.detail) if result.detail else ''}"
        )

        if not result.ok:
            # 推不出去就没人会作答，**不能等**——否则流程挂死
            self._log("[决策] 推送失败，采用保守默认动作，不阻塞流程")
            return decision.resolve_effective()

        if self.on_decision != "wait":
            self._log("[决策] on_decision != wait，采用保守默认动作")
            return decision.resolve_effective()

        self._wait_for_answer(decision)
        return decision.resolve_effective()

    def _wait_for_answer(self, decision, poll_seconds: float = 2.0) -> None:
        """阻塞等待人工作答，直到作答或超时。

        用文件轮询而不是内存 Future，是为了让**另一个进程**（Web 服务）
        也能写入作答——这样 CLI 跑 cycle、手机通过 Web 作答也能成立。
        """
        import time
        from datetime import datetime

        deadline = None
        if decision.expires_at:
            try:
                deadline = datetime.fromisoformat(decision.expires_at)
            except ValueError:
                deadline = None

        self._log(
            f"[决策] 等待作答中（{self.approval_base_url or '本地'}"
            f"/decisions/{decision.id}）…"
        )
        while True:
            current = self.decisions.get(decision.id)
            if current is None:
                return
            if current.status != "pending":
                # 已回答 / 已超时：把结果同步回本地对象
                decision.status = current.status
                decision.answer = current.answer
                decision.answered_by = current.answered_by
                decision.answered_at = current.answered_at
                self._log(f"[决策] 收到结果: {current.status} -> {current.answer or '(无)'}")
                return
            if deadline and deadline < datetime.now():
                self.decisions.sweep_expired()
                continue
            time.sleep(poll_seconds)

    def _maybe_ask_on_failure(self, report: CycleReport, goal: str) -> str:
        """连续失败达阈值时开决策点。返回 'retry' | 'relax' | 'stop'。"""
        self._consecutive_failures += 1
        if self._consecutive_failures < self.max_consecutive_failures:
            return "retry"
        self._log(
            f"[决策] 连续失败 {self._consecutive_failures} 次"
            f"（阈值 {self.max_consecutive_failures}），转人工"
        )
        self._consecutive_failures = 0
        action = self._ask(
            kind="repeated_failure",
            report=report,
            goal=goal,
            question=f"验证连续失败 {self.max_consecutive_failures} 次，如何继续？",
            options=FAILURE_OPTIONS,
            default="stop",
            extra={"consecutive_failures": self.max_consecutive_failures},
        )
        return action if action in {"retry", "relax", "stop"} else "stop"

    def _confirm_rollback(self, report: CycleReport, goal: str, base_ref: str | None) -> bool:
        """回退会覆盖已有文件，先问一次。返回是否允许回退。"""
        if not base_ref:
            return False
        action = self._ask(
            kind="risky_rollback",
            report=report,
            goal=goal,
            question="即将回退，会丢弃本次改动，是否允许？",
            options=ROLLBACK_OPTIONS,
            default="abort",
            extra={"rollback_to": base_ref},
        )
        return action == "allow"

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg, flush=True)

    # ---------- 主入口 ----------
    async def run(
        self,
        goal: str,
        verify_command: VerifyCommand | None = None,
    ) -> tuple[CycleReport, SharedMemory]:
        cycle_id = f"cy_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        self._current_cycle_id = cycle_id
        report = CycleReport(cycle_id=cycle_id, goal=goal)

        self._log(
            f"\n########## CodingCycle {cycle_id} 开始 "
            f"(checkpoint 后端: {self.checkpoint.name}) ##########"
        )
        if self.checkpoint.name == "none":
            self._log("[警告] 无可用检查点后端，本次运行无法回退。")

        # 基线检查点：回退的锚点
        base_ckpt = self.checkpoint.commit(f"[cycle {cycle_id}] baseline")
        base_ref = base_ckpt.ref if base_ckpt else None

        # ★ 结构性修复（`FIX-VERIFY-WIRING`）：**无条件**注入，不再依赖"调用方给没给 verify"。
        #
        # 原来这里是 `if verify_command is not None:` —— 于是 `_setup_orchestrator`
        # 只在调用方自带验收命令时才被调用。它不是只做一件事，而是注入**三样**：
        #   ① `pipeline`          → 循环内验证回流
        #   ② `verify_command`    → 调用方权威（`None` 即"调用方没给"）
        #   ③ `context_provider`  → 结构化上下文回流
        # 所以那个 `if` 让 ①③ **在生产路径上静默失效**：
        # 真实用户目标（不带 verify_command）永远不执行验证，最后还报
        # 「缺少可机器判定的验证命令」—— 而模型**已经把命令拟好了**。
        # 详见 `docs/EVALUATION-FIX-VERIFY-WIRING.md`。
        self._setup_orchestrator(verify_command)
        if verify_command is not None:
            self._log(f"[verify] 使用调用方指定的验证命令: {verify_command.label()}")

        # 记录 cycle 开始前已存在的文件，并据此判定本轮的目标文件
        self._snapshot_prior_files()

        # `code_dir` / `code_fingerprint`：**这一次到底跑的是哪一份上游代码**。
        # 实测事故（CHANGELOG §31）：用户反复失败而修复没生效，定位只能靠
        # traceback 恰好带了路径 —— 因为运行记录里根本没有这个事实。
        # 现在每次运行的第一个事件就自报代码身份，可逐字比对（含内容级指纹）。
        from .identity import describe as _code_identity

        _code = _code_identity()
        self._emit("cycle_start", cycle_id, goal=goal,
                   backend=self.checkpoint.name, prior_files=self._prior_files,
                   code_dir=_code["code_dir"],
                   code_fingerprint=_code["fingerprint"])

        memory: SharedMemory | None = None

        for attempt in range(1, self.max_attempts + 1):
            report.attempts = attempt
            report.enter(CyclePhase.PLAN)

            attempt_goal = goal
            if attempt > 1:
                attempt_goal = self._retry_goal(goal, report)

            self._log(f"\n----- 第 {attempt}/{self.max_attempts} 次尝试 -----")

            orchestrator = self.orchestrator
            # 每次尝试前重设：保证 verify 命令与文件清单在该次尝试内稳定。
            # **无条件**调用（同上面的结构性修复）——不再看 verify_command 是否为空。
            orchestrator = self._setup_orchestrator(verify_command)

            token = set_cycle_files(self._prior_files)
            declared_token = set_declared_files(None)
            try:
                orch_result = await orchestrator.run(attempt_goal)
            finally:
                reset_cycle_files(token)
                reset_declared_files(declared_token)

            memory = orch_result.memory
            self._log(
                f"[plan] ok={orch_result.ok} tasks={len(memory.records)} "
                f"answer={orch_result.answer[:80]!r}"
            )

            # ★ 验证被跳过（`FIX-VERIFY-WIRING` 附 1）：把"跳过"变成**可见事件**。
            # 原来 `pipeline is None` 时整块静默跳过，上层只能猜 ——
            # 于是猜成「缺少验证命令」，把定位带偏了整整一轮。
            #
            # 第二条来源（`VERIFY-VACUOUS`）：模型自拟的验收判据**不合格被拒**
            # （没引用任何交付物 / 本轮没有交付物）→ 那条命令同样没被执行。
            # **每一条都单独留痕**：实测那一轮里模型先给坏判据被拒、
            # 换一版好判据才通过 —— 只留最后一条的话，事后就看不出
            # "这次为什么多跑了两轮"，而那正是最有价值的信息。
            skip_reason = getattr(orch_result, "verify_skipped", "")
            if skip_reason:
                self._emit("verify_skipped", cycle_id, goal=goal,
                           reason=skip_reason[:600],
                           command=str((orch_result.verify_command or {}).get("command", ""))[:200])
            for rejected in (getattr(memory, "verify_rejections", None) or []) if memory else []:
                self._emit("verify_skipped", cycle_id, goal=goal,
                           reason=str(rejected)[:600], command="")

            # 计划事件：声明清单 + 验证命令（意图，不是现实）
            declared = []
            for d in parse_declared(orch_result.declared_files):
                declared.append({"path": d.path, "role": d.role, "symbols": d.symbols})
            verify_cmd = ""
            if verify_command is not None:
                verify_cmd = verify_command.command
            else:
                vc = (orch_result.verify_command or {}).get("command", "")
                verify_cmd = vc
            self._emit(
                "plan", cycle_id, goal=goal, attempt=attempt,
                declared=declared, verify_command=verify_cmd,
                tasks=len(memory.records),
                # 计划里的"意图"（含 expected_output）。它是**声明**不是现实，
                # 压缩时只能标 declared，不能作为判据。
                intent=[
                    {
                        "id": rec.task.id,
                        "description": (rec.task.description or "")[:120],
                        "expected_output": (rec.task.expected_output or "")[:120],
                    }
                    for rec in memory.records
                ],
            )

            # 任务结果事件（模型自述 → 在压缩里只能作为 assumed）
            for rec in memory.records:
                self._emit(
                    "task_result", cycle_id, goal=goal,
                    task_id=rec.task.id,
                    description=rec.task.description[:200],
                    ok=bool(rec.result.ok),
                    output=(rec.result.output or "")[:300],
                    error=(rec.result.error or "")[:200] if rec.result.error else "",
                )

            if not memory.records:
                report.error = "本轮没有产生任何任务执行记录"
                report.enter(CyclePhase.FAILED)
                self._emit("cycle_end", cycle_id, goal=goal,
                           status="failed", error=report.error, attempt=attempt)
                continue

            # 进入 WRITE 阶段：模型已落盘实现（编排器内部完成），本阶段结束
            report.enter(CyclePhase.WRITE)
            touched = self._new_file_artifacts(memory)
            report.touched_files = touched

            # ---------- 文件清单校验（先于静态检查）----------
            mtoken = set_declared_files(orch_result.declared_files)
            try:
                manifest = self.pipeline.run_manifest()
            finally:
                reset_declared_files(mtoken)

            report.manifest = manifest.to_dict()
            self._emit(
                "manifest", cycle_id, goal=goal,
                checked=manifest.checked, passed=manifest.passed,
                violations=manifest.violations,
                actual_files=manifest.actual,
            )
            self._log(
                f"[manifest] checked={manifest.checked} passed={manifest.passed} "
                f"declared={len(manifest.declared)} actual={len(manifest.actual)} "
                f"violations={len(manifest.violations)}"
            )
            if manifest.checked and not manifest.passed:
                report.error = self._manifest_error_text(manifest)
                report.enter(CyclePhase.FAILED)
                self._log(f"[manifest] 交付缺口: {report.error[:200]}")
                self._emit("cycle_end", cycle_id, goal=goal, status="failed",
                           error=report.error, attempt=attempt)
                if attempt < self.max_attempts:
                    self._rollback_after_confirm(base_ref, report, goal)
                continue

            # ---------- 程序驱动的 check 阶段 ----------
            report.enter(CyclePhase.CHECK)

            check = await self.pipeline.run_check(touched)
            report.check_steps = check["steps"]
            # ★ 「没东西可查」必须与「查过并通过」可区分（`VERIFY-VACUOUS` 建议 4）。
            # 原来只报 `passed=True steps=0`，两者同形 —— 实测被读成绿灯，
            # 而那一轮其实什么都没查（三个绿灯叠在一起 = 什么都没干）。
            report.check = {
                "checked": bool(check.get("checked", bool(check["steps"]))),
                "passed": bool(check["passed"]),
                "status": check.get("status")
                          or ("passed" if check["passed"] else "failed"),
                "skipped_reason": check.get("skipped_reason") or "",
            }
            self._emit_check_steps(cycle_id, goal, check)
            self._log(
                f"[check] checked={report.check['checked']} "
                f"status={report.check['status']} steps={len(check['steps'])}"
                + (f" blocking={check['blocking_file']}" if check["blocking_file"] else "")
                + (f" ({check['skipped_reason']})" if check.get("skipped_reason") else "")
            )
            if not check["passed"]:
                report.error = self._check_error_text(check)
                report.enter(CyclePhase.FAILED)
                self._emit("cycle_end", cycle_id, goal=goal, status="failed",
                           error=report.error, attempt=attempt)
                if attempt < self.max_attempts:
                    self._rollback_after_confirm(base_ref, report, goal)
                continue

            # ---------- 验证结论 ----------
            report.enter(CyclePhase.VERIFY)
            if memory.verify_state is None:
                # ★ 三种情况**必须分开说**（`FIX-VERIFY-WIRING` 附 2 分出了前两种，
                # `VERIFY-VACUOUS` 又分出第三种）。它们的修法完全不同：
                #   ① 判据不合格被拒（自拟命令不引用任何交付物）→ 换判据
                #   ② 有命令但没执行（没 pipeline）              → 修接线
                #   ③ 压根没有命令                                → 加判据
                untrusted = getattr(memory, "verify_untrusted", "")
                if untrusted:
                    report.error = (
                        f"模型自拟的验收判据**不合格，已拒绝采纳**：{untrusted}。"
                        "这与「缺少验证命令」不是一回事 —— 命令是有的，"
                        "但它不引用本轮任何交付物，等于恒真（print('PASS') 就能过）。"
                        "下一轮请给出**引用交付物**的判据"
                        "（如 assert os.path.exists('report.txt')、"
                        "import add; assert add.add(1,2)==3）。"
                    )
                elif (orch_result.verify_command or {}).get("command"):
                    report.error = (
                        "已拟出验证命令但**未执行**（verify_state 为空）："
                        f"{str((orch_result.verify_command or {}).get('command'))[:80]!r}。"
                        "原因通常是主循环没有 pipeline（见 FIX-VERIFY-WIRING），"
                        "不是缺少命令。"
                    )
                else:
                    report.error = (
                        "缺少可机器判定的验证命令（verify_command），"
                        "无法确认目标是否达成，不判定为成功。"
                    )
                self._log(f"[verify] 拒绝通过：{report.error}")
                report.enter(CyclePhase.FAILED)
                self._emit("cycle_end", cycle_id, goal=goal, status="failed",
                           error=report.error, attempt=attempt)
                if attempt < self.max_attempts:
                    self._rollback_after_confirm(base_ref, report, goal)
                continue

            report.verify = {
                "passed": memory.verify_state.get("passed"),
                "detail": memory.verify_state.get("detail"),
                "command": memory.verify_state.get("command"),
                # ★ 判据来源（`VERIFY-VACUOUS` 建议 2）：caller = 调用方给的权威判据，
                # model = 模型自拟（已经过可采性下限）。两者可信度差很远，
                # 而在这之前外部**完全无法区分**。
                "source": memory.verify_state.get("source", ""),
            }
            self._log(
                f"[verify] passed={report.verify['passed']} "
                f"source={report.verify['source'] or '(未知)'} "
                f"detail={str(report.verify.get('detail'))[:120]}"
            )
            self._emit(
                "verify", cycle_id, goal=goal,
                passed=bool(report.verify["passed"]),
                detail=str(report.verify.get("detail") or "")[:300],
                command=str(report.verify.get("command") or "")[:500],
                source=report.verify["source"],
            )

            if not report.verify["passed"]:
                report.error = f"验证未通过: {report.verify.get('detail')}"
                report.enter(CyclePhase.FAILED)
                self._emit("cycle_end", cycle_id, goal=goal, status="failed",
                           error=report.error, attempt=attempt)
                # 连续失败达阈值 → 转人工决策（这是最该停的一处）
                action = self._maybe_ask_on_failure(report, goal)
                self._emit("decision_action", cycle_id, goal=goal, action=action)
                if action == "stop":
                    self._log("[决策] 人工选择停止本轮")
                    break
                if action == "relax":
                    # 放宽验收：不做回退，直接按"未验证通过"记录并结束
                    report.error = (
                        f"人工放宽验收（验证未通过: {report.verify.get('detail')}）"
                    )
                    self._log("[决策] 人工放宽验收，跳过验证门禁")
                    self._emit("cycle_end", cycle_id, goal=goal, status="relaxed",
                               error=report.error, attempt=attempt)
                    break
                if attempt < self.max_attempts:
                    self._rollback_after_confirm(base_ref, report, goal)
                continue

            # ---------- 记录 ----------
            report.enter(CyclePhase.RECORD)
            # 成功即重置连续失败计数，避免多次成功的尝试被历史失败拖累
            self._consecutive_failures = 0
            ckpt = self.checkpoint.commit(
                f"[cycle {cycle_id}] {goal[:60]} (attempt {attempt})"
            )
            report.commit = ckpt.ref if ckpt else None
            # 成功时清空失败痕迹，避免对外报告里残留上一次尝试的状态
            report.error = None
            report.rolled_back = False
            self._log(f"[record] 检查点={report.commit} 文件={len(touched)}")
            self._emit("cycle_end", cycle_id, goal=goal, status="passed",
                       commit=report.commit or "", attempt=attempt)
            self._emit_snapshot(cycle_id, goal)
            return report, memory

        self._log(f"\n[结果] cycle 未通过校验: {report.error}")
        self._emit_snapshot(cycle_id, goal)
        return report, memory if memory is not None else SharedMemory(goal=goal)

    # ---------- 内部 ----------
    def _setup_orchestrator(self, verify_command: VerifyCommand | None) -> Orchestrator:
        """把验证命令和流水线交给主循环，让它在循环内做验证回流。

        ★ 现在**无条件**被调用（`FIX-VERIFY-WIRING` 的结构性修复）——
        因为它注入的不止验证命令，还有 `pipeline` 与 `context_provider`。

        ⚠️ 一条**必须小心**的语义：调用方**没**给 `verify_command` 时，
        **不要**把 `orchestrator.verify_command` 清成 `None` ——
        那会覆盖编排器**自带的**命令（`SkillRunner` 就把技能里烘焙的
        `verify_command` 放在这个属性上）。原来的代码只在"调用方给了"时才会
        走到这里，所以那条 `else None` 从未伤到谁；改成无条件调用后，
        它会立刻把 SkillRunner 的命令抹掉（实测：`test_skills.py` 当场报
        `'NoneType' object has no attribute 'get'`）。
        """
        self.orchestrator.pipeline = self.pipeline
        if verify_command is not None:
            # 调用方给的验收标准是权威的 —— 每次尝试前重设，保证该次尝试内稳定
            self.orchestrator.verify_command = {
                "command": verify_command.command,
                "reason": verify_command.reason,
            }
        # verify_command 为 None 时**保留原值**：那是"调用方没给"，
        # 不是"把已有的清掉"。主循环会据此采纳模型自拟的 verify。
        # 结构化上下文回流：主循环每轮决策前从事件流重算（压缩是纯函数）
        self.orchestrator.context_provider = self._structured_context
        return self.orchestrator

    def _structured_context(self) -> tuple[str, str]:
        """把事件流压缩成给编排器的结构化事实块。

        为什么放在这一层：压缩（`core/compress.py`）是纯函数，事件流在 storage 里，
        只有 CodingCycle 同时握着这两样东西。主循环拿到的只是一个字符串。

        只喂**与本 cycle 及之前轮次有关**的事件；同一 cycle 的各次 attempt 共享
        cycle_id，所以第 2 次 attempt 能看到第 1 次的实测失败（syntax/lint/manifest/verify），
        而不只是 `_retry_goal` 里那句自然语言。

        例外处理：任何异常都返回空串（旁路），并把原因写进日志。
        """
        from .compress import cross_cycle_failures, reduce_all, reduce_cycle

        if not self.storage:
            return "", ""
        try:
            events = self.storage.get_events()
        except Exception as e:  # noqa: BLE001
            self._log(f"[compress] 读取事件失败（结构化上下文留空）: {e}")
            return "", ""
        if not events:
            return "", ""

        try:
            parts: list[str] = []
            current_id = self._current_cycle_id
            if current_id:
                snap = reduce_cycle(events, current_id)
                # attempt==0 且无任何事实时不必输出（首轮刚开始，块是空的）
                if snap.facts or snap.files or snap.failures:
                    parts.append(snap.to_prompt())

            # 跨轮反复失败：同一 reason_hash 在多轮出现 → 系统性问题
            snapshots = reduce_all(events, limit_cycles=8)
            recurring = cross_cycle_failures(snapshots, min_count=2)
            if recurring:
                lines = ["跨轮反复失败（同一原因在多轮出现，属系统性问题，先修根因）:"]
                for item in recurring[:3]:
                    cycles = len(item["cycles"])
                    lines.append(
                        f"  - ×{item['total']}（{cycles} 轮）: {str(item['reason'])[:120]}"
                    )
                parts.append("\n".join(lines))

            body = "\n\n".join(p for p in parts if p.strip())
            source = f"compress:{current_id or '-'}/prev{len(snapshots)}"
            return body, source
        except Exception as e:  # noqa: BLE001
            self._log(f"[compress] 结构化上下文构建失败（已忽略）: {e}")
            return "", ""

    # 本次 cycle 之前 workspace 里已存在的文件；用于区分「目标文件」与历史文件
    def _snapshot_prior_files(self) -> None:
        files: list[str] = []
        for root, dirs, names in os.walk(WORKSPACE_DIR):
            dirs[:] = [d for d in dirs if d not in ("_tmp", "_debug", "__pycache__", ".git")]
            for n in names:
                if n.endswith(".pyc") or n == ".gitignore":
                    continue
                rel = os.path.relpath(os.path.join(root, n), WORKSPACE_DIR).replace("\\", "/")
                files.append(rel)
        self._prior_files = sorted(files)

    def _rollback(self, base_ref: str | None, report: CycleReport) -> None:
        if not base_ref:
            self._log("[rollback] 无基线检查点，跳过回退")
            return
        ok = self.checkpoint.rollback(base_ref)
        report.rolled_back = ok
        self._log(f"[rollback] 已回退到 {base_ref}: {ok}")

    def _rollback_after_confirm(
        self, base_ref: str | None, report: CycleReport, goal: str
    ) -> None:
        """回退前先征求确认——覆盖已有文件属于有风险动作。

        确认被拒（或超时）时不回退，保留现场继续重试。
        无基线检查点时无需确认（没有东西可回退）。
        """
        if not base_ref:
            return
        if not self._confirm_rollback(report, goal, base_ref):
            self._log("[决策] 未获准回退，保留当前改动")
            self._emit("rollback_denied", report.cycle_id, goal=goal, ref=base_ref)
            return
        self._rollback(base_ref, report)

    @staticmethod
    def _new_file_artifacts(memory: SharedMemory) -> list[str]:
        """只取真正由 write_file 产出、且非代码片段的文件产物。"""
        paths: list[str] = []
        for a in memory.artifacts.values():
            if not isinstance(a, Artifact):
                continue
            if a.kind != "file" or not a.path:
                continue
            norm = a.path.replace("\\", "/")
            if norm not in paths:
                paths.append(norm)
        return paths

    def _emit_check_steps(self, cycle_id: str, goal: str, check: dict) -> None:
        """把 check 步骤映射成语义化事件。

        语法与 lint 分开记，因为 lint 的 `skipped` 必须与「通过」区分开——
        这条以前踩过坑（skipped 被当成通过，产生假阴性）。
        """
        for step in check.get("steps") or []:
            tool = step.get("tool")
            parsed = step.get("parsed") or {}
            if tool == "check_syntax":
                self._emit(
                    "syntax", cycle_id, goal=goal,
                    path=step.get("file", ""),
                    ok=bool(step.get("passed")),
                    message=str(parsed.get("message") or parsed.get("raw") or "")[:200],
                )
            elif tool == "run_lint":
                status = step.get("status") or ("passed" if step.get("passed") else "failed")
                self._emit(
                    "lint", cycle_id, goal=goal,
                    path=step.get("file", ""),
                    status=status,
                    # skipped 时把原因带上，压缩层会渲染成「lint 未执行（原因）」
                    reason=str(parsed.get("skipped") or parsed.get("note") or "")[:120],
                    issues=parsed.get("issues") or [],
                )

    @staticmethod
    def _manifest_error_text(manifest) -> str:
        """把交付缺口转成一句可执行的重试提示。"""
        parts = []
        for v in manifest.blocking[:3]:
            if v.get("kind") == "declared-missing":
                msg = f"计划要产出 {v.get('path')}，但文件不存在"
            elif v.get("kind") == "symbol-missing":
                msg = f"{v.get('path')} 缺少符号: {', '.join(v.get('missing') or [])}"
            elif v.get("kind") == "declared-broken":
                msg = f"{v.get('path')} 无法解析: {v.get('message')}"
            else:
                msg = v.get("message", "")
            parts.append(msg)
        head = "；".join(parts) or "文件清单未通过"
        return f"交付清单不完整: {head}"

    @staticmethod
    def _check_error_text(check: dict) -> str:
        blocking = check.get("blocking_file") or "(未知文件)"
        detail = ""
        for step in reversed(check.get("steps") or []):
            if not step.get("passed"):
                parsed = step.get("parsed") or {}
                detail = parsed.get("message") or parsed.get("raw") or ""
                break
        return f"静态检查未通过: {blocking} {detail}".strip()

    def _retry_goal(self, goal: str, report: CycleReport) -> str:
        """重试时把失败原因结构化地注入，避免模型原样再撞一次。"""
        prev = report.error or "(无细节)"
        lines = [
            goal,
            "",
            "【重要：上一次尝试失败了，以下是失败原因，不要重复同样的做法】",
            f"- 失败原因: {prev}",
        ]
        if report.touched_files:
            lines.append(f"- 上次涉及文件: {', '.join(report.touched_files)}")
        if report.manifest and report.manifest.get("violations"):
            lines.append("- 上次的文件清单校验未通过，缺口如下:")
            for v in (report.manifest.get("violations") or [])[:5]:
                lines.append(
                    f"    · {v.get('kind')}: {v.get('path') or v.get('from') or ''} "
                    f"{v.get('message', '')}"
                )
        if report.rolled_back:
            lines.append("- 上次的改动已被回退，工作区已恢复到失败前的状态。")
        lines.append("- 请换一种实现思路或先修正根因，不要提交与上次相同的代码。")
        return "\n".join(lines)
