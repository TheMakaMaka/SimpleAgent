from dataclasses import dataclass
from typing import Optional

from .llm import LLMClient
from .memory import SharedMemory
from .prompts import ORCHESTRATOR_SYSTEM
from .task import Artifact, Task
from .worker import Worker


@dataclass
class OrchestratorResult:
    ok: bool
    answer: str
    memory: SharedMemory
    # 真正用过的验证命令（来自调用方或主循环自己提出的 verify）
    verify_command: Optional[dict] = None
    # 计划声明的交付文件清单（用于 manifest 校验）
    declared_files: Optional[list] = None


class Orchestrator:
    """主循环。

    「目标是否达成」由 verify_command 的退出码决定，并在循环内回流：
    每轮任务执行后，只要有新的文件产物，就用验证命令判定一次；
    一旦通过就立刻结束，不再空转。
    """

    def __init__(
        self,
        llm: LLMClient,
        worker: Worker,
        max_rounds: int | None = None,
        max_same_task: int | None = None,
        pipeline=None,
        verify_command: Optional[dict] = None,
    ):
        self.llm = llm
        self.worker = worker
        # 预算统一来自模型档位；显式传参可覆盖
        profile = getattr(llm, "profile", None)
        limits = getattr(profile, "limits", None)
        self.max_rounds = max_rounds if max_rounds is not None else getattr(limits, "max_rounds", 15)
        self.max_same_task = (
            max_same_task if max_same_task is not None else getattr(limits, "max_same_task", 2)
        )
        self.pipeline = pipeline
        self.verify_command = verify_command

    async def run(self, goal: str) -> OrchestratorResult:
        # 文件上下文由 ContextVar 提供（CodingCycle 设置），避免构造顺序上的循环依赖
        from .context import get_cycle_files

        memory = SharedMemory(goal=goal)
        # 调用方给出的验收标准是权威的：模型可以决定「怎么实现」，
        # 但绝不能改写「什么叫对」。只有调用方没给时，才采纳模型自拟的 verify。
        caller_verify = bool(self.verify_command)
        verify_command: Optional[dict] = (
            dict(self.verify_command) if self.verify_command else None
        )
        if caller_verify:
            print("[verify] 验收标准来自调用方，忽略模型自拟的 verify")
        # 计划声明的交付文件清单；后续轮次可补充，用于 manifest 校验
        declared_files: Optional[list] = None
        cycle_files = get_cycle_files()
        baseline_files = set(cycle_files) if cycle_files else None

        for round_idx in range(self.max_rounds):
            print(f"\n===== Orchestrator 第 {round_idx + 1} / {self.max_rounds} 轮 =====")
            decision = await self._decide(memory)
            print(f"[决策] status={decision.get('status')} reasoning={decision.get('reasoning')}")

            # 只有调用方未指定验收标准时，才采纳模型自拟的 verify
            raw_verify = decision.get("verify")
            if (
                not caller_verify
                and isinstance(raw_verify, dict)
                and (raw_verify.get("command") or "").strip()
            ):
                verify_command = raw_verify

            # 计划声明的交付文件清单（后续轮次覆盖为更新的版本）
            raw_files = decision.get("files")
            if raw_files:
                declared_files = raw_files

            status = decision.get("status", "continue")
            if status == "done":
                return OrchestratorResult(
                    ok=True,
                    answer=decision.get("final_answer", "") or "任务完成",
                    memory=memory,
                    verify_command=verify_command,
                    declared_files=declared_files,
                )
            if status == "blocked":
                return OrchestratorResult(
                    ok=False,
                    answer=decision.get("final_answer", "") or "任务受阻",
                    memory=memory,
                    verify_command=verify_command,
                    declared_files=declared_files,
                )

            tasks = self._parse_tasks(decision.get("tasks") or [])
            if not tasks:
                return OrchestratorResult(
                    ok=False,
                    answer="主循环没有产出可执行任务",
                    memory=memory,
                    verify_command=verify_command,
                    declared_files=declared_files,
                )

            # 指纹去重
            executable = []
            for t in tasks:
                skip, reason = self._should_skip(memory, t)
                if skip:
                    print(f"[跳过] {t.id}: {reason} | {t.description[:60]}")
                    continue
                executable.append(t)
            if not executable:
                return OrchestratorResult(
                    ok=False,
                    answer="所有任务都因重复被拒，无法继续",
                    memory=memory,
                    verify_command=verify_command,
                    declared_files=declared_files,
                )

            # 串行执行
            for task in executable:
                print(f"[执行] {task.id}: {task.description}")
                context = memory.context_for_worker(task)
                result = await self.worker.run(task, context)
                memory.record(task, result)
                print(f"[结果] {result.summary()}")

            # ---------- 验证回流 ----------
            if verify_command and self.pipeline is not None:
                files = self._files_to_verify(memory, baseline_files)
                if files:
                    fp = self._verify_fingerprint(verify_command, files)
                    if not memory.already_verified_at(fp):
                        from .cycle import VerifyCommand  # 避免循环 import

                        vc = VerifyCommand(
                            command=verify_command.get("command", ""),
                            reason=verify_command.get("reason", "") or "",
                        )
                        vr = await self.pipeline.run_verify(vc)
                        memory.set_verify(
                            passed=bool(vr.get("passed")),
                            detail=self._verify_detail(vr),
                            command=vc.label(),
                            fingerprint=fp,
                        )
                        print(
                            f"[验证回流] passed={vr.get('passed')} "
                            f"detail={memory.verify_state['detail'][:120]}"
                        )
                        if vr.get("passed"):
                            return OrchestratorResult(
                                ok=True,
                                answer=f"验证命令通过，目标达成（第 {round_idx + 1} 轮）",
                                memory=memory,
                                verify_command=verify_command,
                                declared_files=declared_files,
                            )
                elif baseline_files is None:
                    # 本轮没有产生任何文件产物，无法验证，继续让主循环推进
                    pass

        # 达到轮次上限：用最后一次验证结论决定 ok
        answer = f"达到主循环上限 {self.max_rounds} 轮，未能完成"
        if memory.verified_passed():
            return OrchestratorResult(
                ok=True,
                answer=f"验证命令已通过（此前已达轮次上限 {self.max_rounds} 轮）",
                memory=memory,
                verify_command=verify_command,
                declared_files=declared_files,
            )
        return OrchestratorResult(
            ok=False,
            answer=answer,
            memory=memory,
            verify_command=verify_command,
        )

    # ---------- 内部 ----------
    @staticmethod
    def _files_to_verify(memory: SharedMemory, baseline_files: set[str] | None) -> list[str]:
        """需要参与验证的文件。

        有 cycle 级目标文件清单时以它为准（不受主循环内部轮次影响）；
        否则退化为主循环自己认定的、来自 write_file 的文件产物。
        """
        if baseline_files:
            return sorted(baseline_files)

        paths: list[str] = []
        for a in memory.artifacts.values():
            if isinstance(a, Artifact) and a.kind == "file" and a.path:
                norm = a.path.replace("\\", "/")
                if norm not in paths:
                    paths.append(norm)
        return sorted(paths)

    @staticmethod
    def _verify_fingerprint(verify_command: dict, files: list[str]) -> str:
        """验证指纹：命令 + 待验证文件。只与「验什么」有关，与历史任务无关。

        这样主循环重复制造同一个验证任务时，也不会重复触发验证。
        """
        import hashlib

        raw = "|".join([
            (verify_command.get("command") or "").strip(),
            ",".join(sorted(files)),
        ])
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

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

    async def _decide(self, memory: SharedMemory) -> dict:
        from tools import TOOLS_MAP  # 避免循环 import
        from tools.registry import tool_names

        # 按 Worker 的 profile 过滤：给编排器的候选列表必须与子循环实际可见的一致，
        # 否则会建议一个当前 profile 下不存在的工具（过滤器也会把它当幻觉丢掉）
        active = getattr(self.worker, "profile", None)
        visible = set(tool_names(active)) if active else set(TOOLS_MAP)
        tool_names_str = ", ".join(n for n in TOOLS_MAP if n in visible) or "(无)"
        system_content = (
                ORCHESTRATOR_SYSTEM
                + f"\n\n可用工具（tool_hint 只能从下面选择，不能编造）：{tool_names_str}"
        )

        user_content = memory.summary_for_orchestrator()
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]
        # 走适配层标准入口：请求构造 + JSON 容错 + 耦合修复都在适配层内完成
        data = await self.llm.chat_json(messages)
        if data.get("_parse_failed"):
            text = data.get("_raw") or ""
            print(f"[Orchestrator] JSON 解析失败，原始输出:\n{text[:500]}")
            return {
                "status": "blocked",
                "reasoning": "JSON 解析失败",
                "tasks": [],
                "final_answer": "主循环输出格式错误",
            }

        # 过滤 tool_hint 里的幻觉工具名（同时过滤掉当前 profile 不可见的）
        for t in data.get("tasks") or []:
            if not isinstance(t, dict):
                continue
            hints = t.get("tool_hint") or []
            valid = [h for h in hints if h in visible]
            invalid = [h for h in hints if h not in visible]
            if invalid:
                print(f"[Orchestrator] 过滤不可用工具: {invalid}")
            t["tool_hint"] = valid

        return data

    @staticmethod
    def _parse_tasks(raw_tasks: list) -> list[Task]:
        tasks: list[Task] = []
        for i, t in enumerate(raw_tasks):
            if not isinstance(t, dict):
                continue
            desc = (t.get("description") or "").strip()
            if not desc:
                continue
            tasks.append(
                Task(
                    id=t.get("id") or f"t{i + 1}",
                    description=desc,
                    expected_output=t.get("expected_output", "") or "",
                    tool_hint=list(t.get("tool_hint") or []),
                    context_refs=list(t.get("context_refs") or []),
                )
            )
        return tasks

    def _should_skip(self, memory, task) -> tuple[bool, str]:
        fp = task.fingerprint()
        same = [r for r in memory.records if r.task.fingerprint() == fp]
        if not same:
            return False, ""
        # 已经成功过 → 跳过
        if any(r.result.ok for r in same):
            return True, f"任务已成功过一次，跳过"
        # 失败次数达到上限 → 跳过
        if len(same) >= self.max_same_task:
            return True, f"任务已失败 {len(same)} 次，跳过"
        return False, ""
