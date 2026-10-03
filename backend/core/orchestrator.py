import re
from dataclasses import dataclass
from typing import Optional

from .llm import LLMClient
from .memory import SharedMemory
from .prompts import ORCHESTRATOR_SYSTEM
from .task import Artifact, Task
from .worker import Worker

#: 判定「自拟验收命令引用了某个交付物」时，允许参与匹配的最小词干长度。
#: 太短的词干（`a` / `x`）会在几乎任何命令里巧合命中，等于没有下限。
#: 短于这个长度的文件要求**整名匹配**（例如 `a.py` 必须写成 `a.py`）。
_MIN_STEM_LEN = 3


@dataclass
class OrchestratorResult:
    ok: bool
    answer: str
    memory: SharedMemory
    # 真正用过的验证命令（来自调用方或主循环自己提出的 verify）
    verify_command: Optional[dict] = None
    # 计划声明的交付文件清单（用于 manifest 校验）
    declared_files: Optional[list] = None
    #: ★ 验证**被跳过**的原因（空串 = 正常）。
    #:
    #: 为什么要有它（`FIX-VERIFY-WIRING` 附 1）：原来 `pipeline is None` 时
    #: **整块静默跳过** —— 无日志、无事件。上层于是只能猜，并且猜成了
    #: 「缺少验证命令」（而命令其实就在 `verify_command` 里）。
    #: 现在把"跳过"变成显式事实，由 cycle 层记成 `verify_skipped` 事件。
    #:
    #: 另一个来源见 `SharedMemory.verify_untrusted`（自拟验收不合格被拒），
    #: 两者都由 cycle 层汇总成同一条 `verify_skipped` 事件。
    verify_skipped: str = ""


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
        # 保留 limits 引用：prompt 字符预算等也从这里取，避免各处再写默认值
        if limits is None:
            from .model_profile import ModelLimits

            limits = ModelLimits()
        self.limits = limits
        self.max_rounds = max_rounds if max_rounds is not None else getattr(limits, "max_rounds", 15)
        self.max_same_task = (
            max_same_task if max_same_task is not None else getattr(limits, "max_same_task", 2)
        )
        self.pipeline = pipeline
        self.verify_command = verify_command
        # 结构化上下文提供方：由调用方注入（CodingCycle 从事件流压缩）。
        # 每轮决策前调用一次——它是**旁路**，抛异常绝不能影响主循环。
        self.context_provider = None

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
        # 本轮开始前已存在的文件（ContextVar 由 CodingCycle 设）。
        # 它回答的是"**哪些是历史文件**"，不是"验什么" —— 后者见 `_files_to_verify`。
        verify_skipped_reason = ""
        prior_files = get_cycle_files()
        prior_set = set(prior_files) if prior_files else None
        #: 上一次**真的执行过且失败**的判据（同 cycle 内）。
        #: B2 的触发条件：模型要**替换**它时，必须给理由。
        last_failed: Optional[dict] = None

        for round_idx in range(self.max_rounds):
            print(f"\n===== Orchestrator 第 {round_idx + 1} / {self.max_rounds} 轮 =====")
            decision = await self._decide(memory)
            print(f"[决策] status={decision.get('status')} reasoning={decision.get('reasoning')}")
            # ★ A1（`TRANSPARENCY-BACKEND`）：把"为什么这么决定"变成**事实**。
            # 原来它只出现在上面那行服务端日志里，事件流里没有，
            # 前端因此无从显示"第 2 轮为什么又去改这个文件"。
            memory.log_decision(round_idx + 1, decision)

            # 计划声明的交付文件清单（后续轮次覆盖为更新的版本）
            # ⚠️ 必须**先**取本次决策的声明，再判自拟验收的可采性 ——
            # 判据是"命令有没有引用交付物"，而交付物首先来自这份声明。
            raw_files = decision.get("files")
            if raw_files:
                declared_files = raw_files

            # 只有调用方未指定验收标准时，才采纳模型自拟的 verify
            raw_verify = decision.get("verify")
            if (
                not caller_verify
                and isinstance(raw_verify, dict)
                and (raw_verify.get("command") or "").strip()
            ):
                new_cmd = str(raw_verify.get("command") or "").strip()
                why_reason = str(raw_verify.get("reason") or "").strip()
                # ★ B2（用户裁决的行为改动）：**换掉一条已执行且失败的判据 → 必须给理由**。
                # 实测那次 `passed` 的根因就在这里：判据 A 真跑过、真失败，
                # 随后被换成一条必过的 B，**代码一行没改**，流程据此记 passed。
                # 用户选的是"留痕 + 必须给理由"（不是禁止换）：
                # 换判据在某些情况下是正当的（前一条自己写错了、环境缺依赖），
                # 但**必须看得见**。没给理由 → 不采纳（走显式失败，不静默）。
                replacing = bool(last_failed) and new_cmd != (
                    last_failed or {}
                ).get("command", "")
                if replacing and not why_reason:
                    why_b2 = (
                        "要替换一条**已执行且失败**的判据（上一条："
                        f"{(last_failed or {}).get('command', '')[:60]!r}），"
                        "但 verify.reason 是空的 —— 换判据必须给理由，"
                        "否则无法区分「修正了判据自身的问题」与「把考卷换成一张必过的」"
                    )
                    memory.reject_verify(raw_verify, why_b2)
                    memory.log_criterion("rejected", new_cmd, reason=why_b2,
                                         passed=False, source="model")
                    print(f"[verify] 拒绝采纳模型自拟的验收判据：{why_b2}")
                else:
                    # ★ 可采性下限（`VERIFY-VACUOUS` + `TRANSPARENCY-BACKEND` B3）：
                    # 自拟判据不得**恒真**，且**必须真的调用**交付物
                    # （`assert generate_obstacles` 引用得到、却从不调用 → 恒真）。
                    ok_adm, why = self._model_verify_admissible(
                        raw_verify, self._deliverables(memory, declared_files)
                    )
                    if ok_adm:
                        verify_command = raw_verify
                        memory.verify_untrusted = ""
                        memory.log_criterion(
                            "adopted", new_cmd,
                            reason=why_reason or "(未给理由)",
                            passed=None, source="model",
                        )
                    else:
                        # **不清空**已经采纳过的命令：本轮给出坏判据，不该把
                        # 前几轮已经采纳的好判据一起作废。
                        memory.reject_verify(raw_verify, why)
                        memory.log_criterion("rejected", new_cmd, reason=why,
                                             passed=False, source="model")
                        print(f"[verify] 拒绝采纳模型自拟的验收判据：{why}")

            status = decision.get("status", "continue")
            if status == "done":
                return OrchestratorResult(
                    ok=True,
                    answer=decision.get("final_answer", "") or "任务完成",
                    memory=memory,
                    verify_command=verify_command,
                    declared_files=declared_files,
                    verify_skipped=verify_skipped_reason,
                )
            if status == "blocked":
                return OrchestratorResult(
                    ok=False,
                    answer=decision.get("final_answer", "") or "任务受阻",
                    memory=memory,
                    verify_command=verify_command,
                    declared_files=declared_files,
                    verify_skipped=verify_skipped_reason,
                )

            tasks = self._parse_tasks(decision.get("tasks") or [])
            if not tasks:
                return OrchestratorResult(
                    ok=False,
                    answer="主循环没有产出可执行任务",
                    memory=memory,
                    verify_command=verify_command,
                    declared_files=declared_files,
                    verify_skipped=verify_skipped_reason,
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
                    verify_skipped=verify_skipped_reason,
                )

            # 串行执行
            for task in executable:
                print(f"[执行] {task.id}: {task.description}")
                context = memory.context_for_worker(task)
                result = await self.worker.run(task, context)
                memory.record(task, result)
                print(f"[结果] {result.summary()}")

            # ---------- 验证回流 ----------
            if verify_command and self.pipeline is None:
                # 有命令却跑不了验证 —— **必须说出来**，不能静默跳过。
                # （`FIX-VERIFY-WIRING` 附 1：静默跳过导致上层误诊成"缺少命令"。）
                if not verify_skipped_reason:
                    verify_skipped_reason = (
                        "主循环没有 pipeline（未注入），验证回流整块被跳过 —— "
                        "命令存在，是**没执行**"
                    )
                    print(f"[验证回流] 跳过：{verify_skipped_reason}")
            if verify_command and self.pipeline is not None:
                files = self._files_to_verify(memory, prior_set, declared_files)
                if files:
                    fp = self._verify_fingerprint(verify_command, files)
                    if not memory.already_verified_at(fp):
                        from .cycle import VerifyCommand  # 避免循环 import

                        vc = VerifyCommand(
                            command=verify_command.get("command", ""),
                            reason=verify_command.get("reason", "") or "",
                        )
                        vr = await self.pipeline.run_verify(vc, files)
                        passed = bool(vr.get("passed"))
                        detail = self._verify_detail(vr)
                        memory.set_verify(
                            passed=passed,
                            detail=detail,
                            command=vc.label(),
                            fingerprint=fp,
                            # ★ 判据**来源**留痕（`VERIFY-VACUOUS` 建议 2）：
                            # "调用方给的"与"模型自拟的"可信度差很远，
                            # 而在这之前外部**完全无法区分**。
                            source="caller" if caller_verify else "model",
                            # ★ P6：判词必须描述产物 —— 记下被验证产物的内容哈希、
                            # 验证的工作目录、以及是否清过字节码缓存。
                            artifact_hashes=vr.get("artifact_hashes") or {},
                            cwd=str(vr.get("cwd") or ""),
                            cache_cleared=int(vr.get("cache_cleared") or 0),
                            cache_warning=str(vr.get("cache_warning") or ""),
                            # ★ P17：**执行记录**（真实退出码 + 期望值）。
                            # pass 的 executed 证据要求它非空 —— 没有它，
                            # "通过"就只是模型自述（见 core/evidence.py）。
                            exit_code=(vr.get("parsed") or {}).get("exit_code"),
                            expect_exit=vr.get("expect_exit"),
                        )
                        # ★ B1：判据**被执行**这件事本身也要留痕（含结果）。
                        # 原来这条事实只存在于前端 bridge 的 `verify_probe` 里，
                        # 于是"上一条真跑过、真失败"在**上游事件流**里读不出来。
                        memory.log_criterion(
                            "executed", vc.label(),
                            passed=passed, detail=detail,
                            source="caller" if caller_verify else "model",
                        )
                        if not passed:
                            # B2 的触发条件：这一条已执行且失败。
                            last_failed = {"command": vc.label(), "detail": detail}
                        # 验证真的跑过了 → 之前"被跳过"的理由作废
                        verify_skipped_reason = ""
                        memory.verify_untrusted = ""
                        print(
                            f"[验证回流] passed={passed} "
                            f"detail={memory.verify_state['detail'][:120]}"
                        )
                        if vr.get("passed"):
                            return OrchestratorResult(
                                ok=True,
                                answer=f"验证命令通过，目标达成（第 {round_idx + 1} 轮）",
                                memory=memory,
                                verify_command=verify_command,
                                declared_files=declared_files,
                                verify_skipped=verify_skipped_reason,
                            )
                elif prior_set is None:
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
                verify_skipped=verify_skipped_reason,
            )
        return OrchestratorResult(
            ok=False,
            answer=answer,
            memory=memory,
            verify_command=verify_command,
            verify_skipped=verify_skipped_reason,
        )

    # ---------- 内部 ----------
    @staticmethod
    def _files_to_verify(
        memory: SharedMemory,
        prior_files: set[str] | None = None,
        declared_files: Optional[list] = None,
    ) -> list[str]:
        """需要参与验证的文件 = **本轮交付物**。

        ★ 语义修正（`FIX-VERIFY-WIRING` 附 4）：这里原来是
        `if baseline_files: return sorted(baseline_files)` —— 而调用方传进来的是
        **本轮开始前已存在的文件**（`coding_cycle._prior_files`）。于是
        `_verify_fingerprint()`（命令 + 文件）**键在一个不随交付物变化的旧文件集上**：

          · 同一命令在后续轮次会被 `already_verified_at()` 判为"已验过" → **跳过重验**；
          · 模型在中途把文件修好了，**验证不会再跑一次**，循环因此可能把
            已经达成的目标判成失败。

        现在的优先顺序（从"最贴近交付物"到"兜底"）：

          1. **计划声明的交付文件**（`declared_files`，本轮意图）
          2. `write_file` 产出的文件（主循环自己认定的交付物）
          3. `prior_files`（本轮开始前已存在的文件 —— 只在 1、2 都空时才兜底）

        `prior_files` 的正确定位是**"哪些是历史文件"**（用于提示与 manifest 区分），
        不是"验什么"。见 `docs/EVALUATION-FIX-VERIFY-WIRING.md`。
        """
        from .manifest import normalize_declared_path, parse_declared

        paths: list[str] = []
        for d in parse_declared(declared_files or []):
            norm = normalize_declared_path(d.path)
            if norm and norm not in paths:
                paths.append(norm)
        if paths:
            return sorted(paths)

        for a in memory.artifacts.values():
            if isinstance(a, Artifact) and a.kind == "file" and a.path:
                norm = a.path.replace("\\", "/")
                if norm not in paths:
                    paths.append(norm)
        if paths:
            return sorted(paths)

        return sorted(prior_files) if prior_files else []

    @staticmethod
    def _deliverables(memory: SharedMemory, declared_files: Optional[list] = None) -> list[str]:
        """本轮**可被验收判据引用的交付物**（规范化路径）。

        只收两类能落到磁盘上的东西：

          1. 计划声明的交付文件（`declared_files`）
          2. `write_file` 真正产出的文件（`memory.artifacts` 中 `kind="file"`）

        **刻意不收 `prior_files`**：那是**本轮开始前**就存在的历史文件
        （`FIX-VERIFY-WIRING` 附 4 已把它从"验什么"里降级）。把它算成交付物，
        等于允许「验收引用一个我根本没碰过的文件」—— 那正是 `VERIFY-VACUOUS`
        那次运行里发生的事（工作区里躺着上一次测试留下的 `calc.py`/`notes.txt`）。
        """
        from .manifest import normalize_declared_path, parse_declared

        out: list[str] = []
        for d in parse_declared(declared_files or []):
            norm = normalize_declared_path(d.path)
            if norm and norm not in out:
                out.append(norm)
        for a in memory.artifacts.values():
            if isinstance(a, Artifact) and a.kind == "file" and a.path:
                norm = a.path.replace("\\", "/")
                if norm not in out:
                    out.append(norm)
        return out

    @staticmethod
    def _code_without_literals(command: str) -> str:
        """剥掉**字符串字面量**后的命令文本（只用于词干匹配）。

        为什么需要它：`print('add')` 里那个 `add` 只是**打在字符串里**，
        并没有对交付物做任何操作。不剥字面量的话，这种命令会巧合命中
        `add.py` 的词干，下限就形同虚设。

        解析失败（命令本身语法不全）时**退回原文**：宁可判宽一点，
        也不要因为解析器的小脾气误拒一条合法判据。
        """
        import io
        import tokenize

        pieces: list[str] = []
        try:
            for tok in tokenize.generate_tokens(io.StringIO(command).readline):
                if tok.type == tokenize.STRING:
                    continue
                pieces.append(tok.string)
        except Exception:  # noqa: BLE001 —— 解析失败只影响"更严"这一侧
            return command
        return " ".join(pieces)

    @classmethod
    def _verify_references(cls, command: str, deliverables: list[str]) -> list[str]:
        """命令里**确实引用到**的交付物（纯文本匹配，规则就写在这里）。

        两条规则，对应实测见过的两类真实写法：

          **A. 路径/文件名出现在命令文本里**（含字符串字面量内部，因为
          `open('report.txt')` 本来就长这样）：
             `assert open('report.txt').read()`
             `assert os.path.exists('add.py')`（交付物是 `src/add.py` 也命中）

          **B. 词干出现在命令的\**代码**里**（先剥掉字符串字面量），
          用于模块式判据：
             `import add; assert add.add(1, 2) == 3`（交付物 `add.py`）

        词干匹配只在 `len(stem) >= _MIN_STEM_LEN` 时启用，且要求词边界 ——
        否则 `a.py` 的词干 `a` 会在任何命令里巧合命中，下限形同虚设。

        已知的**误收**（刻意留白，见 `docs/EVALUATION-VERIFY-VACUOUS.md` §7）：
        `print('report.txt')` 这类"只把路径打在字符串里、不做任何判定"的命令
        仍会被判为引用了交付物。要堵它就得判断"这条命令有没有认真检查"，
        而那不是机器可判定的事实 —— 本层只提供一个**可判定的下限**。
        """
        text = (command or "").replace("\\", "/")
        low = text.lower()
        code = cls._code_without_literals(command)
        hit: list[str] = []
        for path in deliverables:
            norm = path.replace("\\", "/")
            base = norm.rsplit("/", 1)[-1]
            # 规则 A：路径/文件名出现在原文里（大小写不敏感）
            if base and base.lower() in low:
                hit.append(path)
                continue
            if norm.lower() in low:
                hit.append(path)
                continue
            # 规则 B：词干出现在**代码**里（词边界）
            stem = base.rsplit(".", 1)[0] if "." in base else ""
            if len(stem) >= _MIN_STEM_LEN and re.search(
                rf"(?<![\w.]){re.escape(stem)}(?![\w])", code, re.IGNORECASE
            ):
                hit.append(path)
        return hit

    @staticmethod
    def _module_names_for(path: str) -> set[str]:
        """某个 `.py` 交付物**可以被 import 成什么名字**。非 `.py` 返回空集。

        `obstacle_generator.py`      → {`obstacle_generator`}
        `src/add.py`                 → {`src.add`, `add`}
        `pkg/__init__.py`            → {`pkg.__init__`, `pkg`}
        """
        norm = (path or "").replace("\\", "/")
        if not norm.endswith(".py"):
            return set()
        dotted = norm[:-3].replace("/", ".")
        base = dotted.rsplit(".", 1)[-1]
        names = {dotted}
        if base == "__init__":
            pkg = dotted.rsplit(".", 1)[0] if "." in dotted else ""
            if pkg:
                names.add(pkg)
        else:
            names.add(base)
        return {n for n in names if n}

    @staticmethod
    def _called_modules(command: str) -> set[str]:
        """命令**调用进了哪些模块**（AST 上真的出现了 `Call`）。

        `import mod` + `mod.f(1)`            → {`mod`, `mod.f`}（前缀都算）
        `from mod import f` + `f(1)`         → {`f`, `mod`}（按 import 别名解析回去）
        `assert mod.f`（**没有括号**）        → 空集 ← 这正是要拦住的那一类
        `import numpy as np` + `np.array(...)` → {`np`, `numpy`, ...}
        """
        import ast

        try:
            tree = ast.parse(command)
        except SyntaxError:
            return set()

        def dotted(node) -> str:
            parts: list[str] = []
            while isinstance(node, ast.Attribute):
                parts.append(node.attr)
                node = node.value
            if isinstance(node, ast.Name):
                parts.append(node.id)
                return ".".join(reversed(parts))
            return ""

        alias: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    alias[a.asname or a.name.split(".")[0]] = a.name
            elif isinstance(node, ast.ImportFrom):
                if node.module and not node.level:
                    for a in node.names:
                        alias[a.asname or a.name] = node.module

        out: set[str] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = dotted(node.func)
            if not name:
                continue
            parts = name.split(".")
            for i in range(1, len(parts) + 1):
                out.add(".".join(parts[:i]))
            # `from mod import f` 之后调用 `f(...)` —— 调的是 mod 里的符号
            if parts[0] in alias:
                out.add(alias[parts[0]])
        return out

    @classmethod
    def _model_verify_admissible(
        cls, raw_verify: dict, deliverables: list[str]
    ) -> tuple[bool, str]:
        """模型自拟的验收判据**可采性下限**。

        三层，逐层收紧（每一层都是实测踩出来的）：

        1. **不得恒真**（`VERIFY-VACUOUS`）：本轮必须有交付物，且判据必须**引用**它。
           反例：`print('PASS')`。
        2. **引用 ≠ 执行**（`TRANSPARENCY-BACKEND` B3）：判据引用了 `.py` 交付物时，
           必须**调用**它。反例：`from obstacle_generator import generate_obstacles`
           + `assert generate_obstacles` —— 引用得到、却从不调用，于是恒真。
           **这条是实测那次假 `passed` 里唯一能被拦住的规则。**

        为什么判据选"引用/调用交付物"而不是"识别废话"：
        `docs/CHANGE-PROCESS.md` C2 要求每条主张可机器验证，判据本身也一样 ——
        "命令里出现了交付物、并且 AST 上真的调用了它"是**可判定的事实**，
        而"这条命令是不是恒真"在一般情况下不可判定。

        **边界（刻意如此）**：只作用于**自拟**判据。调用方给了 `verify_command` 时，
        验收标准是调用方的权威，本方法不参与。
        """
        command = str(raw_verify.get("command") or "")
        if not deliverables:
            return False, (
                "本轮没有任何交付物（计划没声明文件、也没有 write_file 产物），"
                "自拟的验收无从判定 —— 一份交付声明都没有，就说不出「交付了什么」，"
                "因此不该有「验证通过」这个结论"
            )
        hit = cls._verify_references(command, deliverables)
        if not hit:
            return False, (
                f"自拟的验收命令没有引用本轮任何交付物 {deliverables[:5]}，"
                "疑为恒真判据（例：print('PASS')）"
            )
        # B3：引用了 `.py` 交付物 → 必须真的调用它
        py_refs = [d for d in hit if d.replace("\\", "/").endswith(".py")]
        if py_refs:
            called = cls._called_modules(command)
            silent = [d for d in py_refs if not (cls._module_names_for(d) & called)]
            if silent:
                return False, (
                    f"自拟的验收命令引用了 {silent[:3]} 却**没有调用**它："
                    "只写 `assert 名字`、只检查文件存在，都不算执行过 —— "
                    "必须真的调用交付物（如 `import mod` 后 `mod.func(...)`，"
                    "或 `from mod import func` 后 `func(...)`）"
                )
        return True, ""

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

    def _refresh_structured_context(self, memory: SharedMemory) -> None:
        """调用 context_provider 刷新结构化上下文。

        三条纪律：
        1. **失败必须静默降级为"无结构化上下文"，绝不能让主循环崩**——
           它是旁路增强，不是判据；
        2. 提供方可以返回 `(text, source)` 或纯 `str`，两种都接受；
        3. 返回空串即清空（说明快照里没有可用事实），不保留上一轮的陈旧块。
        """
        provider = self.context_provider
        if provider is None:
            return
        try:
            produced = provider()
        except Exception as e:  # noqa: BLE001 —— 旁路，任何异常都不该中断决策
            print(f"[Orchestrator] 结构化上下文获取失败（已忽略）: {e}")
            memory.set_structured_context("")
            return
        if isinstance(produced, tuple):
            seq = tuple(produced)
            text = seq[0] if seq else ""
            source = seq[1] if len(seq) > 1 else ""
        else:
            text, source = produced or "", ""
        memory.set_structured_context(text or "", source or "")

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

        # 每轮决策前刷新结构化上下文（压缩快照）。
        # 放在这里而不是 run() 开头：同一 attempt 内可能决策多轮，
        # 每轮都应看到"到此刻为止"的实测事实。
        self._refresh_structured_context(memory)

        user_content = memory.summary_for_orchestrator(
            char_budget=getattr(self.limits, "orchestrator_prompt_chars", None)
        )
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
