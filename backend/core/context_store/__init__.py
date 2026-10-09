"""`core.context_store` —— 外部记忆库（**P21 / M1，独立库**）。

用户提议：把上下文/知识存进**特定单元**，需要一个**物理存储上下文的区域**，
按**对话时间/关键词**分区，**平常不调用**、调用**分机制**（分数达量级才调），
目的是**释放模型的上下文限制**。

统筹方指定的做法（逐字）：「**后端单独开一个区域 · 独立测试 · 成型之后再谈接入** ·
做好**沙箱隔离**与**物理文件隔离**」，并把工作拆成三期、**不许跳级**：

  ======  ==================================================  ==============================
  M1      存储与检索 + 独立根 + 越界拒绝。**不接模型**        本包（本轮）
  M2      对每个单元算调用分并**记录**，**不改任何行为**        下一期
  M3      **需用户批准**，按校准后的阈值接入，且**可一键关**    再下一期
  ======  ==================================================  ==============================

★ 独立性是**刻意**的，也是可机判的：本包**不 import** `core.*`（除自身）与
`tools.*`，`ContextStore` **不注册成工具**，`main.py` 一行未动
⇒ 主链路行为**逐字节不变**。

用法（独立测试 / 离线脚本）：

    from core.context_store import ContextStore
    store = ContextStore(r"D:\\somewhere\\outside\\repos")
    store.write("T9 失败是因为 reuse 层把 app.route 判成了不存在符号",
                source="T9", keywords=["reuse", "false-positive"],
                symbols=["app.route"])
    print(store.recall(query="reuse false positive", symbols=["app.route"]))
    print(store.profile())
"""

from __future__ import annotations

from . import retrieval, scope, units
from .retrieval import (
    SCORER_ID, SCORER_KIND, canonical_config, config_sha256, score,
    score_breakdown, scoring_profile,
)
from .store import MAX_UNITS, STORE_VERSION, ContextStore, broken_index_lines

__all__ = [
    "ContextStore", "STORE_VERSION", "MAX_UNITS", "broken_index_lines",
    "retrieval", "scope", "units", "describe",
    "SCORER_ID", "SCORER_KIND", "score", "score_breakdown", "scoring_profile",
    "canonical_config", "config_sha256",
]


def describe() -> dict:
    """整包的契约面：M1 的边界、默认根、两路召回、可解释记分、归档语义。"""
    return {
        "phase": "M1",
        "wired_into_main_chain": False,
        "imports_production": False,
        "entry": "core.context_store.ContextStore",
        "root": scope.describe(),
        "recall": retrieval.describe(),
        "scoring": scoring_profile(),
        "units": units.describe(),
        "archival": {
            "delete_path": None,
            "status_values": ["active", "archived"],
            "archive_dir": scope.LAYOUT["archive"],
        },
        "next_phases": {
            "M2": "算调用分并记录（不改行为）+ 事后判定落盘 + scorer 对照臂 S-B/S-C",
            "M3": "按校准后的阈值接入，可一键关（需用户批准）",
        },
    }
