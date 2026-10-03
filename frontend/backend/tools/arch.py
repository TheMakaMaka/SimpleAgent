"""架构视图工具：让模型按需查询工程结构，而不必把所有代码读进上下文。

设计选择：**查询式，而非推送式。**
每轮自动把架构摘要塞进 prompt 会持续消耗预算，最终退化成"每轮塞一大堆"，
和 summary_for_orchestrator 没本质区别。查询式才真正满足"不加载所有代码"，
而且模型问什么就暴露了它在关心什么——这些查询本身就是架构跟踪角色的原料。

数据来源是 core/symbol_index.py 与 core/manifest.py 解析出的**结构事实**
（AST 扫描，不经过模型），因此内容可信、不会幻觉。

三个工具的分工：
  get_architecture()  总览：有哪些模块、各自导出什么、依赖谁
  get_module(path)    单模块详情：完整符号表 + 被谁依赖
  find_symbol(name)   反查：某个符号定义在哪里（避免读整个文件找定义）
"""

import json

from core.manifest import architecture_view
from core.symbol_index import build_index, find_symbol as _find_symbol

from .registry import register

# 单次返回的模块数上限，避免一次把整个工程倒给模型
_DEFAULT_LIMIT = 20


def _view() -> dict:
    return architecture_view(build_index())


@register(
    name="get_architecture",
    description=(
        "查看当前 workspace 的工程结构总览：每个 .py 文件导出的符号、"
        "依赖的其他本地模块、行数。"
        "在需要从全局考虑（例如多个文件如何协作、是否已有可复用的函数）时调用它，"
        "而不是把每个文件都读一遍。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": f"最多返回多少个模块（默认 {_DEFAULT_LIMIT}）",
            }
        },
        "required": [],
    },
    profiles=("coding",),
)
async def get_architecture(limit: int = _DEFAULT_LIMIT) -> str:
    view = _view()
    modules = view["modules"]

    if not modules:
        return json.dumps(
            {"ok": True, "modules": [], "totals": view["totals"],
             "note": "workspace 下还没有任何 .py 文件"},
            ensure_ascii=False,
        )

    # 只给"结构摘要"，不给每个符号的完整签名，控制返回体量
    compact = []
    for m in modules[: max(1, int(limit))]:
        compact.append({
            "path": m["path"],
            "exports": [e["signature"] for e in m["exports"]],
            "depends_on": m["depends_on"],
            "lines": m["lines"],
        })

    return json.dumps(
        {
            "ok": True,
            "modules": compact,
            "totals": view["totals"],
            "truncated": len(modules) > len(compact),
            "note": "只含结构事实（AST 解析）。需要单个模块的完整符号表请用 get_module。",
        },
        ensure_ascii=False,
    )


@register(
    name="get_module",
    description=(
        "查看某个模块的完整结构：所有顶层函数/类的签名、类的方法、"
        "它依赖的本地模块、以及被哪些模块依赖。"
        "修改或复用某个文件前先看这个，比读整个文件省上下文。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "相对 workspace 的文件路径，例如 cli.py 或 pkg/util.py",
            }
        },
        "required": ["path"],
    },
    profiles=("coding",),
)
async def get_module(path: str) -> str:
    index = build_index()
    key = (path or "").strip().replace("\\", "/").lstrip("./")
    if key.startswith("workspace/"):
        key = key[len("workspace/"):]

    entry = index.get(key)

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
            },
            ensure_ascii=False,
        )

    if not entry.syntax_ok:
        return json.dumps(
            {"ok": False, "error": f"{key} 无法解析: {entry.error}"},
            ensure_ascii=False,
        )

    # 反向依赖：谁 import 了我
    dependents = sorted(
        e.path for e in index.values() if entry.module in e.local_deps
    )

    return json.dumps(
        {
            "ok": True,
            "path": entry.path,
            "module": entry.module,
            "symbols": [s.to_dict() for s in entry.symbols],
            "depends_on": entry.local_deps,
            "depended_by": dependents,
            "lines": entry.lines,
            "sha1": entry.sha1,
        },
        ensure_ascii=False,
    )


@register(
    name="find_symbol",
    description=(
        "按名字查找某个函数/类定义在哪个文件的哪一行，返回签名。"
        "想复用已有实现、或确认某个函数是否已经写过时用它，不要靠读文件猜。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "符号名，例如 bubble_sort 或 Stack"}
        },
        "required": ["name"],
    },
    profiles=("coding",),
)
async def find_symbol(name: str) -> str:
    target = (name or "").strip()
    if not target:
        return json.dumps({"ok": False, "error": "name 不能为空"}, ensure_ascii=False)

    hits = _find_symbol(build_index(), target)
    if not hits:
        return json.dumps(
            {
                "ok": True,
                "found": False,
                "name": target,
                "note": "workspace 里没有这个符号的定义，可能还没实现",
            },
            ensure_ascii=False,
        )

    return json.dumps(
        {"ok": True, "found": True, "name": target, "definitions": hits},
        ensure_ascii=False,
    )
