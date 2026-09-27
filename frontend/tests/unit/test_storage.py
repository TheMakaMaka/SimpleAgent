"""存储抽象 + 结构化压缩自检。

重点验证两件事：
  1. Storage 的 Protocol 是否站得住——用一个「内存实现」替换文件实现，
     调用方代码不改。这决定了将来接数据库是不是真的只换实现。
  2. 压缩是否守住了核心纪律——**verified facts 只能来自程序校验**，
     模型自述只能落到 assumed，绝不能混进可信事实里。
"""

import json
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401

from core.compress import (  # noqa: E402
    SCHEMA_VERSION, cross_cycle_failures, reduce_all, reduce_cycle,
)
from storage.store import Event, FileStorage, Storage  # noqa: E402

TMP = os.path.join(ROOT, ".tmp_storage_test")


# ============================================================
# 一个替代实现：用来证明 Protocol 真的可替换
# ============================================================
class MemoryStorage:
    """内存实现。不写盘，仅用于验证抽象可替换。"""

    name = "memory"

    def __init__(self):
        self.events: list[Event] = []
        self.snaps: dict[str, dict] = {}
        self._seq = 0

    def append_event(self, event: Event) -> None:
        self._seq += 1
        event.seq = self._seq
        self.events.append(event)

    def get_events(self, cycle_id=None):
        return [e for e in self.events if cycle_id is None or e.cycle_id == cycle_id]

    def save_snapshot(self, cycle_id, snapshot):
        self.snaps[cycle_id] = snapshot

    def load_snapshot(self, cycle_id):
        return self.snaps.get(cycle_id)

    def list_cycles(self):
        out = []
        for e in self.events:
            if e.cycle_id and e.cycle_id not in out:
                out.append(e.cycle_id)
        return out

    def search(self, keyword, limit=20):
        kw = keyword.lower()
        return [{"cycle_id": e.cycle_id, "kind": e.kind}
                for e in self.events if kw in json.dumps(e.payload, ensure_ascii=False).lower()][:limit]


def build_events() -> list[Event]:
    """构造一个「先失败后成功」的 cycle 事件流。"""
    cid = "cy_test"
    evs = [
        Event(kind="cycle_start", cycle_id=cid, goal="实现 fib", seq=1, payload={}),
        Event(kind="plan", cycle_id=cid, goal="实现 fib", seq=2, payload={
            "attempt": 1,
            "declared": [{"path": "fib.py", "role": "实现", "symbols": ["fib"]}],
            "verify_command": "import fib\nassert fib.fib(10) == 55",
        }),
        # 模型自述成功——但验证没过（经典的假成功场景）
        Event(kind="task_result", cycle_id=cid, goal="实现 fib", seq=3, payload={
            "task_id": "t1", "ok": True, "output": "已实现 fib 函数并验证通过",
            "error": "",
        }),
        # lint 未执行：必须与「通过」区分
        Event(kind="lint", cycle_id=cid, goal="实现 fib", seq=4, payload={
            "path": "fib.py", "status": "skipped", "reason": "ruff not installed",
        }),
        Event(kind="syntax", cycle_id=cid, goal="实现 fib", seq=5, payload={
            "path": "fib.py", "ok": True,
        }),
        Event(kind="verify", cycle_id=cid, goal="实现 fib", seq=6, payload={
            "passed": False, "detail": "AssertionError: got 34",
            "command": "import fib\nassert fib.fib(10) == 55",
        }),
        Event(kind="rollback", cycle_id=cid, goal="实现 fib", seq=7, payload={"ref": "abc123"}),
        Event(kind="cycle_end", cycle_id=cid, goal="实现 fib", seq=8, payload={
            "status": "failed", "commit": "", "attempt": 1,
        }),
    ]
    return evs


