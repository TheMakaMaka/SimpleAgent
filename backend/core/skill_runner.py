"""技能重放：把固化的计划交给子模型执行。

为什么做成 Orchestrator 的替代实现
----------------------------------
`CodingCycle.run()` 只要求 orchestrator 有 `run(goal)` 并返回 `OrchestratorResult`。
所以「固定链路」不需要新增旁路——实现同一个接口，就能**复用全部既有机制**：
manifest 校验、语法/lint 门禁、验证回流、回退、事件存储、人工决策。

这比另写一条执行路径安全得多：功能不会因为走"快捷通道"而绕过门禁。

与模型规划的区别
----------------
  普通流程：模型 PLAN（1 次 LLM） → 模型执行（N 次 LLM）
  技能重放：读技能（0 次 LLM）   → 模型执行（N 次 LLM）

省掉的是**规划那一步**，而不是执行。执行仍由模型按参数生成代码，
因此仍需实测——技能记录的是"曾经成功过"，不是"永远正确"。
"""

from .llm import LLMClient
from .memory import SharedMemory
from .orchestrator import OrchestratorResult
from .skills import Skill
from .task import Task
from .worker import Worker

try:  # 避免与 checkpoint 的常量分叉
    from .checkpoint import WORKSPACE_DIR
except Exception:  # pragma: no cover
    import os
    WORKSPACE_DIR = os.path.abspath("workspace")


def render_task_description(skill: Skill, params: dict[str, str]) -> str:
    """把技能渲染成给子模型的任务说明。

    刻意把三样东西写清楚，因为它们分别对应三个门禁：
      1. 产出哪些文件（对应 manifest 的文件存在性）
      2. 每个文件要有哪些符号（对应 manifest 的符号检查）
      3. 参考实现（帮助模型一次写对，但**参数不同则代码必须不同**）
    """
    files = skill.render_files(params)
    lines = [skill.render_goal(params), ""]

    lines.append("【必须产出以下文件】")
    for f in files:
        sym = f"，必须包含符号: {', '.join(f.symbols)}" if f.symbols else ""
        role = f"（{f.role}）" if f.role else ""
        lines.append(f"  - {f.path}{role}{sym}")

    lines.append("")
    lines.append("【验收方式】")
    lines.append("系统会用下面这段断言验证你的产出，退出码为 0 才算通过：")
    lines.append("```python")
    lines.append(skill.render_verify(params))
    lines.append("```")

    # 参考实现：只在有示例时给，且明确标注不可照抄
    refs = []
    for f in files:
        code = skill.example_for(f.path, params)
        if code:
            refs.append(f"--- {f.path} 的参考实现 ---\n{code}")
    if refs:
        lines.append("")
        lines.append(
            "【参考实现（来自一次成功运行）】"
            "注意：参数已变化，**不要照抄**，必须按上面的目标与参数重新实现。"
        )
        lines.extend(refs)

    return "\n".join(lines)


class SkillRunner:
    """按技能固定链路执行，接口与 Orchestrator 一致。"""

    def __init__(
        self,
        skill: Skill,
        params: dict[str, str],
        llm: LLMClient,
        worker: Worker | None = None,
    ):
        problems = skill.validate()
        if problems:
            raise ValueError("技能定义有问题，无法重放：\n  - " + "\n  - ".join(problems))

        missing = skill.missing_params(params)
        if missing:
            raise ValueError(f"缺少必填参数: {', '.join(missing)}")

        self.skill = skill
        self.params = dict(params or {})
        self.llm = llm
        self.worker = worker or Worker(llm)

        # CodingCycle 会读这些属性；保持与 Orchestrator 同形
        self.pipeline = None
        self.verify_command = {
            "command": skill.render_verify(self.params),
            "reason": skill.verify_reason or f"技能 {skill.id} 的固化验收方式",
        }
        self.max_rounds = 1
        self.max_same_task = 1

    # ---------- 供 CodingCycle 调用 ----------
    async def run(self, goal: str) -> OrchestratorResult:
        rendered_goal = self.skill.render_goal(self.params)
        memory = SharedMemory(goal=rendered_goal)

        task = Task(
            id="skill_1",
            description=render_task_description(self.skill, self.params),
            expected_output="；".join(
                f"{f.path} 含 {', '.join(f.symbols)}"
                for f in self.skill.render_files(self.params)
            ),
            tool_hint=["write_file"],
        )

        print(f"[skill] 重放 {self.skill.id}｜参数={self.params}", flush=True)
        result = await self.worker.run(task, context="（技能重放，无额外上下文）")
        memory.record(task, result)
        print(f"[skill] 执行结果: {result.summary()}", flush=True)

        declared = [
            {"path": f.path, "role": f.role, "symbols": f.symbols}
            for f in self.skill.render_files(self.params)
        ]

        # ---------- 验证回流 ----------
        # 与 Orchestrator 同样必须在**循环内**执行验证并写入 memory.verify_state，
        # 否则 CodingCycle 会判定「缺少可机器判定的验证命令」而拒绝通过。
        # 这里只验存在声明的文件（缺失由 manifest 报告，避免重复噪音）。
        await self._verify(memory, declared)

        return OrchestratorResult(
            ok=result.ok,
            answer=result.output or "技能重放完成",
            memory=memory,
            verify_command=self.verify_command,
            declared_files=declared,
        )

    async def _verify(self, memory: SharedMemory, declared: list[dict]) -> None:
        """执行技能固化的验证命令，把结论写回 memory。"""
        if self.pipeline is None:
            print("[skill] 未装配 pipeline，跳过验证回流", flush=True)
            return

        from .cycle import VerifyCommand

        import os

        files = sorted(
            d["path"] for d in declared
            if d.get("path") and os.path.exists(os.path.join(WORKSPACE_DIR, d["path"]))
        )
        if not files:
            print("[skill] 声明的文件都不存在，跳过验证回流", flush=True)
            return

        vc = VerifyCommand(
            command=self.verify_command.get("command", ""),
            reason=self.verify_command.get("reason", "") or "",
        )
        vr = await self.pipeline.run_verify(vc)
        detail = self._verify_detail(vr)
        memory.set_verify(
            passed=bool(vr.get("passed")),
            detail=detail,
            command=vc.label(),
            fingerprint=self.skill.id,
            # 技能里**烘焙**的判据算 `caller`：它由技能作者写定，
            # 不是模型自拟的 —— 因此不走 `VERIFY-VACUOUS` 的可采性下限。
            source="caller",
        )
        print(f"[skill] 验证回流 passed={vr.get('passed')} detail={detail[:120]}", flush=True)

    @staticmethod
    def _verify_detail(vr: dict) -> str:
        parsed = vr.get("parsed") or {}
        if parsed.get("ok"):
            return (parsed.get("output") or "验证通过").strip()[:200]
        err = parsed.get("parsed_error") or parsed.get("error") or {}
        if isinstance(err, dict):
            etype = err.get("error_type") or ""
            msg = err.get("message") or parsed.get("raw") or ""
            return f"{etype}: {msg}".strip()[:300]
        return str(vr.get("reason") or "验证未通过")[:300]
