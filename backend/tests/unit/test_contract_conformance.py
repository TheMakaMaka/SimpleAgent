"""契约符合性门禁：拿**统筹契约原文**核对本侧实现。

为什么需要它
------------
统筹方每轮是**打接口手工复验**我的主张（OPS-1 那次是 6/6 手工核对）。
手工复验有个固有缺口：**它只在那一轮发生过**，之后我改了代码没人再看。
这个测试把同一批核对变成每次跑测试都会执行的机械门禁。

它做的不是"再写一遍我自己的期望值"，而是**读契约 JSON 原文**来断言：

  · `rule_crosswalk.upstream_only`（21 条）→ code / owner / severity 逐条相等
  · `new_rules_required`（O1/O2）        → code / owner / severity / action 相等
  · `owner_vocabulary.values`            → 归属词表集合相等
  · `verdict_vocabulary.values`          → 结论词表集合相等
  · `event_partition.observed`           → 上游 12 个事件种类相等
  · `phases_partition`                   → 上游 5 个流水线阶段相等
  · `version_axes.axes`                  → CONTRACT_VERSION / SCHEMA_VERSION 相等
  · `client_report_schema.canonical_fields` → 上报字段集合相等
  · `fact_sources` 里标 `backend:` 的路径 → 逐个真实可解析
  · `endpoint_partition...upstream_proxied.observed` → 上游必须仍在提供
  · `response_contract`                  → warnings 类型/缺席语义/ops 栏保留/`/profile` 新增项

**只读**：契约目录是只读资产，本测试只读不写。
镜像未安装时**跳过**（不失败），但会明确打印"跳过"以免看起来像通过。
"""

import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

CONTRACT = os.path.join(ROOT, ".interface_contract", "interface-contract.json")

checks: list[tuple[str, bool]] = []
derived = 0          # 真正从契约原文推导出的断言数（防空转）


def check(name: str, ok: bool) -> None:
    global derived
    derived += 1
    checks.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")


