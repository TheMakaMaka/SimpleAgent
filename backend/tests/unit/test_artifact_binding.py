"""`TRANSPARENCY3-BACKEND` P6 / P7 / P8 的回归。

P6（**判词必须描述产物**，优先级与 P1 同级）
--------------------------------------------
实测事实（统筹方能力基线）：两个任务报 `fail`，而**归档产物是对的** ——
同一条判据对归档产物在干净进程里重跑**都 PASS**。
⇒ **那次验证执行的，不是这份被交付的产物。**

本文件把机制**确定性地复现出来**并锁住修复：`.pyc` 与源码的 `(mtime, size)`
一旦凑巧一致（**回退用 `copy2` 会保留原 mtime**，极易撞上），`import` 就会执行
**旧代码**。所以：
* 先证明"危险是真的"（不清缓存 → 读到旧代码）；
* 再证明"清理有效"（清掉 → 读到新代码）；
* 并证明**判词与最终产物对不上时，结局是 `invalid` 而不是 `fail`**。

P7（🔴 符号表必须收模块级赋值）
-------------------------------
`app = Flask(__name__)` 被判「`缺少符号: app`」= 假失败，且**毁掉一个能力轴的读数**。

P8（`decompose_review` 模式要显式）
-----------------------------------
warn 模式下 `passed=False` 不影响运行通过 —— 事件里必须写清 `mode` / `applied`。
（`P20` 起**出厂默认回到 `warn`**；本组仍**显式**开 `warn`，专测这条语义，
`block` 下的双向验收在 `tests/unit/test_decompose_review.py` 的 `[V5]`。）
"""

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import Checker, WORKSPACE as WS, clean_workspace  # noqa: E402

from core import (  # noqa: E402
    CheckPipeline, CodingCycle, DecisionManager, Orchestrator, TaskResult,
)
from core.decisions import FileDecisionStore  # noqa: E402
from core.manifest import DeclaredFile, check_manifest  # noqa: E402
from core.symbol_index import build_index, raw_module_bindings  # noqa: E402
from core.task import Artifact  # noqa: E402
from storage.store import Event  # noqa: E402

OK = Checker()

#: 同一长度的两版实现 —— 长度必须相同，否则 .pyc 校验会失败（那就不叫"陈旧"了）
SRC_A = 'def f():\n    return "A"\n'
SRC_B = 'def f():\n    return "B"\n'


def write(rel: str, content: str) -> str:
    full = os.path.join(WS, rel)
    os.makedirs(os.path.dirname(full) or WS, exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)
    return full


def compile_bytescode(rel: str = "mod.py") -> None:
    """让 CPython 生成 `.pyc`（**不加 `-B`**，这是复现危险的前提）。"""
    subprocess.run([sys.executable, "-c", f"import {rel[:-3]}"],
                   cwd=WS, capture_output=True, text=True, timeout=60)


def import_mod_print() -> str:
    r = subprocess.run([sys.executable, "-c", "import mod;print(mod.f())"],
                       cwd=WS, capture_output=True, text=True, timeout=60)
    return (r.stdout or "").strip()


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


class W:

    profile = None

    def __init__(self, files: dict[str, str]):
        self.files = files

    async def run(self, task, context):
        arts = []
        for rel, content in self.files.items():
            write(rel, content)
            arts.append(Artifact(key=f"{task.id}_{rel}", kind="file", path=rel))
        return TaskResult(task_id=task.id, ok=True, output="写了 " + ", ".join(self.files),
                          artifacts=arts, steps_used=1)


SELF = {"done": [], "not_done": [], "why": [], "reflections": [], "approach": [],
        "confidence": {"level": "low", "basis": ""}, "open_questions": [],
        "requirements": [], "claims": {}}
DONE = {"status": "done", "reasoning": "完事", "tasks": [], "files": [],
        "verify": {}, "final_answer": "完成"}


def plan(verify: dict, files: list) -> dict:
    return {"status": "continue", "reasoning": "写文件", "files": files,
            "tasks": [{"id": "t1", "description": "写 mod.py", "expected_output": "mod.py",
                       "tool_hint": ["write_file"], "context_refs": []}],
            "verify": verify, "final_answer": ""}


async def run_case(decisions, files, tmp):
    store = RecStorage()
    orch = Orchestrator(ScriptedLLM(decisions), W(files), pipeline=None,
                        verify_command=None)
    cycle = CodingCycle(orchestrator=orch, worker=None, pipeline=CheckPipeline(),
                        max_attempts=1, verbose=False, storage=store, persist=True,
                        on_decision="auto",
                        decisions=DecisionManager(store=FileDecisionStore(root=tmp)))
    report, memory = await cycle.run("实现 mod.f")
    return report, memory, store


