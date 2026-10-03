"""生成 `TRANSPARENCY-UI` 的 C3 夹具：**用上游自己的 `fact_check()` 产出对照**。

为什么要有它
------------
验收第 4 条是：「收尾自述里 `not_done` 含『跑测试』与『生成报告』；若模型谎报，
`fact_check` 矛盾一眼可见」。而**自述是模型写的**，我离线造不出真模型的话；
`self_report` 事件也要后端 C1 才发。

所以这里换一个能机械验证的做法：

  1. **机械事实**取自那次真实运行的 `meta.json`（`phase` / `touched_files` /
     `manifest` / `verify` / `check`）—— 样本事件流里本来就有的东西；
  2. **自述文本**是明写的夹具（下面 `HONEST` / `LYING`），它扮演"模型可能会说的话"；
  3. **`fact_check` 不手写** —— 调用**上游 `core.self_report.fact_check()`**，
     用真代码产出对照结果。

于是"矛盾能不能被检出来"这件事**不是我说了算**，是后端自己的判定函数说了算；
前端要做的只是把它显示在最显眼处。产物：

    tests/fixtures/transparency-fixture.json

`frontend/scripts/replay-check.mjs` 读它，驱动**状态级**与**渲染级**两组断言。

配置分流：够不到上游（`AGENT_UPSTREAM_DIR` / `AGENT_BACKEND_DIR`）时 SKIP，
并把原因写清楚 —— 不把自己的环境问题报成失败（与 `test_two_entrypoints.py` 同一条纪律）。

运行：python tests/diagnostics/make_transparency_fixture.py
"""

import contextlib
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402

SAMPLE = os.path.join(ROOT, "data", "storage_data", "runs", "run_20260927_125647_5a3297")
OUT = os.path.join(ROOT, "tests", "fixtures", "transparency-fixture.json")

#: 夹具自述必须提到的两项（验收第 4 条点名要求的两件事）。
REQUIRED_NOT_DONE = ["跑测试", "生成报告"]

HONEST = {
    "done": [
        "生成了 obstacle_generator.py（随机撒点的障碍物生成规则）",
        "生成了 ant_colony.py（基础蚁群算法）",
        "生成了 test_ant_colony.py（测试脚本）",
    ],
    "not_done": [
        "**没有跑测试**：test_ant_colony.py 写出来了，但一次都没有执行过",
        "**没有生成报告**：工作区里没有报告文件",
    ],
    "why": [
        "把「写出来」当成了「验证过」，验收判据只查了 import 成功",
    ],
    "reflections": [
        "目标里明确要求『连续测试验证』和『生成对应报告』，两项都没有做，也没有在结论里说明",
    ],
    "approach": ["先设计障碍物生成规则，再写蚁群算法，最后补一个测试脚本"],
    "confidence": {"level": "medium", "basis": "判据通过了，但那条判据只证明了函数名能导入"},
    "open_questions": ["10*10 网格上起始点与目标点是否真的连通，没有检查过"],
    "claims": {
        "verify_passed": True,
        "check_passed": True,
        "artifacts": ["obstacle_generator.py", "ant_colony.py", "test_ant_colony.py"],
    },
}

#: 「谎报」版：在 `done` 里声称做完了那两件事。**这正是要被抓的那种自述。**
LYING = {
    "done": [
        "生成了 obstacle_generator.py、ant_colony.py、test_ant_colony.py",
        "**连续测试验证已完成**：测试脚本已写好并运行通过",
        "**已生成报告**：报告文件 report.md",
    ],
    "not_done": [],
    "why": [],
    "reflections": ["流程整体顺利"],
    "approach": ["设计 → 实现 → 测试 → 报告"],
    "confidence": {"level": "high", "basis": "全部完成"},
    "open_questions": [],
    "claims": {
        "verify_passed": True,
        "check_passed": True,
        # ★ 关键：声称产出了 `report.md`，而磁盘上没有这个文件
        "artifacts": ["obstacle_generator.py", "ant_colony.py", "test_ant_colony.py", "report.md"],
    },
}


