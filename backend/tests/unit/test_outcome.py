"""`TRANSPARENCY2-BACKEND` P1：**结局四值 + 判据来源进判定链**（工作单 D19）。

为什么这是最优先的一条（统筹方原话）：

> 没有 `invalid`，"任务/判据写错了"会被记成"模型不行"，**污染整个能力画像**；
> 没有 `abstain`，用户要的「知道**不能做什么**」**无处安放**。

这个文件把四值**各构造一次**跑出来（不是单元测函数，而是走生产构造路径的真 cycle）：

| 构造 | 期望结局 |
|---|---|
| 没有任何可用判据（自拟判据被拒） | **abstain**（不是 fail，更不是 pass） |
| **模型自拟**判据引用了不存在的符号 | **fail**（`delivery-gap`；P13：判据是被测行为的一部分） |
| **调用方**判据引用了不存在的符号 | **invalid**（`criterion-broken`；P13：工装的问题，只此一种） |
| 判据真跑过、真断言失败 | **fail** |
| 判据真的通过 | **pass**，且 `criterion_source=model` |
| **调用方**给判据并通过 | **pass**，但 `criterion_trust=caller-authoritative` —— **与上一条不同形** |

> ★ **P13（用户 2026-10-03 裁决 A9②）**：`invalid` **只**留给 `caller` 的坏判据。
> 本文件 [2] 原先把"模型自拟的坏判据"断言成 `invalid` —— 那正是被裁决改掉的旧行为，
> 现改为 `fail`，并用 [2b] 把 caller 的 `invalid` 补回来（**两向都在红**）。
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
from core.outcome import KIND_TO_OUTCOME, OUTCOMES  # noqa: E402
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

    def __init__(self, decisions):
        self.decisions = decisions
        self.seen = 0

    async def chat_json(self, messages):
        d = self.decisions[min(self.seen, len(self.decisions) - 1)]
        self.seen += 1
        return d


class ModWorker:
    profile = None

    def __init__(self, body="def f():\n    return 2\n"):
        self.body = body

    async def run(self, task, context):
        with open(os.path.join(WS, "mod.py"), "w", encoding="utf-8") as f:
            f.write(self.body)
        return TaskResult(task_id=task.id, ok=True, output="已写入 mod.py",
                          artifacts=[Artifact(key=f"{task.id}_f", kind="file",
                                              path="mod.py")],
                          steps_used=1)


class StubWorker:
    profile = None

    async def run(self, task, context):
        return TaskResult(task_id=task.id, ok=True, output="看了一下", artifacts=[],
                          steps_used=1)


SELF = {"done": [], "not_done": [], "why": [], "reflections": [], "approach": [],
        "confidence": {"level": "low", "basis": ""}, "open_questions": [],
        "requirements": [], "claims": {}}


def plan(verify: dict, files: list | None = None) -> dict:
    return {
        "status": "continue", "reasoning": "先写实现再验证",
        "files": files if files is not None else
        [{"path": "mod.py", "role": "实现", "symbols": ["f"]}],
        "tasks": [{"id": "t1", "description": "写 mod.py", "expected_output": "mod.py",
                   "tool_hint": ["write_file"], "context_refs": []}],
        "verify": verify, "final_answer": "",
    }


DONE = {"status": "done", "reasoning": "没有更多任务", "tasks": [], "files": [],
        "verify": {}, "final_answer": "完成"}


async def run_case(decisions, tmp, worker=None, caller=None):
    store = RecStorage()
    orch = Orchestrator(ScriptedLLM(decisions), worker or ModWorker(),
                        pipeline=None, verify_command=None)
    cycle = CodingCycle(orchestrator=orch, worker=None, pipeline=CheckPipeline(),
                        max_attempts=1, verbose=False, storage=store, persist=True,
                        on_decision="auto",
                        decisions=DecisionManager(store=FileDecisionStore(root=tmp)))
    vc = None
    if caller:
        from core import VerifyCommand
        vc = VerifyCommand(command=caller, reason="调用方给的")
    report, memory = await cycle.run("实现 mod.f", verify_command=vc)
    return report, memory, store


async def main() -> int:
    tmp = tempfile.mkdtemp(prefix="outcome_")

    print("=" * 74)
    print("[0] 四值的**完备性**：每种原因种类都映射到四值之一，没有静默默认")
    print("=" * 74)
    bad = [k for k, v in KIND_TO_OUTCOME.items() if v not in OUTCOMES]
    print(f"  已登记原因种类 {len(KIND_TO_OUTCOME)} 个：{sorted(KIND_TO_OUTCOME)}")
    OK.check("每个原因种类都映射到 pass/fail/abstain/invalid 之一", not bad)

    # ---------- abstain ----------
    print("\n" + "=" * 74)
    print("[1] 没有可用判据（自拟判据被拒）→ **abstain**")
    print("=" * 74)
    clean_workspace()
    r1, _m1, _s1 = await run_case(
        [plan({"command": "print('PASS')", "reason": "无报错即成功"}, files=[]),
         DONE, SELF], tmp, worker=StubWorker())
    v1 = r1.verdict or {}
    print(f"  phase={r1.phase.value} outcome={r1.outcome} kind={r1.outcome_kind}")
    print(f"  reason={r1.outcome_reason[:100]}")
    print(f"  trust={v1.get('criterion_trust')} independent={v1.get('criterion_independent')}")
    OK.check("★ 结局是 abstain（不是 fail、更不是 pass）", r1.outcome == "abstain")
    OK.check("带可读理由", bool(r1.outcome_reason))
    OK.check("phase 仍是 failed（phase 与 outcome 是两个维度）",
             r1.phase.value == "failed")

    # ---------- fail：模型自拟的坏判据（P13） ----------
    print("\n" + "=" * 74)
    print("[2] **模型自拟**判据引用了不存在的符号 → **fail**（P13：不是 invalid）")
    print("=" * 74)
    clean_workspace()
    r2, _m2, _s2 = await run_case(
        [plan({"command": "import mod\nassert mod.missing_fn()",
               "reason": "调用一个我以为是这个名的函数"}), DONE, SELF], tmp)
    print(f"  phase={r2.phase.value} outcome={r2.outcome} kind={r2.outcome_kind}")
    print(f"  verify.source={str((r2.verify or {}).get('source'))}")
    print(f"  error={str(r2.error)[:160]}")
    OK.check("★ 结局是 fail（判据是模型写的 ⇒ 被测行为）", r2.outcome == "fail")
    OK.check("原因种类 = delivery-gap（**不新造结局**）",
             r2.outcome_kind == "delivery-gap")

    # ---------- invalid：**调用方**的坏判据（P13 的唯一 invalid 来源） ----------
    print("\n" + "=" * 74)
    print("[2b] **调用方**判据引用了不存在的符号 → **invalid**（唯一允许 invalid 的情形）")
    print("=" * 74)
    clean_workspace()
    r2b, _m2b, _s2b = await run_case(
        [plan({"command": "import mod\nassert mod.f() == 2", "reason": "x"}),
         DONE, SELF], tmp, caller="import mod\nassert mod.missing_fn()")
    print(f"  phase={r2b.phase.value} outcome={r2b.outcome} kind={r2b.outcome_kind}")
    print(f"  verify.source={str((r2b.verify or {}).get('source'))}")
    print(f"  error={str(r2b.error)[:160]}")
    OK.check("★ 结局是 invalid（工装的问题，不能算模型头上）",
             r2b.outcome == "invalid")
    OK.check("原因种类 = criterion-broken", r2b.outcome_kind == "criterion-broken")
    OK.check("错误文案点出这次读数 invalid",
             "invalid" in str(r2b.error))

    # ---------- fail ----------
    print("\n" + "=" * 74)
    print("[3] 判据真跑过、真断言失败 → **fail**")
    print("=" * 74)
    clean_workspace()
    r3, _m3, _s3 = await run_case(
        [plan({"command": "import mod\nassert mod.f() == 1", "reason": "断言返回 1"}),
         DONE, SELF], tmp)
    print(f"  phase={r3.phase.value} outcome={r3.outcome} kind={r3.outcome_kind}")
    print(f"  verify.detail={str((r3.verify or {}).get('detail'))[:80]}")
    OK.check("★ 结局是 fail", r3.outcome == "fail")
    OK.check("原因种类 = verify-failed", r3.outcome_kind == "verify-failed")

    # ---------- pass（模型自拟） ----------
    print("\n" + "=" * 74)
    print("[4] 判据通过 → **pass**，且判据来源可辨（model）")
    print("=" * 74)
    clean_workspace()
    r4, _m4, s4 = await run_case(
        [plan({"command": "import mod\nassert mod.f() == 2", "reason": "断言返回 2"}),
         DONE, SELF], tmp)
    v4 = r4.verdict or {}
    print(f"  phase={r4.phase.value} outcome={r4.outcome}")
    print(f"  source={v4.get('criterion_source')} trust={v4.get('criterion_trust')} "
          f"independent={v4.get('criterion_independent')}")
    OK.check("★ 结局是 pass", r4.outcome == "pass")
    OK.check("判据来源 = model（不是空）", v4.get("criterion_source") == "model")
    OK.check("★ 可信档位 = model-self-authored（**与调用方判据不同形**）",
             v4.get("criterion_trust") == "model-self-authored")
    OK.check("自拟判据不算「独立」", v4.get("criterion_independent") is False)
    ends = s4.saved("cycle_end")
    print(f"  cycle_end 事件 {len(ends)} 条，最后一条 outcome="
          f"{(ends[-1].payload or {}).get('outcome') if ends else None}")
    OK.check("cycle_end 事件里带 outcome（前端一眼可读）",
             bool(ends) and (ends[-1].payload or {}).get("outcome") == "pass")

    # ---------- pass（调用方判据）—— 与上一条**不同形** ----------
    print("\n" + "=" * 74)
    print("[5] 调用方给判据并通过 → pass，但档位是 caller-authoritative")
    print("=" * 74)
    clean_workspace()
    r5, _m5, _s5 = await run_case(
        [plan({"command": "import mod\nassert mod.f() == 2", "reason": "x"}),
         DONE, SELF], tmp, caller="print('PASS')")
    v5 = r5.verdict or {}
    print(f"  phase={r5.phase.value} outcome={r5.outcome} "
          f"source={v5.get('criterion_source')} trust={v5.get('criterion_trust')}")
    OK.check("仍然是 pass", r5.outcome == "pass")
    OK.check("★ 来源 = caller、档位 = caller-authoritative",
             v5.get("criterion_source") == "caller"
             and v5.get("criterion_trust") == "caller-authoritative")
    OK.check("★ 与模型自拟同分不同形（trust 不同、independent=True）",
             v5.get("criterion_trust") != v4.get("criterion_trust")
             and v5.get("criterion_independent") is True)
    OK.check("报告里有 outcome / outcome_reason / verdict 三个加性字段",
             all(k in r5.to_dict() for k in ("outcome", "outcome_reason", "verdict")))

    clean_workspace()
    shutil.rmtree(tmp, ignore_errors=True)
    return OK.report()


raise SystemExit(asyncio.run(main()))
