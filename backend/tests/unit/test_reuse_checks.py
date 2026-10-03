"""`TRANSPARENCY2-BACKEND` P2（机械复用性 · **硬否决**）+ P4（架构事实层）。

**为什么 P2 最要紧**（工作单原文）：用户那两次运行里**同一个概念模型发明了三个名字**
（真名 `obstacle_generator.generate_obstacles`；Run A 写 `ant_colony.generate_obstacles`
→ `AttributeError`；Run B 写 `obstacle_generator.generate_obstacle_grid()`
→ **函数不存在**）—— **两次都因此失败**。

**为什么 P4 要一条"会红的检查"**：架构视图必须是 **AST 派生的事实**，
不能有"模型手写的架构文档"（那是架构事实的第二份拷贝）。
本文件同时证明：**手写件被拦下、渲染件被放行**。
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
from core.reuse_checks import (  # noqa: E402
    BLOCKING_KINDS, check_code, check_undefined_names, check_workspace,
)
from core.task import Artifact  # noqa: E402
from storage.store import Event  # noqa: E402

OK = Checker()


def write(rel: str, content: str) -> str:
    full = os.path.join(WS, rel)
    os.makedirs(os.path.dirname(full) or WS, exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)
    return rel


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


class FileWorker:
    """按脚本写文件（可多个）。"""

    profile = None

    def __init__(self, files: dict[str, str]):
        self.files = files
        self.n = 0

    async def run(self, task, context):
        self.n += 1
        arts = []
        for rel, content in self.files.items():
            write(rel, content)
            arts.append(Artifact(key=f"{task.id}_{rel}", kind="file", path=rel))
        return TaskResult(task_id=task.id, ok=True,
                          output=f"已写入 {', '.join(self.files)}",
                          artifacts=arts, steps_used=1)


SELF = {"done": [], "not_done": [], "why": [], "reflections": [], "approach": [],
        "confidence": {"level": "low", "basis": ""}, "open_questions": [],
        "requirements": [], "claims": {}}
DONE = {"status": "done", "reasoning": "完事", "tasks": [], "files": [],
        "verify": {}, "final_answer": "完成"}


def plan(verify: dict, files: list) -> dict:
    return {"status": "continue", "reasoning": "写文件", "files": files,
            "tasks": [{"id": "t1", "description": "写文件", "expected_output": "文件",
                       "tool_hint": ["write_file"], "context_refs": []}],
            "verify": verify, "final_answer": ""}


async def run_case(decisions, files, tmp, verify=None):
    store = RecStorage()
    orch = Orchestrator(ScriptedLLM(decisions), FileWorker(files),
                        pipeline=None, verify_command=None)
    cycle = CodingCycle(orchestrator=orch, worker=None, pipeline=CheckPipeline(),
                        max_attempts=1, verbose=False, storage=store, persist=True,
                        on_decision="auto",
                        decisions=DecisionManager(store=FileDecisionStore(root=tmp)))
    report, memory = await cycle.run("写一个能跑的程序")
    return report, memory, store


async def main() -> int:
    tmp = tempfile.mkdtemp(prefix="reuse_")

    # ================= 1. 实测那两条判据必须被抓住 =================
    print("=" * 74)
    print("[1] 实测反例：判据引用了**不存在的符号**（真名是 generate_obstacles）")
    print("=" * 74)
    clean_workspace()
    write("obstacle_generator.py",
          "def generate_obstacles(w, h, density, seed):\n    return []\n")
    write("ant_colony.py", "class AntColony:\n    def run(self):\n        return True\n")
    cases = [
        ("import ant_colony\nassert ant_colony.generate_obstacles((10, 10))", True,
         "Run A 的判据（符号在别的模块里）"),
        ("import obstacle_generator\nassert obstacle_generator.generate_obstacle_grid()",
         True, "Run B 的判据（函数名根本不存在）"),
        ("import obstacle_generator\nassert obstacle_generator.generate_obstacles(10,10,1,1)",
         False, "**正确**的判据（不该被误伤）"),
    ]
    for code, want, why in cases:
        v, _refs = check_code(code, label="<判据>")
        got = bool(v)
        print(f"  {'PASS' if got == want else 'FAIL'}  抓到={got!s:5} {why}")
        OK.check(f"P2：{why}", got == want)
        if got:
            print(f"        → {v[0]['message'][:110]}")

    # ================= 2. 阻塞 vs 警告的分级是**声明过的** =================
    print("\n" + "=" * 74)
    print("[2] 分级：阻塞只留「必然崩」的两类；其余是警告（看得见但不拦路）")
    print("=" * 74)
    print(f"  BLOCKING_KINDS = {sorted(BLOCKING_KINDS)}")
    OK.check("阻塞集合 = 三类「必然崩」",
             set(BLOCKING_KINDS) == {"undefined-symbol", "undefined-name",
                                     "symbol-arity-mismatch"})
    # 签名重构（实测 U2）：判据按旧签名传参 → 必然 TypeError → 阻塞
    write("sig_mod.py", "def f(a, b, c):\n    return a\n")
    arity, _r = check_code("import sig_mod\nsig_mod.f(1)", label="<判据>")
    print(f"  参数个数不符 → {[v['kind'] for v in arity]}")
    OK.check("★ 「按旧签名传参」也是阻塞级（实测那条 `generate_obstacles(10)`）",
             bool(arity) and arity[0]["kind"] == "symbol-arity-mismatch")
    ok_arity, _r2 = check_code("import sig_mod\nsig_mod.f(1, 2, 3)", label="<判据>")
    OK.check("参数个数正确时**不误报**", not ok_arity)
    f821 = check_undefined_names("def f():\n    return np.zeros(3)\n", label="x.py")
    print(f"  用了没导入 → {[v['kind'] for v in f821]} | {f821[0]['message'][:70] if f821 else ''}")
    OK.check("★ 「用了没导入」是阻塞级（实测 `np` 未定义就是它）",
             bool(f821) and f821[0]["kind"] in BLOCKING_KINDS)
    ws = check_workspace()
    w_kinds = {w["kind"] for w in ws["warnings"]}
    print(f"  workspace 警告种类：{sorted(w_kinds)}")
    OK.check("重复符号/命名不一致**只进 warnings**（不拦路）",
             all(w["severity"] == "warning" for w in ws["warnings"]))

    # ================= 3. 端到端：交付物调了不存在的符号 → check 必须红 =================
    print("\n" + "=" * 74)
    print("[3] 端到端：交付物里调了不存在的符号 → check 红、结局 fail")
    print("=" * 74)
    clean_workspace()
    files = {
        "b.py": "def other():\n    return 1\n",
        "a.py": "import b\n\ndef run():\n    return b.missing_fn()\n",
    }
    r3, _m3, s3 = await run_case(
        [plan({"command": "import a\na.run()", "reason": "调用"},
              [{"path": "a.py", "role": "入口", "symbols": ["run"]}]),
         DONE, SELF], files, tmp)
    rc = r3.reuse_checks or {}
    print(f"  phase={r3.phase.value} outcome={r3.outcome} kind={r3.outcome_kind}")
    print(f"  check={r3.check}")
    for v in rc.get("blocking") or []:
        print(f"    [阻塞] {v.get('kind')}: {str(v.get('message'))[:100]}")
    OK.check("★ check 判红（不再带着错误放行）", (r3.check or {}).get("passed") is False)
    OK.check("check.status=failed", (r3.check or {}).get("status") == "failed")
    OK.check("报告里带 reuse_checks 结论", bool(rc.get("blocking")))
    OK.check("结局是 fail（交付物自己坏了，算模型头上）", r3.outcome == "fail")
    reuse_ev = s3.saved("reuse")
    print(f"  reuse 事件 {len(reuse_ev)} 条")
    OK.check("reuse 事件进了事件流且 passed=false",
             bool(reuse_ev) and (reuse_ev[0].payload or {}).get("passed") is False)

    # ================= 4. P4：架构文档 —— 手写被拦、渲染件放行 =================
    print("\n" + "=" * 74)
    print("[4] P4：架构视图**不得由模型手写**；派生视图渲染件放行")
    print("=" * 74)
    clean_workspace()
    pipe = CheckPipeline()
    write("架构说明.md", "# 架构说明\n\n我认为系统分三层……\n")
    hand = pipe._arch_doc_violations(["架构说明.md"])
    print(f"  手写件 → {[v['kind'] for v in hand]}")
    OK.check("★ 手写架构文档**被拦下**（检查会红）",
             bool(hand) and hand[0]["kind"] == "hand-written-architecture-doc")

    from tools.arch import ARCH_VIEW_MARKER, render_architecture_view

    rendered = render_architecture_view(limit=5)
    write("架构视图.md", rendered)
    ok_render = pipe._arch_doc_violations(["架构视图.md"])
    print(f"  渲染件 → {[v['kind'] for v in ok_render]}（首行标记 {rendered.splitlines()[0][:44]}）")
    OK.check("★ 渲染件（带 derived-from 标记）**放行**", not ok_render)
    OK.check("渲染件确实带来源标记", rendered.startswith(ARCH_VIEW_MARKER))
    OK.check("渲染件内容来自 AST 派生视图（有模块表）", "| 模块 |" in rendered)

    # 端到端：手写件当交付物 → check 红
    clean_workspace()
    r5, _m5, _s5 = await run_case(
        [plan({"command": "assert open('架构说明.md').read().strip()", "reason": "非空"},
              [{"path": "架构说明.md", "role": "架构文档", "symbols": []}]),
         DONE, SELF], {"架构说明.md": "# 架构说明\n\n手写的\n"}, tmp)
    print(f"  端到端：phase={r5.phase.value} kind={r5.outcome_kind} "
          f"check.passed={(r5.check or {}).get('passed')}")
    OK.check("★ 手写架构文档作为交付物 → check 红、结局 fail",
             (r5.check or {}).get("passed") is False and r5.outcome == "fail")

    clean_workspace()
    shutil.rmtree(tmp, ignore_errors=True)
    return OK.report()


raise SystemExit(asyncio.run(main()))