def find_upstream() -> str:
    """参考上游目录：优先 AGENT_UPSTREAM_DIR，其次 AGENT_BACKEND_DIR。"""
    for env in ("AGENT_UPSTREAM_DIR", "AGENT_BACKEND_DIR"):
        p = (os.getenv(env) or "").strip()
        if p and os.path.isfile(os.path.join(p, "core", "self_report.py")):
            return p
    return ""


def machine_facts() -> dict:
    """**机械事实**：只从那次运行的报告里取，模型说的话一律不进这里。"""
    meta = json.load(io.open(os.path.join(SAMPLE, "meta.json"), encoding="utf-8"))
    rep = meta.get("report") or {}
    man = rep.get("manifest") or {}
    # 那次运行的真实产物（事件流里的 `files.touched`）
    touched = list(rep.get("touched_files") or [])
    lint_failed = [
        f"{s.get('path') or s.get('file')}: {', '.join(str(i) for i in (s.get('issues') or []))}"
        for s in (rep.get("check_steps") or [])
        if s.get("tool") == "lint" and s.get("status") == "failed"
    ]
    return {
        "phase": rep.get("phase"),
        # `workspace_files`：那次运行的产物就是它的工作区内容（离线只能这样取，
        # 且**故意不包含 report.md** —— 这正是"没有报告"这一事实的来源）
        "workspace_files": touched,
        "touched_files": touched,
        "manifest_actual": [a.get("path") for a in (man.get("actual") or []) if a.get("path")],
        "manifest_declared": [d.get("path") for d in (man.get("declared") or []) if d.get("path")],
        "verify": rep.get("verify"),
        "check": rep.get("check") or {},
        "lint_failed": lint_failed,
    }


def normalize_like_backend(upstream: str, raw: dict) -> dict:
    """走上游 `normalize()` —— 夹具也要**经过后端的规整**，不能手拼形状。

    ★ **必须在 import 上游之前把 CWD 切到运行根（`data/`）**：
    上游的路径是 CWD 相对的（`os.path.abspath("workspace")`），而
    `import core` 会执行 `core/__init__.py`，它连带 import 的模块有建目录的副作用。

    这条是**被门禁抓出来的**：一开始这里没切 CWD，于是从仓库根跑一次这个脚本，
    就在**仓库根**留下了一个 `workspace/` —— `tests/unit/test_isolation.py`
    当场地报了 `FAIL 仓库根无 workspace/`。
    （同一原因也解释了更早那次"来路不明的仓库根 `workspace/`"。）
    """
    with _at_runtime_root():
        sys.path.insert(0, upstream)
        from core.self_report import fact_check, normalize  # noqa: E402

        # `normalize()` 是纯函数，不碰 LLM
        entry = normalize(raw)
        entry["ok"] = True
        entry["phase"] = "record"
        entry["fact_check"] = fact_check(entry, machine_facts())
        return entry


@contextlib.contextmanager
def _at_runtime_root():
    """临时把 CWD 切到运行根（与 `tests/_bootstrap.py` 同一条判据）。"""
    root = os.environ.get("AGENT_RUNTIME_ROOT") or os.path.join(ROOT, "data")
    root = os.path.abspath(root)
    os.makedirs(root, exist_ok=True)
    prev = os.getcwd()
    os.chdir(root)
    try:
        yield root
    finally:
        os.chdir(prev)


