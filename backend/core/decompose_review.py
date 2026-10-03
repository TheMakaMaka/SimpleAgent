"""③ 拆解合规关卡（`TRANSPARENCY2-BACKEND` P3）—— 与 ② 解耦，先机械，**能否决**。

**为什么单独一个关卡**（统筹方 §3.3b）：

> 声明为"建议性、无自由否决权"的审查，**不能当门禁**。
> 而 ③ 需要一个**能否决拆解**的关卡 —— **机械判据天生带否决权**。

**原则是契约载荷，执行方不得改写**（L1 层保证）：本模块**只读**地把
`core/contract.py` 里的 `DECOMPOSE_PRINCIPLES` 拿来用，不在这里改判据。

八条原则（`STANDARD-capability-and-decomposition.md` §2）里 **6 条完全机械**
（P1/P2/P3/P4/P7/P8），**P5/P6 用机械近似并标注 `undecidable`** ——
"机械查不了的、模型也判不了的，**明说判不了**，不要默认通过"。

三层独立性的如实呈现（§3.1）：

| 层 | 内容 | 本模块 |
|---|---|---|
| L1 | 原则本身是外部的 | 读契约里的常量，**不改写** |
| L2 | 机械审查 | `checked_by="tool"` |
| L3 | 判断类审查（语义重复、覆盖完整） | **REVIEW 角色未配置 → 不跑，且明写 `independent=false`** |

⚠️ **绝不把"只有 L1+L2"呈现成"审查通过"**：`passed` 只代表**机械条款**通过，
`coverage_complete=False` 会同时给出，前端要一起看。
"""

from __future__ import annotations

import re
from typing import Any

#: 原则 ID → 一句话（判据本体在 `core/contract.py`，那份是契约载荷）。
PRINCIPLES = ("P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8")

#: P3 的并列连接词表（**契约里也有一份**；这里保持同源，改要一起改）。
CONJUNCTIONS = ("并", "和", "以及", "同时", "然后", "再", "与")

#: P7 的界。
MAX_TASKS = 12
MAX_DEPTH = 3

#: P6 的同义阈值（Jaccard）。
SYNONYM_JACCARD = 0.6

_STOP = {"的", "了", "把", "在", "为", "一个", "并", "和", "以及", "同时", "然后", "再",
         "到", "成", "好", "它", "这个", "那个", "文件", "保存", "实现", "编写", "修正"}


def _tokens(text: str) -> set[str]:
    """粗分词：中文按字/双字、英文/数字按词。**只为机械近似**，不追求正确分词。"""
    t = (text or "").lower()
    words = set(re.findall(r"[a-z_][a-z0-9_]{2,}", t))
    for ch in re.findall(r"[\u4e00-\u9fff]{2,}", t):
        for i in range(len(ch) - 1):
            words.add(ch[i:i + 2])
    return {w for w in words if w not in _STOP}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _paths_in(text: str) -> set[str]:
    return {m.replace("\\", "/").lstrip("./").lower()
            for m in re.findall(r"[\w./\\-]+\.py\b", text or "")}


def _refs_in(text: str, declared_symbols: set[str]) -> set[str]:
    """某个任务**动了哪些东西**：文件名 ∪ 它提到的已声明符号。

    为什么要把符号名算进来（P4）：实测的重复不是"同一个文件名写了两遍"，
    而是「**反复改同一个符号**」—— Run A 里 6 个任务都在改
    `generate_obstacles`，描述里写的是**函数名**而不是文件名。
    只匹配 `.py` 会漏掉整类症状。
    """
    refs = _paths_in(text)
    for sym in declared_symbols:
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(sym)}(?![A-Za-z0-9_])", text or ""):
            refs.add(f"@{sym}")
    return refs


