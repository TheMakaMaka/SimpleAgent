"""`VERIFY-VACUOUS`：模型自拟的验收判据不得**恒真**。

缺陷（统筹方缺陷报告，真实运行 `cy_20260926_154707_882595`）
----------------------------------------------------------
调用方不给 `verify_command` 时，模型自己定义"什么叫对"，
`qwen2.5:7b` 给出的是 `print('PASS')` —— **恒真**。
`FIX-VERIFY-WIRING` 让这条命令真的被执行之后：

    declared=0（什么都没声明）+ checked=False（硬校验跳过）
    + steps=0（没东西可查）+ print('PASS') → **phase=record（成功）**
    而工作区里根本没有产出那份分析报告。

三个绿灯叠在一起，恰好等于"什么都没干"。

这个文件测什么
--------------
1. **判据下限的矩阵**：什么算"引用了交付物"，什么不算（含误收留白）；
2. **端到端**：经生产的构造路径（`CodingCycle.run` 不传 `verify_command`
   → `_setup_orchestrator` 注入 pipeline），那次的组合**必须不再出现**；
3. ★ **反向证明**：把可采性开关关掉（复刻修复前行为）→ 那个组合**必须复现**。
   没有这一组，第 2 组的断言就无法证明自己抓的是这个缺陷
   （可能只是"碰巧没走到 record"）；
4. **正向对照**：合法的自拟判据、以及**调用方给的判据**都不能被误伤 ——
   调用方给 `print('PASS')` 仍然算通过（标准由调用方定，这是权威性，不是缺陷）。
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
    VerifyCommand,
)
from core.decisions import FileDecisionStore  # noqa: E402
from core.task import Artifact  # noqa: E402
from storage.store import Event  # noqa: E402

OK = Checker()

#: 复刻那次真实运行：工作区里躺着上一次测试留下的文件（历史文件）。
#: 这一点很关键 —— 正是因为**有历史文件**，`_files_to_verify` 的兜底
#: 才让 `print('PASS')` 有"文件"可挂，验证才跑得起来。
PRIOR = {"calc.py": "def add(a, b):\n    return a + b\n",
         "notes.txt": "上一条需求留下的笔记\n"}

GOAL = "读取根目录下的项目结构输出一份分析报告"

#: 模型自拟的判据 —— 就是实测拿到的那一条
VACUOUS = {"command": "print('PASS')", "reason": "程序无报错即视为成功"}


class RecStorage:
    """只记录事件，不落盘。"""

    def __init__(self):
        self.events: list[Event] = []

    def append_event(self, event: Event) -> None:
        self.events.append(event)

    def get_events(self, cycle_id=None):
        return list(self.events)

    def saved(self, kind: str) -> list[Event]:
        return [e for e in self.events if e.kind == kind]


class ScriptedLLM:
    """按脚本返回编排器的 JSON 决策，不调模型（确定性）。"""

    profile = None

    def __init__(self, decisions: list[dict]):
        self.decisions = decisions
        self.seen = 0

    async def chat_json(self, messages: dict) -> dict:
        d = self.decisions[min(self.seen, len(self.decisions) - 1)]
        self.seen += 1
        return d


class StubWorker:
    """只回报"看过了"，**不产出任何文件产物** —— 复刻那次真实运行。"""

    profile = None

    def __init__(self):
        self.calls = 0

    async def run(self, task, context):
        self.calls += 1
        return TaskResult(
            task_id=task.id,
            ok=True,
            output="工作区内的文件列表如下：- calc.py (34 bytes) - notes.txt (37 bytes)",
            artifacts=[],
            steps_used=1,
        )


class WriteWorker:
    """真的写一个文件并回报 artifact（正向对照用）。"""

    profile = None

    def __init__(self, path: str, content: str):
        self.path, self.content = path, content

    async def run(self, task, context):
        full = os.path.join(WS, self.path)
        os.makedirs(os.path.dirname(full) or WS, exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(self.content)
        return TaskResult(
            task_id=task.id, ok=True, output=f"已写入 {self.path}",
            artifacts=[Artifact(key=f"{task.id}_file_{self.path}",
                                kind="file", path=self.path)],
            steps_used=1,
        )


class MixedWorker:
    """第一次只"看看"（不产文件），之后专写 report.txt —— 复刻实测那一轮的走法。"""

    profile = None

    def __init__(self, path: str = "report.txt"):
        self.path = path
        self.n = 0

    async def run(self, task, context):
        self.n += 1
        if self.path not in (task.description or ""):
            return TaskResult(
                task_id=task.id, ok=True,
                output="工作区内的文件列表如下：- calc.py (34 bytes) - notes.txt (37 bytes)",
                artifacts=[], steps_used=1,
            )
        full = os.path.join(WS, self.path)
        with open(full, "w", encoding="utf-8") as f:
            f.write("工作区包含两个文件。\n")
        return TaskResult(
            task_id=task.id, ok=True, output=f"已写入 {self.path}",
            artifacts=[Artifact(key=f"{task.id}_file_{self.path}",
                                kind="file", path=self.path)],
            steps_used=1,
        )


def scripted(verify: dict | None, declared: list | None, tasks: list | None = None):
    """两轮脚本：第 1 轮干活，第 2 轮说 done。"""
    t = tasks if tasks is not None else [{
        "id": "t1", "description": "列出工作区内的文件和目录",
        "expected_output": "文件列表", "tool_hint": ["list_workspace"],
        "context_refs": [],
    }]
    return [
        {"status": "continue", "reasoning": "需要先列出工作区内容",
         "files": declared or [], "tasks": t,
         "verify": verify or {}, "final_answer": ""},
        {"status": "done", "reasoning": "已完成分析", "tasks": [],
         "files": declared or [], "verify": verify or {},
         "final_answer": "分析报告已给出"},
    ]


async def run_cycle(verify: dict | None, declared: list | None, *,
                    caller_verify: str | None = None, worker=None,
                    decisions: list[dict] | None = None,
                    tmp: str) -> tuple[object, object, RecStorage]:
    """走**生产构造路径**：CodingCycle.run 不传 verify_command。

    `_setup_orchestrator` 负责注入 pipeline 与（可选的）调用方判据 ——
    这正是 `FIX-VERIFY-WIRING` 修好的那条线，测试不手工注入任何东西。
    """
    store = RecStorage()
    orch = Orchestrator(
        ScriptedLLM(decisions if decisions is not None else scripted(verify, declared)),
        worker if worker is not None else StubWorker(),
        pipeline=None,             # 生产里就是从 None 开始的
        verify_command=None,       # 调用方不给 —— 触发条件
    )
    cycle = CodingCycle(
        orchestrator=orch, worker=None, pipeline=CheckPipeline(),
        max_attempts=1, verbose=False, storage=store, persist=True,
        on_decision="auto",
        decisions=DecisionManager(store=FileDecisionStore(root=tmp)),
    )
    vc = VerifyCommand(command=caller_verify, reason="调用方给的") if caller_verify else None
    report, memory = await cycle.run(GOAL, verify_command=vc)
    return report, memory, store


def prepare_workspace():
    clean_workspace()
    for name, content in PRIOR.items():
        with open(os.path.join(WS, name), "w", encoding="utf-8") as f:
            f.write(content)


async def main() -> int:
    tmp = tempfile.mkdtemp(prefix="verify_vacuous_")

    # ================= 1. 判据下限的矩阵 =================
    print("=" * 74)
    print("[1] 判据下限：什么算「引用了本轮交付物」")
    print("=" * 74)
    cases = [
        # (命令, 交付物, 期望可采, 说明)
        ("print('PASS')", ["report.txt"], False, "恒真命令（实测拿到的那条）"),
        ("assert True", ["report.txt"], False, "恒真断言"),
        ("assert True", [], False, "没有任何交付物 → 说不出交付了什么"),
        ("assert open('report.txt').read().strip()", ["report.txt"], True,
         "路径用在 open() 里"),
        ("assert open('out/report.txt').read().strip()", ["out/report.txt"], True,
         "交付物在子目录，命令引用文件名"),
        ("assert os.path.exists('add.py')", ["add.py"], False,
         "★ .py 交付物只检查存在、不调用 —— 由 B3 收紧为不可采（见 test_transparency）"),
        ("import add\nassert add.add(1, 2) == 3", ["add.py"], True,
         "模块式判据（词干匹配）"),
        ("assert 'report.txt' in os.listdir()", ["report.txt"], True,
         "路径出现在命令文本里"),
        ("print('add')", ["add.py"], False,
         "★ 名字只是打在字符串里 —— 剥字面量后不算引用"),
        ("print('a')", ["a.py"], False,
         "★ 词干太短（<3）不参与匹配，避免巧合命中"),
        ("assert a.f() == 1", ["a.py"], False, "同上：短词干必须整名匹配"),
    ]
    for cmd, deliv, want, why in cases:
        got, _ = Orchestrator._model_verify_admissible({"command": cmd}, deliv)
        print(f"  {'PASS' if got == want else 'FAIL'}  可采={got!s:5} 交付物={deliv} "
              f"命令={cmd!r}")
        OK.check(f"下限：{why}", got == want)

    # ================= 2. 端到端：修复后那个组合不该出现 =================
    print("\n" + "=" * 74)
    print("[2] 端到端（生产构造路径，调用方不给 verify_command）")
    print("=" * 74)
    prepare_workspace()
    report, memory, store = await run_cycle(VACUOUS, None, tmp=tmp)
    m = report.manifest or {}
    v = report.verify or {}
    print(f"  phase={report.phase.value}  attempts={report.attempts}")
    print(f"  manifest: declared={len(m.get('declared') or [])} "
          f"checked={m.get('checked')} passed={m.get('passed')}")
    print(f"  check:    checked={(report.check or {}).get('checked')} "
          f"status={(report.check or {}).get('status')} steps={len(report.check_steps)}")
    print(f"  touched_files={report.touched_files}")
    print(f"  verify={v}")
    print(f"  error={(report.error or '')[:160]}")
    skipped = store.saved("verify_skipped")
    for e in skipped:
        print(f"  [事件 verify_skipped] reason={(e.payload or {}).get('reason', '')[:140]}")

    no_work = (not (m.get("declared") or [])) and not report.touched_files
    OK.check("★ 本轮确实「什么都没产出」（declared=0 且 touched=[]）", no_work)
    OK.check("★ 这个组合**不再**能是 phase=record", report.phase.value != "record")
    OK.check("没有验证结论（判据被拒 → 不是 passed=True）", report.verify is None)
    OK.check("拒绝理由被记下（memory.verify_untrusted）",
             "没有引用" in (memory.verify_untrusted or "")
             or "没有任何交付物" in (memory.verify_untrusted or ""))
    OK.check("错误文案指出是「自拟判据不合格/已拒绝采纳」，不是「缺少命令」",
             "拒绝采纳" in (report.error or "")
             and "缺少可机器判定的验证命令" not in (report.error or ""))
    OK.check("被拒的命令原文可见（可事后追查）",
             "print('PASS')" in (memory.verify_untrusted or ""))
    OK.check("事件流里留痕：verify_skipped 带理由",
             bool(skipped) and "不合格" in str((skipped[0].payload or {}).get("reason", "")))
    OK.check("check 阶段三态：没东西可查时 status=skipped 且 checked=False",
             (report.check or {}).get("status") == "skipped"
             and (report.check or {}).get("checked") is False)

    # ================= 3. ★ 反向证明：关掉开关必须复现缺陷 =================
    print("\n" + "=" * 74)
    print("[3] ★ 反向证明：关掉可采性检查（= 复刻修复前行为）→ 缺陷必须复现")
    print("=" * 74)
    orig = Orchestrator.__dict__["_model_verify_admissible"]
    Orchestrator._model_verify_admissible = classmethod(
        lambda cls, raw_verify, deliverables: (True, "")
    )
    try:
        prepare_workspace()
        r_old, mem_old, _ = await run_cycle(VACUOUS, None, tmp=tmp)
    finally:
        Orchestrator._model_verify_admissible = orig

    m_old = r_old.manifest or {}
    v_old = r_old.verify or {}
    print(f"  phase={r_old.phase.value}  touched={r_old.touched_files}")
    print(f"  manifest: declared={len(m_old.get('declared') or [])} "
          f"checked={m_old.get('checked')}")
    print(f"  check_steps={r_old.check_steps}")
    print(f"  verify={v_old}")
    OK.check("★ 关掉后确实复现：declared=0 + print('PASS') → phase=record",
             r_old.phase.value == "record"
             and not (m_old.get("declared") or [])
             and not r_old.touched_files)
    OK.check("★ 复现时 verify.command 正是 print('PASS')",
             v_old.get("command") == "print('PASS')")
    OK.check("★ 复现时 source=model（判据是模型自拟的）",
             v_old.get("source") == "model")
    OK.check("→ 因此第 2 组的断言**确实**抓的是这个缺陷（不是碰巧没走到 record）",
             r_old.phase.value == "record" and report.phase.value != "record")

    # ================= 4. 正向对照：不许误伤 =================
    print("\n" + "=" * 74)
    print("[4] 正向对照：合法的自拟判据、以及调用方的判据都不能被误伤")
    print("=" * 74)
    prepare_workspace()
    good = {"command": "assert open('report.txt').read().strip()", "reason": "报告必须非空"}
    r_ok, mem_ok, _ = await run_cycle(
        good, [{"path": "report.txt", "role": "分析报告", "symbols": []}],
        worker=WriteWorker("report.txt", "项目结构分析…\n"), tmp=tmp,
    )
    print(f"  phase={r_ok.phase.value}  verify={r_ok.verify}")
    OK.check("合法的自拟判据仍然通过（phase=record）", r_ok.phase.value == "record")
    OK.check("合法的自拟判据：verify.passed=True",
             bool((r_ok.verify or {}).get("passed")))
    OK.check("合法的自拟判据：source=model（留痕，可区分）",
             (r_ok.verify or {}).get("source") == "model")

    # 调用方给恒真判据 —— 权威在调用方，本门禁**不得**插手
    prepare_workspace()
    r_caller, _, _ = await run_cycle(VACUOUS, None, caller_verify="print('PASS')", tmp=tmp)
    print(f"  [调用方给 print('PASS')] phase={r_caller.phase.value} "
          f"verify={r_caller.verify}")
    OK.check("★ 调用方给的判据不受本门禁影响（标准由调用方定）",
             r_caller.phase.value == "record"
             and (r_caller.verify or {}).get("source") == "caller")

    # 无交付物 + 调用方判据：也不该被拦（同上，权威在调用方）
    print("\n" + "=" * 74)
    print("[5] 无交付物但调用方给了判据：仍按调用方的判据走")
    print("=" * 74)
    prepare_workspace()
    r_c2, _, _ = await run_cycle(None, None, caller_verify="assert True", tmp=tmp)
    print(f"  phase={r_c2.phase.value} verify={r_c2.verify}")
    OK.check("调用方判据 + 无声明 → 仍然 record，source=caller",
             r_c2.phase.value == "record"
             and (r_c2.verify or {}).get("source") == "caller")

    # ================= 6. 实测那一轮的走法：先被拒、换判据、真通过 =================
    print("\n" + "=" * 74)
    print("[6] 先给坏判据被拒 → 换一版引用交付物的判据 → 真的通过（留痕不能丢）")
    print("=" * 74)
    good = {"command": "assert open('report.txt').read().strip()", "reason": "报告非空"}
    t_list = [{"id": "t1", "description": "列出工作区内的文件和目录",
               "expected_output": "文件列表", "tool_hint": ["list_workspace"],
               "context_refs": []}]
    t_write = [{"id": "t2", "description": "编写报告保存到 report.txt",
                "expected_output": "report.txt", "tool_hint": ["write_file"],
                "context_refs": []}]
    decisions = [
        {"status": "continue", "reasoning": "先看看工作区",
         "files": [], "tasks": t_list, "verify": VACUOUS, "final_answer": ""},
        {"status": "continue", "reasoning": "写报告",
         "files": [{"path": "report.txt", "role": "分析报告", "symbols": []}],
         "tasks": t_write, "verify": good, "final_answer": ""},
        {"status": "done", "reasoning": "已完成", "tasks": [], "files": [],
         "verify": good, "final_answer": "报告已生成"},
    ]
    prepare_workspace()
    r_seq, mem_seq, st_seq = await run_cycle(
        None, None, decisions=decisions, worker=MixedWorker(), tmp=tmp)
    skipped_seq = st_seq.saved("verify_skipped")
    print(f"  phase={r_seq.phase.value}  touched={r_seq.touched_files}")
    print(f"  verify={r_seq.verify}")
    print(f"  verify_skipped 事件 {len(skipped_seq)} 条；verify 事件 "
          f"{len(st_seq.saved('verify'))} 条")
    for e in skipped_seq:
        print(f"    [verify_skipped] {str((e.payload or {}).get('reason'))[:110]}")
    OK.check("换到合法判据后仍然通过（门禁不是一刀切拒）",
             r_seq.phase.value == "record")
    OK.check("★ 被拒的那一次**留痕仍在**（成功不能把审计流水擦掉）",
             bool(skipped_seq)
             and "不合格" in str((skipped_seq[0].payload or {}).get("reason", "")))
    OK.check("通过的 verify 事件带 source=model",
             (st_seq.saved("verify") or [{}])[0].payload.get("source") == "model")

    clean_workspace()
    shutil.rmtree(tmp, ignore_errors=True)
    return OK.report()


raise SystemExit(asyncio.run(main()))