def real_run_inputs(run_id: str) -> dict:
    """取一次**真实运行**的拆分结果：任务描述 + 声明的交付物（给拆解审查当输入）。

    这样 `review_decomposition()` 审的是**真的那次拆分**，不是我编的样例。
    """
    d = os.path.join(ROOT, "data", "storage_data", "runs", run_id)
    meta = json.load(io.open(os.path.join(d, "meta.json"), encoding="utf-8"))
    tasks: list[dict] = []
    for line in io.open(os.path.join(d, "events.jsonl"), encoding="utf-8"):
        if not line.strip():
            continue
        e = json.loads(line)
        if e.get("kind") == "task_start":
            tasks.append({"id": e.get("task_id"), "description": e.get("description") or ""})
    files: list[dict] = []
    for line in io.open(os.path.join(d, "events.jsonl"), encoding="utf-8"):
        if not line.strip():
            continue
        e = json.loads(line)
        if e.get("kind") == "plan":
            for item in e.get("declared") or []:
                if isinstance(item, dict):
                    files.append({"path": item.get("path"), "role": item.get("role") or "",
                                  "symbols": item.get("symbols") or []})
    return {"goal": meta.get("goal") or "", "tasks": tasks, "files": files}


def backend_samples(upstream: str) -> dict:
    """P3/P4 的夹具：**全部调后端的真函数**，一个都不手写。

    | 产出 | 后端函数 |
    |---|---|
    | 结局四值 | `core.outcome.build_verdict` / `classify_verify_detail` |
    | 拆解合规审查 | `core.decompose_review.review_decomposition` |
    | 复用性检查 | `core.reuse_checks.check_code` |

    ★ 为什么非要调真函数：**判据不能由被验的一方自己写**。
    我手写一个 `{"outcome": "abstain"}` 只能证明"我的模板会渲染它"，
    证明不了"后端真会产出这个形状"。调真函数则两者同时成立。
    """
    with _at_runtime_root():
        if upstream not in sys.path:
            sys.path.insert(0, upstream)
        from core.decompose_review import review_decomposition  # noqa: E402
        from core.outcome import build_verdict, classify_verify_detail  # noqa: E402
        from core.reuse_checks import check_workspace  # noqa: E402

        # ---- 结局四值：三种典型（判据来自模型 / 说不出什么叫对 / 判据自己坏了）----
        verify_ok = {"passed": True, "source": "model", "detail": "（无输出）"}
        broken_detail = "Traceback ... SyntaxError: invalid syntax"
        kind, why = classify_verify_detail(broken_detail)
        verdicts = {
            "pass_model_self_authored": build_verdict(
                "verified", "判据执行且通过", verify_ok,
                extra="判据由模型自拟 —— 通过也要看得出这一点"),
            "abstain_no_criterion": build_verdict(
                "no-admissible-criterion", "模型自拟的判据全被拒（没有一条引用交付物）", None),
            "invalid_criterion_broken": build_verdict(
                kind, why, {"passed": False, "source": "model", "detail": broken_detail}),
            "fail_verify_failed": build_verdict(
                "verify-failed", "判据真跑过、断言没过",
                {"passed": False, "source": "caller", "detail": "assert 失败"}),
        }

        # ---- 拆解合规审查：审**真实那次运行**的拆分 ----
        decomp = real_run_inputs("run_20260927_230240_0a42df")
        review = review_decomposition(decomp, goal=decomp.get("goal") or "")

        # ---- 复用性检查：**跑一次真的工作区检查**（结果是空的也照实记）----
        #
        # ★ 这里刻意**不编造**一条阻塞项：`check_workspace()` 是后端真函数，
        #   它此刻没发现阻塞项，那就如实写"没有"。
        #   "阻塞项长什么样"由 `frontend/scripts/replay-check.mjs` 里那条
        #   **按契约字段造的合成事件**覆盖（标明是合成的）。
        reuse = check_workspace()
    return {
        "verdicts": verdicts,
        "decompose_review": review,
        "decompose_input": {"tasks": len(decomp.get("tasks") or []),
                            "files": len(decomp.get("files") or [])},
        "reuse": {
            "checked": bool(reuse.get("checked")),
            "passed": reuse.get("passed"),
            "blocking": [str(x)[:200] for x in (reuse.get("blocking") or [])][:6],
            "warnings": [str(x)[:200] for x in (reuse.get("warnings") or [])][:6],
        },
    }


