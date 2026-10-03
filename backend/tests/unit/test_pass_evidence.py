"""`P17` 门禁：**pass 必须带机械证据**（`checked_by` + `evidence_kind`）。

契约 `pass_evidence`（加性）。规则（工作单 P17）：

  1. 每次 **pass** 必须带 `checked_by`（tool/model）+ `evidence_kind`，且按类别给结构：
     `executed{command, exit_code}` / `artifacts{path, sha256, size}` /
     `static_declared{reason}`；
  2. **`checked_by == model` 且无 `evidence_kind` ⇒ 结局不得为 `pass`**
     （记 `invalid` / `unsubstantiated-pass`）；
  3. `artifacts` 的路径**必须在输出根内**（与 P14 一致）；
  4. `static_declared` 必须带**可复核的理由**。

反空洞（"不是把检查关掉"）：
  · 正常执行（有退出码）**必须仍然 pass**，且证据类别 = `executed`（不是一律报红）；
  · 抽掉执行记录（没有 `exit_code`）⇒ **同一个 pass 立刻被判 invalid** ——
    这正是统筹方实测的形状（8 个 pass 里 7 个没有执行证据）；
  · `pass_allowed` 对三种类别的**结构空洞**各自变红（不是只看类别名）。
"""

import asyncio
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import Checker  # noqa: E402

from core import CheckPipeline, CodingCycle, OrchestratorResult, SharedMemory  # noqa: E402
from core import Task, TaskResult  # noqa: E402
from core import evidence as ev  # noqa: E402
from core import outcome as outcome_mod  # noqa: E402
from core import runtime  # noqa: E402
from storage.store import Event  # noqa: E402

c = Checker()


class RecStorage:
    def __init__(self):
        self.events: list[Event] = []

    def append_event(self, event: Event) -> None:
        self.events.append(event)

    def get_events(self, cycle_id=None):
        return list(self.events)

    def saved(self, kind: str):
        return [e for e in self.events if e.kind == kind]


class StubOrch:
    """脚本化编排器：给一个**已经得出验证结论**的记忆，直接进入 pass 判定。"""

    def __init__(self, verify_state: dict | None):
        self.pipeline = None
        self.verify_command = None
        self.context_provider = None
        self._vs = verify_state

    async def run(self, goal: str):
        mem = SharedMemory(goal=goal)
        # 至少一条任务记录：否则主流程会在 "no-tasks" 就结束，走不到 verify/pass。
        mem.record(
            Task(id="t1", description="实现 mod.f"),
            TaskResult(task_id="t1", ok=True, output="done", steps_used=1),
        )
        if self._vs is not None:
            mem.verify_state = dict(self._vs)
        return OrchestratorResult(ok=True, answer="stub", memory=mem,
                                  verify_command=None, declared_files=None)


def cycle_for(orch, storage):
    return CodingCycle(orchestrator=orch, worker=None,          # type: ignore[arg-type]
                       pipeline=CheckPipeline(), storage=storage, persist=True,
                       verbose=False, max_attempts=1, checkpoint_prefer="none")


