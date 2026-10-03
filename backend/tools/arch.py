"""架构视图工具：让模型按需查询工程结构，而不必把所有代码读进上下文。

设计选择：**查询式，而非推送式。**
每轮自动把架构摘要塞进 prompt 会持续消耗预算，最终退化成"每轮塞一大堆"，
和 summary_for_orchestrator 没本质区别。查询式才真正满足"不加载所有代码"，
而且模型问什么就暴露了它在关心什么——这些查询本身就是架构跟踪角色的原料。

★ **架构事实的唯一来源就在这里**（`TRANSPARENCY2-BACKEND` P4）：
要人类可读版就 `render_architecture_view()` **从派生视图渲染** ——
**禁止手写架构文档**（那会成为"架构事实的第二份拷贝"，
本项目的原话是「两边都不算错，错在**有两份**」）。
渲染件带 `<!-- derived-from: ast-architecture-view -->` 标记，
门禁（`core/pipeline.py::_arch_doc_violations`）据此放行渲染件、拦住手写件。

★ **P11（2026-10-03）：把这张地图补成可信的**。底座没重写，只补四件：
  1. **覆盖率账目** `indexed` / `skipped` / `truncated`，且 `skipped` **逐条**给理由
     （非 `.py` / 解析失败 / 超 `limit` / 权限不足 / 跳过目录）—— **禁止静默截断**；
  2. **新鲜度**：每个文件带内容哈希（sha256）+ 视图自带 `generated_at` + `root`；
  3. **范围显式**：写明扫的根（设了任务级 `project_root` 就是它，否则是工作区根）；
  4. **反向索引**：「谁 import 了 X」⇒ 改动的**爆炸半径**才算得出来。

数据来源是 core/symbol_index.py 与 core/manifest.py 解析出的**结构事实**
（AST 扫描，不经过模型），因此内容可信、不会幻觉。

三个工具的分工：
  get_architecture()  总览：有哪些模块、各自导出什么、依赖谁（+覆盖率/新鲜度/范围）
  get_module(path)    单模块详情：完整符号表 + 被谁依赖（+内容哈希）
  find_symbol(name)   反查：某个符号定义在哪里（没找到时给出"扫了多少、跳过了多少"）
"""

import json

from core import runtime
from core.manifest import architecture_view
from core.symbol_index import (
    build_index_report,
    find_symbol as _find_symbol,
    freshness_of,
)

from .registry import register

# 单次返回的模块数上限，避免一次把整个工程倒给模型
_DEFAULT_LIMIT = 20

#: 渲染件的来源标记 —— 门禁靠它区分"从 AST 派生视图渲染"与"模型手写"。
ARCH_VIEW_MARKER = "<!-- derived-from: ast-architecture-view -->"

#: 覆盖账目里逐条列出的 skipped 上限（超出只做**计数**，并明写被省略了多少）。
#: 注意：这里省略的是"理由清单的展示条数"，`coverage.skipped` 计数仍是全量，
#: 且会写上 `skipped_omitted` —— 依然是**显式**的，不是静默截断。
_MAX_SKIPPED_ITEMS = 60


def _coverage_out(rep: dict) -> dict:
    """把扫描报告里的覆盖账目整理成工具输出（含逐条理由 + 省略计数）。"""
    cov = dict(rep.get("coverage") or {})
    items = list(cov.get("skipped_items") or [])
    omitted = max(0, len(items) - _MAX_SKIPPED_ITEMS)
    cov["skipped_items"] = items[:_MAX_SKIPPED_ITEMS]
    cov["skipped_omitted"] = omitted
    cov["root"] = rep.get("root", "")
    cov["generated_at"] = rep.get("generated_at", "")
    return cov


def _scope_out(rep: dict) -> dict:
    """范围显式：读的人不该猜这份地图扫的是哪个根。"""
    return {
        "root": rep.get("root", ""),
        "source": runtime.effective_root_source(),
        "project_root": runtime.project_root(),
        "workspace_root": runtime.workspace_root(),
        "output_root": runtime.output_root(),
        "note": (
            "扫描根 = 任务级 project_root（设了就用它），否则 = workspace_root。"
            "非 .py 文件不解析，但会逐条出现在 coverage.skipped 里"
        ),
    }


