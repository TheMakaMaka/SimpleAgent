"""记忆单元：**结构 + 抽取 + 内容指纹**（P21 / M1）。

来源：用户 2026-10-03 提议的「上下文链路调用算法（外部记忆库）」，
统筹方在 `WORK-ORDER.md`【P21】里把它落成三期（M1 存储与检索 / M2 记分不决策 /
M3 接入），并写死三条硬要求：

  1. 判据要覆盖**漏召 / 误召**，不能只看「调用成功」；
  2. 必须有**第二路召回** —— 挂在已有结构索引（`find_symbol`/`get_module`/
     `get_architecture`）上，**别另起关键词库**；
  3. 阈值第一阶段**不许定死**：只记分、不决策，用数据校准。

本模块只负责第 2 条里的「符号引用」这一半：把一段上下文里**真实出现过的标识符**
抽成 `symbol_refs`。它是**纯语法抽取**（正则，不查索引、不猜语义），
因此可机械复现；到 M2/M3 再由**同一份** `symbol_refs` 去问结构索引
「这个符号定义在哪个文件:行」—— **不新建关键词库**。

单元结构（M1 验收 ①「单元结构（时间 / 关键词 / 符号引用）」）：

    {
      "id":         内容寻址 id（sha256 前 16 位）
      "created_at": 第一次写入的时刻（**保留最早值** ⇒ 重放不会改时间线）
      "content":    正文
      "keywords":   关键词（**调用方给的 + 从正文兜底抽的**，去重排序）
      "symbol_refs": 符号引用（标识符形态；`file:line` 引用另见 `refs`）
      "refs":       `[{file, line}]`，从正文里的 `文件:行` 抽出来
      "source":     来源标签（任务 / 批次 / 会话）
      "sha256":     正文内容哈希（新鲜度：内容一变哈希就变）
      "status":     "active" | "archived"
      "archived_at" 归档时刻（未归档为 None）
    }

★ 「淘汰 = 归档，不是删除」在这里就定死：单元只有 `status` 的迁移，
**没有删除路径**（见 `store.ContextStore.archive`）。
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

#: 内容哈希进 id 时取前多少位（够用且可读；碰撞由 `store.write` 的
#: 同 id 不同哈希检测兜住，不会静默覆盖）。
ID_LEN = 16

#: 关键词下限/上限：太多关键词等于没有关键词（会把任何查询都召回）。
MAX_KEYWORDS = 24
MAX_SYMBOL_REFS = 64

#: 标识符形态。**刻意保守**：只认 Python/JS 风格的普通标识符，
#: 不认中文（中文是关键词的活，不是符号的活）。
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,63}")

#: 正文里的 `文件:行` 引用（与 P7b / P11 的「可复核位置」同一形状）。
_REF_RE = re.compile(r"([A-Za-z0-9_./\\-]+\.[A-Za-z0-9_]+):(\d+)")

#: 关键词切分：空白 + 常见标点。中文没有空白，所以**整串中文短语**也是一个关键词
#: （这正是「同义不同词」只能靠第二路召回的原因）。
_WORD_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}")

#: 这些词几乎出现在任何一段代码上下文里，作为**关键词**没有区分度。
#: 注意：它们仍然可以出现在 `symbol_refs` 里（那一路看的是「是不是符号」）。
_STOPWORDS = frozenset({
    "the", "and", "for", "with", "this", "that", "from", "not", "are", "was",
    "def", "class", "return", "import", "self", "none", "true", "false",
    "print", "str", "int", "list", "dict", "test", "run", "code", "file",
})


def now_iso() -> str:
    """统一时刻格式（本地时间，秒级；便于人读日志）。"""
    return datetime.now().isoformat(timespec="seconds")


def utc_iso() -> str:
    """带时区的时刻（归档留痕用；跨机器比较不会歧义）。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_text(text: str) -> str:
    """归一化：行尾统一 LF、去掉首尾空白。

    为什么必须做：内容寻址的前提是「**同一段上下文**」在不同平台上得到同一个 id。
    CRLF/LF 的差异会让同一段记忆变成两个单元 —— 那正是「同一件事有两份」的老病。
    """
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def content_sha256(text: str) -> str:
    """正文内容哈希（新鲜度判据：内容一变，哈希就变）。"""
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def unit_id(content: str, source: str = "") -> str:
    """内容寻址 id：`sha256(source \\n content)` 前 `ID_LEN` 位。

    ★ 为什么把 `source` 也算进去：**同一条经验在两个来源下是两条记忆**
    （「T9 那次为什么失败」与「V2 那次为什么失败」正文可能逐字相同）。
    反过来，同 source 同内容重复写入必须得到同一个 id ⇒ 可机械复现、不重复膨胀。
    """
    raw = f"{str(source or '').strip()}\n{normalize_text(content)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:ID_LEN]


