"""文档只读访问：为「文档审查」开一扇受控的窗。

为什么需要单独一层
------------------
`tools/files.py` 的路径防护把访问限制在 `workspace/` 内——那是**代码生成沙箱**，
边界是对的，不该放宽。但文档（`README.md`、`docs/*.md`）在仓库根，
子循环根本读不到（`../docs/MODULES.md` 会被拒绝）。

所以不复用写代码的沙箱，而是**另开一个只读窗口**：

  - 只读，不含写：本模块只提供 `read()`，没有写路径
  - 显式白名单：默认只允许 `README.md` / `docs/` / `CYCLE.md`，
    可用 `DOC_REVIEW_ROOTS` 覆盖
  - 拒绝穿越：`..` 一律拒绝，符号链接不跟随
  - 有大小上限：避免一个巨文件把上下文吃光

这与 `ModelLimits` 的纪律一致：**边界显式、可配置、有单一来源**，
而不是散落的魔法值。
"""

import os
from dataclasses import dataclass

# 默认允许审查的文档根（相对仓库根）
DEFAULT_DOC_ROOTS = (
    "README.md",
    "CYCLE.md",
    "docs",
)

MAX_DOC_BYTES = 256 * 1024


class DocAccessError(ValueError):
    """文档访问被拒绝。原因见消息——这是策略，不是 bug。"""


def project_root() -> str:
    """仓库根目录。以本文件位置为准，不依赖 CWD。"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def doc_roots() -> tuple[str, ...]:
    """允许的文档根。可用 DOC_REVIEW_ROOTS 覆盖（冒号分隔）。"""
    raw = (os.getenv("DOC_REVIEW_ROOTS") or "").strip()
    if not raw:
        return DEFAULT_DOC_ROOTS
    sep = ";" if ";" in raw else ":"
    return tuple(p.strip() for p in raw.split(sep) if p.strip())


def resolve_doc_path(rel_path: str) -> str:
    """把文档相对路径解析成绝对路径，并做白名单校验。

    拒绝规则（都要拒绝，不是警告）：
      - 绝对路径、盘符
      - 任何 `..` 段
      - 落在允许根之外
      - 解析后不是普通文件（目录/设备）
    """
    if not rel_path or not rel_path.strip():
        raise DocAccessError("路径为空")

    raw = rel_path.strip().replace("\\", "/")
    if os.path.isabs(raw) or (len(raw) > 1 and raw[1] == ":"):
        raise DocAccessError(f"只接受相对仓库根的路径: {rel_path}")

    parts = [p for p in raw.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise DocAccessError(f"禁止路径穿越: {rel_path}")

    root = project_root()
    target = os.path.abspath(os.path.join(root, *parts))

    # 必须在允许根之内（比较归一化后的路径前缀）
    allowed = False
    for r in doc_roots():
        base = os.path.abspath(os.path.join(root, r))
        if target == base or target.startswith(base + os.sep):
            allowed = True
            break
    if not allowed:
        raise DocAccessError(
            f"不在允许的文档范围内: {rel_path}（允许 {list(doc_roots())}）"
        )

    if not os.path.exists(target):
        raise DocAccessError(f"文档不存在: {rel_path}")
    if not os.path.isfile(target):
        raise DocAccessError(f"不是普通文件: {rel_path}")

    return target


def read(rel_path: str) -> str:
    """读取一份文档。超限直接拒绝（而不是静默截断——截断会让审查漏掉内容）。"""
    target = resolve_doc_path(rel_path)
    size = os.path.getsize(target)
    if size > MAX_DOC_BYTES:
        raise DocAccessError(
            f"文档过大（{size} 字节 > {MAX_DOC_BYTES}），拒绝整体读取"
        )
    with open(target, "r", encoding="utf-8") as f:
        return f.read()


@dataclass
class DocEntry:
    path: str          # 相对仓库根
    size: int

    def to_dict(self) -> dict:
        return {"path": self.path, "size": self.size}


def list_docs() -> list[DocEntry]:
    """列出允许范围内的全部 markdown 文档。"""
    root = project_root()
    out: list[DocEntry] = []
    seen: set[str] = set()

    for r in doc_roots():
        base = os.path.join(root, r)
        if os.path.isfile(base) and base.endswith(".md"):
            rel = os.path.relpath(base, root).replace("\\", "/")
            if rel not in seen:
                seen.add(rel)
                out.append(DocEntry(path=rel, size=os.path.getsize(base)))
            continue
        if not os.path.isdir(base):
            continue
        for cur, dirs, names in os.walk(base):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for n in sorted(names):
                if not n.endswith(".md"):
                    continue
                full = os.path.join(cur, n)
                rel = os.path.relpath(full, root).replace("\\", "/")
                if rel in seen:
                    continue
                seen.add(rel)
                out.append(DocEntry(path=rel, size=os.path.getsize(full)))

    out.sort(key=lambda e: e.path)
    return out


def describe() -> dict:
    """诊断用。"""
    return {
        "project_root": project_root(),
        "roots": list(doc_roots()),
        "max_bytes": MAX_DOC_BYTES,
        "documents": len(list_docs()),
        "note": "只读窗口；写路径不存在。改文档仍需人或有写权限的角色。",
    }