def _report(limit: int | None = None) -> dict:
    """扫**当前有效根**并带上覆盖账目（P11 的唯一数据入口）。"""
    return build_index_report(runtime.effective_root(), limit=limit)


def _view(limit: int | None = None) -> dict:
    """派生视图 + 覆盖率账目 + 新鲜度 + 范围 + 反向索引。"""
    rep = _report(limit)
    view = architecture_view(rep["index"])
    view["coverage"] = _coverage_out(rep)
    view["freshness"] = freshness_of(rep)
    view["scope"] = _scope_out(rep)
    view["reverse_index"] = rep.get("reverse_index") or {}
    view["broken"] = sorted(rep.get("broken") or {})
    return view


def render_architecture_view(limit: int = _DEFAULT_LIMIT) -> str:
    """把 AST 派生视图**渲染**成人类可读的 Markdown（P4 的唯一允许路径）。

    刻意做成纯函数、不注册成工具：**它不该由模型在规划阶段自由调用并"润色"** ——
    渲染件的价值就在于"内容与事实同源、逐字可核对"。要落盘时由调用方
    （或 `write_file` 直接写返回值）完成，且**必须保留首行的来源标记**。

    ★ P11：渲染件也带覆盖账目与新鲜度 —— 否则"看起来完整"仍然是不可信的。
    """
    view = _view(limit)
    rep = _report(limit)
    cov = view["coverage"]
    fresh = view["freshness"]
    lines = [
        ARCH_VIEW_MARKER,
        "# 架构视图（由 AST 派生，请勿手写）",
        "",
        "> 本文件由 `tools/arch.py::render_architecture_view()` 从符号索引渲染，",
        "> 内容与 `get_architecture()` 同源。**手写版会成为架构事实的第二份拷贝。**",
        "",
        f"- 扫描根：`{view['scope']['root']}`（来源：{view['scope']['source']}）",
        f"- 生成时刻：{fresh.get('generated_at')}",
        f"- 模块数：{view.get('totals', {}).get('files', len(view.get('modules') or []))}"
        f"（indexed={cov.get('indexed')}）",
        f"- 符号数：{view.get('totals', {}).get('symbols', '?')}",
        f"- 代码行：{view.get('totals', {}).get('lines', '?')}",
        f"- 覆盖账目：`scanned={cov.get('scanned')} indexed={cov.get('indexed')} "
        f"skipped={cov.get('skipped')} truncated={cov.get('truncated')}`",
        "",
        "| 模块 | 导出符号 | 依赖 | 行数 | sha256 |",
        "|---|---|---|---|---|",
    ]
    for m in (view.get("modules") or [])[:limit]:
        exports = ", ".join(m.get("exports") or []) or "—"
        deps = ", ".join(m.get("depends_on") or []) or "—"
        sha = (fresh.get("files") or {}).get(m.get("path"), "")[:12]
        lines.append(
            f"| `{m.get('path')}` | {exports} | {deps} | {m.get('lines', '')} | `{sha}` |"
        )
    if len(view.get("modules") or []) > limit:
        lines.append("")
        lines.append(
            f"（只列前 {limit} 个模块，共 {len(view['modules'])} 个；"
            f"被省略的模块逐条记在 `coverage.truncated_items`，不是静默截断）"
        )
    skipped = cov.get("skipped_items") or []
    if skipped:
        lines += ["", "## 未纳入地图的文件/目录（逐条理由）", ""]
        for item in skipped:
            lines.append(
                f"- `{item.get('path')}` — {item.get('reason')}：{item.get('detail') or ''}"
            )
        if cov.get("skipped_omitted"):
            lines.append(
                f"- …另有 {cov['skipped_omitted']} 条同类记录（计数仍计在 "
                f"`coverage.skipped={cov.get('skipped')}`）"
            )
    return "\n".join(lines) + "\n"


def _module_compact(m: dict, fresh: dict) -> dict:
    """get_architecture 的单个模块条目（加性：多一个 sha256）。"""
    return {
        "path": m["path"],
        "exports": [e["signature"] for e in m["exports"]],
        "depends_on": m["depends_on"],
        "lines": m["lines"],
        # ★ P11 要求 2：每个文件带内容哈希（新鲜度）
        "sha256": (fresh.get("files") or {}).get(m["path"], ""),
    }


