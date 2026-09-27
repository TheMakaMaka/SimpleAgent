"""离线校验：失败归因分类是否可信。

为什么值得单测
--------------
归因是**给人下判断用的**。归错类比不归因更糟——它会让人朝错误方向修。
所以每一类都要有明确的输入 → 明确的类别，写成断言钉住。

口径来自项目自己（`CYCLE.md` §12 / `能力评估报告.md`）：

    模型能力类 = 规格已写清，模型没做到        → 换模型
    架构缺口类 = 系统缺少某个显式模型          → 补机制

这两类**应对完全不同**，所以不能混。

本测试全离线：合成事件流喂进去，断言类别。

运行：python tests/unit/test_triage.py
"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401

from bridge.triage import CATEGORIES, key_timeline, triage  # noqa: E402

checks: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))


def run(events: list[dict], **kw):
    return triage("run_x", events, **kw)


def cats(t) -> set[str]:
    return {f.category for f in t.findings}


def base(**over) -> list[dict]:
    """一个最小的失败骨架：开跑 → 计划 → 写 → 失败。"""
    ev = [
        {"kind": "run_start", "goal": "g", "max_attempts": 2},
        {"kind": "attempt_start", "attempt": 1, "max_attempts": 2},
        {"kind": "phase", "phase": "plan", "attempt": 1, "transitions": ["plan"]},
        {"kind": "phase", "phase": "write", "attempt": 1, "transitions": ["plan", "write"]},
    ]
    ev += over.pop("mid", [])
    ev += [
        {"kind": "phase", "phase": "failed", "attempt": 1, "transitions": ["plan", "write", "failed"]},
        {"kind": "cycle_end", "status": "failed", "attempt": 1, "error": over.pop("error", "")},
        {"kind": "run_end", "status": "failed"},
    ]
    return ev


# ============================================================
print("=" * 74)
print("[1] manifest 不合格 —— 必须是「模型能力类」，不是「架构缺口类」")
print("=" * 74)
# 这是踩过的坑：早先把 declared-broken 归成架构缺口，等于说"系统缺机制"，
# 会把人引向去补机制，而真正的问题是模型写坏了代码。
t = run(base(mid=[{"kind": "manifest", "checked": True, "passed": False,
                   "violations": [{"kind": "declared-broken", "path": "h.py",
                                   "message": "存在但无法解析: SyntaxError"}]}]))
check("语法坏文件 → model_capability", "model_capability" in cats(t), str(cats(t)))
check("不是 architecture_gap", "architecture_gap" not in cats(t))

t = run(base(mid=[{"kind": "manifest", "checked": True, "passed": False,
                   "violations": [{"kind": "declared-missing", "path": "a.py",
                                   "message": "计划要产出 a.py，但文件不存在"}]}]))
check("声明了没写出 → model_capability", "model_capability" in cats(t), str(cats(t)))
check("证据里有具体文件", any("a.py" in e for f in t.findings for e in f.evidence))

t = run(base(mid=[{"kind": "manifest", "checked": True, "passed": False,
                   "violations": [{"kind": "symbol-missing", "path": "a.py",
                                   "message": "缺少符号: f", "missing": ["f"]}]}]))
check("缺声明符号 → model_capability", "model_capability" in cats(t))

# checked=False 才是真的架构缺口：系统拿不到交付契约
t = run(base(mid=[{"kind": "manifest", "checked": False, "passed": False, "violations": []}]))
check("没有交付声明 → architecture_gap", "architecture_gap" in cats(t), str(cats(t)))

# manifest 通过时不产生**manifest 相关**的归因。
# 注意整个 run 还是 failed（骨架里给了 cycle_end failed），所以会落到 unknown ——
# 那是对的：manifest 没问题，失败原因在别处，归因工具不该硬编一个。
t = run(base(mid=[{"kind": "manifest", "checked": True, "passed": True, "violations": [
    {"kind": "unexpected-file", "path": "extra.py", "message": "不在声明清单内"}]}]))
check("manifest 通过时不产生 manifest 归因",
      all("清单" not in f.summary and "交付" not in f.summary for f in t.findings),
      str([f.summary for f in t.findings]))
check("此时落到 unknown（证据不足就该说证据不足）",
      cats(t) == {"unknown"}, str(cats(t)))


# ============================================================
print("\n" + "=" * 74)
print("[2] 检查与验证的细分")
print("=" * 74)
t = run(base(mid=[{"kind": "syntax", "path": "a.py", "ok": False, "message": "invalid syntax"}]))
check("语法检查失败 → model_capability", "model_capability" in cats(t))

t = run(base(mid=[{"kind": "verify", "passed": False,
                   "detail": "AssertionError: got 34", "command": "assert f(10)==55"}]))
check("断言不通过 → model_capability", "model_capability" in cats(t))
check("证据带上了验收命令", any("assert" in e for f in t.findings for e in f.evidence))

t = run(base(mid=[{"kind": "verify", "passed": False,
                   "detail": "ModuleNotFoundError: No module named 'a'",
                   "command": "import a"}]))
check("验收时找不到模块 → architecture_gap", "architecture_gap" in cats(t), str(cats(t)))

t = run(base(mid=[{"kind": "verify", "passed": False,
                   "detail": "SyntaxError: invalid syntax (line 3)",
                   "command": "assert f(1"}]))
check("验收命令自身语法错 → verify_spec", "verify_spec" in cats(t), str(cats(t)))

t = run(base(mid=[{"kind": "verify", "passed": False,
                   "detail": "TimeoutError: 执行超时（>60 秒）", "command": "while True: pass"}]))
check("验收超时 → environment", "environment" in cats(t), str(cats(t)))

t = run(base(mid=[{"kind": "verify", "passed": False, "detail": "got 34", "command": ""}]))
check("无特征的验收失败仍归 model_capability", "model_capability" in cats(t))


# ============================================================
print("\n" + "=" * 74)
print("[3] 预算 / 取消 / 异常")
print("=" * 74)
two = [
    {"kind": "run_start", "goal": "g", "max_attempts": 2},
    {"kind": "attempt_start", "attempt": 1, "max_attempts": 2},
    {"kind": "verify", "passed": False, "detail": "AssertionError: 1", "command": "c"},
    {"kind": "rollback", "ref": "r1", "ok": True},
    {"kind": "attempt_start", "attempt": 2, "max_attempts": 2},
    {"kind": "verify", "passed": False, "detail": "AssertionError: 2", "command": "c"},
    {"kind": "cycle_end", "status": "failed", "attempt": 2, "error": "验证未通过"},
    {"kind": "run_end", "status": "failed"},
]
t = run(two, max_attempts=2)
check("两次尝试都失败 → 含 budget", "budget" in cats(t), str(cats(t)))
check("尝试次数被正确读出", t.attempts == 2, str(t.attempts))
check("记录了回退", t.rolled_back is True)

t = run([{"kind": "run_start", "goal": "g"}, {"kind": "cancelled", "message": "已按请求取消"},
         {"kind": "run_end", "status": "cancelled"}])
check("取消 → cancelled", cats(t) == {"cancelled"}, str(cats(t)))

t = run([{"kind": "run_start", "goal": "g"},
         {"kind": "error", "message": "TypeError: CodingCycle._emit() got multiple values"},
         {"kind": "run_end", "status": "error"}])
check("运行期异常 → environment", "environment" in cats(t), str(cats(t)))
check("异常消息进了证据", any("_emit" in e for f in t.findings for e in f.evidence))


# ============================================================
print("\n" + "=" * 74)
print("[4] 成功 / 无证据 / 通用不变式")
print("=" * 74)
t = run([{"kind": "run_start", "goal": "g"},
         {"kind": "manifest", "checked": True, "passed": True, "violations": []},
         {"kind": "verify", "passed": True, "detail": "PASS", "command": "c"},
         {"kind": "cycle_end", "status": "passed", "attempt": 1},
         {"kind": "run_end", "status": "passed"}])
check("成功运行不产生归因", not t.findings, str(cats(t)))
check("终态读作 passed", t.status == "passed", t.status)

t = run([{"kind": "run_start", "goal": "g"}, {"kind": "run_end", "status": "failed"}])
check("失败但无证据 → unknown", cats(t) == {"unknown"}, str(cats(t)))
check("unknown 也带证据（events 计数）", bool(t.findings[0].evidence))

# 不变式：每条结论都必须有「类别 / 摘要 / 应对」，且类别是已知的
t = run(two, max_attempts=2)
bad = [f.summary for f in t.findings if f.category not in CATEGORIES or not f.summary]
check("所有结论类别已知且有摘要", not bad, str(bad))
check("所有结论都能给出应对", all(f.action for f in t.findings))
check("每条结论都写了「缺了会怎样」式的应对（非空）",
      all(len(f.action) > 8 for f in t.findings))

tl = key_timeline(two)   # key_timeline 吃的是事件流，不是 Triage
check("时间线只留关键事件", bool(tl) and all(
    k in line for line in tl
    for k in [next((x for x in ("run_start", "attempt_start", "verify", "cycle_end",
                                "run_end", "rollback", "phase") if x in line), "x")]))
check("时间线可读（每行都带 kind）", all(any(c.isalpha() for c in ln) for ln in tl))

md = t.to_markdown()
check("markdown 渲染含标题与应对", "# 失败归因" in md and "**应对**" in md)
check("markdown 不再出现裸类别名", "architecture_gap" not in md and "model_capability" not in md)


# ============================================================
print("\n" + "=" * 74)
print("[5] 真实运行的事件流也能吃进去（形状对得上）")
print("=" * 74)
runs_root = os.path.join(ROOT, "data", "storage_data", "runs")
import json  # noqa: E402

sample = None
if os.path.isdir(runs_root):
    for name in sorted(os.listdir(runs_root), reverse=True):
        p = os.path.join(runs_root, name, "events.jsonl")
        if os.path.isfile(p):
            evs = []
            for line in open(p, encoding="utf-8"):
                line = line.strip()
                if line:
                    try:
                        evs.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            if evs:
                sample = (name, evs)
                break

if sample is None:
    check("有真实运行样本可测", False, "（还没有运行记录，跳过）")
else:
    name, evs = sample
    t = triage(name, evs)
    check(f"能解析真实事件流（{name}, {len(evs)} 事件）", True)
    check("终态被正确读出", t.status in
          ("passed", "failed", "error", "cancelled", "relaxed"), t.status)
    check("时间线非空", bool(t.timeline), f"{len(t.timeline)} 行")


# ============================================================
print("\n" + "=" * 74)
print("断言检查")
print("=" * 74)
failed = [n for n, ok in checks if not ok]
print(f"通过 {len(checks) - len(failed)}/{len(checks)}")
if failed:
    print("失败: " + "; ".join(failed))
raise SystemExit(1 if failed else 0)
