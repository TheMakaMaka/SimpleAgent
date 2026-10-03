"""`TRANSPARENCY-BACKEND` A1 / B1 / B2 / B3 的运行时回归。

背景（真实运行 `run_20260927_125647_5a3297`）
--------------------------------------------
用户的目标明确要求「保证起始点与目标点至少可通 / 连续测试验证 / 生成报告」，
结果报了 `passed`；而机械事实是**没跑过测试、没有报告、有个 `np` 未定义的文件**。
根因不是模型单方面自嗨，也不是流程坏了：

    (b) 判据真跑过、真失败（生成障碍物+跑蚁群+检查报告 → passed=false）
    (c) 随后被判据换成 `assert generate_obstacles` —— 恒真 → passed=true → record
        **而代码一行没改**

**流程允许模型在自己的判据失败之后，把考卷换成一张必过的。**

测什么
------
* **A1**：每一轮的 `reasoning`（决策依据）必须能从事件流读到；
* **B3**：自拟判据引用了 `.py` 交付物时**必须真的调用它**（`assert 名字` 不算）——
  这是实测那次唯一能被拦住的规则；
* **B2**：换掉一条**已执行且失败**的判据 → **必须给理由**，没给理由**不采纳**；
* **B1**：判据的演化（采纳/拒绝/执行 + 前后关系）能从事件流**直接**还原。
"""

import asyncio
import os
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import Checker, WORKSPACE as WS, clean_workspace  # noqa: E402

from core import (  # noqa: E402
    CheckPipeline, CodingCycle, DecisionManager, Orchestrator, TaskResult,
)
from core.decisions import FileDecisionStore  # noqa: E402
from core.orchestrator import Orchestrator as O  # noqa: E402
from core.task import Artifact  # noqa: E402
from storage.store import Event  # noqa: E402

OK = Checker()


class RecStorage:
    def __init__(self):
        self.events: list[Event] = []

    def append_event(self, event: Event) -> None:
        self.events.append(event)

    def get_events(self, cycle_id=None):
        return list(self.events)

    def saved(self, kind: str) -> list[Event]:
        return [e for e in self.events if e.kind == kind]


class ScriptedLLM:
    profile = None

    def __init__(self, decisions: list[dict]):
        self.decisions = decisions
        self.seen = 0

    async def chat_json(self, messages):
        d = self.decisions[min(self.seen, len(self.decisions) - 1)]
        self.seen += 1
        return d


class ModWorker:
    """写 `mod.py`（内容可指定），并回报 artifact。"""

    profile = None

    def __init__(self, body: str = "def f():\n    return 2\n"):
        self.body = body

    async def run(self, task, context):
        with open(os.path.join(WS, "mod.py"), "w", encoding="utf-8") as f:
            f.write(self.body)
        return TaskResult(
            task_id=task.id, ok=True, output="已写入 mod.py",
            artifacts=[Artifact(key=f"{task.id}_file_mod.py", kind="file", path="mod.py")],
            steps_used=1,
        )


SELF_REPORT_OK = {
    "done": ["写了 mod.py"], "not_done": [], "why": [], "reflections": [],
    "approach": ["直接写实现"], "confidence": {"level": "low", "basis": "证据有限"},
    "open_questions": [], "requirements": [],
    "claims": {"verify_passed": None, "check_passed": None, "artifacts": ["mod.py"]},
}

#: 第二轮必须给一个**新**任务：同一任务会被指纹去重跳过，
#: 一旦没有可执行任务，主循环会在验证之前就返回（实测踩到）。
ROUND2_TASKS = [{
    "id": "t2", "description": "确认 mod.py 的实现符合断言", "expected_output": "确认结论",
    "tool_hint": ["read_file"], "context_refs": [],
}]


def plan(verify: dict, files: list | None = None, tasks: list | None = None) -> dict:
    return {
        "status": "continue", "reasoning": "需要先写出实现再验证",
        "files": files if files is not None else [
            {"path": "mod.py", "role": "实现", "symbols": ["f"]}
        ],
        "tasks": tasks or [{
            "id": "t1", "description": "写 mod.py", "expected_output": "mod.py",
            "tool_hint": ["write_file"], "context_refs": [],
        }],
        "verify": verify, "final_answer": "",
    }


