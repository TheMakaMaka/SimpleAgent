"""`ContextStore`：**独立根**上的记忆库（P21 / M1 —— 只做存储与检索，不接模型）。

用户提议（逐字）：「外部记忆链表 + **物理存储上下文的区域** …… 每个上下文/知识
存进**特定单元** …… 释放模型的上下文限制」。统筹方指定的做法：「后端单独开一个
区域 · 独立测试 · 成型之后再考虑接入模型」，并给 M1 四条验收：

| M1 验收 | 落点 |
|---|---|
| ① 写入/读取可机械复现 | 内容寻址 id + `units.jsonl` 确定性排序；`write` 同输入 ⇒ 同 id、不重复 |
| ② 越界写被**结构化拒绝** | `scope.resolve_store_path` / `StoreScopeError.to_result()` |
| ③ 库根在两侧仓库之外（可机判） | `scope.assert_outside_repos` / `profile()["outside_repos"]` |
| ④ 有**归档**而非删除 | `archive()`：移入 `archive/`，索引里 `status=archived`，**没有删除路径** |

★ 「不接模型」是**刻意**的（统筹方：在跨模型对比结论出来之前，不得进主链路）：
本模块**不 import** `core.runtime` / `tools.*`，`ContextStore` 也**不注册成工具**，
`main.py` 一行未动 ⇒ 主链路行为**逐字节不变**（`AGENT_CONTEXT_STORE_ENABLED` 也
还不需要，因为接入本身就是 M3 的事）。

★ 存储形态：`units.jsonl`（**一行一条单元**，append-only 索引）。选它而不是
"每个单元一个文件"或 SQLite，是因为本项目反复抓的形状是「数不清、对不上」：
JSONL 既能被 `Get-Content` 人眼直接核对，又能被逐行机械比对，
而且**幂等重写**（`units.jsonl` 由内存全量写回）让重放得到逐字节相同的文件。
"""

from __future__ import annotations

import json
import os

from . import retrieval, scope, units as units_mod

#: 版本号（库自身的形态版本；与契约的三套版本轴无关）。
#: `m1.1` → `m1.2`：**召回结果的形态**变了（`score_parts` 扩到四项构成 +
#: `basis`/`config`/`score_explain`），打分变成 `retrieval.score()` 单一纯函数入口
#: （统筹方 2026-10-05 追加的第四条硬要求）。
STORE_VERSION = "m1.2"

#: 每个库最多装多少单元（防止无限膨胀；**超出不是静默丢弃** ——
#: 调用方会拿到结构化拒绝，必须先归档腾位置）。
MAX_UNITS = 5000


