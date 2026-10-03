"""`TRANSPARENCY-BACKEND` C1 / C2：收尾自述 + **必须与机械事实交叉核对**。

为什么这个文件必须存在
----------------------
没有 C2，`self_report` 就是**第二个"模型自嗨"通道** —— 统筹方原话。
触发它的那次运行正是最好的样例：一场 `status=passed`，机械事实却是
"没跑过测试、没有报告、有个 `np` 未定义的文件"。
一个**被核对过**的自述会立刻暴露这个矛盾；**不被核对**的自述只会复述"任务完成"。

所以这里测的核心不是"自述写得好不好"，而是：
**模型撒谎时，`fact_check` 会不会红。** 以及它**不会**改判 cycle 结果。
"""

import asyncio
import json
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
from storage.store import Event  # noqa: E402

OK = Checker()


class StubWorker:
    """只回报"看过了"，不产出任何文件 —— 复刻那次"什么都没有"的运行。"""

    profile = None

    async def run(self, task, context):
        return TaskResult(task_id=task.id, ok=True,
                          output="工作区包含 notes.txt", artifacts=[], steps_used=1)


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
    """按脚本返回：前几条是编排器决策，最后一条是**自述**。"""

    profile = None

    def __init__(self, decisions: list[dict], self_report: dict | None):
        self.decisions = decisions
        self.self_report = self_report
        self.seen = 0
        self.self_report_calls = 0

    async def chat_json(self, messages):
        # 自述那一问的系统消息里带 SELF_REPORT 标记，据此分流
        text = json.dumps(messages, ensure_ascii=False)
        if "收尾自述" in text:
            self.self_report_calls += 1
            if isinstance(self.self_report, Exception):
                raise self.self_report
            return self.self_report if self.self_report is not None else {}
        d = self.decisions[min(self.seen, len(self.decisions) - 1)]
        self.seen += 1
        return d


class NoLLMOrchestrator(Orchestrator):
    """没有 llm 的编排器（复刻"自述生成失败"那一类环境）。"""

    def __init__(self):
        pass


#: 一次**什么都没做**的运行：没有交付物、没有验证结论、check 没跑。
PLAN_EMPTY = {
    "status": "continue", "reasoning": "先看看工作区",
    "files": [], "tasks": [{"id": "t1", "description": "列出工作区内容",
                            "tool_hint": ["list_workspace"], "context_refs": []}],
    "verify": {}, "final_answer": "",
}
DONE = {"status": "done", "reasoning": "没什么可做的", "tasks": [], "files": [],
        "verify": {}, "final_answer": "完成"}

#: ★ 撒谎的自述：声称产出了报告、验证通过、检查通过 —— 三样都与事实相反。
LYING = {
    "done": ["已生成项目分析报告 report.txt", "已通过验证", "检查通过"],
    "not_done": [],
    "why": [],
    "reflections": ["流程顺畅"],
    "approach": ["先列举再总结"],
    "confidence": {"level": "high", "basis": "任务全部完成"},
    "open_questions": [],
    "requirements": [
        {"text": "生成分析报告", "status": "done", "evidence": "report.txt"},
        {"text": "保证连通性", "status": "unknown", "evidence": ""},
    ],
    "claims": {"verify_passed": True, "check_passed": True, "artifacts": ["report.txt"]},
}

#: 诚实的自述：把"没做"写出来。
HONEST = {
    "done": ["列出了工作区内容"],
    "not_done": ["没有生成报告", "没有跑测试"],
    "why": ["这一轮只做了列举"],
    "reflections": ["应该先规划交付物"],
    "approach": ["先看现状"],
    "confidence": {"level": "low", "basis": "没有验证结论"},
    "open_questions": ["报告要写什么格式"],
    "requirements": [
        {"text": "生成分析报告", "status": "not_done", "evidence": ""},
    ],
    "claims": {"verify_passed": None, "check_passed": None, "artifacts": []},
}