def done_decision() -> dict:
    return {"status": "done", "reasoning": "已无更多任务", "tasks": [],
            "files": [], "verify": {}, "final_answer": "完成"}


async def run_case(decisions: list[dict], tmp: str, worker=None):
    store = RecStorage()
    orch = Orchestrator(ScriptedLLM(decisions), worker or ModWorker(),
                        pipeline=None, verify_command=None)
    cycle = CodingCycle(orchestrator=orch, worker=None, pipeline=CheckPipeline(),
                        max_attempts=1, verbose=False, storage=store, persist=True,
                        on_decision="auto",
                        decisions=DecisionManager(store=FileDecisionStore(root=tmp)))
    report, memory = await cycle.run("实现 mod.f 并保证返回 1")
    return report, memory, store


async def main() -> int:
    tmp = tempfile.mkdtemp(prefix="transparency_")

    # ================= A1：决策依据进事件 =================
    print("=" * 74)
    print("[A1] orchestrator_round：每一轮的 reasoning 必须能从事件流读到")
    print("=" * 74)
    clean_workspace()
    report, memory, store = await run_case(
        [plan({"command": "import mod\nassert mod.f() == 2", "reason": "调用并断言返回值"}),
         done_decision(), SELF_REPORT_OK], tmp)
    rounds = store.saved("orchestrator_round")
    for e in rounds:
        p = e.payload or {}
        print(f"  [round {p.get('round')}] status={p.get('status')} "
              f"reasoning={str(p.get('reasoning'))[:50]!r} tasks={len(p.get('tasks') or [])}")
    OK.check("至少发出了一条 orchestrator_round 事件", len(rounds) >= 1)
    OK.check("reasoning 非空（A1 的验收点）",
             bool(rounds) and all((e.payload or {}).get("reasoning") for e in rounds))
    OK.check("带上了这一轮打算做什么（intent/tasks）",
             bool(rounds) and all("tasks" in (e.payload or {}) for e in rounds))
    OK.check("round 序号从 1 开始且递增",
             [e.payload.get("round") for e in rounds] == list(range(1, len(rounds) + 1)))
    OK.check("phase=record（这条判据真的调用了交付物，允许通过）",
             report.phase.value == "record")

    # ================= B3：引用 ≠ 执行 =================
    print("\n" + "=" * 74)
    print("[B3] 自拟判据引用了 .py 交付物就必须**调用**它")
    print("=" * 74)
    b3_cases = [
        # 实测那次被采纳的判据 —— 必须被拒
        ("from obstacle_generator import generate_obstacles\nassert generate_obstacles",
         ["obstacle_generator.py"], False, "实测反例：只 assert 名字（恒真）"),
        ("import obstacle_generator\nassert obstacle_generator.generate_obstacles",
         ["obstacle_generator.py"], False, "属性形式但不调用"),
        ("import obstacle_generator\nobstacle_generator.generate_obstacles((10, 10))",
         ["obstacle_generator.py"], True, "属性调用"),
        ("from obstacle_generator import generate_obstacles\ngenerate_obstacles((10, 10))",
         ["obstacle_generator.py"], True, "import 后调用"),
        ("import os\nassert os.path.exists('add.py')", ["add.py"], False,
         "只检查文件存在（已知误伤，见评估文档 §7）"),
        ("assert open('report.txt').read().strip()", ["report.txt"], True,
         "数据交付物不受 B3 影响"),
        ("import add\nassert add.add(1, 2) == 3", ["add.py"], True, "模块调用"),
    ]
    for cmd, deliv, want, why in b3_cases:
        got, detail = O._model_verify_admissible({"command": cmd}, deliv)
        print(f"  {'PASS' if got == want else 'FAIL'}  可采={got!s:5} {why}")
        OK.check(f"B3：{why}", got == want)
        if (not got) and (not want) and deliv[0].endswith(".py") and "存在" not in why:
            OK.check(f"B3 拒绝理由说清是「没有调用」：{why}", "没有调用" in detail)

    # ================= B2：换判据必须给理由 =================
    print("\n" + "=" * 74)
    print("[B2-1] 判据 A 执行失败 → 换成 B 但**不给理由** → 不得静默采纳")
    print("=" * 74)
    clean_workspace()
    a_fail = {"command": "import mod\nassert mod.f() == 1", "reason": "断言返回 1"}
    b_weak = {"command": "import mod\nassert mod.f() == 2", "reason": ""}
    report1, mem1, store1 = await run_case(
        [plan(a_fail), plan(b_weak, tasks=ROUND2_TASKS), done_decision(), SELF_REPORT_OK], tmp)
    crit1 = store1.saved("verify_criterion")
    for e in crit1:
        p = e.payload or {}
        print(f"  [{p.get('action')}] passed={p.get('passed')} "
              f"cmd={str(p.get('command'))[:40]!r} reason={str(p.get('reason'))[:40]!r} "
              f"prev_passed={p.get('previous_passed')}")
    OK.check("A 被判据采纳并**真的执行且失败**",
             any((e.payload or {}).get("action") == "executed"
                 and (e.payload or {}).get("passed") is False for e in crit1))
    OK.check("B 被拒绝（没给理由就不采纳）",
             any((e.payload or {}).get("action") == "rejected" for e in crit1))
    OK.check("拒绝理由说清是「换判据必须给理由」",
             any("换判据必须给理由" in str((e.payload or {}).get("reason"))
                 for e in crit1 if (e.payload or {}).get("action") == "rejected"))
    OK.check("B 出现在事件里（前端能看到候选本身）",
             any("mod.f() == 2" in str((e.payload or {}).get("command")) for e in crit1))
    OK.check("→ 本轮不得通过（不静默采纳）", report1.phase.value != "record")

    print("\n" + "=" * 74)
    print("[B2-2] 同样替换，但**给了理由** → 允许（正当替换要看得见）")
    print("=" * 74)
    clean_workspace()
    b_good = {"command": "import mod\nassert mod.f() == 2",
              "reason": "上一条断言写错了期望值（实现返回 2），修正为 2"}
    report2, mem2, store2 = await run_case(
        [plan(a_fail), plan(b_good, tasks=ROUND2_TASKS), done_decision(), SELF_REPORT_OK], tmp)
    crit2 = store2.saved("verify_criterion")
    for e in crit2:
        p = e.payload or {}
        print(f"  [{p.get('action')}] passed={p.get('passed')} "
              f"cmd={str(p.get('command'))[:36]!r} reason={str(p.get('reason'))[:44]!r} "
              f"prev={str(p.get('previous_command'))[:24]!r} prev_passed={p.get('previous_passed')}")
    OK.check("B 被采纳（给了理由）",
             any((e.payload or {}).get("action") == "adopted"
                 and "mod.f() == 2" in str((e.payload or {}).get("command"))
                 for e in crit2))
    OK.check("B 的理由进了事件",
             any("写错了期望值" in str((e.payload or {}).get("reason")) for e in crit2))
    OK.check("事件里带上了**前后关系**（previous_command / previous_passed）",
             any((e.payload or {}).get("previous_passed") is False
                 and "mod.f() == 1" in str((e.payload or {}).get("previous_command"))
                 for e in crit2))
    OK.check("B 执行通过 → phase=record", report2.phase.value == "record")
    print("\n  ★ B2 的验收原文：「事件流里能读到 A 的命令 + A 失败 + B 的命令 + B 的理由」")
    cmds = " | ".join(str((e.payload or {}).get("command")) for e in crit2)
    reasons = " | ".join(str((e.payload or {}).get("reason")) for e in crit2)
    OK.check("→ 四样都能读到",
             "mod.f() == 1" in cmds and "mod.f() == 2" in cmds
             and any((e.payload or {}).get("passed") is False for e in crit2)
             and "写错了期望值" in reasons)

    clean_workspace()
    shutil.rmtree(tmp, ignore_errors=True)
    return OK.report()


raise SystemExit(asyncio.run(main()))