def _norm_desc(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").lower())


def _item(principle: str, verdict: str, evidence: list, level: str) -> dict:
    return {
        "principle": principle,
        "verdict": verdict,          # violated | ok | undecidable
        "evidence": evidence[:5],
        "checked_by": "tool",
        "independent": False,        # 机械层不涉及模型；"独立审查模型"未启用
        "level": level,              # mechanical | approximate
    }


def review_decomposition(decomp: dict, *, goal: str = "") -> dict:
    """审一份拆解。`decomp` 形如 `{"goal","tasks","files","requirements"}`。

    `tasks[]`：`{id, description, expected_output, criterion?}`
    `files[]`：`{path, role, symbols[]}`
    """
    tasks = [t for t in (decomp or {}).get("tasks") or [] if isinstance(t, dict)]
    files = [f for f in (decomp or {}).get("files") or [] if isinstance(f, dict)]
    reqs = [str(r) for r in (decomp or {}).get("requirements") or []]
    goal = goal or str((decomp or {}).get("goal") or "")

    out: list[dict] = []

    # ---------- P1 叶任务=单交付物 ----------
    if not files:
        out.append(_item("P1", "undecidable",
                         ["计划没有声明任何交付物（declared=0）—— 无法判『单交付物』；"
                          "这本身是 P5/P8 要拿的缺口"], "approximate"))
    else:
        bad = []
        for f in files:
            syms = [s for s in (f.get("symbols") or []) if s]
            path = str(f.get("path") or "")
            if len(syms) > 1:
                bad.append(f"{path} 一次要交付 {len(syms)} 个符号：{syms[:4]}")
            elif not syms and path.endswith(".py"):
                bad.append(f"{path} 是 .py 却没说要交付哪个符号")
        out.append(_item("P1", "violated" if bad else "ok", bad or
                         [f"每个交付物恰好 1 个符号（共 {len(files)} 个）"], "mechanical"))

    # ---------- P2 叶任务=单判据 ----------
    with_crit = [t for t in tasks if t.get("criterion")]
    many = [f"{t.get('id')} 声明了多条判据" for t in with_crit
            if isinstance(t.get("criterion"), list) and len(t["criterion"]) > 1]
    if many:
        out.append(_item("P2", "violated", many, "mechanical"))
    elif not with_crit:
        out.append(_item("P2", "undecidable",
                         ["当前拆解形态没有**逐叶判据**（只有 cycle 级一条）—— "
                          "无法判『单判据』；按 §1.2 A3，原子任务本应有逐叶外部判据"],
                         "approximate"))
    else:
        out.append(_item("P2", "ok", [f"{len(with_crit)} 个叶子各带 1 条判据"],
                         "mechanical"))

    # ---------- P3 不并列 ----------
    hits = []
    for t in tasks:
        desc = str(t.get("description") or "")
        found = [c for c in CONJUNCTIONS if c in desc]
        if found:
            hits.append(f"{t.get('id')}「{desc[:40]}」含并列词 {found}")
    out.append(_item("P3", "violated" if hits else "ok", hits or ["没有任务描述含并列连接词"],
                     "mechanical"))

    # ---------- P4 交付物不重叠 ----------
    overlap = []
    declared_symbols = {s for f in files for s in (f.get("symbols") or []) if s}
    seen_sym: dict[str, str] = {}
    for f in files:
        for s in (f.get("symbols") or []):
            if s in seen_sym:
                overlap.append(f"符号 `{s}` 被 {seen_sym[s]} 与 {f.get('path')} 同时声明")
            seen_sym[s] = str(f.get("path"))
    paths = [(t.get("id"), _refs_in(str(t.get("description") or ""), declared_symbols))
             for t in tasks]
    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            shared = paths[i][1] & paths[j][1]
            if shared:
                overlap.append(f"{paths[i][0]} 与 {paths[j][0]} 动同一个文件 {sorted(shared)}")
    out.append(_item("P4", "violated" if overlap else "ok", overlap or ["兄弟交付物两两不相交"],
                     "mechanical"))

    # ---------- P5 覆盖完备（机械近似） ----------
    if not reqs:
        out.append(_item("P5", "undecidable",
                         ["拆解里没有给出『根目标的明确要求』清单 —— "
                          "无法判覆盖完备（机械近似需要那份清单）"], "approximate"))
    else:
        leaf_tokens = [_tokens(str(t.get("description") or "") + " "
                               + str(t.get("expected_output") or "")) for t in tasks]
        uncovered = []
        for r in reqs:
            rt = _tokens(r)
            best = max((_jaccard(rt, lt) for lt in leaf_tokens), default=0.0)
            if best < 0.15:
                uncovered.append(f"要求「{r[:40]}」没有任何叶子覆盖（最高相似度 {best:.2f}）")
        out.append(_item("P5", "violated" if uncovered else "ok",
                         uncovered or [f"{len(reqs)} 条要求都有叶子覆盖"], "approximate"))

    # ---------- P6 无同义重复（机械近似） ----------
    dup = []
    raw_toks = [_tokens(str(t.get("description") or "")) for t in tasks]
    # ★ **去掉"每个任务都有"的词**：它们没有区分度。
    # 为什么必须这么做：真实拆解常用同一个模板
    # （「实现 X 函数写入 X.py」），模板词会让**互相独立的两个任务**看起来
    # 相似度 0.7+，于是审查器一律报红 —— 那和一律报"通过"一样没用。
    if len(raw_toks) > 1:
        common = set.intersection(*raw_toks) if all(raw_toks) else set()
    else:
        common = set()
    toks = [(t.get("id"), rt - common) for t, rt in zip(tasks, raw_toks)]
    for i in range(len(toks)):
        for j in range(i + 1, len(toks)):
            sim = _jaccard(toks[i][1], toks[j][1])
            if sim >= SYNONYM_JACCARD:
                dup.append(f"{toks[i][0]} 与 {toks[j][0]} 描述相似度 {sim:.2f}（阈值 "
                           f"{SYNONYM_JACCARD}）—— 疑似同义重复")
    out.append(_item("P6", "violated" if dup else "ok", dup or ["任务描述两两不重复（近似）"],
                     "approximate"))

    # ---------- P7 单调缩窄 + 有界 + 环 ----------
    p7 = []
    if len(tasks) > MAX_TASKS:
        p7.append(f"叶子数 {len(tasks)} 超过上限 {MAX_TASKS}")
    ids = [str(t.get("id") or "") for t in tasks]
    dupe_ids = sorted({i for i in ids if i and ids.count(i) > 1})
    if dupe_ids:
        p7.append(f"任务 id 重复：{dupe_ids}（同一节点出现两次 = 环的征兆）")
    norm = [_norm_desc(str(t.get("description") or "")) for t in tasks]
    again = sorted({d for d in norm if d and norm.count(d) > 1})
    if again:
        p7.append(f"同一任务描述出现多次：{[a[:30] for a in again[:3]]}")
    depth = int((decomp or {}).get("depth") or 1)
    if depth > MAX_DEPTH:
        p7.append(f"拆解深度 {depth} 超过上限 {MAX_DEPTH}")
    out.append(_item("P7", "violated" if p7 else "ok", p7 or ["有界、无重复 id、无环"],
                     "mechanical"))

    # ---------- P8 现在就写得判据 ----------
    p8 = []
    for t in tasks:
        if not str(t.get("expected_output") or "").strip() and not t.get("criterion"):
            p8.append(f"{t.get('id')} 既没有 expected_output 也没有判据 —— "
                      "拆解时就写不出『怎么算对』")
    out.append(_item("P8", "violated" if p8 else "ok", p8 or ["每个叶子都写得出判据"],
                     "mechanical"))

    violated = [i["principle"] for i in out if i["verdict"] == "violated"]
    undecided = [i["principle"] for i in out if i["verdict"] == "undecidable"]
    return {
        "checked_by": "tool",
        "independent": False,          # ★ 机械层不是"独立审查模型"
        "mechanical_only": True,
        "model_layer": {
            "available": False,
            "reason": "REVIEW 角色未配置 → 判断类审查（L3）**未启用**；"
                      "本结论只覆盖机械条款，不得呈现为『审查通过』",
        },
        "passed": not violated,        # 只有 violated 才有否决权
        "violated": violated,
        "undecidable": undecided,
        "coverage_complete": not violated and not undecided,
        "principles": out,
        "summary": (
            f"机械层：{8 - len(violated) - len(undecided)} 条通过 / "
            f"{len(violated)} 条违反 {violated} / "
            f"{len(undecided)} 条判不了 {undecided}"
            + ("；**且 L3 判断类审查未启用**（REVIEW 未配置）" if undecided else "")
        ),
    }


def from_cycle_plan(goal: str, declared: list | None, tasks: list[dict] | None,
                    requirements: list | None = None) -> dict:
    """从 cycle 的 plan 形态组装待审对象（`coding_cycle` 用）。"""
    return {
        "goal": goal,
        "files": [
            {"path": d.get("path"), "role": d.get("role"),
             "symbols": list(d.get("symbols") or [])}
            for d in (declared or []) if isinstance(d, dict)
        ],
        "tasks": [
            {"id": t.get("id"), "description": t.get("description"),
             "expected_output": t.get("expected_output")}
            for t in (tasks or []) if isinstance(t, dict)
        ],
        "requirements": list(requirements or []),
    }