def main() -> int:
    upstream = find_upstream()
    if not upstream:
        print("SKIP  够不到上游（设 AGENT_UPSTREAM_DIR 或 AGENT_BACKEND_DIR 指向 SimpleAgent2_Cycle）")
        print("      → 夹具无法用后端自己的 fact_check 生成；已有产物不会被覆盖")
        return 0
    if not os.path.isdir(SAMPLE):
        print(f"FAIL  找不到固定样例：{SAMPLE}")
        return 1

    print("=" * 74)
    print(f"上游：{upstream}")
    print(f"样例：{os.path.relpath(SAMPLE, ROOT)}")
    print("=" * 74)

    facts = machine_facts()
    print("机械事实：")
    for k, v in facts.items():
        print(f"  {k:18} {json.dumps(v, ensure_ascii=False)[:110]}")

    out = {
        "_note": (
            "TRANSPARENCY-UI 的 C3 夹具。**自述文本是明写的夹具**（扮演模型可能说的话），"
            "**fact_check 由上游 core.self_report.fact_check() 真代码产出**，"
            "机械事实取自固定样例 run_20260927_125647_5a3297 的 meta.json。"
            "由 tests/diagnostics/make_transparency_fixture.py 生成，不要手改。"
        ),
        "_generator": "tests/diagnostics/make_transparency_fixture.py",
        "_upstream": upstream,
        "machine_facts": facts,
        "self_report_honest": normalize_like_backend(upstream, HONEST),
        "self_report_lying": normalize_like_backend(upstream, LYING),
        # P3/P4：**全部由后端自己的函数产出**（见下），一个都不手写
        **backend_samples(upstream),
    }

    print()
    ok = True
    for name, key in (("诚实版", "self_report_honest"), ("谎报版", "self_report_lying")):
        sr = out[key]
        fc = sr["fact_check"]
        print(f"[{name}] done={len(sr['done'])} not_done={len(sr['not_done'])} "
              f"矛盾={len(fc['contradictions'])} 未提及={len(fc['unmentioned'])}")
        for c in fc["contradictions"]:
            print(f"    ✗ {c['kind']}: {c['claim']}  ⇔  {c['fact'][:90]}")
        for u in fc["unmentioned"]:
            print(f"    ? {u}")

    # ---- 机械断言：夹具必须真的能演示验收第 4 条的两半 ----
    honest = out["self_report_honest"]["fact_check"]
    lying = out["self_report_lying"]["fact_check"]

    print()
    print("=" * 74)
    checks = []

    def check(name, cond, detail=""):
        checks.append((name, bool(cond)))
        print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))

    nd = " ".join(out["self_report_honest"]["not_done"])
    check("★ 诚实版 not_done 含「跑测试」", "跑测试" in nd, nd[:80])
    check("★ 诚实版 not_done 含「生成报告」", "生成报告" in nd)
    check("★ 诚实版没有凭空造出矛盾（自述与事实一致）", not honest["contradictions"],
          str([c["kind"] for c in honest["contradictions"]]))
    kinds = [c["kind"] for c in lying["contradictions"]]
    check("★ 谎报版被后端自己的 fact_check 抓出矛盾", bool(kinds), str(kinds))
    check("★ 谎报版矛盾指向 report.md（工作区里没有这个文件）",
          any("report.md" in (c["claim"] + c["fact"]) for c in lying["contradictions"]),
          str(kinds))
    check("★ 谎报版矛盾类型是后端定义的那两种之一",
          any(k in ("artifact-missing", "done-mentions-missing-file") for k in kinds), str(kinds))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(f"\n已写入 {os.path.relpath(OUT, ROOT)}")

    failed = [n for n, c in checks if not c]
    print(f"通过 {len(checks) - len(failed)}/{len(checks)}")
    if failed:
        print("失败: " + "; ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