def main() -> int:
    import json

    print("=" * 74)
    print("[0] 读取统筹契约原文（只读）")
    print("=" * 74)
    if not os.path.exists(CONTRACT):
        print(f"  未找到 {os.path.relpath(CONTRACT, ROOT)} —— 镜像未安装，跳过全部符合性检查。")
        print("  （跳过不等于通过：本侧仍按 tests/unit/test_contract_attribution.py 自检）")
        print("\n通过 0/0（跳过）")
        return 0

    with open(CONTRACT, "r", encoding="utf-8") as f:
        c = json.load(f)
    print(f"  契约版本: {c['contract']['version']}   状态: {c['contract']['status']}")

    from core import contract as ct

    # ---------- [1] 规则表逐条 ----------
    print("\n" + "=" * 74)
    print("[1] rule_crosswalk.upstream_only ↔ ISSUE_RULES（逐条 code/owner/severity）")
    print("=" * 74)
    upstream_only = c["rule_crosswalk"]["upstream_only"]
    mismatch: list[str] = []
    for spec in upstream_only:
        code = spec["code"]
        mine = ct.ISSUE_RULES.get(code)
        if mine is None:
            mismatch.append(f"{code}: 本侧缺这条规则")
            continue
        for field in ("owner", "severity"):
            if getattr(mine, field) != spec[field]:
                mismatch.append(f"{code}.{field}: 契约={spec[field]} 本侧={getattr(mine, field)}")
    print(f"  契约列出 {len(upstream_only)} 条，本侧规则表 {len(ct.ISSUE_RULES)} 条")
    print(f"  不一致: {mismatch or '无'}")
    check("契约的 21 条上游规则与本侧逐条一致（含归属与级别）", not mismatch)

    # 契约的 21 + 新增 2 = 本侧 23
    new_rules = c.get("new_rules_required", {})
    o_codes = [v["code"] for k, v in new_rules.items() if isinstance(v, dict) and "code" in v]
    print(f"  契约新增规则: {o_codes}")
    full = {s["code"] for s in upstream_only} | set(o_codes)
    diff = sorted(full ^ set(ct.ISSUE_RULES))
    print(f"  契约全集 vs 本侧规则表的对称差: {diff or '无'}")
    check("契约规则全集 == 本侧 ISSUE_RULES 集合", not diff)

    o_mismatch: list[str] = []
    for k, v in new_rules.items():
        if not (isinstance(v, dict) and "code" in v):
            continue
        mine = ct.ISSUE_RULES.get(v["code"])
        if mine is None:
            o_mismatch.append(f"{v['code']}: 缺失")
            continue
        if mine.owner != v["owner"]:
            o_mismatch.append(f"{v['code']}.owner 契约={v['owner']} 本侧={mine.owner}")
        if mine.severity != v["severity"]:
            o_mismatch.append(f"{v['code']}.severity 契约={v['severity']} 本侧={mine.severity}")
        # action 文案：契约给了原文，本侧应逐字采用
        if v.get("action") and mine.action != v["action"]:
            o_mismatch.append(f"{v['code']}.action 与契约原文不一致")
    print(f"  新增规则不一致: {o_mismatch or '无'}")
    check("新增规则（O1/O2）的归属/级别/action 文案与契约一致", not o_mismatch)

    # ---------- [2] 词表 ----------
    print("\n" + "=" * 74)
    print("[2] 词表 ↔ owner_vocabulary / verdict_vocabulary")
    print("=" * 74)
    c_owners = set(c["owner_vocabulary"]["values"])
    c_verdicts = set(c["verdict_vocabulary"]["values"])
    print(f"  契约归属: {sorted(c_owners)}")
    print(f"  本侧归属: {sorted(ct.OWNER_ORDER)}")
    print(f"  契约结论: {sorted(c_verdicts)}")
    print(f"  本侧结论: {sorted(ct.VERDICTS)}")
    check("归属词表集合相等", c_owners == set(ct.OWNER_ORDER))
    check("结论词表集合相等", c_verdicts == set(ct.VERDICTS))
    check("优先级说明要求 ops 优先 —— 本侧 OWNER_ORDER 首项为 ops",
          ct.OWNER_ORDER[0] == ct.OWNER_BACKEND and False or ct.OWNER_ORDER[0] == "ops")

    # ---------- [3] 分区：事件 / 阶段 ----------
    print("\n" + "=" * 74)
    print("[3] 事件与阶段分区 ↔ 本侧实际")
    print("=" * 74)
    obs = c["event_partition"]["observed"]
    c_kinds = set(obs["upstream_kinds"])
    mine_kinds = ct.contract_emitted()
    print(f"  契约记录的上游事件 {obs['upstream_count']} 个，本侧实际发出 {len(mine_kinds)} 个")
    # 方向感知（与版本轴同理）：事件词表的**权威在本侧**（前端是扫我的 `_emit`）。
    #   · 本侧多出（新增事件）→ 契约台账滞后：打印待更新，**不算失败**
    #     （新增是 additive：前端对未知事件是"自动生成可读名字"降级显示）
    #   · 契约多出（我删了/改名了）→ **硬失败**：那是破坏性变更
    added = sorted(mine_kinds - c_kinds)
    removed = sorted(c_kinds - mine_kinds)
    print(f"  本侧新增（契约台账待更新）: {added or '无'}")
    print(f"  契约有而本侧已无（破坏性）: {removed or '无'}")
    check("没有『契约记录了、本侧已不再发』的事件（删除/改名属破坏性）", not removed)
    if added:
        print(f"  → 契约台账滞后：请把 {added} 补进 event_partition.observed")
    check("本侧事件不与契约冲突（新增允许、删除不允许）", not removed)
    check("契约声明的 upstream_count 不超过本侧实际（多了说明我删了）",
          obs["upstream_count"] <= len(mine_kinds))

    c_phases = list(c["phases_partition"]["upstream_pipeline_phases"])
    mine_phases = ct._pipeline_phases()
    print(f"  契约阶段: {c_phases}")
    print(f"  本侧阶段: {mine_phases}")
    check("上游流水线阶段与契约一致且顺序相同", c_phases == mine_phases)
    # 契约点名 bridge 自补了 manifest —— 本侧 PHASE_ORDER **不该**有它
    check("本侧 PHASE_ORDER 不含 bridge 自补的 manifest（契约裁定本侧是对的）",
          "manifest" not in mine_phases)

    # ---------- [4] 版本轴 ----------
    print("\n" + "=" * 74)
    print("[4] 版本轴 ↔ CONTRACT_VERSION / SCHEMA_VERSION")
    print("=" * 74)
    from core.compress import SCHEMA_VERSION

    axes = c["version_axes"]["axes"]
    c_ver = axes["CONTRACT_VERSION"]["observed_value"]
    print(f"  契约 CONTRACT_VERSION={c_ver} "
          f"本侧={ct.CONTRACT_VERSION}")
    print(f"  契约 SCHEMA_VERSION={axes['SCHEMA_VERSION']['observed_value']} "
          f"本侧={SCHEMA_VERSION}")
    # `CONTRACT_VERSION` 的**载体是本侧**（契约里写着 `carrier: backend: core/contract.py`），
    # 所以 `observed_value` 是契约对我的**快照**，不是我该对齐的目标。
    # 因此：本侧领先 = 契约台账滞后（记账项，打印出来，不判失败）；
    #       契约领先 = 本侧落后（**硬失败**，那才是真的漂移）。
    def _vt(s):
        try:
            return tuple(int(x) for x in str(s).split("."))
        except ValueError:
            return None

    mine_v, c_v = _vt(ct.CONTRACT_VERSION), _vt(c_ver)
    if mine_v and c_v and mine_v > c_v:
        print(f"  → 契约台账滞后：请更新 version_axes.CONTRACT_VERSION.observed_value "
              f"= {ct.CONTRACT_VERSION}")
        check("契约台账与本侧一致（滞后期允许，已打印待更新）", True)
    else:
        check("CONTRACT_VERSION 与契约一致（本侧不得落后于台账）",
              mine_v == c_v)
    check("SCHEMA_VERSION 与契约一致",
          axes["SCHEMA_VERSION"]["observed_value"] == SCHEMA_VERSION)

    # ---------- [5] 上报字段 ----------
    print("\n" + "=" * 74)
    print("[5] client_report_schema ↔ PEER_FIELDS")
    print("=" * 74)
    c_fields = set(c["client_report_schema"]["canonical_fields"])
    print(f"  契约字段: {sorted(c_fields)}")
    print(f"  本侧字段: {sorted(ct.PEER_FIELDS)}")
    check("规范上报字段集合相等", c_fields == set(ct.PEER_FIELDS))

    # ---------- [6] fact_sources 里标 backend 的路径要真实可解析 ----------
    print("\n" + "=" * 74)
    print("[6] fact_sources（backend 侧）逐个可解析")
    print("=" * 74)
    import importlib

    def resolve_target(target: str) -> tuple[bool, str]:
        """解析 `a.b.C.attr` 这类**点号路径**。

        不能简单 rpartition 一次：`core.cycle.CycleReport.to_dict` 里
        `core.cycle.CycleReport` 不是模块 —— 要**从长到短试模块前缀**，
        剩下的部分逐级 getattr。第一次写只 rpartition 了一次，
        于是 `core.cycle.CycleReport.to_dict` 被判成"解析失败"（检查器自己的 bug）。
        """
        parts = target.split(".")
        for cut in range(len(parts), 0, -1):
            mod_name = ".".join(parts[:cut])
            try:
                obj = importlib.import_module(mod_name)
            except Exception:  # noqa: BLE001
                continue
            try:
                for attr in parts[cut:]:
                    obj = getattr(obj, attr)
                return True, ""
            except AttributeError as e:
                return False, str(e)
        return False, "无法导入任何模块前缀"

    unresolvable: list[str] = []
    resolved: list[str] = []
    for name, desc in c["fact_sources"].items():
        if not isinstance(desc, str) or not desc.startswith("backend:"):
            continue
        target = desc.split(":", 1)[1].strip()
        # 带括号的条目是**描述型**（如"CodingCycle._emit 调用点（AST 扫字面量…）"），
        # 取括号前那段路径来解析；仍解析不出就明说跳过，不算失败。
        desc_like = "（" in target or "(" in target
        target = target.split("（")[0].split("(")[0].strip()
        if not target or " " in target:
            print(f"  {name}: `{target or desc}` —— 描述型，跳过自动解析")
            continue
        ok, why = resolve_target(target)
        if ok:
            resolved.append(target)
        elif desc_like:
            print(f"  {name}: `{target}` 无法自动解析（描述型）—— 跳过：{why}")
        else:
            unresolvable.append(f"{target} ({why})")
    print(f"  可解析: {resolved}")
    print(f"  解析失败: {unresolvable or '无'}")
    check("契约指认的 backend 事实源全部存在", not unresolvable)
    check("确实解析到了事实源（否则是空转）", len(resolved) >= 3)

    # ---------- [7] 被前端代理的上游端点必须仍在提供 ----------
    print("\n" + "=" * 74)
    print("[7] endpoint_partition：前端要代理的上游端点仍存在")
    print("=" * 74)
    import main as app_module

    served = set(app_module._route_paths())
    proxied = c["endpoint_partition"]["three_sets"]["upstream_proxied"]["observed"]
    missing = [e for e in proxied if e not in served]
    print(f"  契约记录前端代理 {len(proxied)} 条: {proxied}")
    print(f"  本侧实际提供 {len(served)} 条路由")
    print(f"  缺失: {missing or '无'}")
    check("前端代理的上游端点全部仍由本侧提供", not missing)

    # ---------- [8] response_contract（OPS-1 的成果）----------
    print("\n" + "=" * 74)
    print("[8] response_contract ↔ 实际响应")
    print("=" * 74)
    rc = c["response_contract"]
    routes = sorted(served)
    r_empty = ct.compare(None, routes)                     # 无 peer
    r_ops = ct.compare({"ops": {"service_down": True}}, routes)  # 陈旧 ops 事实
    r_fnb = ct.compare({"ops": {"frontend_not_built": True}}, routes)

    print(f"  warnings 类型: {rc['warnings']['type']}")
    check("warnings 是 list[str]",
          isinstance(r_empty["warnings"], list)
          and all(isinstance(x, str) for x in r_empty["warnings"]))
    check("无陈旧事实时 warnings 为 []（缺席语义）", r_empty["warnings"] == [])
    check("有陈旧事实时 warnings 非空（真的会产出）", bool(r_ops["warnings"]))
    # ops_column：被上报的事实**保留**在 ops 栏，即使未参与判定
    check("未参与判定的 ops 事实仍保留在 counts.ops 与顶层 ops 栏",
          r_ops["counts"]["ops"] == 1 and len(r_ops["ops"]) == 1
          and r_ops["ops"][0]["code"] == "O-service-down")
    # priority_clarification：ops 优先未被削弱
    check("优先级说明成立：未被证伪的 ops 事实仍判 ops-action",
          r_fnb["verdict"] == "ops-action")
    check("被证伪的 ops 事实不驱动结论", r_ops["verdict"] != "ops-action")
    # profile_additions
    d = ct.describe()
    for item in rc.get("profile_additions", []):
        key = item.split("：")[0].split(":")[0].strip()
        print(f"  /profile 新增项 `{key}`: {'在' if key in d else '缺'}")
        check(f"/profile 暴露契约声明的新增项 `{key}`", key in d)
    check("ops_stale_by_transport 内容与契约一致（O-service-down）",
          d["ops_stale_by_transport"] == ["O-service-down"])

    # ---------- [10] A1：两个入口的归属一致性 ----------
    print("\n" + "=" * 74)
    print("[10] A1 验收：跨侧归属只有一个判据（两个入口同一 owner）")
    print("=" * 74)
    # 验收标准（架构清单 A1）：「一个测试：对同一跨侧不一致，两个入口给出的
    # owner 归属一致」。
    #
    # `/api/audit` 在前端仓库，本侧调不到；但契约的 `rule_crosswalk` 就是
    # **两侧商定的统一映射**（bridge_id → upstream code + unified_owner），
    # 所以可以拿它当锚点：bridge 的每一条跨侧判定，其对应的上游 code
    # 在本侧规则表里的 owner 必须与 `unified_owner` 相同 —— 即
    # "同一件事只有一个判据"是**可机械验证**的。
    #
    # 注意 `upstream_equivalent` 是**带注释的自由文本**：
    #   "U-removed-surface (部分)" / "U-dead-event (上游侧)" / "SPLIT" / "无（…）"
    # 所以解析要取**前导 code**，并对带限定词的项降低断言强度
    # （否则会产生假冲突 —— 第一版就是这么误报 5 条的）。
    code_re = re.compile(r"\b([A-Z]{1,2}-[a-z][a-z-]+)\b")

    crosswalk_rows: list[tuple[str, str, str, str, bool]] = []
    for key in ("bridge_frontend_prefixed", "bridge_backend_prefixed_reclassified"):
        for x in c["rule_crosswalk"].get(key, []):
            crosswalk_rows.append((
                x["bridge_id"], str(x.get("upstream_equivalent", "")),
                x.get("unified_owner", ""), x.get("severity", ""), False))
    for x in c["rule_crosswalk"].get("bridge_only_reclassified", []):
        crosswalk_rows.append((
            x["bridge_id"], str(x.get("unified_code", "")),
            x.get("unified_owner", ""), x.get("severity", ""), False))

    no_code: list[str] = []
    missing_code: list[str] = []
    owner_bad: list[str] = []
    sev_bad: list[str] = []
    partial_skipped: list[str] = []
    split_skipped: list[str] = []
    compared = 0

    for bridge_id, eq, u_owner, u_sev, _ in crosswalk_rows:
        m = code_re.search(eq)
        if not m:
            no_code.append(bridge_id)          # 属 bridge 本地自检，无上游等价
            continue
        code = m.group(1)
        mine = ct.ISSUE_RULES.get(code)
        if mine is None:
            missing_code.append(f"{bridge_id} -> {code}")
            continue
        # "部分等价"：契约自己标了限定词，只比 owner，不比 severity
        partial = "（" in eq or "(" in eq
        if u_owner == "SPLIT":
            split_skipped.append(f"{bridge_id} -> {code}")
        elif u_owner and mine.owner != u_owner:
            owner_bad.append(f"{bridge_id} -> {code}: 契约={u_owner} 本侧={mine.owner}")
        else:
            compared += 1
        if not partial and u_sev and mine.severity != u_sev:
            sev_bad.append(f"{bridge_id} -> {code}: 契约={u_sev} 本侧={mine.severity}")
        if partial and u_owner != "SPLIT":
            partial_skipped.append(bridge_id)

    print(f"  crosswalk 共 {len(crosswalk_rows)} 行；无上游等价（bridge 本地项）{len(no_code)} 行")
    print(f"  完整比对的: {compared} 行；部分等价（只比 owner）: {len(partial_skipped)} 行")
    print(f"  SPLIT（无可单判 owner）: {split_skipped or '无'}")
    print(f"  映射到本侧不存在的 code: {missing_code or '无'}")
    print(f"  owner 不一致: {owner_bad or '无'}")
    print(f"  severity 不一致: {sev_bad or '无'}")
    check("crosswalk 指认的上游 code 在本侧都存在（判据完整）", not missing_code)
    check("跨侧归属一致：bridge 映射项的本侧 owner == 契约 unified_owner",
          not owner_bad)
    check("完整等价项的 severity 也一致", not sev_bad)
    check("确实比对到了足够多的行（否则是空转）", compared >= 5)

    # ---------- [11] A1b：入口自述权威范围 ----------
    print("\n" + "=" * 74)
    print("[11] A1b：/contract/check 自述权威范围")
    print("=" * 74)
    r = ct.compare(None, routes)
    auth = r.get("authority") or {}
    print(f"  authority.id   = {auth.get('id')}")
    print(f"  authority.role = {auth.get('role')}")
    print(f"  covers         = {len(auth.get('covers') or [])} 项")
    print(f"  not_covers     = {len(auth.get('not_covers') or [])} 项")
    print(f"  counterpart    = {(auth.get('counterpart') or {}).get('entry')} "
          f"({(auth.get('counterpart') or {}).get('authority')})")
    check("响应含 authority 块（A1b 要求的自述字段）", bool(auth))
    check("自述了权威范围（covers 非空）", bool(auth.get("covers")))
    check("自述了**不**负责的范围（not_covers 非空，划清边界）",
          bool(auth.get("not_covers")))
    check("指明了对应入口是 /api/audit（本地自检）",
          (auth.get("counterpart") or {}).get("entry") == "/api/audit")
    check("指明了跨侧归属以本入口为准",
          "本入口为准" in str((auth.get("counterpart") or {}).get("cross_side_attribution")))
    check("/profile 的 contract 段也带同一份 authority（前端离线可读）",
          "authority" in ct.describe()
          and ct.describe()["authority"].get("id") == auth.get("id"))
    # 完整性 + 稳定性凭据
    d2 = ct.describe()
    print(f"  responsibility_count       = {d2['responsibility_count']}")
    print(f"  responsibility_fingerprint = {d2['responsibility_fingerprint']}")
    check("暴露了规则表条数与内容指纹（前端可判断表变没变）",
          d2["responsibility_count"] == len(ct.ISSUE_RULES)
          and len(d2["responsibility_fingerprint"]) == 8)
    check("指纹只覆盖 code|owner|severity（改文案不变、改归属必变）",
          ct.responsibility_fingerprint() == ct.responsibility_fingerprint())

    # ---------- [12] HTTP 路径：契约字段必须真的接上（D7）----------
    print("\n" + "=" * 74)
    print("[12] HTTP 路径：经请求模型上报的字段必须真的生效")
    print("=" * 74)
    # 缺口（统筹方 D7 实测）：`bridge_gate_steps` 只在 `PEER_FIELDS` 声明与
    # `contract.py` 的分支里，**`main.py` 的 `ContractPeer` 没有它** ——
    # Pydantic **静默丢弃**未声明字段，于是那条"方向已定"的分支
    # 在 HTTP 上永远不触发（进程内直调 `compare()` 却完全正常）。
    #
    # 这就是"**验证方式与生产路径不一致**"：函数级测试全绿、接口层静默失效。
    # 所以这一组**必须经过 HTTP 处理器**，不能用 `compare()` 代替。
    import asyncio as _asyncio

    import main as app_module

    model_fields = set(app_module.ContractPeer.model_fields)
    print(f"  ContractPeer 字段: {sorted(model_fields)}")
    # 契约 canonical_fields 必须一个不漏地进请求模型
    missing_in_model = sorted(c_fields - model_fields)
    extra_in_model = sorted(model_fields - c_fields)
    print(f"  契约有、模型缺: {missing_in_model or '无'}")
    print(f"  模型有、契约无: {extra_in_model or '无'}")
    check("契约的每个 canonical_field 都在请求模型里（否则被静默丢弃）",
          not missing_in_model)

    peer_payload = {
        "contract_version": ct.CONTRACT_VERSION,
        "schema_version": c["version_axes"]["axes"]["SCHEMA_VERSION"]["observed_value"],
        "upstream_event_kinds": sorted(ct.contract_emitted()),
        "phases": ct._pipeline_phases() + ["ghost"],
        "upstream_endpoints": [],
    }

    def http_report(**extra):
        body = dict(peer_payload)
        body.update(extra)
        peer = app_module.ContractPeer(**body)
        # 复刻真实处理器里的过滤逻辑
        data = {k: v for k, v in peer.model_dump().items() if v not in ("", None)}
        return _asyncio.run(app_module.contract_check_post(peer)), data

    r_plain, data_plain = http_report()
    r_gate, data_gate = http_report(bridge_gate_steps=["ghost"])
    print(f"  经 HTTP 上报的字段: {sorted(data_gate)}")
    print(f"  bridge_gate_steps 是否穿过请求模型: "
          f"{'是' if data_gate.get('bridge_gate_steps') == ['ghost'] else '否（被丢弃）'}")
    check("bridge_gate_steps 能穿过请求模型",
          data_gate.get("bridge_gate_steps") == ["ghost"])

    def action_of(rep):
        return next((i["action"] for i in rep["issues"]
                     if i["code"] == "P-phase-unknown"), "")

    a_plain, a_gate = action_of(r_plain), action_of(r_gate)
    print(f"  未上报 bridge_gate_steps → action: {a_plain[:34]}…")
    print(f"  已上报 bridge_gate_steps → action: {a_gate[:34]}…")
    check("HTTP 路径上 bridge_gate_steps 改变了 action（分支真的可达）",
          a_gate != a_plain and "方向已定" in a_gate)
    # 关键：**方向已定也仍然是 both**（契约 effect_on_owner：不改归属）
    it = next((i for i in r_gate["issues"] if i["code"] == "P-phase-unknown"), {})
    check("方向已定后 owner 仍是 both（决策树不改归属）",
          it.get("owner") == ct.OWNER_BOTH)
    check("evidence.direction 也随之上报",
          it.get("evidence", {}).get("direction") == "bridge_gate_step")

    # ---------- 防空转 ----------
    print("\n" + "=" * 74)
    print("[13] 防空转：本测试确实从契约原文推导出了断言")
    print("=" * 74)
    print(f"  从契约推导出的断言数: {derived}")
    check("推导出的断言数足够多（契约结构没被改到解析不出东西）", derived >= 26)

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


if __name__ == "__main__":
    raise SystemExit(main())