async def main() -> int:
    tmp = os.path.join(runtime.workspace_root(), "_p17_probe")
    os.makedirs(tmp, exist_ok=True)
    out_dir = runtime.output_root()
    os.makedirs(out_dir, exist_ok=True)

    try:
        # ================= ① 纯判据：硬规则 + 三种类别的结构 =================
        print("=" * 74)
        print("[1] ★ 硬规则：checked_by=model 且无 evidence_kind ⇒ **不得 pass**")
        print("=" * 74)
        forbidden = {"checked_by": "model", "evidence_kind": ""}
        ok, why = ev.pass_allowed(forbidden)
        print(f"  pass_allowed({forbidden}) = {ok}")
        print(f"  why = {why}")
        c.check("不成立（这是 P17 要求 2 的原话）", ok is False)
        c.check("理由点明『model + 无 evidence_kind』",
                "model" in why and "evidence_kind" in why)

        print("\n" + "=" * 74)
        print("[2] 三种类别**齐全**时都允许；结构有空洞时逐条变红")
        print("=" * 74)
        good = {
            "executed": {"checked_by": "tool", "evidence_kind": "executed",
                         "executed": {"command": "python v.py", "exit_code": 0}},
            "artifacts": {"checked_by": "tool", "evidence_kind": "artifacts",
                          "artifacts": [{"path": "outputs/a.txt", "sha256": "ab",
                                         "size": 1}]},
            "static_declared": {"checked_by": "model",
                                "evidence_kind": "static_declared",
                                "static_declared": {"reason": "非代码交付物"}},
        }
        for kind, sample in good.items():
            g_ok, g_why = ev.pass_allowed(sample)
            print(f"  {kind:<16} ⇒ {g_ok} {g_why}")
            c.check(f"{kind} 结构齐全 ⇒ 允许", g_ok is True)
        holes = {
            "executed 缺 exit_code": {"checked_by": "tool", "evidence_kind": "executed",
                                      "executed": {"command": "python v.py"}},
            "executed 缺 command": {"checked_by": "tool", "evidence_kind": "executed",
                                    "executed": {"exit_code": 0}},
            "artifacts 为空": {"checked_by": "tool", "evidence_kind": "artifacts",
                               "artifacts": []},
            "static_declared 缺理由": {"checked_by": "model",
                                       "evidence_kind": "static_declared",
                                       "static_declared": {"reason": "  "}},
        }
        for name, sample in holes.items():
            h_ok, _h_why = ev.pass_allowed(sample)
            print(f"  {name:<24} ⇒ {h_ok}")
            c.check(f"{name} ⇒ 拒绝", h_ok is False)

        print("\n" + "=" * 74)
        print("[3] 结局映射：unsubstantiated-pass 已登记为 invalid（不是静默默认）")
        print("=" * 74)
        mapped = outcome_mod.KIND_TO_OUTCOME.get(ev.UNSUBSTANTIATED_KIND)
        print(f"  {ev.UNSUBSTANTIATED_KIND} → {mapped}")
        c.check("登记为 invalid", mapped == "invalid")
        c.check("在四值之内", outcome_mod.outcome_of(ev.UNSUBSTANTIATED_KIND)
                in outcome_mod.OUTCOMES)

        # ================= ② build_evidence 的阶梯 =================
        print("\n" + "=" * 74)
        print("[4] executed 证据要求**退出码真的被记录**（有命令 ≠ 执行过）")
        print("=" * 74)
        no_code = ev.build_evidence({"passed": True, "command": "python v.py",
                                     "source": "model"}, None)
        print(f"  evidence_kind={no_code['evidence_kind']!r} "
              f"problems={no_code['problems']}")
        c.check("没有 exit_code ⇒ 不产生 executed 证据",
                no_code["evidence_kind"] != "executed")
        c.check("problems 如实说明『没有退出码』",
                any("退出码" in p for p in no_code["problems"]))
        with_code = ev.build_evidence({"passed": True, "command": "python v.py",
                                       "exit_code": 7, "expect_exit": 7,
                                       "source": "caller"}, None)
        print(f"  有 exit_code ⇒ kind={with_code['evidence_kind']} "
              f"executed={with_code['executed']}")
        c.check("有 exit_code ⇒ executed（checked_by=tool）",
                with_code["evidence_kind"] == "executed"
                and with_code["checked_by"] == "tool")
        c.check("退出码与期望值都进了证据",
                with_code["executed"]["exit_code"] == 7
                and with_code["executed"]["expect_exit"] == 7)

        print("\n" + "=" * 74)
        print("[5] artifacts 证据：**输出根内**才算；工作区里的逐条记原因（不静默）")
        print("=" * 74)
        abs_out = os.path.join(out_dir, "_p17_evidence.txt")
        with open(abs_out, "w", encoding="utf-8") as f:
            f.write("deliverable\n")
        dv_out = runtime.check_deliverables(["outputs/_p17_evidence.txt"])
        ev_out = ev.build_evidence(None, dv_out)
        print(f"  输出根内 ⇒ kind={ev_out['evidence_kind']} "
              f"artifacts={ev_out['artifacts']}")
        c.check("输出根内的产物 ⇒ artifacts 证据",
                ev_out["evidence_kind"] == "artifacts"
                and ev_out["checked_by"] == "tool")
        c.check("带 {path, sha256, size}",
                bool(ev_out["artifacts"])
                and all(k in ev_out["artifacts"][0] for k in ("path", "sha256", "size")))

        abs_ws = os.path.join(runtime.workspace_root(), "_p17_probe", "ws.txt")
        with open(abs_ws, "w", encoding="utf-8") as f:
            f.write("draft\n")
        dv_ws = runtime.check_deliverables(["_p17_probe/ws.txt"])
        ev_ws = ev.build_evidence(None, dv_ws)
        print(f"  工作区里 ⇒ kind={ev_ws['evidence_kind']!r} "
              f"excluded={ev_ws['excluded_artifacts']}")
        c.check("工作区里的产物**不算**交付证据", ev_ws["evidence_kind"] != "artifacts")
        c.check("但它被逐条记进 excluded_artifacts（不是静默消失）",
                any(x.get("reason") == "out-of-output-root"
                    for x in ev_ws["excluded_artifacts"]))

        print("\n" + "=" * 74)
        print("[6] static_declared：理由为空 ⇒ 不算证据；有理由才算")
        print("=" * 74)
        ev_none = ev.build_evidence(None, None, static_reason="   ")
        ev_decl = ev.build_evidence(None, None, static_reason="本次交付物是文档")
        print(f"  空理由 ⇒ kind={ev_none['evidence_kind']!r}")
        print(f"  有理由 ⇒ kind={ev_decl['evidence_kind']} "
              f"reason={ev_decl['static_declared']['reason']}")
        c.check("空理由不产生证据", ev_none["evidence_kind"] == "")
        c.check("有理由 ⇒ static_declared（checked_by=model，如实标注）",
                ev_decl["evidence_kind"] == "static_declared"
                and ev_decl["checked_by"] == "model")
        c.check("空理由时 pass_allowed 拒绝",
                ev.pass_allowed(ev_none)[0] is False)

        # ================= ③ 端到端：门禁真的接在 pass 出口上 =================
        print("\n" + "=" * 74)
        print("[7] ★ 端到端：正常执行（有退出码）⇒ 仍然 pass，证据=executed")
        print("=" * 74)
        store_ok = RecStorage()
        vs_ok = {"passed": True, "detail": "ok", "command": "python v.py",
                 "source": "model", "artifact_hashes": {}, "cwd": "",
                 "exit_code": 0, "expect_exit": 0}
        r_ok, _m = await cycle_for(StubOrch(vs_ok), store_ok).run("实现 mod.f")
        ends_ok = store_ok.saved("cycle_end")
        payload = (ends_ok[-1].payload or {}) if ends_ok else {}
        print(f"  phase={r_ok.phase.value} outcome={r_ok.outcome} "
              f"kind={(r_ok.evidence or {}).get('evidence_kind')}")
        print(f"  cycle_end.checked_by={payload.get('checked_by')} "
              f"cycle_end.evidence_kind={payload.get('evidence_kind')}")
        c.check("★ 仍然 pass（门禁不是一律报红）", r_ok.phase.value == "record"
                and r_ok.outcome == "pass")
        c.check("报告里证据类别 = executed",
                (r_ok.evidence or {}).get("evidence_kind") == "executed")
        c.check("cycle_end 事件也带 checked_by / evidence_kind（可审计）",
                payload.get("checked_by") == "tool"
                and payload.get("evidence_kind") == "executed"
                and isinstance(payload.get("evidence"), dict))

        print("\n" + "=" * 74)
        print("[8] ★ 反空洞：抽掉**执行记录**（没有 exit_code）⇒ 同一个 pass 被判 invalid")
        print("=" * 74)
        store_bad = RecStorage()
        vs_bad = {"passed": True, "detail": "ok", "command": "python v.py",
                  "source": "model", "artifact_hashes": {}, "cwd": ""}  # ← 无 exit_code
        r_bad, _m2 = await cycle_for(StubOrch(vs_bad), store_bad).run("实现 mod.f")
        print(f"  phase={r_bad.phase.value} outcome={r_bad.outcome} "
              f"kind={r_bad.outcome_kind}")
        print(f"  error={str(r_bad.error)[:140]}")
        c.check("★ 不再 pass（执行事实缺失）", r_bad.outcome != "pass")
        c.check("结局 = invalid / unsubstantiated-pass（契约允许的两值之一）",
                r_bad.outcome == "invalid"
                and r_bad.outcome_kind == ev.UNSUBSTANTIATED_KIND)
        c.check("phase=failed，且**没有打检查点**（无效读数不落提交）",
                r_bad.phase.value == "failed" and not r_bad.commit)

        print("\n" + "=" * 74)
        print("[9] 调用方声明静态理由 + 无执行记录 ⇒ 走 static_declared（第三档真的接上了）")
        print("=" * 74)
        store_sd = RecStorage()
        r_sd, _m3 = await cycle_for(StubOrch(vs_bad), store_sd).run(
            "写说明文档", static_reason="本次交付物是说明文档，不是代码，没有可执行判据"
        )
        print(f"  phase={r_sd.phase.value} outcome={r_sd.outcome} "
              f"kind={(r_sd.evidence or {}).get('evidence_kind')}")
        c.check("静态交付物 + 可复核理由 ⇒ 允许 pass",
                r_sd.outcome == "pass"
                and (r_sd.evidence or {}).get("evidence_kind") == "static_declared")
        c.check("checked_by 如实标注为 model（不是伪装成 tool）",
                (r_sd.evidence or {}).get("checked_by") == "model")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            os.remove(os.path.join(out_dir, "_p17_evidence.txt"))
        except OSError:
            pass

    return c.report()


raise SystemExit(asyncio.run(main()))