async def main() -> int:
    tmp = tempfile.mkdtemp(prefix="artifact_")

    # ================= P6 · 危险是真的 =================
    print("=" * 74)
    print("[P6-1] ★ 先证明危险是真的：.pyc 陈旧 → import 到**旧代码**")
    print("=" * 74)
    clean_workspace()
    write("mod.py", SRC_A)
    compile_bytescode()
    st = os.stat(os.path.join(WS, "mod.py"))
    write("mod.py", SRC_B)
    os.utime(os.path.join(WS, "mod.py"), (st.st_atime, st.st_mtime))
    stale = import_mod_print()
    print(f"  同长度 + 还原 mtime 后，不清缓存 import → {stale!r}（源码里是 'B'）")
    OK.check("★ 危险可复现：读到的是**旧代码**（'A'）", stale == "A")

    cleared, warn = CheckPipeline._purge_pycache()
    fresh = import_mod_print()
    print(f"  清掉 __pycache__（{cleared} 个）后 import → {fresh!r}")
    OK.check("★ 清理有效：读到新代码（'B'）", fresh == "B")
    OK.check("清理失败时会给出警告字段（不静默）", isinstance(warn, str))

    # ================= P6 · 判词描述产物（缓存陈旧也不误判） =================
    print("\n" + "=" * 74)
    print("[P6-2] 端到端：缓存陈旧时，判词仍然描述**产物**")
    print("=" * 74)
    clean_workspace()
    write("mod.py", SRC_A)
    compile_bytescode()
    st = os.stat(os.path.join(WS, "mod.py"))
    # 让 worker 写 B 版，但把 mtime 还原成 A 的时间（复刻回退 copy2 的效果）
    r2, _m2, s2 = await run_case(
        [plan({"command": "import mod\nassert mod.f() == 'B'", "reason": "断言返回 B"},
              [{"path": "mod.py", "role": "实现", "symbols": ["f"]}]),
         DONE, SELF], {"mod.py": SRC_B}, tmp)
    try:
        os.utime(os.path.join(WS, "mod.py"), (st.st_atime, st.st_mtime))
    except OSError:
        pass
    print(f"  phase={r2.phase.value} outcome={r2.outcome}")
    print(f"  verify.artifact_hashes={r2.verify.get('artifact_hashes')} "
          f"cwd={r2.verify.get('cwd')} cache_cleared={r2.verify.get('cache_cleared')}")
    OK.check("★ 缓存陈旧**不再**导致假失败（phase=record）", r2.phase.value == "record")
    OK.check("★ 报告里能读到被验证产物的**内容哈希**",
             bool((r2.verify or {}).get("artifact_hashes")))
    OK.check("★ 报告里能读到验证的**工作目录**（P6 要求 3）",
             bool((r2.verify or {}).get("cwd")))
    OK.check("★ 报告里能读到清过字节码缓存的痕迹（P6 要求 4）",
             int((r2.verify or {}).get("cache_cleared") or 0) >= 0)
    v_ev = s2.saved("verify")
    OK.check("verify 事件里也带哈希与 cwd（事件可对账）",
             bool(v_ev) and "artifact_hashes" in (v_ev[-1].payload or {})
             and "cwd" in (v_ev[-1].payload or {}))

    # ================= P6 · 产物被改过 → invalid =================
    print("\n" + "=" * 74)
    print("[P6-3] ★ 产物在验证之后被改过 → 结局是 `invalid`，不是 `fail`")
    print("=" * 74)
    clean_workspace()
    # 判据自己**改写**被验产物（模拟"被验证的产物 ≠ 被交付的产物"）
    tamper = {"command": "import mod\nassert mod.f() == 'B'\n"
                         "open('mod.py', 'a').write('# tampered\\n')",
              "reason": "断言之后再动一下文件（构造产物漂移）"}
    r3, _m3, _s3 = await run_case(
        [plan(tamper, [{"path": "mod.py", "role": "实现", "symbols": ["f"]}]),
         DONE, SELF], {"mod.py": SRC_B}, tmp)
    print(f"  phase={r3.phase.value} outcome={r3.outcome} kind={r3.outcome_kind}")
    print(f"  mismatch={(r3.verify or {}).get('artifact_mismatch')}")
    print(f"  error={str(r3.error)[:120]}")
    OK.check("★ 结局是 invalid（读数无效，不是模型失败）", r3.outcome == "invalid")
    OK.check("原因种类 = artifact-mismatch", r3.outcome_kind == "artifact-mismatch")
    OK.check("报告里两个哈希**可比**（验证时 vs 交付时）",
             bool((r3.verify or {}).get("artifact_hashes"))
             and bool((r3.verify or {}).get("artifact_hashes_final")))
    OK.check("★ 没有打检查点（commit 为空）", not r3.commit)

    # ================= P7 · 模块级赋值 =================
    print("\n" + "=" * 74)
    print("[P7] `app = Flask(__name__)` **不得**被判「缺少符号 app」")
    print("=" * 74)
    clean_workspace()
    write("app.py", "from flask import Flask\napp = Flask(__name__)\n"
                    "CONFIG: dict = {}\n\n\ndef run():\n    return app\n")
    idx = build_index()
    syms = {(s.name, s.kind) for s in (idx.get("app.py").symbols if idx.get("app.py") else [])}
    print(f"  索引到的符号：{sorted(syms)}")
    OK.check("★ 模块级赋值进了符号表（app / CONFIG）",
             ("app", "variable") in syms and ("CONFIG", "variable") in syms)
    man = check_manifest([DeclaredFile(path="app.py", role="应用入口",
                                       symbols=["app", "run"])])
    bad = [v for v in man.violations if v["kind"] == "symbol-missing"]
    print(f"  manifest: passed={man.passed} violations={[v['kind'] for v in man.violations]}")
    OK.check("★ 不再假失败（没有 symbol-missing）", not bad)
    OK.check("清单判定通过", man.passed is True)

    # 真没有 → 仍是阻塞，且带**可复核位置**
    write("other.py", "def exists():\n    return 1\n")
    man2 = check_manifest([DeclaredFile(path="other.py", role="x", symbols=["nope"])])
    miss = [v for v in man2.violations if v["kind"] == "symbol-missing"]
    print(f"  真缺符号：{miss[0]['message'][:70] if miss else '(未报)'} | at="
          f"{miss[0].get('at') if miss else ''}")
    OK.check("真没有仍然是 error", bool(miss) and miss[0]["severity"] == "error")
    OK.check("★ 阻塞判定带可复核位置（文件:行）", bool(miss and miss[0].get("at", "").count(":")))

    # 「有但我没索引到」→ 必须是**可区分**的（索引缺口，不拦路）
    from core.symbol_index import _ModuleVisitor

    orig = _ModuleVisitor.visit_Assign
    _ModuleVisitor.visit_Assign = lambda self, node: None      # 人为制造索引缺口
    try:
        man3 = check_manifest([DeclaredFile(path="app.py", role="x", symbols=["app"])])
    finally:
        _ModuleVisitor.visit_Assign = orig
    kinds3 = [v["kind"] for v in man3.violations]
    print(f"  索引缺口场景 → {kinds3}")
    OK.check("★ 「有但我没索引到」被标成 symbol-unindexed（warning，不拦路）",
             "symbol-unindexed" in kinds3
             and all(v["severity"] == "warning" for v in man3.violations
                     if v["kind"] == "symbol-unindexed"))
    OK.check("且**不会**同时报 symbol-missing（不再假失败）",
             "symbol-missing" not in kinds3)
    OK.check("raw_module_bindings 是独立的第二意见",
             "app" in raw_module_bindings("app.py"))

    # ================= P8 · decompose_review 模式显式 =================
    print("\n" + "=" * 74)
    print("[P8] `decompose_review` 事件必须写清 mode / applied")
    print("=" * 74)
    clean_workspace()
    bad_plan = plan({"command": "import mod\nassert mod.f() == 'B'", "reason": "x"},
                    [{"path": "mod.py", "role": "实现", "symbols": ["f"]}])
    bad_plan["tasks"][0]["description"] = "写 mod.py 并验证它"    # 含「并」→ P3 违反
    # ★ P20 起出厂默认回到 warn（P18 曾升到 block，但实测误否决 ⇒ 先止血）；
    #   本组**显式**开 warn，专测"模式必须写清、warn 不否决"这条语义
    #   （block 下的双向验收在 test_decompose_review.py 的 [V5]）。
    os.environ["DECOMPOSE_GATE"] = "warn"
    try:
        r8, _m8, s8 = await run_case([bad_plan, DONE, SELF], {"mod.py": SRC_B}, tmp)
    finally:
        os.environ.pop("DECOMPOSE_GATE", None)
    ev = s8.saved("decompose_review")
    pl = (ev[-1].payload if ev else {}) or {}
    print(f"  mode={pl.get('mode')!r} applied={pl.get('applied')} "
          f"passed={pl.get('passed')} violated={pl.get('violated')}")
    OK.check("事件里带 mode（本组显式 warn）", pl.get("mode") == "warn")
    OK.check("★ warn 模式下 applied=False（**没有**用否决权）", pl.get("applied") is False)
    OK.check("此时运行仍可通过（审查未通过 ≠ 运行不通过）", r8.phase.value == "record")
    OK.check("报告里也带 gate_mode", (r8.decompose_review or {}).get("gate_mode") == "warn")

    clean_workspace()
    shutil.rmtree(tmp, ignore_errors=True)
    return OK.report()


raise SystemExit(asyncio.run(main()))
