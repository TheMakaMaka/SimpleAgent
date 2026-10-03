from dataclasses import dataclass, field
from typing import Optional

from .task import Artifact, Task, TaskResult


@dataclass
class MemoryRecord:
    task: Task
    result: TaskResult


class SharedMemory:
    """主循环唯一持有的全局状态。Worker 只能拿到一个只读快照。"""

    def __init__(self, goal: str):
        self.goal = goal
        self.records: list[MemoryRecord] = []
        self.artifacts: dict[str, Artifact] = {}
        self.facts: list[str] = []
        self._fp_count: dict[str, int] = {}
        # 验证结论回流：让主循环在循环内就能知道目标有没有达成
        self.verify_state: dict | None = None
        self._verified_fingerprint: str | None = None
        #: ★ 模型自拟的验收判据**被拒绝采纳**的原因（空串 = 当前没有这回事）。
        #:
        #: 为什么放在这里而不是 `OrchestratorResult` 上（`VERIFY-VACUOUS`）：
        #: 这个事实要同时被 ①cycle 层的事件与错误文案 ②诊断脚本 读到，
        #: 而 `OrchestratorResult` 有 6 个返回点，逐点携带容易漏一个就静默丢失
        #: （`bridge_gate_steps` 被 Pydantic 丢掉那次的教训）。
        #: 挂在"本次运行的记忆"上，写入点只有一处。
        #: 验证真的跑起来之后它会被清空（它回答的是"当下为什么没在验证"）。
        self.verify_untrusted: str = ""
        #: ★ **每一次**"自拟判据被拒"的留痕（只增不减，本 attempt 内不清空）。
        #:
        #: 与 `verify_untrusted` 的分工：后者是"当下"的状态（供错误文案用），
        #: 这个是**审计流水**。为什么不能只留最后一条 —— 实测那一轮里模型
        #: 先给坏判据被拒、换一版好判据才通过；如果成功时把留痕清掉，
        #: 事后就看不到"这次为什么多跑了两轮"，而那正是最有价值的信息。
        #: 事件只能由 `CodingCycle._emit` 发出，所以这里只存事实、由 cycle 层记录。
        self.verify_rejections: list[str] = []
        #: ★ **判据的演化**（`TRANSPARENCY-BACKEND` B1）：按发生顺序记下每一次
        #: 候选 / 采纳 / 拒绝 / 执行结果，每条自带 `previous_command` /
        #: `previous_passed`，因此"上一条失败了，这一条换成了什么"**不用按 seq 拼**。
        #:
        #: 为什么要有它：`verify_probe`（前端 bridge 发）只覆盖**被执行**的判据，
        #: 被拒的只有 `verify_skipped`，而**"这次换判据了、上一条是失败的"这件事
        #: 在事件流里根本读不出来** —— 实测那次 `passed` 就是这么发生的。
        #: 判据是"目标达成"的判据本身，它的变更必须和别的关键事实一样可审计。
        self.criterion_log: list[dict] = []
        #: ★ **每一轮的决策依据**（A1）：`reasoning` 与这一轮打算做什么。
        #: 原来它只出现在服务端日志里，事件流里没有 —— 前端无从显示"为什么"。
        self.decision_log: list[dict] = []
        # 结构化上下文回流：由程序从事件流压缩出的、带可信度标注的事实块。
        # 只存**渲染结果**，不存 Snapshot 对象——这样 SharedMemory 仍不依赖 compress，
        # 也让"注入什么"这件事只有一个来源（CodingCycle 决定，memory 只负责排版）。
        self.structured_context: str = ""
        self.structured_source: str = ""

    # ---------- 写 ----------
    def record(self, task: Task, result: TaskResult) -> None:
        self.records.append(MemoryRecord(task=task, result=result))
        for a in result.artifacts:
            self.artifacts[a.key] = a
        fp = task.fingerprint()
        self._fp_count[fp] = self._fp_count.get(fp, 0) + 1

    def add_fact(self, fact: str) -> None:
        if fact and fact not in self.facts:
            self.facts.append(fact)

    def count_fingerprint(self, task: Task) -> int:
        return self._fp_count.get(task.fingerprint(), 0)

    # ---------- 验证状态 ----------
    def set_verify(
        self,
        passed: bool,
        detail: str,
        command: str,
        fingerprint: str,
        source: str = "caller",
        artifact_hashes: dict | None = None,
        cwd: str = "",
        cache_cleared: int = 0,
        cache_warning: str = "",
        exit_code: int | None = None,
        expect_exit: int | None = None,
    ) -> None:
        """记录验证结论。

        `source` 是判据的**来源**（`caller` / `model`），只作事实留痕：
        「调用方给的判据」与「模型自拟的判据」可信度差很远，而在这之前
        外部**完全无法区分**（`VERIFY-VACUOUS` 建议 2：降级必须留痕）。
        它不参与判定 —— 判定只看退出码。

        ★ P6（`TRANSPARENCY3-BACKEND`）：`artifact_hashes` 是**这次判词所描述的
        那份产物**的内容哈希，`cwd` 是验证真正的工作目录。判词必须能与
        **最终交付产物**逐字对账 —— 对不上就是 `invalid`（读数无效），
        而不是 `fail`（模型不行）。

        ★ P17：`exit_code` 是**执行记录**（`check_and_run` 的真实退出码）。
        `pass` 的 `executed` 证据要求它非空 —— "有一条命令"不等于"真的执行过"，
        没有退出码的通过说明执行事实缺失（见 `core/evidence.py`）。
        """
        self.verify_state = {
            "passed": passed,
            "detail": detail,
            "command": command,
            "source": source or "",
            "artifact_hashes": dict(artifact_hashes or {}),
            "cwd": cwd or "",
            "cache_cleared": int(cache_cleared or 0),
            "cache_warning": cache_warning or "",
            # P17：执行事实（None = 没记录，**不拿 0 冒充**）
            "exit_code": None if exit_code is None else int(exit_code),
            "expect_exit": None if expect_exit is None else int(expect_exit),
        }
        self._verified_fingerprint = fingerprint

    def reject_verify(self, raw_verify: dict, why: str) -> None:
        """记下"模型自拟的验收判据不合格、已拒绝采纳"这条事实。

        与 `set_verify` 互斥：判据没被采纳 → 没有验证结论 → 走
        「未验证」的显式失败路径，而不是 `passed=True`。

        写两处（见 `__init__` 里的分工）：
          · `verify_untrusted`  —— 当下的原因，供 cycle 的错误文案直接引用；
          · `verify_rejections` —— 只增不减的审计流水，由 cycle 发成事件。
            每条都自带"不合格，已拒绝采纳"这句，因为它会**脱离上下文**
            出现在事件流里，必须自己能读懂。
        """
        cmd = str((raw_verify or {}).get("command") or "")
        detail = f"{why}；被拒命令: {cmd[:120]!r}" if cmd else why
        self.verify_untrusted = detail
        self.verify_rejections.append(
            f"模型自拟的验收判据不合格，已拒绝采纳（{detail}）"
        )

    # ---------- 判据演化（B1）----------
    def log_criterion(
        self,
        action: str,
        command: str,
        *,
        reason: str = "",
        passed: Optional[bool] = None,
        detail: str = "",
        source: str = "",
    ) -> None:
        """记一条判据演化。`action ∈ {adopted, rejected, executed}`。

        `previous_*` 由这里**自动补齐**（取上一条"被执行过"的判据）——
        调用点不必各自记状态，也就不会出现"某条路径忘了带前后关系"
        （`bridge_gate_steps` 被静默丢掉那次的教训：散在各处的事实容易漏）。
        """
        prev_cmd, prev_passed = "", None
        for item in reversed(self.criterion_log):
            if item.get("action") == "executed":
                prev_cmd = str(item.get("command") or "")
                prev_passed = item.get("passed")
                break
        self.criterion_log.append({
            "action": action,
            "command": str(command or "")[:500],
            "reason": str(reason or "")[:300],
            "passed": passed,
            "detail": str(detail or "")[:300],
            "source": source,
            "previous_command": prev_cmd[:500],
            "previous_passed": prev_passed,
        })

    # ---------- 决策依据（A1）----------
    def log_decision(self, round_no: int, data: dict) -> None:
        """记一轮编排器决策的**依据**（`reasoning` + 这一轮打算做什么）。"""
        tasks = []
        for t in (data or {}).get("tasks") or []:
            if not isinstance(t, dict):
                continue
            tasks.append({
                "id": str(t.get("id") or "")[:40],
                "description": str(t.get("description") or "")[:200],
                "expected_output": str(t.get("expected_output") or "")[:200],
            })
        self.decision_log.append({
            "round": int(round_no),
            "status": str((data or {}).get("status") or "continue")[:40],
            "reasoning": str((data or {}).get("reasoning") or "")[:600],
            "tasks": tasks[:3],
            "final_answer": str((data or {}).get("final_answer") or "")[:300],
        })

    def already_verified_at(self, fingerprint: str) -> bool:
        """同一状态是否已经验证过；未变化就不必重复验证。

        注意：判定必须同时要求「指纹相同」且「本次已得出过结论」。
        后者用于区分「本 attempt 内已验过」与「上一次 attempt 留下的陈旧结论」——
        新建的 SharedMemory 不应该继承上一轮的验证结果。
        """
        return bool(self.verify_state) and self._verified_fingerprint == fingerprint

    def verified_passed(self) -> bool:
        return bool(self.verify_state and self.verify_state.get("passed"))

    # ---------- 结构化上下文（派生视图，程序生成）----------
    def set_structured_context(self, text: str, source: str = "") -> None:
        """注入压缩快照渲染出的结构化事实块。

        `source` 只作诊断用（例如 "compress:cy_x/py"），不参与判定。
        空串表示"没有可用快照"，此时渲染层不输出该段——不输出空标题，
        避免模型把空段当成"上一轮什么都没发生"的证据。
        """
        self.structured_context = (text or "").strip()
        self.structured_source = source or ""

    # ---------- 读：给主循环 ----------
    def summary_for_orchestrator(
        self,
        char_budget: int | None = None,
        max_records: int | None = None,
    ) -> str:
        """把记忆渲染成给编排器的 prompt。

        两条纪律（都是修过的坑）：

        1. **验证结论放最前面，不放最后。**
           它决定编排器下一步行动（通过就 done、未通过就修）。
           放最后的话，一旦 prompt 被截断，最该看到的信息反而先丢。

        2. **按优先级 + 字符预算渲染，而不是按条数硬截断。**
           旧实现取"最近 12 条"，更早的重要记录会**静默消失**。
           现在按优先级填预算，并在截断时**明说丢了多少条**。

        预算来源：`ModelLimits.orchestrator_prompt_chars`（由 context_window 推导）。
        不传时用默认值，便于测试与离线调用。
        """
        budget = int(char_budget if char_budget is not None else 6000)
        out: list[str] = []

        def room() -> int:
            return max(0, budget - len("\n".join(out)))

        # ---------- 优先级 0：验证结论（永不省略）----------
        if self.verify_state:
            ok = self.verify_state.get("passed")
            out.append("【验证结论】")
            out.append(f"  结果: {'通过' if ok else '未通过'}")
            if self.verify_state.get("detail"):
                out.append(f"  细节: {self.verify_state['detail']}")
            out.append(f"  验证命令: {self.verify_state.get('command', '')}")
            out.append(
                "  → 目标已由验证命令确认达成，本轮必须返回 status=done，"
                "不要再规划任何新任务。"
                if ok else
                "  → 目标尚未达成，请针对上面的失败细节规划修复任务，"
                "不要重复已经做过且无效果的动作。"
            )
            out.append("")

        out.append(f"目标: {self.goal}")
        out.append("")

        # ---------- 优先级 0.5：结构化上下文（压缩快照，程序生成）----------
        # 位置在「验证结论」之后、「模型自述」之前：它比模型自述可信，
        # 但绝不能挤掉验证结论——所以给它的预算是**独立上限**，
        # 且被截断时必须写明，不静默丢。
        if self.structured_context and room() > 150:
            cap = max(200, min(budget // 3, 1500))
            block = self.structured_context
            truncated = len(block) > cap
            if truncated:
                block = block[:cap].rstrip()
            out.append("【结构化上下文】（程序从事件流提取，带可信度标注）")
            for line in block.splitlines():
                if room() < len(line) + 1:
                    truncated = True
                    break
                out.append(line)
            if truncated:
                out.append("  …（结构化上下文超出预算，已截断）")
            out.append("")

        # ---------- 优先级 1：失败任务（不要原样重试）----------
        failed = [r for r in self.records if not r.result.ok]
        if failed and room() > 120:
            out.append("失败任务（不要原样重试）:")
            for r in failed[-5:]:
                line = (f"  {r.task.id}: {r.task.description[:80]}"
                        f" -> {r.result.error}")
                if room() < len(line) + 1:
                    out.append("  …（失败记录较多，仅显示部分）")
                    break
                out.append(line)
            out.append("")

        # ---------- 优先级 2：关键事实 ----------
        if self.facts and room() > 80:
            out.append("关键事实:")
            for f in self.facts[-8:]:
                line = f"  - {f}"
                if room() < len(line) + 1:
                    break
                out.append(line)
            out.append("")

        # ---------- 优先级 3：已有产物 ----------
        if self.artifacts and room() > 80:
            out.append("已有产物:")
            for a in self.artifacts.values():
                line = f"  - {a.preview()}"
                if room() < len(line) + 1:
                    out.append("  …（产物较多，仅显示部分）")
                    break
                out.append(line)
            out.append("")

        # ---------- 优先级 4：已完成任务（最新优先）----------
        # 从最新往回填，保证"最近发生的事"一定在预算内
        done = list(self.records)
        shown = 0
        if done and room() > 120:
            limit = max_records if max_records is not None else len(done)
            out.append(f"已完成任务（共 {len(done)} 条，按时间倒序）:")
            for r in reversed(done):
                if shown >= limit:
                    break
                line = f"  {r.result.summary()}"
                if room() < len(line) + 1:
                    break
                out.append(line)
                shown += 1
            omitted = len(done) - shown
            if omitted > 0:
                # 明说丢了多少——旧实现是静默截断
                out.append(f"  …（省略较早的 {omitted} 条记录）")
            out.append("")

        # ---------- 兜底：预算在到达"已完成任务"前就被吃光 ----------
        # 这种情况最容易变成静默截断：任务记录一条都没进来，也没有任何提示。
        # 必须留下一个可见的截断标记。
        omitted_total = len(done) - shown
        if omitted_total > 0 and not any("省略较早的" in ln for ln in out):
            out.append(f"…（因 prompt 预算不足，省略了 {omitted_total} 条任务记录）")

        return "\n".join(out)

    def prompt_chars(self) -> int:
        """诊断用：当前渲染一次 prompt 的实际字符数。"""
        return len(self.summary_for_orchestrator())

    # ---------- 读：给子循环 ----------
    def context_for_worker(self, task: Task) -> str:
        if not task.context_refs:
            return "（无额外上下文）"

        parts = []
        for ref in task.context_refs:
            # 优先当 artifact 找
            if ref in self.artifacts:
                a = self.artifacts[ref]
                # file 类只给路径，不展开内容
                if a.kind == "file":
                    parts.append(
                        f"<artifact key='{ref}' kind='file' path='{a.path}'/>"
                    )
                else:
                    parts.append(f"<artifact key='{ref}' kind='{a.kind}'>")
                    if a.content:
                        parts.append(a.content)
                    elif a.path:
                        parts.append(f"(file: {a.path})")
                    parts.append("</artifact>")
                continue
            # 否则当 task_id 找
            for r in self.records:
                if r.task.id == ref:
                    parts.append(f"<task id='{ref}' ok='{r.result.ok}'>")
                    parts.append(r.result.output)
                    parts.append("</task>")
                    break
            else:
                parts.append(f"<missing ref='{ref}'/>")

        return "\n".join(parts)