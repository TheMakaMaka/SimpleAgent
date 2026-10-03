"""存储抽象：原始事件与压缩快照的持久化接口。

设计原则
--------
1. **原始记录只增不改。** 事件以 JSONL 追加，永不重写。压缩产物是**派生视图**，
   可以随时从事件重算——这样"丢信息"变成可回滚的，而不是不可逆的。
2. **接口先于实现。** 这里只定义 Protocol；本地文件是唯一完整实现，
   SQLite 实现用来验证抽象是否站得住（见 tests）。数据库实现按计划不落地。
3. **只存事实，不存模型自述。** 事件的 fact 字段只能由程序校验过的结果产生。

检索语义（含未来的向量检索）留在 `search()` 里，业务代码不感知存储形态。
"""

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

STORAGE_ROOT = os.path.abspath("storage_data")


# ============================================================
# 事件：只增不改的最小记录单元
# ============================================================
EventKind = str  # "cycle_start" | "task_result" | "manifest" | "verify" | "rollback" | "cycle_end"


@dataclass
class Event:
    """一条不可变的原始事件。

    source 字段是**溯源凭据**：任何进入压缩快照的信息都必须能指回一条事件，
    否则它就是不可信的自由文本。
    """

    kind: EventKind
    cycle_id: str
    ts: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    seq: int = 0
    goal: str = ""
    payload: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, line: str) -> "Event":
        d = json.loads(line)
        return cls(
            kind=d.get("kind", ""),
            cycle_id=d.get("cycle_id", ""),
            ts=d.get("ts", ""),
            seq=int(d.get("seq", 0)),
            goal=d.get("goal", ""),
            payload=d.get("payload") or {},
        )


# ============================================================
# 存储接口
# ============================================================
@runtime_checkable
class Storage(Protocol):
    """业务代码只依赖这个接口；换存储形态不改调用方。"""

    def append_event(self, event: Event) -> None: ...

    def get_events(self, cycle_id: str | None = None) -> list[Event]: ...

    def save_snapshot(self, cycle_id: str, snapshot: dict) -> None: ...

    def load_snapshot(self, cycle_id: str) -> dict | None: ...

    def list_cycles(self) -> list[str]: ...

    def search(self, keyword: str, limit: int = 20) -> list[dict]: ...


# ============================================================
# 本地文件实现
# ============================================================
class FileStorage:
    """JSONL 事件 + JSON 快照。

    events.jsonl  只追加，一行一条事件（写入廉价、可追溯、崩溃不易损坏）
    snapshots/    每个 cycle 一个压缩快照（派生视图，可重算）
    meta.json     序号与索引
    """

    name = "file"

    def __init__(self, root: str = STORAGE_ROOT):
        self.root = os.path.abspath(root)
        self.events_path = os.path.join(self.root, "events.jsonl")
        self.snapshot_dir = os.path.join(self.root, "snapshots")
        os.makedirs(self.snapshot_dir, exist_ok=True)
        self._seq = self._load_seq()

    # ---------- 内部 ----------
    def _meta_path(self) -> str:
        return os.path.join(self.root, "meta.json")

    def _load_seq(self) -> int:
        try:
            with open(self._meta_path(), "r", encoding="utf-8") as f:
                return int(json.load(f).get("seq", 0))
        except (OSError, json.JSONDecodeError, ValueError):
            return 0

    def _save_seq(self) -> None:
        tmp = self._meta_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"seq": self._seq, "updated_at": datetime.now().isoformat()}, f)
        os.replace(tmp, self._meta_path())

    @staticmethod
    def _safe(cycle_id: str) -> str:
        # 防止 cycle_id 里的路径分隔符逃出 snapshot 目录
        return "".join(c if c.isalnum() or c in "-_." else "_" for c in cycle_id)

    # ---------- 事件 ----------
    def append_event(self, event: Event) -> None:
        self._seq += 1
        event.seq = self._seq
        with open(self.events_path, "a", encoding="utf-8") as f:
            f.write(event.to_json() + "\n")
        self._save_seq()

    def get_events(self, cycle_id: str | None = None) -> list[Event]:
        if not os.path.exists(self.events_path):
            return []
        out: list[Event] = []
        with open(self.events_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = Event.from_json(line)
                except (json.JSONDecodeError, TypeError):
                    continue  # 坏行跳过，不让一条脏数据毁掉整个历史
                if cycle_id is None or ev.cycle_id == cycle_id:
                    out.append(ev)
        return out

    # ---------- 快照 ----------
    def save_snapshot(self, cycle_id: str, snapshot: dict) -> None:
        path = os.path.join(self.snapshot_dir, f"{self._safe(cycle_id)}.json")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    def load_snapshot(self, cycle_id: str) -> dict | None:
        path = os.path.join(self.snapshot_dir, f"{self._safe(cycle_id)}.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

    def list_cycles(self) -> list[str]:
        out: list[str] = []
        for ev in self.get_events():
            if ev.cycle_id and ev.cycle_id not in out:
                out.append(ev.cycle_id)
        return out

    # ---------- 检索 ----------
    def search(self, keyword: str, limit: int = 20) -> list[dict]:
        """关键词检索。

        当前是朴素的子串匹配（大小写不敏感），覆盖"找某文件/某符号/某目标"的场景。
        未来换向量检索时只替换本方法体，调用方不变。
        """
        kw = (keyword or "").strip().lower()
        if not kw:
            return []

        hits: list[dict] = []
        for ev in self.get_events():
            blob = json.dumps(
                {"goal": ev.goal, "payload": ev.payload}, ensure_ascii=False
            ).lower()
            if kw in blob:
                hits.append({
                    "cycle_id": ev.cycle_id,
                    "seq": ev.seq,
                    "kind": ev.kind,
                    "goal": ev.goal[:120],
                    "ts": ev.ts,
                })
            if len(hits) >= limit:
                break
        return hits

    # ---------- 诊断 ----------
    def stats(self) -> dict:
        return {
            "backend": self.name,
            "root": self.root,
            "events": len(self.get_events()),
            "cycles": len(self.list_cycles()),
            "seq": self._seq,
        }


def default_storage() -> Storage:
    """默认存储实例。调用方可换成任意满足 Storage 的实现。"""
    return FileStorage()
