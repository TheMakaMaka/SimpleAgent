"""`P17` 机械取证：**pass 必须带机械证据**（`checked_by` + `evidence_kind`）。

不是单元测函数，而是走**生产构造路径**（`Orchestrator` + `CodingCycle` + `CheckPipeline`，
验证真的 `check_and_run` 子进程执行）跑出来的事实：

  [1] 正常通过 ⇒ 报告/事件里带 `checked_by=tool` + `evidence_kind=executed`
      + **真实退出码**（证明 `executed` 不是声明，是测出来的）；
  [2] ★ 反空洞：把**执行记录**（`exit_code`）抽掉 ⇒ 同一个 pass **立刻被拒**
      （`unsubstantiated-pass → invalid`，且不打检查点）—— 这正是统筹方实测的
      「8 个 pass 里 7 个没有执行证据」那条形状；
  [3] `artifacts`：输出根内的产物算证据，工作区里的逐条记原因（不静默）；
  [4] `static_declared`：必须带可复核理由；
  [5] `/profile.pass_evidence` 契约面（前端/统筹方一眼可读）。
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
from core import evidence as evidence_mod  # noqa: E402
from core import runtime  # noqa: E402
from core.decisions import FileDecisionStore  # noqa: E402
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


SELF = {"done": [], "not_done": [], "why": [], "reflections": [], "approach": [],
        "confidence": {"level": "low", "basis": ""}, "open_questions": [],
        "requirements": [], "claims": {}}
DONE = {"status": "done", "reasoning": "没有更多任务", "tasks": [], "files": [],
        "verify": {}, "final_answer": "完成"}


def plan(verify: dict, files: list) -> dict:
    return {"status": "continue", "reasoning": "先写实现再验证", "files": files,
            "tasks": [{"id": "t1", "description": "写 mod.py", "expected_output": "mod.py",
                       "tool_hint": ["write_file"], "context_refs": []}],
            "verify": verify, "final_answer": ""}


FILES = [{"path": "mod.py", "role": "实现", "symbols": ["f"]}]
VERIFY = {"command": "import mod\nassert mod.f() == 2", "reason": "断言返回 2"}


async def run_case(tmp, decisions, worker=None):
    store = RecStorage()
    orch = Orchestrator(ScriptedLLM(decisions), worker or ModWorker(),
                        pipeline=None, verify_command=None)
    cycle = CodingCycle(orchestrator=orch, worker=None, pipeline=CheckPipeline(),
                        max_attempts=1, verbose=False, storage=store, persist=True,
                        on_decision="auto",
                        decisions=DecisionManager(store=FileDecisionStore(root=tmp)))
    report, _mem = await cycle.run("实现 mod.f")
    return report, store


def show_case(tag: str, report, store: RecStorage) -> None:
    ends = store.saved("cycle_end")
    payload = (ends[-1].payload or {}) if ends else {}
    ev = report.evidence or {}
    print(f"  [{tag}] phase={report.phase.value} outcome={report.outcome} "
          f"kind={report.outcome_kind}")
    print(f"    verify.exit_code={((report.verify or {}).get('exit_code'))} "
          f"verify.passed={(report.verify or {}).get('passed')}")
    print(f"    evidence.checked_by={ev.get('checked_by')} "
          f"evidence.evidence_kind={ev.get('evidence_kind')}")
    print(f"    evidence.executed={ev.get('executed')}")
    print(f"    evidence.problems={ev.get('problems')}")
    print(f"    cycle_end.checked_by={payload.get('checked_by')} "
          f"cycle_end.evidence_kind={payload.get('evidence_kind')}")


async def main() -> int:
    tmp = tempfile.mkdtemp(prefix="p17_probe_")
    out_dir = runtime.output_root()
    os.makedirs(out_dir, exist_ok=True)
    probe_out = os.path.join(out_dir, "_p17_probe.txt")
    probe_ws_dir = os.path.join(runtime.workspace_root(), "_p17_probe")
    os.makedirs(probe_ws_dir, exist_ok=True)

    try:
        # ================= [1] 正常执行 → executed 证据（含真实退出码） =================
        print("=" * 74)
        print("[1] 生产路径：判据真的被执行 ⇒ evidence_kind=executed（带真实退出码）")
        print("=" * 74)
        clean_workspace()
        r1, s1 = await run_case(tmp, [plan(VERIFY, FILES), DONE, SELF])
        show_case("real", r1, s1)
        OK.check("★ 正常执行仍然 pass（门禁不是一律报红）",
                 r1.phase.value == "record" and r1.outcome == "pass")
        OK.check("证据类别 = executed，checked_by = tool",
                 (r1.evidence or {}).get("evidence_kind") == "executed"
                 and (r1.evidence or {}).get("checked_by") == "tool")
        OK.check("退出码是**真实子进程**测出来的（0）",
                 ((r1.verify or {}).get("exit_code") == 0)
                 and ((r1.evidence or {}).get("executed") or {}).get("exit_code") == 0)
        ends1 = s1.saved("cycle_end")
        OK.check("cycle_end 事件也带 checked_by/evidence_kind",
                 bool(ends1)
                 and (ends1[-1].payload or {}).get("evidence_kind") == "executed")

        # ================= [2] 反空洞：抽掉执行记录 =================
        print("\n" + "=" * 74)
        print("[2] ★ 反空洞：抽掉 exit_code（模拟执行记录缺失）⇒ 同一个 pass 被拒")
        print("=" * 74)
        orig = CheckPipeline.run_verify

        async def stripped(self, command, files=None):
            vr = await orig(self, command, files)
            if isinstance(vr.get("parsed"), dict):
                vr["parsed"] = {k: v for k, v in vr["parsed"].items()
                                if k != "exit_code"}
            return vr

        CheckPipeline.run_verify = stripped
        try:
            clean_workspace()
            r2, s2 = await run_case(tmp, [plan(VERIFY, FILES), DONE, SELF])
        finally:
            CheckPipeline.run_verify = orig
        show_case("no-exit-code", r2, s2)
        OK.check("★ 不再 pass（执行事实缺失）", r2.outcome != "pass")
        OK.check("结局 = invalid / unsubstantiated-pass",
                 r2.outcome == "invalid"
                 and r2.outcome_kind == evidence_mod.UNSUBSTANTIATED_KIND)
        OK.check("无效读数**不落检查点**（commit 为空）", not r2.commit)

        # ================= [3] artifacts：输出根内才算 =================
        print("\n" + "=" * 74)
        print("[3] artifacts 证据：输出根内算数；工作区里的逐条记原因（不静默）")
        print("=" * 74)
        with open(probe_out, "w", encoding="utf-8") as f:
            f.write("deliverable\n")
        dv_out = runtime.check_deliverables(["outputs/_p17_probe.txt"])
        ev_out = evidence_mod.build_evidence(None, dv_out)
        print(f"  输出根内 ⇒ kind={ev_out['evidence_kind']} artifacts={ev_out['artifacts']}")
        os.makedirs(probe_ws_dir, exist_ok=True)   # clean_workspace() 会清掉它，这里重建
        with open(os.path.join(probe_ws_dir, "draft.txt"), "w", encoding="utf-8") as f:
            f.write("draft\n")
        dv_ws = runtime.check_deliverables(["_p17_probe/draft.txt"])
        ev_ws = evidence_mod.build_evidence(None, dv_ws)
        print(f"  工作区里 ⇒ kind={ev_ws['evidence_kind']!r} "
              f"excluded={ev_ws['excluded_artifacts']}")
        OK.check("输出根内 ⇒ artifacts（tool）",
                 ev_out["evidence_kind"] == "artifacts"
                 and ev_out["checked_by"] == "tool")
        OK.check("工作区里的不算证据，但**逐条**记进 excluded_artifacts",
                 ev_ws["evidence_kind"] != "artifacts"
                 and any(x.get("reason") == "out-of-output-root"
                         for x in ev_ws["excluded_artifacts"]))

        # ================= [4] static_declared：理由必须可复核 =================
        print("\n" + "=" * 74)
        print("[4] static_declared：空理由 ⇒ 不成立；有理由 ⇒ checked_by=model")
        print("=" * 74)
        e_none = evidence_mod.build_evidence(None, None, static_reason="  ")
        e_decl = evidence_mod.build_evidence(None, None, static_reason="非代码交付物")
        print(f"  空理由 ⇒ kind={e_none['evidence_kind']!r} "
              f"allowed={evidence_mod.pass_allowed(e_none)[0]}")
        print(f"  有理由 ⇒ kind={e_decl['evidence_kind']} "
              f"checked_by={e_decl['checked_by']} reason={e_decl['static_declared']['reason']}")
        OK.check("空理由不产生证据且被拒",
                 e_none["evidence_kind"] == ""
                 and evidence_mod.pass_allowed(e_none)[0] is False)
        OK.check("有理由 ⇒ static_declared / checked_by=model（如实标注）",
                 e_decl["evidence_kind"] == "static_declared"
                 and e_decl["checked_by"] == "model"
                 and evidence_mod.pass_allowed(e_decl)[0] is True)

        # ================= [5] 契约面 =================
        print("\n" + "=" * 74)
        print("[5] /profile.pass_evidence 契约面（加性、可读）")
        print("=" * 74)
        desc = evidence_mod.describe()
        print(f"  required_on_pass = {desc['required_on_pass']}")
        print(f"  evidence_kinds   = {sorted(desc['evidence_kinds'])}")
        print(f"  gate             = {desc['gate']}")
        OK.check("契约面声明了 pass 的必需项与门禁",
                 desc["required_on_pass"] == ["checked_by", "evidence_kind"]
                 and set(desc["evidence_kinds"]) == set(evidence_mod.EVIDENCE_KINDS)
                 and bool(desc["gate"]))
        OK.check("硬规则单测两向都在：model+无类别 ⇒ 拒绝",
                 evidence_mod.pass_allowed(
                     {"checked_by": "model", "evidence_kind": ""})[0] is False)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(probe_ws_dir, ignore_errors=True)
        try:
            os.remove(probe_out)
        except OSError:
            pass

    return OK.report()


raise SystemExit(asyncio.run(main()))