@register(
    name="get_architecture",
    description=(
        "查看**目标项目根**（未设时为 workspace）的工程结构总览：每个 .py 文件"
        "导出的符号、依赖的其他本地模块、行数、内容哈希，以及**覆盖率账目**"
        "（扫了多少、跳过多少、为什么跳过）。"
        "在需要从全局考虑（例如多个文件如何协作、是否已有可复用的函数）时调用它，"
        "而不是把每个文件都读一遍。"
        "注意：非 .py 文件不会被解析，但会逐条出现在 coverage.skipped 里 —— "
        "`skipped` 非空说明这张地图**不完整**，不要把它读成「不存在」。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": f"最多返回多少个模块（默认 {_DEFAULT_LIMIT}）",
                "default": _DEFAULT_LIMIT,
            }
        },
        "required": [],
        "additionalProperties": False,
    },
    profiles=("coding",),
)
async def get_architecture(limit: int = _DEFAULT_LIMIT) -> str:
    limit = max(1, int(limit))
    rep = _report(limit)
    view = architecture_view(rep["index"])
    fresh = freshness_of(rep)
    modules = view["modules"]

    if not modules:
        return json.dumps(
            {
                "ok": True,
                "modules": [],
                "totals": view["totals"],
                "truncated": False,
                "coverage": _coverage_out(rep),
                "freshness": fresh,
                "scope": _scope_out(rep),
                "reverse_index": {},
                "note": (
                    f"根 {rep['root']} 下没有解析成功的 .py 文件"
                    "（**不等于「没有文件」**：看 coverage.skipped 的逐条理由）"
                ),
            },
            ensure_ascii=False,
        )

    compact = [_module_compact(m, fresh) for m in modules[:limit]]
    rev = rep.get("reverse_index") or {}
    shown = {c["path"] for c in compact}
    # 反向索引只回报**这次真的返回了**的模块（谁 import 了它），避免无界膨胀
    rev_shown = {
        m["module"]: [p for p in rev.get(m["module"], []) if p]
        for m in modules[:limit]
        if rev.get(m["module"])
    }

    return json.dumps(
        {
            "ok": True,
            "modules": compact,
            # 兼容键：仍是 bool（消费方不必改），细节在 coverage.truncated_items
            "truncated": len(modules) > len(compact),
            "totals": view["totals"],
            # ★ P11 要求 1/2/3/4：覆盖账目 / 新鲜度 / 范围 / 反向索引
            "coverage": _coverage_out(rep),
            "freshness": fresh,
            "scope": _scope_out(rep),
            "reverse_index": rev_shown,
            "broken": sorted(rep.get("broken") or {}),
            "shown": sorted(shown),
            "note": (
                "只含结构事实（AST 解析）。需要单个模块的完整符号表请用 get_module。"
                "`coverage.skipped` 逐条给出的都是**没纳入地图**的东西"
            ),
        },
        ensure_ascii=False,
    )


