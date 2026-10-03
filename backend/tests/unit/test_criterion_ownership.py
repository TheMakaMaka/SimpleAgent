"""P13 门禁：verify 失败的归因**要看判据是谁写的**（用户 2026-10-03 裁决 A9②）。

规则（契约 `criterion_ownership`）：
  · 判据出自 `caller` ⇒ 允许 `criterion-broken → invalid`（那是**测量工装**的问题）；
  · 模型自拟 ⇒ 走**已现成**的 `delivery-gap → fail`（判据是被测行为的一部分）。

方向：**这不是放宽，是收紧** —— 少一批「无可奉告」，多一批「模型没做到」。

反空洞（两向都要红）：
  · caller 的坏判据**必须仍然**是 invalid（不能把 caller 的工装问题算到模型头上）；
  · 模型自拟的坏判据**必须**是 fail（不能继续冲淡能力画像）；
  · 没有 blocking 的普通断言失败仍是 `verify-failed`（这条路径不许被误改）。
"""

import asyncio
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import Checker  # noqa: E402

from core import (  # noqa: E402
    CheckPipeline, CodingCycle, OrchestratorResult, SharedMemory, Task, TaskResult,
)
from storage.store import Event  # noqa: E402

c = Checker()

#: 实测里模型自拟的那条坏判据（引用了自己从没交付的符号）
BAD_CMD = "assert ant_colony.generate_obstacles(1)"


class RecStorage:
    def __init__(self):
        self.events: list[Event] = []

    def append_event(self, event: Event) -> None:
        self.events.append(event)

    def get_events(self, cycle_id=None):
        return list(self.events)


class StubOrch:
    """给一个「已经跑过验证且失败」的记忆，直接进入 P13 的归因分支。"""

    def __init__(self, verify_state: dict):
        self.pipeline = None
        self.verify_command = None
        self.context_provider = None
        self._vs = dict(verify_state)

    async def run(self, goal: str):
        mem = SharedMemory(goal=goal)
        mem.record(
            Task(id="t1", description="实现 ant_colony"),
            TaskResult(task_id="t1", ok=True, output="done", steps_used=1),
        )
        mem.verify_state = dict(self._vs)
        return OrchestratorResult(ok=True, answer="stub", memory=mem,
                                  verify_command=None, declared_files=None)


async def run_case(source: str, command: str, detail: str):
    vs = {"passed": False, "detail": detail, "command": command,
          "source": source, "artifact_hashes": {}, "cwd": ""}
    cyc = CodingCycle(orchestrator=StubOrch(vs), worker=None,   # type: ignore[arg-type]
                      pipeline=CheckPipeline(), storage=RecStorage(),
                      persist=True, verbose=False, max_attempts=1,
                      checkpoint_prefer="none")
    report, _mem = await cyc.run("实现 ant_colony")
    return report


async def main() -> int:
    print("=" * 74)
    print("[1] 模型自拟判据 + 引用未交付符号 ⇒ **fail / delivery-gap**（本轮修的）")
    print("=" * 74)
    r_model = await run_case("model", BAD_CMD, "NameError: name 'ant_colony' is not defined")
    print(f"  outcome={r_model.outcome} kind={r_model.outcome_kind}")
    print(f"  error={r_model.error}")
    c.check("结局是 fail（不是 invalid）", r_model.outcome == "fail")
    c.check("原因是 delivery-gap（已现成的档位，不新造结局）",
            r_model.outcome_kind == "delivery-gap")
    c.check("可读理由点明『模型自拟』", "模型自拟" in (r_model.error or ""))
    c.check("verdict.criterion_source == model",
            (r_model.verdict or {}).get("criterion_source") == "model")

    print("\n" + "=" * 74)
    print("[2] caller 判据 + 同样的引用错 ⇒ **invalid / criterion-broken**（不变）")
    print("=" * 74)
    r_caller = await run_case("caller", BAD_CMD, "NameError: name 'ant_colony' is not defined")
    print(f"  outcome={r_caller.outcome} kind={r_caller.outcome_kind}")
    c.check("结局是 invalid（工装的问题，不能算模型头上）",
            r_caller.outcome == "invalid")
    c.check("原因是 criterion-broken", r_caller.outcome_kind == "criterion-broken")

    print("\n" + "=" * 74)
    print("[3] 判据自身语法错：model ⇒ fail，caller ⇒ invalid（同一条分界线）")
    print("=" * 74)
    r3m = await run_case("model", "assert (1 +", "SyntaxError: unexpected EOF while parsing")
    r3c = await run_case("caller", "assert (1 +", "SyntaxError: unexpected EOF while parsing")
    print(f"  model : outcome={r3m.outcome} kind={r3m.outcome_kind}")
    print(f"  caller: outcome={r3c.outcome} kind={r3c.outcome_kind}")
    c.check("模型的语法错判据 ⇒ fail", r3m.outcome == "fail")
    c.check("调用方的语法错判据 ⇒ invalid", r3c.outcome == "invalid")

    print("\n" + "=" * 74)
    print("[4] 环境缺依赖：caller ⇒ invalid；model ⇒ fail（invalid 只留给 caller）")
    print("=" * 74)
    r4c = await run_case("caller", "import numpy", "ModuleNotFoundError: No module named 'numpy'")
    r4m = await run_case("model", "import numpy", "ModuleNotFoundError: No module named 'numpy'")
    print(f"  caller: outcome={r4c.outcome} kind={r4c.outcome_kind}")
    print(f"  model : outcome={r4m.outcome} kind={r4m.outcome_kind}")
    c.check("caller 的缺依赖 ⇒ invalid（environment-missing）",
            r4c.outcome == "invalid" and r4c.outcome_kind == "environment-missing")
    c.check("model 的缺依赖 ⇒ fail（判据是它自己写的）", r4m.outcome == "fail")

    print("\n" + "=" * 74)
    print("[5] 判据来源缺失（历史读数）⇒ 按【非 caller】处理 ⇒ fail")
    print("=" * 74)
    r5 = await run_case("", BAD_CMD, "NameError: name 'ant_colony' is not defined")
    print(f"  outcome={r5.outcome} kind={r5.outcome_kind}")
    c.check("source 为空也必须 fail（只有显式 caller 才允许 invalid）",
            r5.outcome == "fail")

    print("\n" + "=" * 74)
    print("[6] 普通断言失败仍是 verify-failed → fail（这条路径不许被误改）")
    print("=" * 74)
    r6 = await run_case("caller", "assert 1 == 2", "AssertionError")
    r6m = await run_case("model", "assert 1 == 2", "AssertionError")
    print(f"  caller: outcome={r6.outcome} kind={r6.outcome_kind} / "
          f"model: outcome={r6m.outcome} kind={r6m.outcome_kind}")
    c.check("caller 的普通断言失败 = verify-failed/fail",
            r6.outcome_kind == "verify-failed" and r6.outcome == "fail")
    c.check("model 的普通断言失败 = verify-failed/fail（不因来源而改判）",
            r6m.outcome_kind == "verify-failed" and r6m.outcome == "fail")

    return c.report()


raise SystemExit(asyncio.run(main()))