class ContextStore:
    """外部记忆库（M1：存储 + 检索 + 独立根 + 越界拒绝）。

    一次读写 = 一次 `_load()`（索引是唯一事实源）+ 一次 `_flush()`（全量写回，
    确定性排序）⇒ **同输入必得同字节**。
    """

    def __init__(self, root: str | None = None, *, create: bool = True,
                 allow_inside_repos: bool = False):
        # `allow_inside_repos` 是**测试专用逃生口**（见 `scope.assert_outside_repos`）：
        # 生产代码没有任何一处会传它；放宽了会在 `profile()["scope"]` 里如实印出来。
        self._allow_inside_repos = bool(allow_inside_repos)
        self._root = scope.assert_outside_repos(
            root or scope.default_root(), allow_inside_repos=self._allow_inside_repos)
        self._units_path = os.path.join(self._root, scope.LAYOUT["units"])
        self._archive_dir = os.path.join(self._root, scope.LAYOUT["archive"])
        self._manifest_path = os.path.join(self._root, scope.LAYOUT["manifest"])
        self._units: dict[str, dict] | None = None
        self._created_now: list[str] = []
        if create:
            self._ensure_layout()

    # ------------------------------------------------------------------
    # 根与布局
    # ------------------------------------------------------------------
    def root(self) -> str:
        return self._root

    def path_of(self, rel: str, *, write: bool = False) -> str:
        """库内相对路径 → 绝对路径（越界 ⇒ `StoreScopeError`）。

        ★ 刻意**不**复用 `core.runtime.resolve_write`：库根**不是**工作区根，
        也不该落在被测项目的写入白名单里 —— 它是第四块地方，判据自己带。
        """
        try:
            return scope.resolve_store_path(
                rel, self._root, allow_inside_repos=self._allow_inside_repos)
        except scope.StoreScopeError as err:
            if not write and err.code == "out-of-scope-write":
                err.code = "out-of-scope-read"
            raise

    def _ensure_layout(self) -> None:
        os.makedirs(self._root, exist_ok=True)
        os.makedirs(self._archive_dir, exist_ok=True)
        if not os.path.exists(self._manifest_path):
            self._write_manifest()

    def _write_manifest(self, extra: dict | None = None) -> dict:
        manifest = {
            "store_version": STORE_VERSION,
            "root": self._root,
            "env": scope.ENV_STORE_ROOT,
            "layout": dict(scope.LAYOUT),
            "created_at": units_mod.now_iso(),
            "delete_path": None,
            "note": (
                "M1：只做存储与检索（不接模型）。库根**在两侧仓库之外**；"
                "淘汰 = 移入 archive/，不是删除"
            ),
        }
        if extra:
            manifest.update(extra)
        with open(self._manifest_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        return manifest

    def manifest(self) -> dict:
        try:
            with open(self._manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    # ------------------------------------------------------------------
    # 索引读写（唯一事实源 = units.jsonl）
    # ------------------------------------------------------------------
    def _load(self, refresh: bool = False) -> dict[str, dict]:
        if self._units is not None and not refresh:
            return self._units
        out: dict[str, dict] = {}
        if os.path.exists(self._units_path):
            with open(self._units_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        # 坏行**不许静默丢**：留痕在 `_broken_lines`，
                        # `profile()` 会把它印出来（"读不出来"≠"不存在"）。
                        continue
                    if rec.get("id"):
                        out[rec["id"]] = rec
        self._units = out
        return out

    def _flush(self) -> None:
        rows = sorted((self._units or {}).values(),
                      key=lambda r: (str(r.get("created_at") or ""), str(r.get("id") or "")))
        tmp = self._units_path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            for rec in rows:
                f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
        os.replace(tmp, self._units_path)
        self._write_manifest()

    # ------------------------------------------------------------------
    # 写 / 读
    # ------------------------------------------------------------------
    def write(self, content: str, *, source: str = "", keywords=None, symbols=None,
              created_at: str | None = None) -> dict:
        """写入一条单元。**内容寻址**：同 source 同内容 ⇒ 同 id、不重复。

        返回 `{ok, unit_id, id, status, created, deduped, unit, path}`。
        """
        unit = units_mod.build_unit(
            content, source=source, keywords=keywords, symbols=symbols,
            created_at=created_at,
        )
        if not unit["content"]:
            raise ValueError("内容为空：空单元没有召回价值，不写入")

        store = self._load()
        existing = store.get(unit["id"])
        if existing is not None:
            if existing.get("sha256") != unit["sha256"]:
                # id 碰撞（16 位前缀理论上有概率）⇒ 结构化拒绝，**绝不覆盖**
                raise scope.StoreScopeError(
                    "id-collision",
                    f"id {unit['id']} 已存在但内容哈希不同（拒绝覆盖已有记忆）",
                    path=self._units_path, allowed_roots=(self._root,),
                    hint="换更长 id 或改内容；不许用后写覆盖先写",
                )
            # 幂等：不新增、不改时间线（`created_at` 保留最早值）
            return {
                "ok": True, "unit_id": unit["id"], "id": unit["id"],
                "status": "exists", "created": False, "deduped": True,
                "unit": existing, "path": self._units_path,
            }

        if len(store) >= MAX_UNITS:
            raise scope.StoreScopeError(
                "store-full",
                f"记忆库已满（{len(store)}/{MAX_UNITS}）—— 先归档再写",
                path=self._units_path, allowed_roots=(self._root,),
                hint="archive(unit_id) 把旧单元移入归档层（淘汰 = 归档，不是删除）",
            )

        store[unit["id"]] = unit
        self._flush()
        return {
            "ok": True, "unit_id": unit["id"], "id": unit["id"],
            "status": "written", "created": True, "deduped": False,
            "unit": unit, "path": self._units_path,
        }

    def read(self, unit_id: str) -> dict:
        """按 id 读一条（**可机械复现**：同 id 同内容，两次读逐字相同）。"""
        store = self._load(refresh=True)
        rec = store.get(str(unit_id or "").strip())
        if rec is None:
            return {"ok": False, "id": unit_id, "found": False,
                    "error": "unit-not-found"}
        return {"ok": True, "id": rec["id"], "found": True, "unit": rec}

    def list_units(self, *, include_archived: bool = True) -> list[dict]:
        store = self._load(refresh=True)
        rows = [r for r in store.values()
                if include_archived or r.get("status") == "active"]
        return sorted(rows, key=lambda r: (str(r.get("created_at") or ""),
                                           str(r.get("id") or "")))

    # ------------------------------------------------------------------
    # 检索（两路召回，只记分不决策）
    # ------------------------------------------------------------------
    def recall(self, *, query: str = "", symbols=None, since: str = "", until: str = "",
               source: str = "", limit: int | None = None,
               include_archived: bool = False, config: dict | None = None,
               now: str = "") -> dict:
        """两路召回（转发 `retrieval.recall`）。

        `config` 是**显式配置**（权重 / 时间衰减 / 定制加权）；`now` 是**显式时刻**
        （时间衰减要它，缺省不衰减 —— 打分函数自己不许读时钟，见 `retrieval.score`）。
        """
        return retrieval.recall(
            self.list_units(include_archived=include_archived),
            query=query, symbols=symbols, since=since, until=until,
            source=source, limit=limit, include_archived=include_archived,
            config=config, now=now,
        )

    def calibrate(self, cases: list[dict], *, config: dict | None = None) -> dict:
        """漏召 / 误召的机械读数 + 候选阈值曲线（`retrieval.calibrate` 的转发）。

        `config` 必须是**产出这些 `result` 的那份配置** —— 校准记录靠它复现。
        """
        return retrieval.calibrate(cases, config=config)

    # ------------------------------------------------------------------
    # 淘汰 = 归档（**没有删除路径**）
    # ------------------------------------------------------------------
    def archive(self, unit_id: str) -> dict:
        """把单元移入归档层：索引留痕（`status=archived`）+ `archive/` 存一份。

        ★ 统筹方约束 6：「淘汰 = 归档，不是删除；淘汰不得抹掉证据」。
        因此本类**没有任何删除方法**，只有这一个迁移；归档后
        `list_units()` 仍能看到它（`include_archived=True`），
        `read()` 仍能读出原文。
        """
        store = self._load(refresh=True)
        key = str(unit_id or "").strip()
        rec = store.get(key)
        if rec is None:
            return {"ok": False, "id": key, "error": "unit-not-found"}
        if rec.get("status") == "archived":
            return {"ok": True, "id": key, "status": "already-archived",
                    "archive_path": rec.get("archive_path"), "unit": rec}

        target = os.path.join(self._archive_dir, f"{key}.json")
        with open(target, "w", encoding="utf-8", newline="\n") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        rec["status"] = "archived"
        rec["archived_at"] = units_mod.utc_iso()
        rec["archive_path"] = os.path.relpath(target, self._root).replace("\\", "/")
        self._flush()
        return {"ok": True, "id": key, "status": "archived",
                "archive_path": rec["archive_path"], "unit": rec}

    # ------------------------------------------------------------------
    # 契约面（/profile 之外的自述：它还没进主链路）
    # ------------------------------------------------------------------
    def profile(self) -> dict:
        """记忆库的**可读事实**：根、隔离判据、计数、两路召回、归档。

        ★ 为什么 M1 就要有它：统筹方门禁要能**不读代码**就核出
        「库根在不在仓库里」「有没有删除路径」「接没接主链路」。
        本方法就是那三个问题的机判入口。
        """
        rows = self.list_units()
        active = [r for r in rows if r.get("status") == "active"]
        archived = [r for r in rows if r.get("status") == "archived"]
        archive_files = []
        if os.path.isdir(self._archive_dir):
            archive_files = sorted(os.listdir(self._archive_dir))
        return {
            "store_version": STORE_VERSION,
            "phase": "M1",
            "wired_into_main_chain": False,
            "wired_note": (
                "M1 刻意不接模型、不注册成工具、main.py 未改；"
                "接入是 M3（需用户批准 + 可一键关）"
            ),
            "root": self._root,
            "scope": scope.describe(self._root,
                                   allow_inside_repos=self._allow_inside_repos),
            "paths": {
                "units": self._units_path,
                "archive_dir": self._archive_dir,
                "manifest": self._manifest_path,
            },
            "counts": {
                "units": len(rows),
                "active": len(active),
                "archived": len(archived),
                "archive_files": len(archive_files),
                "max_units": MAX_UNITS,
                # 坏行也是事实：读不出来 ≠ 不存在（不静默）
                "unreadable_index_lines": broken_index_lines(self._units_path),
            },
            "delete_path": None,
            "archive_is_not_delete": True,
            "recall": retrieval.describe(),
            "scoring": retrieval.scoring_profile(),
            "units_schema": units_mod.describe(),
            "generated_at": units_mod.now_iso(),
        }


def broken_index_lines(path: str) -> int:
    """数一数索引里有几行读不出来（**不静默**：坏行要能被看见）。"""
    if not os.path.exists(path):
        return 0
    n = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                json.loads(line)
            except ValueError:
                n += 1
    return n


__all__ = ["ContextStore", "STORE_VERSION", "MAX_UNITS", "broken_index_lines"]