async def run_case(decisions: list[dict], self_report, tmp: str, orchestrator=None):
    store = RecStorage()
    orch = orchestrator or Orchestrator(
        ScriptedLLM(decisions, self_report), worker=StubWorker(), pipeline=None)
    cycle = CodingCycle(orchestrator=orch, worker=None, pipeline=CheckPipeline(),
                        max_attempts=1, verbose=False, storage=store, persist=True,
                        on_decision="auto",
                        decisions=DecisionManager(store=FileDecisionStore(root=tmp)))
    report, memory = await cycle.run("列出工作区内容并生成一份分析报告")
    return report, memory, store


async def main() -> int:
    tmp = tempfile.mkdtemp(prefix="self_report_")

    # ================= C1：自述确实产出并进了报告/事件 =================
    print("=" * 74)
    print("[C1] 收尾自述：结构齐备、进报告、进事件")
    print("=" * 74)
    clean_workspace()
    report, memory, store = await run_case([PLAN_EMPTY, DONE], HONEST, tmp)
    sr = report.self_report or {}
    print(f"  phase={report.phase.value} self_report.ok={sr.get('ok')}")
    print(f"  done={sr.get('done')}")
    print(f"  not_done={sr.get('not_done')}")
    print(f"  confidence={sr.get('confidence')}")
    OK.check("self_report 出现在 CycleReport 里（C1 要求的报告字段）",
             "self_report" in report.to_dict() and sr)
    OK.check("七个必需字段齐备",
             all(k in sr for k in ("done", "not_done", "why", "reflections",
                                   "approach", "confidence", "open_questions")))
    OK.check("自述生成成功（ok=True、无 error）",
             sr.get("ok") is True and not sr.get("error"))
    events = store.saved("self_report")
    print(f"  self_report 事件 {len(events)} 条")
    OK.check("发出了 self_report 事件", len(events) == 1)
    OK.check("事件里带上 done / not_done / fact_check",
             bool(events) and all(k in (events[0].payload or {})
                                  for k in ("done", "not_done", "fact_check", "confidence")))
    OK.check("未取代机械字段（verify / check / manifest 照旧在）",
             all(k in report.to_dict() for k in ("verify", "check", "manifest")))

    # ================= C2：撒谎必须被标出来 =================
    print("\n" + "=" * 74)
    print("[C2] ★ 模型在 done 里谎报 → fact_check 必须标出矛盾")
    print("=" * 74)
    clean_workspace()
    report2, _m2, store2 = await run_case([PLAN_EMPTY, DONE], LYING, tmp)
    fc = (report2.self_report or {}).get("fact_check") or {}
    print(f"  phase={report2.phase.value}  （自述不影响它）")
    print(f"  机械事实: verify={report2.verify} check={report2.check}")
    for c in fc.get("contradictions") or []:
        print(f"  [矛盾/{c.get('kind')}] {c.get('claim')} ←→ {c.get('fact')}")
    for u in fc.get("unmentioned") or []:
        print(f"  [未提及] {u}")
    kinds = {c.get("kind") for c in fc.get("contradictions") or []}
    OK.check("★ 谎报「已产出 report.txt」被标出（artifact-missing）",
             "artifact-missing" in kinds)
    OK.check("★ 谎报「验证通过」被标出（verify-claim-vs-fact）",
             "verify-claim-vs-fact" in kinds)
    OK.check("★ 谎报「检查通过」被标出（check-claim-vs-fact）",
             "check-claim-vs-fact" in kinds)
    OK.check("★ 目标要求「保证连通性」既没 done 也没 not_done → 标为未提及",
             any("保证连通性" in u for u in fc.get("unmentioned") or []))
    OK.check("矛盾里带了「自述说了什么 / 机械事实是什么」两栏",
             all(c.get("claim") and c.get("fact") for c in fc.get("contradictions") or []))
    OK.check("矛盾也进了 self_report 事件（前端拿得到）",
             bool(store2.saved("self_report"))
             and bool((store2.saved("self_report")[0].payload or {})
                      .get("fact_check", {}).get("contradictions")))
    OK.check("★ 自述**不改判定**：phase 仍由机械事实决定（不是 record）",
             report2.phase.value != "record")

    # ================= C2 正向对照：诚实自述不该被冤枉 =================
    print("\n" + "=" * 74)
    print("[C2+] 正向对照：诚实的自述 + 真实的产出 → 没有矛盾")
    print("=" * 74)
    clean_workspace()
    with open(os.path.join(WS, "notes.txt"), "w", encoding="utf-8") as f:
        f.write("已有文件\n")
    honest_about_notes = dict(HONEST)
    honest_about_notes["claims"] = {
        "verify_passed": None, "check_passed": None, "artifacts": ["notes.txt"]}
    report3, _m3, _s3 = await run_case([PLAN_EMPTY, DONE], honest_about_notes, tmp)
    fc3 = (report3.self_report or {}).get("fact_check") or {}
    print(f"  矛盾 {len(fc3.get('contradictions') or [])} 条 / "
          f"未提及 {len(fc3.get('unmentioned') or [])} 条")
    OK.check("真实存在的产出不被误报为矛盾",
             not any(c.get("kind") == "artifact-missing"
                     for c in fc3.get("contradictions") or []))
    OK.check("有正面证据记录（notes 里有该文件）",
             any("notes.txt" in n for n in fc3.get("notes") or []))

    # ================= C1 的失败路径必须是显式的 =================
    print("\n" + "=" * 74)
    print("[C1-失败] 拿不到自述 → 显式记为 ok=false + error（不静默、不改判定）")
    print("=" * 74)
    clean_workspace()
    report4, _m4, store4 = await run_case(
        [PLAN_EMPTY, DONE], RuntimeError("模型超时"), tmp)
    sr4 = report4.self_report or {}
    print(f"  ok={sr4.get('ok')} error={str(sr4.get('error'))[:80]}")
    print(f"  fact_check.checked={ (sr4.get('fact_check') or {}).get('checked') }")
    OK.check("自述失败被显式记录（ok=false + error）",
             sr4.get("ok") is False and bool(sr4.get("error")))
    OK.check("仍然发出了 self_report 事件（失败也要留痕）",
             len(store4.saved("self_report")) == 1)
    OK.check("失败也不改判定（phase 不变）", report4.phase.value != "record")

    # 编排器没有 llm（复刻老对象的形态）→ 同样只降级
    print("\n" + "=" * 74)
    print("[C1-失败2] 编排器没有 llm（老对象/假编排器）→ 只降级，不抛异常")
    print("=" * 74)
    clean_workspace()
    fake = NoLLMOrchestrator()
    fake.pipeline = None
    fake.verify_command = None
    fake.context_provider = None
    fake.max_rounds = 3
    fake.max_same_task = 2
    fake.limits = type("L", (), {"max_rounds": 3, "max_same_task": 2,
                                 "orchestrator_prompt_chars": 1000})()
    fake.llm = None

    async def _fake_run(goal):
        from core import OrchestratorResult, SharedMemory
        mem = SharedMemory(goal=goal)
        return OrchestratorResult(ok=False, answer="没有可执行任务", memory=mem)

    fake.run = _fake_run
    store5 = RecStorage()
    cycle = CodingCycle(orchestrator=fake, worker=None, pipeline=CheckPipeline(),
                        max_attempts=1, verbose=False, storage=store5, persist=True,
                        on_decision="auto",
                        decisions=DecisionManager(store=FileDecisionStore(root=tmp)))
    report5, _m5 = await cycle.run("任意目标")
    sr5 = report5.self_report or {}
    print(f"  ok={sr5.get('ok')} error={str(sr5.get('error'))[:80]}")
    OK.check("没有 llm → 显式记因，不抛异常",
             sr5.get("ok") is False and "没有可用的 LLM" in str(sr5.get("error")))

    clean_workspace()
    shutil.rmtree(tmp, ignore_errors=True)
    return OK.report()


raise SystemExit(asyncio.run(main()))