def main() -> int:
    shutil.rmtree(TMP, ignore_errors=True)
    checks: list[tuple[str, bool]] = []

    # ============================================================
    print("=" * 74)
    print("[1] Storage Protocol 可替换性")
    print("=" * 74)
    fs = FileStorage(root=TMP)
    ms = MemoryStorage()
    checks.append(("FileStorage 满足 Storage 协议", isinstance(fs, Storage)))
    checks.append(("MemoryStorage 也满足 Storage 协议", isinstance(ms, Storage)))
    print(f"  FileStorage   isinstance(Storage) = {isinstance(fs, Storage)}")
    print(f"  MemoryStorage isinstance(Storage) = {isinstance(ms, Storage)}")

    # 用同一段调用代码分别驱动两种实现
    for store in (fs, ms):
        for ev in build_events():
            store.append_event(ev)
        got = store.get_events("cy_test")
        snap = reduce_cycle(store.get_events(), "cy_test")
        store.save_snapshot("cy_test", snap.to_dict())
        loaded = store.load_snapshot("cy_test")
        hits = store.search("fib")
        print(f"  {store.name:<8} events={len(got)} status={snap.status} "
              f"snapshot_ok={loaded is not None} search_hits={len(hits)}")
        checks.append((f"{store.name} 事件数正确", len(got) == 8))
        checks.append((f"{store.name} 快照可往返", loaded is not None
                       and loaded["cycle_id"] == "cy_test"))
        checks.append((f"{store.name} 检索命中", len(hits) > 0))

    # 两种实现产出的压缩结果必须一致（证明压缩与存储形态无关）
    a = reduce_cycle(fs.get_events(), "cy_test").to_dict()
    b = reduce_cycle(ms.get_events(), "cy_test").to_dict()
    checks.append(("两种存储的压缩结果一致", a == b))
    print(f"  压缩结果一致: {a == b}")

    # ============================================================
    print("\n" + "=" * 74)
    print("[2] JSONL 只追加 + 坏行容错")
    print("=" * 74)
    with open(fs.events_path, "a", encoding="utf-8") as f:
        f.write("{ 这不是合法 JSON\n\n")
    after = len(fs.get_events())
    checks.append(("坏行被跳过而非崩溃", after == 8))
    print(f"  写入坏行后仍能读出 {after} 条事件")
    checks.append(("事件文件是 JSONL（一行一条）",
                   sum(1 for _ in open(fs.events_path, encoding="utf-8")) == 10))

    # 序号单调递增
    seqs = [e.seq for e in fs.get_events()]
    checks.append(("序号单调递增", seqs == sorted(seqs) and len(set(seqs)) == len(seqs)))
    print(f"  seq = {seqs}")

    # ============================================================
    print("\n" + "=" * 74)
    print("[3] 压缩的核心纪律：verified 只能来自程序校验")
    print("=" * 74)
    snap = reduce_cycle(fs.get_events(), "cy_test")
    by_conf = {}
    for f in snap.facts:
        by_conf.setdefault(f.confidence, []).append(f)

    for conf in ("verified", "declared", "assumed"):
        print(f"\n  [{conf}]")
        for f in by_conf.get(conf, []):
            print(f"    - {f.text[:64]}   @{f.source}")

    # 声称"验证通过"的模型自述必须落在 assumed
    claimed = [f for f in snap.facts if "验证通过" in f.text and f.confidence == "assumed"]
    checks.append(("模型自述的成功进 assumed", len(claimed) == 1))

    # verified 里不能出现模型自述的痕迹
    verified_texts = " ".join(f.text for f in by_conf.get("verified", []))
    checks.append(("verified 中不含模型自述", "已实现 fib 函数并验证通过" not in verified_texts))

    # 每个 fact 都必须有 source（可溯源）
    checks.append(("每个 fact 都有 source", all(f.source for f in snap.facts)))

    # verified 只应来自程序源（rollback 由程序记录，也是确定性的）
    allowed = {"verify", "syntax", "lint", "manifest", "rollback"}
    checks.append(("verified 来源合法",
                   all(f.source.split("@")[0] in allowed
                       for f in by_conf.get("verified", []))))

    # ============================================================
    print("\n" + "=" * 74)
    print("[4] 关键事实与失败记录")
    print("=" * 74)
    vf = [f.text for f in snap.verified_facts()]
    for t in vf:
        print(f"  verified: {t[:70]}")
    checks.append(("记录了验证失败", any("未通过" in t for t in vf)))
    checks.append(("记录了语法通过", any("语法检查 通过" in t for t in vf)))
    checks.append(("lint skipped 被标为未执行",
                   any("lint 未执行" in t and "不代表通过" in t for t in
                       (f.text for f in snap.facts))))
    checks.append(("记录了回退", any("已回退" in t for t in vf)))

    print("\n  failures:")
    for fl in snap.failures:
        print(f"    - {fl.what}: {fl.reason[:50]} (hash={fl.reason_hash}, count={fl.count})")
    checks.append(("失败被归纳为结构化记录", len(snap.failures) >= 1))
    checks.append(("失败带 reason_hash", all(f.reason_hash for f in snap.failures)))

    # 文件清单：声明的 + 实测状态
    print(f"\n  files: {[(f.path, f.status) for f in snap.files]}")
    checks.append(("声明文件已记录", any(f.path == "fib.py" for f in snap.files)))
    checks.append(("未产出的声明文件标 missing",
                   any(f.path == "fib.py" and f.status != "exists" for f in snap.files)))

    # ============================================================
    print("\n" + "=" * 74)
    print("[5] 渲染给模型的 prompt：assumed 必须显式隔离")
    print("=" * 74)
    prompt = snap.to_prompt()
    print("\n".join("  " + ln for ln in prompt.splitlines()[:24]))
    checks.append(("prompt 含可信区", "已实测确认" in prompt))
    checks.append(("prompt 把自述单列并警告", "未经校验" in prompt or "不可作为判据" in prompt))

    # ============================================================
    print("\n" + "=" * 74)
    print("[6] 跨周期聚合（架构跟踪雏形）")
    print("=" * 74)
    # 造第二个 cycle，重复同样的失败
    evs2 = []
    for ev in build_events():
        evs2.append(Event(kind=ev.kind, cycle_id="cy_second", goal=ev.goal,
                          seq=ev.seq, payload=dict(ev.payload)))
    all_events = fs.get_events() + evs2
    snaps = reduce_all(all_events)
    recurring = cross_cycle_failures(snaps, min_count=2)
    print(f"  周期数: {list(snaps.keys())}")
    for r in recurring:
        print(f"    反复出现: {r['reason'][:50]} 于 {len(r['cycles'])} 个周期")
    checks.append(("聚合出跨周期重复失败", len(recurring) >= 1))

    # schema 版本存在（便于将来迁移）
    checks.append(("快照带 schema_version", snap.schema_version == SCHEMA_VERSION))

    shutil.rmtree(TMP, ignore_errors=True)

    print("\n" + "=" * 74)
    print("断言检查")
    print("=" * 74)
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    failed = [n for n, ok in checks if not ok]
    print(f"\n通过 {len(checks) - len(failed)}/{len(checks)}")
    if failed:
        print("失败: " + "; ".join(failed))
    return 1 if failed else 0


raise SystemExit(main())
