"""`TRANSPARENCY2-BACKEND` P3：③ 拆解合规关卡（机械层，**有否决权**）。

**最重要的一条验收**（工作单原文）：

> 拿**用户那两次真实运行**的分解去审 → **必须判不通过**，并指出违反了
> P3/P4/P6/P7 中的哪几条
> （**一个对所有分解都报"通过"的审查器，等于没有审查器**）。
> 另：构造一个**符合全部原则**的分解 → 审查**通过**（证明不会一律报红）。

另外三条一起守：
* `checked_by="tool"` / `independent=false` —— **REVIEW 未配置时必须如实标注**，
  不得呈现为"审查通过"；
* `undecidable` 是**第三态**（P5/P6 机械近似），不是"通过"；
* **否决权真的有效**：`DECOMPOSE_GATE=block` 时不合规的拆解会被拦下；
* **P20 出厂默认**：不设任何环境变量时 `DECOMPOSE_GATE_DEFAULT == "warn"`（止血），
  且**分档**：`undecidable`（判不了）**不得**等同于不通过 —— 只有 `violated` 才否决。
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
from core.decompose_review import review_decomposition  # noqa: E402
from core.task import Artifact  # noqa: E402
from storage.store import Event  # noqa: E402

OK = Checker()

# ---------------------------------------------------------------------------
# 样例 1：**逐字复刻**用户那次运行的 plan 事件（我从 probe 的原始事件里抄的）
# ---------------------------------------------------------------------------
REAL_PLAN = {
    "goal": "以10*10网格为结构，设计一个随机障碍物生成规则，保证网格中起始点和目标点"
            "至少可通，写一个基础的蚁群算法，并连续测试验证，生成对应报告",
    "files": [{"path": "obstacle_generator.py", "role": "障碍物生成规则",
               "symbols": ["generate_obstacles"]}],
    "tasks": [
        {"id": "t1", "description": "设计并实现障碍物生成规则",
         "expected_output": "障碍物生成规则实现，保存为 obstacle_generator.py"},
        {"id": "t2", "description": "编写蚁群算法实现并保存为 ant_colony.py",
         "expected_output": "ant_colony.py 文件，包含 AntColony 类"},
        {"id": "t3", "description": "编写蚁群算法测试脚本并保存为 test_ant_colony.py",
         "expected_output": "test_ant_colony.py 文件，包含测试用例"},
        {"id": "t4", "description": "修改 generate_obstacles 函数，添加 width, height, density 参数",
         "expected_output": "obstacle_generator.py 文件，包含修正后的 generate_obstacles 函数"},
    ],
}

# ---------------------------------------------------------------------------
# 样例 2：按工作单 §P3 的**实测症状描述**重建的 Run A 型分解
#   「10 个任务里 6 个同义（"再修一次 generate_obstacles 参数"）、
#     反复改同一个文件、任务 id 重复（t9 出现两次）」
# ---------------------------------------------------------------------------
RUN_A_LIKE = {
    "goal": "同上",
    "files": [{"path": "obstacle_generator.py", "symbols": ["generate_obstacles"]}],
    "tasks": (
        [{"id": "t1", "description": "实现 obstacle_generator.py 的 generate_obstacles",
          "expected_output": "obstacle_generator.py"},
         {"id": "t2", "description": "再修一次 generate_obstacles 的参数",
          "expected_output": "obstacle_generator.py"},
         {"id": "t3", "description": "再修一次 generate_obstacles 的参数",
          "expected_output": "obstacle_generator.py"},
         {"id": "t4", "description": "再次修正 generate_obstacles 的 density 参数",
          "expected_output": "obstacle_generator.py"},
         {"id": "t5", "description": "再次修正 generate_obstacles 的 seed 参数",
          "expected_output": "obstacle_generator.py"},
         {"id": "t6", "description": "再次调整 generate_obstacles 的 width 参数",
          "expected_output": "obstacle_generator.py"},
         {"id": "t9", "description": "再次验证 generate_obstacles 的输出",
          "expected_output": "obstacle_generator.py"},
         {"id": "t9", "description": "再次验证 generate_obstacles 的输出",
          "expected_output": "obstacle_generator.py"}]
    ),
}

# ---------------------------------------------------------------------------
# 样例 3：符合全部八条原则的分解（V2：证明审查器不会一律报红）
# ---------------------------------------------------------------------------
GOOD = {
    "goal": "实现 add 与 calc 两个函数",
    "files": [{"path": "add.py", "symbols": ["add"]},
              {"path": "calc.py", "symbols": ["calc"]}],
    "tasks": [
        {"id": "t1", "description": "实现 add 函数写入 add.py",
         "expected_output": "add.py 中的 add",
         "criterion": "import add\nassert add.add(1, 2) == 3"},
        {"id": "t2", "description": "实现 calc 函数写入 calc.py",
         "expected_output": "calc.py 中的 calc",
         "criterion": "import calc\nassert calc.calc('1+1') == 2"},
    ],
}


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
        # ★ P19：报告要能看到 reasoning 用量（推理模型的思考 token 先吃预算）。
        self.usage = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
                      "reasoning_tokens": 0}

    async def chat_json(self, messages):
        d = self.decisions[min(self.seen, len(self.decisions) - 1)]
        self.seen += 1
        self.usage["calls"] += 1
        self.usage["completion_tokens"] += 10
        self.usage["reasoning_tokens"] += 7
        return d


class StubWorker:
    profile = None

    async def run(self, task, context):
        with open(os.path.join(WS, "add.py"), "w", encoding="utf-8") as f:
            f.write("def add(a, b):\n    return a + b\n")
        return TaskResult(task_id=task.id, ok=True, output="写了 add.py",
                          artifacts=[Artifact(key=f"{task.id}_f", kind="file",
                                              path="add.py")],
                          steps_used=1)


def show(tag: str, review: dict) -> None:
    print(f"  {tag}: passed={review['passed']} violated={review['violated']} "
          f"undecidable={review['undecidable']}")
    for item in review["principles"]:
        if item["verdict"] != "ok":
            print(f"      [{item['verdict']}] {item['principle']}: "
                  f"{str(item['evidence'][0] if item['evidence'] else '')[:88]}")


async def main() -> int:
    tmp = tempfile.mkdtemp(prefix="decompose_")

    # ================= V1：已知错的分解必须被判错 =================
    print("=" * 74)
    print("[V1] 用户那次真实运行的 plan（逐字复刻）→ 必须**不通过**")
    print("=" * 74)
    r_real = review_decomposition(REAL_PLAN)
    show("真实 plan", r_real)
    OK.check("★ 判不通过（不是一律报红、也不是一律放行）", r_real["passed"] is False)
    OK.check("指出了具体原则（P3：描述里含并列词「并」）",
             "P3" in r_real["violated"])
    OK.check("每条结论都带证据", all(i["evidence"] for i in r_real["principles"]
                                     if i["verdict"] == "violated"))
    OK.check("checked_by=tool（机械层）", r_real["checked_by"] == "tool")
    OK.check("★ independent=false 且写明 L3 未启用",
             r_real["independent"] is False and "未启用" in r_real["model_layer"]["reason"])

    print("\n" + "=" * 74)
    print("[V1-b] Run A 型分解（同义重复 + 反复改同一文件 + id 重复）→ 四条都该红")
    print("=" * 74)
    r_a = review_decomposition(RUN_A_LIKE)
    show("Run A 型", r_a)
    OK.check("★ 判不通过", r_a["passed"] is False)
    OK.check("★ P3（并列词「再」）被抓",
             "P3" in r_a["violated"])
    OK.check("★ P4（反复改同一个文件）被抓", "P4" in r_a["violated"])
    OK.check("★ P6（同义重复）被抓", "P6" in r_a["violated"])
    OK.check("★ P7（任务 id 重复/描述重复）被抓", "P7" in r_a["violated"])

    # ================= V2：好分解必须通过 =================
    print("\n" + "=" * 74)
    print("[V2] 符合全部原则的分解 → 必须**通过**（证明不会一律报红）")
    print("=" * 74)
    r_good = review_decomposition(GOOD)
    show("好分解", r_good)
    OK.check("★ 八条原则没有一条 violated", r_good["passed"] is True)
    OK.check("六条机械原则全 ok", all(
        i["verdict"] == "ok" for i in r_good["principles"]
        if i["principle"] in ("P1", "P2", "P3", "P4", "P7", "P8")))
    OK.check("P5 因没给要求清单标 undecidable（**不是默认通过**）",
             next(i["verdict"] for i in r_good["principles"]
                  if i["principle"] == "P5") == "undecidable")
    OK.check("★ `coverage_complete=False`（只有机械条款通过，不等于审查完整）",
             r_good["coverage_complete"] is False)

    # ================= P1 违反样例（一次要交付多个符号） =================
    print("\n" + "=" * 74)
    print("[V1-c] P1：一个叶子要交付多个符号 → 违反")
    print("=" * 74)
    r_p1 = review_decomposition({
        "files": [{"path": "storage.py", "symbols": ["save", "load", "delete"]}],
        "tasks": [{"id": "t1", "description": "实现 storage.py",
                   "expected_output": "storage.py"}],
    })
    show("多符号", r_p1)
    OK.check("P1 被判违反", "P1" in r_p1["violated"])

    # ================= 否决权真的有效（block 模式） =================
    print("\n" + "=" * 74)
    print("[V3] 否决权：`DECOMPOSE_GATE=block` 时不合规的拆解被拦下")
    print("=" * 74)
    clean_workspace()
    plan_bad = {
        "status": "continue", "reasoning": "写并测试",
        "files": [{"path": "add.py", "role": "实现", "symbols": ["add"]}],
        "tasks": [{"id": "t1", "description": "写 add.py 并测试它",
                   "expected_output": "add.py", "tool_hint": ["write_file"],
                   "context_refs": []}],
        "verify": {"command": "import add\nassert add.add(1, 2) == 3", "reason": "断言"},
        "final_answer": "",
    }
    done = {"status": "done", "reasoning": "完事", "tasks": [], "files": [],
            "verify": {}, "final_answer": "完成"}
    # P18：合规拆解（无并列词、单交付物单符号、逐叶 expected_output）——
    # 用来证明默认 block **不会一律拦死**。
    plan_good = {
        "status": "continue", "reasoning": "写 add.py",
        "files": [{"path": "add.py", "role": "实现", "symbols": ["add"]}],
        "tasks": [{"id": "t1", "description": "写 add.py", "expected_output": "add.py",
                   "tool_hint": ["write_file"], "context_refs": []}],
        "verify": {"command": "import add\nassert add.add(1, 2) == 3", "reason": "断言"},
        "final_answer": "",
    }
    self_report = {"done": [], "not_done": [], "why": [], "reflections": [],
                   "approach": [], "confidence": {"level": "low", "basis": ""},
                   "open_questions": [], "requirements": [], "claims": {}}

    async def run(mode, first=None):
        if mode is None:
            os.environ.pop("DECOMPOSE_GATE", None)   # 不设环境变量 = 测出厂默认
        else:
            os.environ["DECOMPOSE_GATE"] = mode
        store = RecStorage()
        orch = Orchestrator(ScriptedLLM([first or plan_bad, done, self_report]),
                            StubWorker(), pipeline=None, verify_command=None)
        cycle = CodingCycle(orchestrator=orch, worker=None, pipeline=CheckPipeline(),
                            max_attempts=1, verbose=False, storage=store, persist=True,
                            on_decision="auto",
                            decisions=DecisionManager(store=FileDecisionStore(root=tmp)))
        report, _mem = await cycle.run("写 add 函数")
        return report, store

    try:
        r_warn, s_warn = await run("warn")
        print(f"  warn 模式：phase={r_warn.phase.value} outcome={r_warn.outcome} "
              f"violated={(r_warn.decompose_review or {}).get('violated')}")
        OK.check("warn 模式：**照样留痕**（事件 + 报告字段）",
                 bool(s_warn.saved("decompose_review"))
                 and bool(r_warn.decompose_review))
        OK.check("warn 模式：不否决（phase 由后续阶段决定）",
                 r_warn.phase.value == "record")
        r_block, s_block = await run("block")
        print(f"  block 模式：phase={r_block.phase.value} outcome={r_block.outcome} "
              f"kind={r_block.outcome_kind}")
        print(f"    error={str(r_block.error)[:110]}")
        OK.check("★ block 模式：**否决**（不进写码/验证，直接判不通过）",
                 r_block.phase.value == "failed"
                 and r_block.outcome_kind == "decomposition-violation")
        OK.check("否决文案要求「重新拆解，或声明做不到」",
                 "重新拆解" in str(r_block.error))
    finally:
        os.environ.pop("DECOMPOSE_GATE", None)

    # ================= V4：P20 出厂默认 = warn（止血）+ 分档双向 =================
    print("\n" + "=" * 74)
    print("[V4] P20：不设 DECOMPOSE_GATE ⇒ 出厂默认 warn（先止血，分档后再决定升 block）")
    print("=" * 74)
    probe = CodingCycle(orchestrator=None, worker=None, pipeline=None,
                        storage=RecStorage(), persist=False)
    os.environ.pop("DECOMPOSE_GATE", None)
    OK.check("★ 类默认值 == warn（P20 要求 1：退回 warn 止血）",
             CodingCycle.DECOMPOSE_GATE_DEFAULT == "warn")
    OK.check("★ 不设环境变量 ⇒ _decompose_gate_mode() == 'warn'",
             probe._decompose_gate_mode() == "warn")
    for m in ("off", "warn", "block"):
        os.environ["DECOMPOSE_GATE"] = m
        OK.check(f"环境变量 {m} 仍可覆盖（保留灰度）",
                 probe._decompose_gate_mode() == m)
    os.environ["DECOMPOSE_GATE"] = "bogus"
    OK.check("非法值回落到默认 warn（不是静默放行）",
             probe._decompose_gate_mode() == "warn")
    os.environ.pop("DECOMPOSE_GATE", None)

    clean_workspace()
    try:
        r_def_bad, s_def_bad = await run(None)          # 不合规 + 无环境变量
        print(f"  默认 + 不合规：phase={r_def_bad.phase.value} "
              f"outcome={r_def_bad.outcome} kind={r_def_bad.outcome_kind}")
        evd = s_def_bad.saved("decompose_review")
        pld = (evd[-1].payload if evd else {}) or {}
        print(f"    事件：mode={pld.get('mode')!r} applied={pld.get('applied')} "
              f"violated={pld.get('violated')} undecidable={pld.get('undecidable')}")
        OK.check("★ 默认 warn：不合规拆解**只留痕、不拦路**（这正是止血）",
                 r_def_bad.outcome_kind != "decomposition-violation"
                 and pld.get("applied") is False)
        OK.check("留痕仍在：事件带 violated（含 P3）与 mode=warn",
                 pld.get("mode") == "warn" and "P3" in (pld.get("violated") or []))
        mu = r_def_bad.model_usage or {}
        print(f"  P19 报告用量：{mu.get('total')}")
        OK.check("★ P19：报告带模型用量（含 reasoning_tokens，且进了 to_dict）",
                 int((mu.get("total") or {}).get("reasoning_tokens") or 0) > 0
                 and "model_usage" in r_def_bad.to_dict())
    finally:
        os.environ.pop("DECOMPOSE_GATE", None)

    # ================= V5：P20 分档 —— undecidable ≠ 不通过（双向） =================
    print("\n" + "=" * 74)
    print("[V5] P20 分档：只有 undecidable（无 violated）⇒ 放行；有 violated ⇒ 拦下")
    print("=" * 74)
    clean_workspace()
    try:
        # plan_good 的机械层结论恰好是「0 条违反 / 2 条判不了（P2/P5）」——
        # 正是统筹方实测里被 `block` 误否决的那种拆解。
        os.environ["DECOMPOSE_GATE"] = "block"
        r_und, s_und = await run("block", first=plan_good)
        print(f"  block + 只有 undecidable：phase={r_und.phase.value} "
              f"outcome={r_und.outcome} kind={r_und.outcome_kind}")
        evu = s_und.saved("decompose_review")
        plu = (evu[-1].payload if evu else {}) or {}
        print(f"    事件：passed={plu.get('passed')} violated={plu.get('violated')} "
              f"undecidable={plu.get('undecidable')}")
        OK.check("★ 只有 undecidable、没有 violated ⇒ **放行**（不被否决）",
                 r_und.phase.value == "record"
                 and r_und.outcome_kind != "decomposition-violation")
        OK.check("★ 事件如实分档：violated 为空、undecidable 非空、passed=True",
                 not (plu.get("violated") or [])
                 and bool(plu.get("undecidable"))
                 and plu.get("passed") is True)

        clean_workspace()
        r_vio, s_vio = await run("block", first=plan_bad)
        print(f"  block + 有 violated：phase={r_vio.phase.value} "
              f"outcome={r_vio.outcome} kind={r_vio.outcome_kind}")
        print(f"    error={str(r_vio.error)[:110]}")
        OK.check("★ 有 violated ⇒ **拦下**（双向，不是一律放行）",
                 r_vio.phase.value == "failed"
                 and r_vio.outcome_kind == "decomposition-violation")
        OK.check("拦下理由写明违反了 P3 + 逐条证据",
                 "P3" in str(r_vio.error) and "逐条证据" in str(r_vio.error))
    finally:
        os.environ.pop("DECOMPOSE_GATE", None)

    clean_workspace()
    shutil.rmtree(tmp, ignore_errors=True)
    return OK.report()


raise SystemExit(asyncio.run(main()))
