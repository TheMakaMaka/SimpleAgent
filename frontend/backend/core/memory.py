from dataclasses import dataclass, field

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
    def set_verify(self, passed: bool, detail: str, command: str, fingerprint: str) -> None:
        self.verify_state = {
            "passed": passed,
            "detail": detail,
            "command": command,
        }
        self._verified_fingerprint = fingerprint

    def already_verified_at(self, fingerprint: str) -> bool:
        """同一状态是否已经验证过；未变化就不必重复验证。

        注意：判定必须同时要求「指纹相同」且「本次已得出过结论」。
        后者用于区分「本 attempt 内已验过」与「上一次 attempt 留下的陈旧结论」——
        新建的 SharedMemory 不应该继承上一轮的验证结果。
        """
        return bool(self.verify_state) and self._verified_fingerprint == fingerprint

    def verified_passed(self) -> bool:
        return bool(self.verify_state and self.verify_state.get("passed"))

    # ---------- 读：给主循环 ----------
    def summary_for_orchestrator(self, max_records: int = 12) -> str:
        lines = [f"目标: {self.goal}", ""]

        if self.facts:
            lines.append("关键事实:")
            for f in self.facts[-8:]:
                lines.append(f"  - {f}")
            lines.append("")

        if self.artifacts:
            lines.append("已有产物:")
            for a in self.artifacts.values():
                lines.append(f"  - {a.preview()}")
            lines.append("")

        recent = self.records[-max_records:]
        if recent:
            lines.append(f"已完成任务（最近 {len(recent)} 条，共 {len(self.records)} 条）:")
            for r in recent:
                lines.append(f"  {r.result.summary()}")
            lines.append("")

        failed = [r for r in self.records if not r.result.ok]
        if failed:
            lines.append("失败任务（不要原样重试）:")
            for r in failed[-5:]:
                lines.append(f"  {r.task.id}: {r.task.description[:80]} -> {r.result.error}")
            lines.append("")

        # 验证结论放在最后——这是模型下一步行动的直接依据
        if self.verify_state:
            ok = self.verify_state.get("passed")
            lines.append("【验证结论】")
            lines.append(f"  结果: {'通过' if ok else '未通过'}")
            if self.verify_state.get("detail"):
                lines.append(f"  细节: {self.verify_state['detail']}")
            lines.append(f"  验证命令: {self.verify_state.get('command', '')}")
            if ok:
                lines.append(
                    "  → 目标已由验证命令确认达成，本轮必须返回 status=done，"
                    "不要再规划任何新任务。"
                )
            else:
                lines.append(
                    "  → 目标尚未达成，请针对上面的失败细节规划修复任务，"
                    "不要重复已经做过且无效果的动作。"
                )
            lines.append("")

        return "\n".join(lines)

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