def symbol_refs(text: str, limit: int = MAX_SYMBOL_REFS) -> list[str]:
    """抽出正文里出现过的**标识符形态**符号引用（去重、按出现顺序）。

    这是「第二路召回」的原料：M2/M3 拿这些名字去问 `find_symbol` /
    `get_module` / `get_architecture`（P11 已可信化），**不另建关键词库**。
    """
    out: list[str] = []
    for m in _IDENT_RE.finditer(normalize_text(text)):
        name = m.group(0)
        if name not in out:
            out.append(name)
        if len(out) >= limit:
            break
    return out


def file_refs(text: str) -> list[dict]:
    """抽出正文里的 `文件:行` 引用 —— 「每条主张都要能指到位置」的机判形态。"""
    out: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for m in _REF_RE.finditer(normalize_text(text)):
        path, line = m.group(1), int(m.group(2))
        key = (path, line)
        if key in seen:
            continue
        seen.add(key)
        out.append({"file": path, "line": line})
    return out


def keywords_from(text: str, extra: list[str] | None = None) -> list[str]:
    """关键词 = **调用方显式给的** ∪ **从正文兜底抽的**（小写去重、排序）。

    为什么允许调用方给：只有调用方知道这条记忆属于哪个概念（「登录」这件事
    正文里可能一个「登录」都没有）。为什么还要兜底抽：**只靠调用方给的词，
    漏召就变成了静默的** —— 一条没带关键词的记忆将永远召不回来。
    兜底抽让「至少正文里出现过的词能召回它」，而质量由 M2 的分数校准来治。
    """
    out: set[str] = set()
    for item in extra or []:
        for part in _WORD_RE.findall(str(item or "").lower()):
            if part not in _STOPWORDS:
                out.add(part)
    for part in _WORD_RE.findall(normalize_text(text).lower()):
        if part not in _STOPWORDS:
            out.add(part)
    return sorted(out)[:MAX_KEYWORDS]


def build_unit(content: str, *, source: str = "", keywords=None,
               symbols=None, created_at: str | None = None) -> dict:
    """装配一条记忆单元（唯一一处装配点；`store.write` 也走它）。"""
    text = normalize_text(content)
    refs = symbol_refs(text)
    for extra in symbols or []:
        name = str(extra or "").strip()
        if name and name not in refs:
            refs.append(name)
    return {
        "id": unit_id(text, source),
        "created_at": created_at or now_iso(),
        "content": text,
        "keywords": keywords_from(text, keywords),
        "symbol_refs": refs[:MAX_SYMBOL_REFS],
        "refs": file_refs(text),
        "source": str(source or "").strip(),
        "sha256": content_sha256(text),
        "status": "active",
        "archived_at": None,
    }


def describe() -> dict:
    """契约面（可读事实）：单元结构与两路召回的原料在哪。"""
    return {
        "unit_keys": [
            "id", "created_at", "content", "keywords", "symbol_refs", "refs",
            "source", "sha256", "status", "archived_at",
        ],
        "id": {
            "scheme": "sha256(source + LF + normalized_content)[:16]",
            "content_addressed": True,
            "why": "同一段上下文在不同平台上必须得到同一个 id（否则同一件事有两份）",
        },
        "keywords": {
            "sources": ["caller-provided", "auto-extracted-fallback"],
            "why": "只靠调用方给的词，漏召会变成静默的（没带关键词的记忆永远召不回）",
        },
        "symbol_refs": {
            "extraction": "identifier-shaped tokens (regex, pure syntax)",
            "second_recall_path": (
                "M2/M3 用同一份 symbol_refs 去问 find_symbol / get_module / "
                "get_architecture（P11 已可信化）—— 不另起关键词库"
            ),
        },
        "refs": {"form": "file:line", "why": "主张要能指到位置"},
        "archival": {"status_values": ["active", "archived"], "delete_path": None},
    }
