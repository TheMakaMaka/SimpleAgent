"""人工决策路径的**运行时**回归测试。

为什么专门为它写一个文件
------------------------
这条路径此前**从未被任何测试覆盖过**，后果是一个潜伏已久的致命 bug：
`CodingCycle._ask()` 里 `self._emit("decision_opened", ..., kind=kind)` 的
`kind` 与 `_emit` 的**参数名**同名 → 调用点在**参数绑定阶段**就抛
`TypeError: _emit() got multiple values for argument 'kind'`，
连函数体都进不去。于是：

  · 「连续失败 → 问人」与「回退前 → 问人」两条路径 **100% 不可用**；
  · 前端安装 bridge 钩子后，这个 TypeError 还会把整轮 run 变成 `status=error`
    （实测：用户跑真实需求时就是这样失败的）。

而 `_ask` 的 docstring 明写「**本方法不会抛异常**」—— 文档承诺与实现相反。

测什么：**承诺本身**（不抛）、**fail-safe 默认值**（没人作答时选保守动作）、
**事件真的发出去了**、且 payload 键**不与 `_emit` 的参数名冲突**。
"""

import os
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401  （把仓库根加入 sys.path）

from core import CodingCycle, DecisionManager, Orchestrator  # noqa: E402
from core.cycle import CycleReport  # noqa: E402
from core.decisions import (  # noqa: E402
    FAILURE_OPTIONS, ROLLBACK_OPTIONS, FileDecisionStore,
)
from storage.store import Event  # noqa: E402

checks: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    checks.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")


class RecStorage:
    """只记录事件，不落盘。"""

    def __init__(self):
        self.events: list[Event] = []

    def append_event(self, event: Event) -> None:
        self.events.append(event)

    def get_events(self, cycle_id=None):
        return list(self.events)

    def saved(self, kind: str) -> list[Event]:
        return [e for e in self.events if e.kind == kind]


def build(tmp: str, storage: RecStorage) -> CodingCycle:
    # orchestrator 用哑对象：本测试只碰决策路径，不跑主循环
    return CodingCycle(
        orchestrator=object.__new__(Orchestrator),
        worker=None,                       # type: ignore[arg-type]
        storage=storage,
        persist=True,
        verbose=False,
        on_decision="auto",                # 不推送、不等待，直接取保守默认
        decisions=DecisionManager(store=FileDecisionStore(root=tmp)),
    )


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="decision_path_")
    store = RecStorage()
    cyc = build(tmp, store)

    print("=" * 74)
    print("[1] `_ask` 的文档承诺：不会抛异常")
    print("=" * 74)
    report = CycleReport(cycle_id="cy_test", goal="g")
    report.attempts = 2

    # 这两次调用在修复前**必定** TypeError（kind 参数冲突）
    try:
        a1 = cyc._ask("repeated_failure", report, "g", "连续失败，怎么办？",
                      FAILURE_OPTIONS, "stop")
        ok1 = True
    except Exception as e:  # noqa: BLE001
        a1, ok1 = f"{type(e).__name__}: {e}", False
    print(f"  repeated_failure → {a1!r}")
    check("repeated_failure 决策不抛异常（文档承诺）", ok1)
    check("返回 fail-safe 默认动作 'stop'", a1 == "stop")

    try:
        a2 = cyc._ask("risky_rollback", report, "g", "回退会覆盖文件，允许吗？",
                      ROLLBACK_OPTIONS, "abort")
        ok2 = True
    except Exception as e:  # noqa: BLE001
        a2, ok2 = f"{type(e).__name__}: {e}", False
    print(f"  risky_rollback  → {a2!r}")
    check("risky_rollback 决策不抛异常", ok2)
    check("返回 fail-safe 默认动作 'abort'", a2 == "abort")

    print("\n" + "=" * 74)
    print("[2] 事件真的发出去了，且 payload 键不与 _emit 参数名冲突")
    print("=" * 74)
    opened = store.saved("decision_opened")
    print(f"  decision_opened 事件数: {len(opened)}")
    check("两次决策各发出一条 decision_opened", len(opened) == 2)

    params = {"event_kind", "cycle_id", "goal"}
    bad_keys: list[str] = []
    has_decision_kind = False
    for e in opened:
        for k in (e.payload or {}):
            if k in params:
                bad_keys.append(k)
            if k == "decision_kind":
                has_decision_kind = True
    print(f"  payload 键: {sorted(set(k for e in opened for k in (e.payload or {})))}")
    check("payload 里没有与 _emit 参数同名的键", not bad_keys)
    check("决策类型用 decision_kind 传递（原为 kind，会撞参数名）",
          has_decision_kind)
    check("payload 里不再有 kind 键",
          all("kind" not in (e.payload or {}) for e in opened))

    # 事件记录本身的 kind 字段仍然正确（那是 Event 的字段，不是 payload）
    check("Event.kind 仍为 decision_opened",
          all(e.kind == "decision_opened" for e in opened))
    check("决策类型值可用（repeated_failure / risky_rollback）",
          sorted(e.payload.get("decision_kind") for e in opened)
          == ["repeated_failure", "risky_rollback"])

    print("\n" + "=" * 74)
    print("[3] 决策已落盘（可被前端审批页读到）")
    print("=" * 74)
    files = [f for f in os.listdir(tmp) if f.endswith(".json")]
    print(f"  临时决策目录里的记录: {len(files)} 个")
    check("两次决策都写了记录文件", len(files) == 2)

    shutil.rmtree(tmp, ignore_errors=True)
    failed = [n for n, ok in checks if not ok]
    print(f"\n通过 {len(checks) - len(failed)}/{len(checks)}")
    return 1 if failed else 0


raise SystemExit(main())
