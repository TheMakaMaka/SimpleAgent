"""反思工具：让模型自己看到「历史执行暴露了什么模式」。

定位（重要）
------------
这是一个**只读的分析工具**，不是裁决者：
  - 它返回结构化的模式发现 + 证据引用，供模型在规划时参考
  - 它**不修改任何东西**（不改 prompt、不改预算、不改代码）
  - 它**不参与成败判定**

为什么要有它：此前模型只能看到"最近 N 条任务记录"（按条数截断），
看不到跨 cycle 的统计模式。而这类模式恰恰是它自己无法凭记忆发现的——
模型对自身行为的记忆极不可靠（本项目实测：声称建了 3 个文件，实际只建了 1 个）。

分析全部由程序完成（见 core/reflect.py），**不经过模型**，
因此结论可信、可复现；模型拿到的是结论 + 证据，不是"回忆"。
"""

import json

from .registry import register

_MAX_PATTERNS = 12


@register(
    name="reflect_on_history",
    description=(
        "分析历史执行记录，找出反复出现的失败模式、重试热点、"
        "以及「模型声称成功但验证未通过」的情况，返回结构化结论与证据。"
        "在开始一个与以往类似的任务前调用它，可以避免重复踩同一个坑。"
        "注意：这是只读分析，结论仅供参考，不会自动修改任何配置。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "limit_cycles": {
                "type": "integer",
                "description": "分析最近多少个 cycle（默认 20）",
                "default": 20,
            }
        },
        "required": [],
        "additionalProperties": False,
    },
    profiles=("coding",),
)
async def reflect_on_history(limit_cycles: int = 20) -> str:
    from core.reflect import reflect_from_storage

    try:
        report = reflect_from_storage(limit_cycles=max(1, int(limit_cycles)))
    except Exception as e:
        return json.dumps(
            {"ok": False, "error": f"反思分析失败: {e}", "patterns": []},
            ensure_ascii=False,
        )

    if report.cycles_analyzed == 0:
        return json.dumps(
            {
                "ok": True,
                "cycles_analyzed": 0,
                "patterns": [],
                "note": "还没有历史执行记录，无模式可分析。",
            },
            ensure_ascii=False,
        )

    # 按置信度排序后截断，并显式告知被截断了多少
    order = {"high": 0, "medium": 1, "low": 2}
    ordered = sorted(
        report.patterns,
        key=lambda p: (order.get(p.confidence, 3), -p.occurrences),
    )
    kept = ordered[:_MAX_PATTERNS]

    return json.dumps(
        {
            "ok": True,
            "cycles_analyzed": report.cycles_analyzed,
            "summary": report.summary,
            "patterns": [
                {
                    "kind": p.kind,
                    "confidence": p.confidence,
                    "title": p.title,
                    "detail": p.detail,
                    "occurrences": p.occurrences,
                    "cycles": p.cycles[:6],
                    "suggestion": p.suggestion,
                    "target": p.target,
                    "evidence": [e.label() for e in p.evidence[:6]],
                }
                for p in kept
            ],
            "truncated": max(0, len(ordered) - len(kept)),
            "note": (
                "以上为程序统计结论，证据列指向具体事件（cycle#seq）。"
                "这是只读分析，仅供规划参考；不要据此声称任务已完成。"
            ),
        },
        ensure_ascii=False,
    )
