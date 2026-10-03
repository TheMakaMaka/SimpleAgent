"""文档审查工具：让模型能审查文档（机械层）。

定位（与 review_code 的分工）
-----------------------------
  review_code        审**代码**：语法、lint、裸 except、可变默认参数…
  review_document    审**文档**：代码块是否合法、引用是否真实存在

两者都是**建议性**，不参与 cycle 成败判定。但文档审查里的机械部分
（引用存在性、代码块语法）是程序判定的确定事实，所以它的结论**可信**——
不像"这段解释是否误导"那类需要模型判读的问题。

只读
----
它只读文档、不改任何东西。写权限不在这个工具里（见 `core/doc_access.py`
的只读窗口设计）。

为什么不能让子循环直接 read_file 文档
-------------------------------------
`tools/files.py` 的访问被限制在 `workspace/`——那是**代码生成沙箱**，
边界是对的。文档在仓库根，所以另开了受控只读窗口。
"""

import json

from .registry import register

# 单次返回的最大失败条数，避免一个坏文档把上下文吃光
_MAX_FAILURES = 15


@register(
    name="review_document",
    description=(
        "审查一份项目文档（markdown）的机械正确性：python 代码块是否合法、"
        "`from X import Y` 与 `模块.符号` 引用是否真实存在、§ 交叉引用是否有效。"
        "不传 path 时列出可审查的文档。"
        "**只读**，结论是程序判定的确定事实（不涉及语义质量判断）。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "相对仓库根的文档路径，如 docs/MODULES.md 或 README.md；留空则列出全部",
                "default": "",
            }
        },
        "required": [],
        "additionalProperties": False,
    },
    profiles=("coding",),
)
async def review_document(path: str = "") -> str:
    from core.doc_access import DocAccessError, list_docs, read as read_doc
    from core.doc_review import importable_modules, review_text

    # 未给路径 → 列出可审查的文档（让模型知道有什么可看）
    if not (path or "").strip():
        docs = list_docs()
        return json.dumps(
            {
                "ok": True,
                "mode": "list",
                "count": len(docs),
                "documents": [d.to_dict() for d in docs],
                "note": "传入 path 可审查其中一份。只读，不修改文档。",
            },
            ensure_ascii=False,
        )

    try:
        text = read_doc(path)
    except DocAccessError as e:
        return json.dumps(
            {"ok": False, "error": str(e), "path": path},
            ensure_ascii=False,
        )

    mods = importable_modules()
    result = review_text(path, text, mods)
    payload = result.to_dict()

    # 控制返回体量
    if len(payload["failures"]) > _MAX_FAILURES:
        payload["failures"] = payload["failures"][:_MAX_FAILURES]
        payload["truncated"] = True

    payload["ok"] = True
    payload["note"] = (
        "这是**机械检查**：引用存在性、代码块语法，结论可信。"
        "文档的语义质量（表述是否准确、是否误导）不在本工具范围内——"
        "那需要模型判读，属建议层，不能作判据。"
        "本工具只读，不会修改文档。"
    )
    return json.dumps(payload, ensure_ascii=False)
