"""前端兼容契约的门禁（上游侧）。

前端（`bridge/spec.py`）**扫上游**取事实：阶段、事件词表、工具、运行报告。
它按纪律"认不出就降级显示"，所以上游的破坏性改动**不会让前端报错**——
只会让它静默少显示东西。这个测试就是补上那个缺口。

守四类：

  1. **事件词表**：`_emit` 发出去的 kind 必须与 `core.contract.EVENTS` 声明一致。
     未声明 = 改了词表却没说；声明了没发 = 死声明（前端的 dead_calibrations）。
  2. **必须扫得到**：kind 只能是**字面量**，且所有 `_emit` 调用点都在
     `EMIT_SOURCES` 里。否则前端 AST 扫不到 —— 等于发了个"隐形事件"。
  3. **payload 键只增不减**：键被删/改名，前端"自动挑可读字段"就挑不到了。
  4. **冻结面只增不减**：`CycleReport` / `Snapshot` / `Event` / `TOOLS_MAP` /
     阶段清单里已存在的键与值必须保留（允许新增）。

附带一条：契约版本与 `SCHEMA_VERSION` 必须名副其实（声明了就要能读到）。
"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core import contract  # noqa: E402

checks: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    checks.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")


def main() -> int:
    print("=" * 74)
    print("[1] 契约自扫描：emit 源必须唯一且可被前端扫到")
    print("=" * 74)
    a = contract.audit()
    print(f"  允许的 emit 源: {a['emit_sources']}")
    print(f"  实际扫到的: {a['emit_files']}")
    check("_emit 只在声明的文件里调用", a["emit_sources_ok"])
    print(f"  非字面量 kind 的调用点: {a['nonliteral_kinds'] or '无'}")
    check("所有 _emit 的 kind 都是字面量（前端 AST 才能扫到）",
          not a["nonliteral_kinds"])

    print("\n" + "=" * 74)
    print("[2] 事件词表：声明 == 实际")
    print("=" * 74)
    print(f"  实际发出 {a['event_count']} 种，声明 active {a['declared_count']} 种")
    print(f"  未声明就发出的: {a['undeclared_events'] or '无'}")
    check("没有『发了但没声明』的事件（词表改动必须显式登记）",
          not a["undeclared_events"])
    print(f"  声明了但没发的: {a['dead_events'] or '无'}")
    check("没有『声明了但已经不发』的死声明", not a["dead_events"])
    print(f"  已标 deprecated 但仍在发: {a['deprecated_still_emitted'] or '无'}")
    check("deprecated 的事件不得仍在发送", not a["deprecated_still_emitted"])

    print("\n" + "=" * 74)
    print("[2.5] _emit 调用点不许用 payload 键撞参数名（参数绑定会抛 TypeError）")
    print("=" * 74)
    # 实测事故（CHANGELOG §29）：`decision_opened` 曾传 `kind=<决策类型>`，
    # 而 `_emit` 的第一个参数也叫 `kind` → 调用点在**参数绑定阶段**就抛
    # `TypeError: _emit() got multiple values for argument 'kind'`，
    # 连函数体都进不去 → **决策路径 100% 不可用**；前端包装器挂钩后
    # 更是把整轮 run 变成 status=error。
    #
    # 判据（机器可判定）：`_emit` 的第 1、2 个参数由**位置**绑定
    # （每个调用点都位置传 `<kind>, cycle_id`），所以 payload 里**不得**
    # 出现它们的参数名；`goal` 例外 —— 它从不位置传，是设计内的记录字段。
    import ast as _ast
    import inspect as _inspect

    from core.coding_cycle import CodingCycle

    sig_params = list(_inspect.signature(CodingCycle._emit).parameters)
    bound_positionally = sig_params[1:3]      # self 之外的前两个：位置绑定
    allowed = {"goal"}                        # 记录字段，从不位置传
    print(f"  _emit 参数: {sig_params}")
    print(f"  由位置绑定、故 payload 里禁止: {bound_positionally}")
    print(f"  允许出现（记录字段）: {sorted(allowed)}")

    core_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "core")
    bad: list[str] = []
    sites = 0
    for fname in sorted(os.listdir(core_dir)):
        if not fname.endswith(".py"):
            continue
        path = os.path.join(core_dir, fname)
        tree = _ast.parse(open(path, "r", encoding="utf-8").read())
        for node in _ast.walk(tree):
            if not isinstance(node, _ast.Call):
                continue
            fn = node.func
            if getattr(fn, "attr", None) != "_emit" or not node.args:
                continue
            sites += 1
            first = node.args[0]
            kind = first.value if isinstance(first, _ast.Constant) else "?"
            for kw in node.keywords:
                if kw.arg and kw.arg in bound_positionally:
                    bad.append(f"{fname}:{node.lineno} {kind} -> {kw.arg}=")
    print(f"  扫了 {sites} 个 _emit 调用点")
    print(f"  撞参数名的 payload 键: {bad or '无'}")
    check("没有任何 _emit 调用点用 payload 键撞位置参数名", not bad)
    check("确实扫到了调用点（否则是空转）", sites >= 10)

    # ---- 另一类（D10）：payload 键会**覆盖前端扁平化后的记录字段** ----
    # `bridge/runner.py` 把事件拼成 `{seq, ts, kind, run_id, goal, attempt, **payload}`
    # —— payload 在**后**展开，所以同名键会**静默覆盖**记录字段。
    # 这类失效**没有症状**：不报错、接口正常，只是前端的 `ev.<字段>` 变了语义。
    # 实测事故：`decision_opened.kind` 覆盖了记录的 `kind`（CHANGELOG §29）。
    reserved = set(contract.RECORD_FIELDS)
    allowed_shared = dict(contract.PAYLOAD_SHARED_KEYS)
    print(f"  记录字段（payload 可覆盖）: {sorted(reserved)}")
    print(f"  显式豁免的公共键: {allowed_shared}")
    collide_record: list[str] = []
    for fname in sorted(os.listdir(core_dir)):
        if not fname.endswith(".py"):
            continue
        tree2 = _ast.parse(open(os.path.join(core_dir, fname),
                               encoding="utf-8").read())
        for node in _ast.walk(tree2):
            if not isinstance(node, _ast.Call):
                continue
            fn = node.func
            if getattr(fn, "attr", None) != "_emit" or not node.args:
                continue
            first = node.args[0]
            kind = first.value if isinstance(first, _ast.Constant) else "?"
            for kw in node.keywords:
                if kw.arg and kw.arg in reserved and kw.arg not in allowed_shared:
                    collide_record.append(f"{fname}:{node.lineno} {kind} -> {kw.arg}=")
    print(f"  未豁免却撞记录字段的 payload 键: {collide_record or '无'}")
    check("payload 键不撞记录字段（豁免项必须有理由）", not collide_record)
    check("豁免表里每一项都写了理由",
          all(bool(v) for v in allowed_shared.values()))

    # 真实绑定一次：按当前调用点的写法调用，确认不抛
    # （`storage=None` 让函数体提前返回 —— 这里只验**参数绑定**这一关，
    #  那正是出事的地方：TypeError 在进函数体之前就抛了）
    class _Dummy:
        storage = None

    try:
        CodingCycle._emit(_Dummy(), "decision_opened", "cy_x", goal="g",
                          decision_id="d1", decision_kind="repeated_failure")
        emit_ok = True
    except TypeError as e:
        emit_ok = False
        print(f"  实测抛错: {e}")
    check("按当前写法调用 _emit 不会 TypeError（真实绑定一次）", emit_ok)

    print("\n" + "=" * 74)
    print("[3] payload 键：只增不减")
    print("=" * 74)
    print(f"  声明了但扫不到的键: {a['payload_drift'] or '无'}")
    check("没有 payload 键被删除或改名（前端靠它自动挑可读字段）",
          not a["payload_drift"])
    # 反向提示：新增键必须在声明里补上，否则新键会静默逃过上面的检查。
    # `goal` 属于事件记录字段（EMIT_COMMON_KEYS），不算 payload 键。
    scanned = contract.scan_emit_sites()
    common = set(contract.EMIT_COMMON_KEYS)
    missing_from_decl = {
        k: sorted((set(v["payload"]) - common) - set(contract.EVENTS[k].payload))
        for k, v in scanned.items() if k in contract.EVENTS
    }
    missing_from_decl = {k: v for k, v in missing_from_decl.items() if v}
    print(f"  实际发出但没写进声明 payload 的键: {missing_from_decl or '无'}")
    check("声明里补齐了实际会发的 payload 键（goal 属记录字段，不计）",
          not missing_from_decl)

    print("\n" + "=" * 74)
    print("[4] 冻结面：只增不减")
    print("=" * 74)
    for field, label in (
        ("removed_phases", "阶段"),
        ("removed_report_keys", "CycleReport 字段"),
        ("removed_snapshot_keys", "Snapshot 字段"),
        ("removed_event_fields", "Event 字段"),
        ("removed_tool_info_keys", "TOOLS_MAP 条目字段"),
    ):
        gone = a[field]
        print(f"  消失的{label}: {gone or '无'}")
        check(f"{label}只增不减", not gone)

    print("\n" + "=" * 74)
    print("[5] 版本号名副其实")
    print("=" * 74)
    print(f"  CONTRACT_VERSION={a['contract_version']}  SCHEMA_VERSION={a['schema_version']}")
    check("契约版本非空", bool(a["contract_version"]))
    check("快照 schema_version 非空（前端据此判可否解析）",
          bool(a["schema_version"]))
    d = contract.describe()
    check("describe() 能给出事实源清单", bool(d["fact_sources"]))
    check("describe() 能给出事件词表", len(d["event_kinds"]) == a["event_count"])

    print("\n" + "=" * 74)
    print("[6] 能力声明：能推导的必须推导，不许手写漂移")
    print("=" * 74)
    from core.config import role_available

    caps = contract.capabilities()
    summary = ", ".join(f"{k}={v['supported']}" for k, v in caps.items())
    print(f"  声明: {summary}")
    check("vision 能力 == 角色是否可用（推导，不手写）",
          caps["vision"]["supported"] == role_available("vision"))
    check("每个能力都写了 why（便于前端解释为何隐藏）",
          all(v.get("why") for v in caps.values()))
    check("describe() 带上了能力声明", "capabilities" in d)
    check("契约整体自检通过", a["ok"])
    print("\n" + "=" * 74)
    print("断言检查")
    print("=" * 74)
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    failed = [n for n, ok in checks if not ok]
    print(f"\n通过 {len(checks) - len(failed)}/{len(checks)}")
    if failed:
        print("失败项:")
        for f in failed:
            print(f"  - {f}")
    return 1 if failed else 0


raise SystemExit(main())