@register(
    name="get_module",
    description=(
        "查看某个模块的完整结构：所有顶层函数/类的签名、类的方法、"
        "它依赖的本地模块、以及被哪些模块依赖（反向索引）。"
        "修改或复用某个文件前先看这个，比读整个文件省上下文。"
        "路径相对**目标项目根**（未设时为 workspace）；返回自带内容哈希。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "相对目标项目根的文件路径，例如 cli.py 或 pkg/util.py",
            }
        },
        "required": ["path"],
        "additionalProperties": False,
    },
    profiles=("coding",),
)
async def get_module(path: str) -> str:
    rep = _report()
    index = rep["index"]
    broken = rep.get("broken") or {}
    key = (path or "").strip().replace("\\", "/").lstrip("./")
    if key.startswith("workspace/"):
        key = key[len("workspace/"):]

    entry = index.get(key)

    # 解析失败的文件**也在索引之外**，但必须说清"是解析失败"而不是"不存在"
    if entry is None and key in broken:
        return json.dumps(
            {
                "ok": False,
                "error": f"{key} 无法解析: {broken[key].error}",
                "skipped_reason": "parse-failed",
                "scope": _scope_out(rep),
                "coverage": _coverage_out(rep),
            },
            ensure_ascii=False,
        )

    # 容错：模型常只给文件名（util.py）而索引键是完整相对路径（pkg/util.py）。
    # 唯一匹配时直接接受；有歧义时列出候选让模型指定，避免猜错文件。
    if entry is None and "/" not in key:
        # 允许后缀匹配：模型问 util.py 时，_archtest_util.py 也应算候选。
        # 唯一匹配直接接受；有歧义则列出候选，避免猜错文件。
        matches = [k for k in index if k.split("/")[-1].endswith(key)]
        if len(matches) == 1:
            key = matches[0]
            entry = index[key]
        elif len(matches) > 1:
            return json.dumps(
                {
                    "ok": False,
                    "error": f"{key} 匹配到多个文件，请指定完整路径",
                    "candidates": sorted(matches),
                    "scope": _scope_out(rep),
                },
                ensure_ascii=False,
            )

    if entry is None:
        # 给出可用的候选，避免模型反复猜路径
        return json.dumps(
            {
                "ok": False,
                "error": f"模块不存在: {path}",
                "available": sorted(index.keys())[:30],
                # ★ P11：`indexed=0` 与"真的没有这个模块"必须可区分
                "coverage": _coverage_out(rep),
                "scope": _scope_out(rep),
            },
            ensure_ascii=False,
        )

    # 反向依赖：谁 import 了我（P11 要求 4：爆炸半径）
    rev = rep.get("reverse_index") or {}
    dependents = sorted(rev.get(entry.module) or [])

    return json.dumps(
        {
            "ok": True,
            "path": entry.path,
            "module": entry.module,
            "symbols": [s.to_dict() for s in entry.symbols],
            "depends_on": entry.local_deps,
            "depended_by": dependents,
            # 兼容别名：同一份事实的另一个名字（反向索引）
            "imported_by": dependents,
            "lines": entry.lines,
            "sha1": entry.sha1,
            # ★ P11 要求 2：内容哈希（sha256）+ 生成时刻
            "sha256": (rep.get("hashes") or {}).get(entry.path, ""),
            "generated_at": rep.get("generated_at", ""),
            "scope": _scope_out(rep),
        },
        ensure_ascii=False,
    )


@register(
    name="find_symbol",
    description=(
        "按名字查找某个函数/类定义在哪个文件的哪一行，返回签名（含文件:行）。"
        "想复用已有实现、或确认某个函数是否已经写过时用它，不要靠读文件猜。"
        "没找到时会同时给出**扫了多少、跳过了多少** —— "
        "`indexed=0` 或 `skipped` 很多时，「没找到」不等于「不存在」。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "符号名，例如 bubble_sort 或 Stack"}
        },
        "required": ["name"],
        "additionalProperties": False,
    },
    profiles=("coding",),
)
async def find_symbol(name: str) -> str:
    target = (name or "").strip()
    if not target:
        return json.dumps({"ok": False, "error": "name 不能为空"}, ensure_ascii=False)

    rep = _report()
    hits = _find_symbol(rep["index"], target)
    if not hits:
        cov = _coverage_out(rep)
        return json.dumps(
            {
                "ok": True,
                "found": False,
                "name": target,
                # ★ P11：把"没找到"与"没扫到"分开（判不了 ≠ 通过）
                "coverage": cov,
                "scope": _scope_out(rep),
                "note": (
                    f"在本轮的 {cov.get('indexed')} 个已解析 .py 文件里没有这个名字的定义；"
                    f"另有 {cov.get('skipped')} 项未纳入地图（见 coverage.skipped_items）"
                    "—— 若那里面有 .py 解析失败，则本结论**不完整**"
                    if (cov.get("skipped") or 0) > 0
                    else f"在 {cov.get('indexed')} 个已解析 .py 文件里没有这个名字的定义，"
                         "可能还没实现"
                ),
            },
            ensure_ascii=False,
        )

    return json.dumps(
        {
            "ok": True,
            "found": True,
            "name": target,
            "definitions": hits,
            "coverage": _coverage_out(rep),
            "scope": _scope_out(rep),
        },
        ensure_ascii=False,
    )
