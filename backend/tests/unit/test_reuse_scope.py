"""`REUSE-SYMBOL-SCOPE`（P7b）：复用层符号反查的**名字撞车** —— 修好，且不许靠关检查来修。

真实运行（能力基线 T9，`run_20260928_221011_7b7bfc`）
-----------------------------------------------------
目标：用 Flask 写 `app.py`（`flask` 未装，这一轴看模型会不会声明做不到）。
模型写的代码**完全正确**：

    from flask import Flask
    app = Flask(__name__)
    @app.route('/ping', methods=['GET'])
    def ping(): ...

而复用层判 **blocking**：`引用了不存在的符号 `app.route` —— `app` 里只有 ['app','ping']`
—— 因为模型的文件**恰好也叫 `app.py`**，`_lookup("app")` 命中了**同名模块**。
复用层有硬否决权 ⇒ 正确代码被否决，而且模型在 `self_report` 里
写下"静态检查未通过"，**它以为自己对代码是错的、去反思它**。

这个文件同时守两条（缺一不可）：
1. **不再误判**：同一份代码在"有同名文件/没有同名文件"两种工作区下**结论一致且为 0**；
2. ★ **反空洞**：真实的"调用了不存在的符号"**必须仍然红**（含 `np.array` 没 import）。
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
from core.reuse_checks import BLOCKING_KINDS, check_code, check_workspace  # noqa: E402
from core.task import Artifact  # noqa: E402
from storage.store import Event  # noqa: E402

OK = Checker()

#: 逐字复刻统筹方那次的交付物（**完全正确的 Flask 写法**）
FLASK_APP = (
    "from flask import Flask\n"
    "\n"
    "app = Flask(__name__)\n"
    "\n"
    "@app.route('/ping', methods=['GET'])\n"
    "def ping():\n"
    "    return 'Pong!'\n"
)


def write(rel: str, content: str) -> None:
    full = os.path.join(WS, rel)
    os.makedirs(os.path.dirname(full) or WS, exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)


def blocking_of(code: str, files: dict[str, str], label: str = "mod.py") -> list[dict]:
    clean_workspace()
    for rel, content in files.items():
        write(rel, content)
    found, _refs = check_code(code, label=label)
    return [v for v in found if v.get("kind") in BLOCKING_KINDS]


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


class FlaskWorker:
    profile = None

    async def run(self, task, context):
        write("app.py", FLASK_APP)
        return TaskResult(task_id=task.id, ok=True, output="写了 app.py",
                          artifacts=[Artifact(key=f"{task.id}_f", kind="file",
                                              path="app.py")],
                          steps_used=1)


async def main() -> int:
    tmp = tempfile.mkdtemp(prefix="reuse_scope_")

    # ================= 1. A/B 对照：不再误判 =================
    print("=" * 74)
    print("[1] 同一份正确代码：有/没有同名文件，结论必须**一致且为 0**")
    print("=" * 74)
    a = blocking_of(FLASK_APP, {"app.py": FLASK_APP})
    b = blocking_of(FLASK_APP, {})
    print(f"  A) 工作区里有 app.py → blocking={len(a)}")
    print(f"  B) 工作区里没有 app.py → blocking={len(b)}")
    OK.check("★ A 不再误判（0 条 blocking）", len(a) == 0)
    OK.check("★ B 仍是 0", len(b) == 0)
    OK.check("★ 两种工作区结论一致（这正是原缺陷的症候）", len(a) == len(b))

    # ================= 2. 名字撞车不止 app =================
    print("\n" + "=" * 74)
    print("[2] 撞车矩阵：变量名撞模块名 / 参数 / self / with·for·except·推导式")
    print("=" * 74)
    matrix = [
        (f"{n} = 1\n{n}.anything()\n", {f"{n}.py": "x = 1\n"}, f"变量 {n} 撞模块 {n}.py")
        for n in ("app", "data", "utils", "config", "main")
    ] + [
        ("class C:\n    def f(self):\n        return self.db.execute()\n", {},
         "self 属性（外部库实例的方法）"),
        ("def f(obj):\n    return obj.attr\n", {}, "参数对象属性"),
        ("def f():\n    with open('x') as fh:\n        return fh.read()\n", {},
         "with ... as 绑定"),
        ("def f(xs):\n    for it in xs:\n        it.go()\n", {}, "for 目标"),
        ("def f():\n    try:\n        pass\n    except ValueError as e:\n"
         "        return e.args\n", {}, "except ... as 名"),
        ("def f(xs):\n    return [y.trim() for y in xs]\n", {}, "推导式目标"),
    ]
    for code, files, tag in matrix:
        got = blocking_of(code, files)
        print(f"  {'PASS' if not got else 'FAIL'}  {tag}: blocking={len(got)}")
        OK.check(f"不误判：{tag}", not got)

    # ================= 3. ★ 反空洞：真错必须仍然红 =================
    print("\n" + "=" * 74)
    print("[3] ★ 反空洞：真实的「调用了不存在的符号」**必须仍然红**")
    print("=" * 74)
    anti = [
        ("np.array 但没 import numpy",
         "def f():\n    return np.array([1])\n", {}, "undefined-name"),
        ("from mylib import f（mylib 里只有 g）",
         "from mylib import f\n", {"mylib.py": "def g():\n    return 1\n"},
         "undefined-symbol"),
        ("t1.py 有 foo，t2.py 调 t1.bar（有 import）",
         "import t1\nt1.bar()\n",
         {"t1.py": "def foo():\n    return 1\n"}, "undefined-symbol"),
        ("ant_colony 里没有 generate_obstacles（P2 实测反例）",
         "import ant_colony\nant_colony.generate_obstacles(1)\n",
         {"ant_colony.py": "class AntColony:\n    pass\n"}, "undefined-symbol"),
        ("obstacle_generator 里没有 generate_obstacle_grid（P2 另一条）",
         "import obstacle_generator\nobstacle_generator.generate_obstacle_grid()\n",
         {"obstacle_generator.py": "def generate_obstacles(a, b, c):\n    return []\n"},
         "undefined-symbol"),
        ("按旧签名传参",
         "import sig\nsig.f(1)\n", {"sig.py": "def f(a, b, c):\n    return a\n"},
         "symbol-arity-mismatch"),
    ]
    for tag, code, files, want_kind in anti:
        got = blocking_of(code, files, label="criterion")
        kinds = [v["kind"] for v in got]
        print(f"  {'PASS' if want_kind in kinds else 'FAIL'}  {tag} → {kinds}")
        OK.check(f"仍然红：{tag}（{want_kind}）", want_kind in kinds)
        if got:
            print(f"        {got[0]['message'][:96]}")

    # ================= 4. 工作区级：不再整体否决 =================
    print("\n" + "=" * 74)
    print("[4] 工作区级检查：只有 app.py（正确 Flask）→ 0 blocking")
    print("=" * 74)
    clean_workspace()
    write("app.py", FLASK_APP)
    ws = check_workspace()
    print(f"  blocking={len(ws['blocking'])} warnings={[w['kind'] for w in ws['warnings']]}")
    OK.check("★ 工作区级不再把正确代码判红", not ws["blocking"])

    # ================= 5. 端到端：check 阶段不再否决正确交付物 =================
    print("\n" + "=" * 74)
    print("[5] 端到端：正确 Flask 交付物 → check 通过（不再判「静态检查未通过」）")
    print("=" * 74)
    clean_workspace()
    # ★ 拆解关卡（P18/P20）：app.py 按 P1（叶任务=单交付物）本就
    #   "不合规" —— 它必须同时交付 app 与 ping（这正是 P7b 要测的 Flask 写法）。
    #   要测复用层就必须绕过拆解关卡，故**显式**关掉；关卡自身的默认值与
    #   分档行为见 tests/unit/test_decompose_review.py 的 [V4]/[V5]。
    os.environ["DECOMPOSE_GATE"] = "off"
    store = RecStorage()
    plan = {"status": "continue", "reasoning": "写 app.py",
            "files": [{"path": "app.py", "role": "Web 服务", "symbols": ["app", "ping"]}],
            "tasks": [{"id": "t1", "description": "写 app.py", "expected_output": "app.py",
                       "tool_hint": ["write_file"], "context_refs": []}],
            "verify": {"command": "import app\nassert app.ping", "reason": "断言 ping 存在"},
            "final_answer": ""}
    done = {"status": "done", "reasoning": "完事", "tasks": [], "files": [],
            "verify": {}, "final_answer": "完成"}
    self_report = {"done": [], "not_done": [], "why": [], "reflections": [],
                   "approach": [], "confidence": {"level": "low", "basis": ""},
                   "open_questions": [], "requirements": [], "claims": {}}
    orch = Orchestrator(ScriptedLLM([plan, done, self_report]), FlaskWorker(),
                        pipeline=None, verify_command=None)
    cycle = CodingCycle(orchestrator=orch, worker=None, pipeline=CheckPipeline(),
                        max_attempts=1, verbose=False, storage=store, persist=True,
                        on_decision="auto",
                        decisions=DecisionManager(store=FileDecisionStore(root=tmp)))
    from core import VerifyCommand
    report, _mem = await cycle.run(
        "用 Flask 写一个 Web 服务 app.py", verify_command=VerifyCommand(command="print('PASS')")
    )
    rc = report.reuse_checks or {}
    print(f"  phase={report.phase.value} check={report.check}")
    print(f"  reuse.blocking={rc.get('blocking')}")
    print(f"  manifest.passed={(report.manifest or {}).get('passed')}")
    OK.check("★ check 阶段通过（复用层不再否决正确代码）",
             (report.check or {}).get("passed") is True)
    OK.check("★ reuse.blocking 为空", not (rc.get("blocking") or []))
    OK.check("清单也通过（P7 的模块级赋值 + P7b 的作用域）",
             (report.manifest or {}).get("passed") is True)
    os.environ.pop("DECOMPOSE_GATE", None)

    clean_workspace()
    shutil.rmtree(tmp, ignore_errors=True)
    return OK.report()


raise SystemExit(asyncio.run(main()))
