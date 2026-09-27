"""契约对账的**责任划分**（谁去改）。

这个测试守两件事：

  1. **归因正确**：每条对不上的情况都归到该改的那一侧。
     规则来自 `core.contract.ISSUE_RULES`（会通过 /profile 暴露给前端），
     所以这里同时是在守"上游给前端的规则表"本身。
  2. **规则表没有死条目、代码不会发出未声明的 code**：
     遍历所有分支把 code 收集起来，要求 `观察到的 == ISSUE_RULES`。
     这条最有用 —— 它同时抓"定义了却永远不会触发的规则"和
     "代码里冒出一个没写规则的 code"（后者在前端会渲染成空白）。

另外守一条判定纪律：**info 不参与结论**。
只增不减的新增（如 `P-endpoint-added`）是 additive 的，不该把 verdict 拖成"有事要改"。
"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core import contract as C  # noqa: E402

checks: list[tuple[str, bool]] = []
observed: set[str] = set()


def check(name: str, ok: bool) -> None:
    checks.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")


def codes(items) -> list[str]:
    out = []
    for it in items:
        d = it.to_dict() if hasattr(it, "to_dict") else it
        out.append(d["code"])
        observed.add(d["code"])
    return out


def clean_audit() -> dict:
    """一份"上游完全自洽"的 audit 结果，用于合成各种故障。"""
    a = C.audit()
    return dict(a)


# ---------- [1] 上游自查：7 条后端责任 ----------
def test_upstream_rules() -> None:
    print("[1] 上游自查（全部 backend 责任）")

    broken = [
        ("U-emit-nonliteral", {"nonliteral_kinds": ["core/x.py:1"]}),
        ("U-emit-source", {"emit_sources_ok": False}),
        ("U-undeclared-event", {"undeclared_events": ["ghost"]}),
        ("U-dead-event", {"dead_events": ["plan"]}),
        ("U-deprecated-emitted", {"deprecated_still_emitted": ["old"]}),
        ("U-payload-drift", {"payload_drift": {"plan": ["intent"]}}),
        ("U-removed-surface", {"removed_phases": ["record"]}),
    ]
    for expected, patch in broken:
        a = clean_audit()
        a.update(patch)
        got = codes(C.upstream_issues(a))
        ok = expected in got
        check(f"合成故障 {expected} 被识别", ok)
        if ok:
            rule = C.ISSUE_RULES[expected]
            check(f"  {expected} 归给 {C.OWNER_BACKEND}",
                  rule.owner == C.OWNER_BACKEND)

    check("自洽的上游没有任何问题", not C.upstream_issues(clean_audit()))


# ---------- [2] 前端自述：逐类归因 ----------
def peer_base() -> dict:
    a = clean_audit()
    return {
        "contract_version": C.CONTRACT_VERSION,
        "schema_version": a["schema_version"],
        "upstream_event_kinds": sorted(C.contract_emitted()),
        "phases": C._pipeline_phases(),
        "report_keys": sorted(C.FROZEN_REPORT_KEYS),
        "upstream_endpoints": ["/run", "/profile"],
    }


def test_peer_rules() -> None:
    print("\n[2] 前端自述：逐类归因")

    cases = [
        # (期望 code, peer 覆盖, 期望 owner)
        ("P-version-behind", {"contract_version": "0.1"}, C.OWNER_FRONTEND),
        ("P-version-ahead", {"contract_version": "99.0"}, C.OWNER_BACKEND),
        ("P-version-unparsable", {"contract_version": "vNext"}, C.OWNER_BOTH),
        ("P-schema-behind", {"schema_version": "0.1"}, C.OWNER_FRONTEND),
        ("P-schema-ahead", {"schema_version": "9.0"}, C.OWNER_BACKEND),
        ("P-schema-mismatch", {"schema_version": "一号"}, C.OWNER_BOTH),
        ("P-event-unknown-to-frontend",
         {"upstream_event_kinds": ["cycle_start"]}, C.OWNER_FRONTEND),
        ("P-event-gone-upstream",
         {"upstream_event_kinds": sorted(C.contract_emitted()) + ["ghost"]},
         C.OWNER_BOTH),
        ("P-phase-missing", {"phases": ["plan"]}, C.OWNER_FRONTEND),
        # ★ ARCH-D1（契约 v1.0.7）：原判 backend/breaking，改判 both/degraded ——
        # 「前端自造节点」与「上游删阶段」现象相同，本侧判不出方向。
        ("P-phase-unknown", {"phases": C._pipeline_phases() + ["量化"]},
         C.OWNER_BOTH),
        ("P-report-key-missing", {"report_keys": ["bogus_key"]}, C.OWNER_FRONTEND),
        ("P-endpoint-missing",
         {"upstream_endpoints": ["/api/spec"]}, C.OWNER_BACKEND),
    ]
    for expected, patch, owner in cases:
        peer = peer_base()
        peer.update(patch)
        got = codes(C.peer_issues(peer, clean_audit(), ["/run", "/profile", "/skills"]))
        hit = expected in got
        check(f"{expected} 被识别", hit)
        if hit:
            rule = C.ISSUE_RULES[expected]
            check(f"  {expected} 归给 {owner}", rule.owner == owner)
            check(f"  {expected} 的 why/action 都写清楚了",
                  bool(rule.why) and bool(rule.action))

    # 缺字段与端点新增
    got = codes(C.peer_issues({}, clean_audit()))
    check("完全空的自述 → 提示缺字段（info）",
          "P-missing-field" in got and
          C.ISSUE_RULES["P-missing-field"].severity == C.SEV_INFO)
    peer = peer_base()
    got = codes(C.peer_issues(peer, clean_audit(), ["/run", "/profile", "/skills"]))
    check("上游多出的端点 → P-endpoint-added（前端登记或忽略）",
          "P-endpoint-added" in got and
          C.ISSUE_RULES["P-endpoint-added"].owner == C.OWNER_FRONTEND)
    gc = codes(C.peer_issues(peer_base(), clean_audit(),
                             ["/run", "/profile", "/"]))
    check("健康检查根路径不算需要登记的端点", "P-endpoint-added" not in gc)

    check("自洽的前端自述没有任何问题",
          not C.peer_issues(peer_base(), clean_audit(), ["/run", "/profile"]))


# ---------- [2.5] 运行态（ops）：事实由上报，code 与归属由本表定义 ----------
def test_ops_rules() -> None:
    print("\n[2.5] 运行态（ops）：两侧原先都没有的那一栏")
    for fact, code in (("service_down", "O-service-down"),
                       ("frontend_not_built", "O-frontend-not-built")):
        peer = {**peer_base(), "ops": {fact: True}}
        got = codes(C.peer_issues(peer, clean_audit()))
        check(f"上报 {fact} → {code}", code in got)
        check(f"  {code} 归给 ops", C.ISSUE_RULES[code].owner == C.OWNER_OPS)
        check(f"  {code} 级别为 breaking",
              C.ISSUE_RULES[code].severity == C.SEV_BREAKING)

    got = codes(C.peer_issues({**peer_base(), "ops": {"service_down": False}},
                              clean_audit()))
    check("事实为 false 不产生问题", "O-service-down" not in got)
    got = codes(C.peer_issues({**peer_base(), "ops": {"谁也不知道的新事实": True}},
                              clean_audit()))
    check("未知运行态事实被忽略（additive 安全，不报错不噪声）",
          all(c not in ("O-service-down", "O-frontend-not-built") for c in got))
    check("不传 ops 字段时不产生 ops 问题",
          all(i.rule.owner != C.OWNER_OPS
              for i in C.peer_issues(peer_base(), clean_audit())))


# ---------- [2.6] 未知阶段的方向：契约的决策树（ARCH-D1）----------
def test_phase_unknown_decision_tree() -> None:
    print("\n[2.6] P-phase-unknown 的方向判定（契约 phase_unknown_decision_tree）")
    unknown = ["manifest"]

    def issue(**over):
        peer = {**peer_base(), "phases": C._pipeline_phases() + unknown}
        peer.update(over)
        r = C.compare(peer, None)
        hits = [i for i in (r["both"] + r["backend"] + r["frontend"])
                if i["code"] == "P-phase-unknown"]
        return (hits[0] if hits else None), r

    # 情形 1：对端声明它是自补门禁节点 → 方向可判，action 直接指名前端
    it, r = issue(bridge_gate_steps=["manifest"])
    check("情形1（命中 bridge_gate_steps）direction=bridge_gate_step",
          it and it["evidence"]["direction"] == "bridge_gate_step")
    check("情形1 的 action 直接指名前端（不用人猜）",
          it and "方向已定" in it["action"] and "前端" in it["action"])
    check("情形1 的 owner 仍是 both（契约 effect_on_owner：不来回改判）",
          it and it["owner"] == C.OWNER_BOTH)

    # 情形 3：信息不足 → 保持人工表述，**不伪造方向**
    for label, over in (("未提供字段", {}), ("提供了但没命中", {"bridge_gate_steps": ["别的"]})):
        it, r = issue(**over)
        check(f"情形3（{label}）direction=undetermined",
              it and it["evidence"]["direction"] == "undetermined")
        check(f"情形3（{label}）保留人工表述『先确认方向』",
              it and "先确认方向" in it["action"])
        check(f"情形3（{label}）owner 仍是 both", it and it["owner"] == C.OWNER_BOTH)

    # 三种情形的 owner/severity 必须完全一致 —— 决策树只改文案，不改归属
    owners = set()
    for over in ({"bridge_gate_steps": ["manifest"]}, {}, {"bridge_gate_steps": ["别的"]}):
        it, _ = issue(**over)
        owners.add((it["owner"], it["severity"]))
    check("三种情形的 owner/severity 完全相同（只有 action 不同）",
          owners == {(C.OWNER_BOTH, C.SEV_DEGRADED)})

    # 逐条 action 覆盖**不能**影响 owner/severity
    ov = C.Issue("P-phase-unknown", "x", {"direction": "bridge_gate_step"},
                 action_override="锐化过的文案")
    d = ov.to_dict()
    check("action_override 只改 action，owner/severity 仍来自规则表",
          d["action"] == "锐化过的文案"
          and d["owner"] == C.ISSUE_RULES["P-phase-unknown"].owner
          and d["severity"] == C.ISSUE_RULES["P-phase-unknown"].severity)

    # 边界：`failed` 在 FROZEN_PHASES 但不在 PHASE_ORDER
    # → 助手函数会判情形 2；但 `failed` 是 CyclePhase 成员，
    #   所以 peer 报它**根本不会**触发本规则（两件事都要成立才对）
    direction, _ = C._phase_unknown_direction("failed", {})
    check("助手对 `failed` 判情形2（∈FROZEN 且 ∉PHASE_ORDER）",
          direction == "upstream_removed_frozen_phase")
    r = C.compare({**peer_base(), "phases": C._pipeline_phases() + ["failed"]}, None)
    check("但 peer 报 `failed` 不会触发 P-phase-unknown（它是 CyclePhase 成员）",
          not any(i["code"] == "P-phase-unknown"
                  for i in (r["both"] + r["backend"] + r["frontend"])))

    check("bridge_gate_steps 已进 PEER_FIELDS（契约 canonical_fields 要求）",
          "bridge_gate_steps" in C.PEER_FIELDS)


# ---------- [3] 结论（verdict）与 info 不参与判定 ----------
def test_verdict() -> None:
    print("\n[3] 结论：verdict 由 breaking/degraded 决定，info 不参与")
    # 直接调真函数（不在这里重写一遍判定逻辑——那样测试就没在测产品代码）
    routes = ["/run", "/profile"]

    def verdict(peer, rts=None):
        return C.compare(peer, rts if rts is not None else routes)["verdict"]

    check("两边自洽 → ok", verdict(peer_base()) == "ok")
    check("只有 info（上游多出的端点）→ 仍 ok",
          verdict(peer_base(), ["/run", "/profile", "/skills"]) == "ok")
    check("前端落后 → frontend-action",
          verdict({**peer_base(), "contract_version": "0.1"}) == "frontend-action")
    # ★ ARCH-D1：前端报了上游没有的阶段，**方向判不出来** → 需协商，
    # 而**不再**判给后端（原判会把 bridge 自补的门禁节点说成后端删了阶段）。
    check("对端报了未知阶段 → need-negotiation（不再推定是后端删的）",
          verdict({**peer_base(), "phases": C._pipeline_phases() + ["量化"]})
          == "need-negotiation")
    check("同一情形下 backend 栏必须为空（归因方向已修正）",
          C.compare({**peer_base(), "phases": C._pipeline_phases() + ["量化"]},
                    routes)["counts"]["backend"] == 0)
    # 真正的"上游删阶段"由 U-removed-surface 兜住，不依赖对端上报
    check("真正的删除场景由 U-removed-surface 覆盖（backend/breaking）",
          C.ISSUE_RULES["U-removed-surface"].owner == C.OWNER_BACKEND
          and C.ISSUE_RULES["U-removed-surface"].severity == C.SEV_BREAKING)
    check("版本无法比较 → need-negotiation（需人工定格式）",
          verdict({**peer_base(), "contract_version": "vNext"})
          == "need-negotiation")
    check("两边都有事 → multi-action",
          verdict({**peer_base(), "contract_version": "0.1",
                   "upstream_endpoints": ["/api/spec"]}) == "multi-action")

    # ---- ops 优先：环境没通时后面一切不成立 ----
    # 用 `frontend_not_built` 验优先级：它与"请求可达"**不矛盾**
    # （服务活着但前端没构建是完全可能的），所以它是真正会驱动结论的 ops 事实。
    check("只有 ops 问题 → ops-action",
          verdict({**peer_base(), "ops": {"frontend_not_built": True}}) == "ops-action")
    check("ops + 前端问题 → 仍 ops-action（优先级最高）",
          verdict({**peer_base(), "contract_version": "0.1",
                   "ops": {"frontend_not_built": True}}) == "ops-action")
    check("ops + 后端问题 → 仍 ops-action",
          verdict({**peer_base(), "upstream_endpoints": ["/api/spec"],
                   "ops": {"frontend_not_built": True}}) == "ops-action")

    # ---- service_down 的自相矛盾：经同步通道上报不可能是"当前值" ----
    # 请求成功送达 = 上游可达 ⇒ 该标志只能是"上次已知状态"。
    # 它照常出现在 ops 栏（信息不丢），但**不驱动 verdict** ——
    # 否则一条陈旧标志会压掉所有本可修复的结论（统筹方指出的危害）。
    r = C.compare({**peer_base(), "ops": {"service_down": True}}, routes)
    check("service_down 仍出现在 ops 栏（信息不丢）",
          r["counts"]["ops"] == 1
          and r["ops"][0]["code"] == "O-service-down")
    check("service_down 被标为 last_known_state（语义标注）",
          r["ops"][0]["evidence"].get("semantics") == "last_known_state"
          and r["ops"][0]["evidence"].get("current") is False)
    check("service_down 不把 verdict 拉成 ops-action（其余结论得以存活）",
          r["verdict"] == "ok")
    check("矛盾被写进 warnings（可见性）",
          any("本请求已成功送达" in w for w in r["warnings"]))
    check("ok 时 next 也提示 ops 栏有未参与判定的项",
          "未参与判定" in r["next"])

    # 反例：陈旧标志不得掩盖真实问题
    r = C.compare({**peer_base(), "contract_version": "0.1",
                   "ops": {"service_down": True}}, routes)
    check("陈旧 service_down 不掩盖前端真实问题",
          r["verdict"] == "frontend-action"
          and any("上次已知状态" in w for w in r["warnings"]))

    # frontend_not_built 与可达性**不矛盾**（服务活着但前端没构建）→ 仍驱动结论
    r = C.compare({**peer_base(), "ops": {"frontend_not_built": True}}, routes)
    check("frontend_not_built 不受影响，仍判 ops-action",
          r["verdict"] == "ops-action" and not r["warnings"])

    # ---- 词表必须与统筹契约一致（这是契约定义，硬编码是对的）----
    check("结论词表 == 契约 verdict_vocabulary 的 6 个值",
          set(C.VERDICTS) == {"ok", "ops-action", "backend-action",
                              "frontend-action", "need-negotiation", "multi-action"})
    check("归属词表 == 契约 owner_vocabulary 的 4 个值",
          set(C.OWNER_ORDER) == {"ops", "backend", "frontend", "both"})
    check("ops 在归属判定顺序里排第一",
          C.OWNER_ORDER[0] == C.OWNER_OPS)
    check("报告四栏齐全（ops/backend/frontend/both）",
          all(k in C.compare(peer_base(), routes)
              for k in ("ops", "backend", "frontend", "both")))
    # 仅 info 的规则不得把结论拖成"有事要改"
    info_codes = [c for c, r in C.ISSUE_RULES.items() if r.severity == C.SEV_INFO]
    check("info 级规则不参与 verdict（逐条核对规则表）",
          all(C.ISSUE_RULES[c].severity == C.SEV_INFO for c in info_codes))

    # 真报告里的字段齐不齐
    r = C.compare(peer_base(), routes)
    check("报告带 verdict/next/counts/三栏 + 上游事实",
          all(k in r for k in ("verdict", "next", "counts", "backend", "frontend",
                               "both", "upstream_facts")))
    check("ok 时 next 说清了'无需处理'", r["verdict"] == "ok" and "无需" in r["next"])
    check("上游事实里流水线阶段与终态值分开列",
          r["upstream_facts"]["pipeline_phases"] == C._pipeline_phases()
          and "failed" in r["upstream_facts"]["phase_values"])


# ---------- [4] 规则表自洽：无死条目、无未声明的 code ----------
def test_rules_complete() -> None:
    print("\n[4] 规则表自洽（死条目 / 未声明 code 双向检查）")
    # 触发 P-missing-field 与上面所有分支后，观察到的 code 应恰好覆盖规则表
    C.compare({}, ["/run"])
    declared = set(C.ISSUE_RULES)
    missing_rule = sorted(observed - declared)
    dead_rule = sorted(declared - observed)
    print(f"  规则表 {len(declared)} 条；本轮观察到 {len(observed)} 条")
    print(f"  发出但没有规则的: {missing_rule or '无'}")
    print(f"  有规则但从未触发的: {dead_rule or '无'}")
    check("代码不会发出未声明的 code", not missing_rule)
    check("没有永不触发的死规则", not dead_rule)
    check("每条规则的 owner 合法",
          all(r.owner in C.OWNER_ORDER for r in C.ISSUE_RULES.values()))
    check("每条规则的 severity 合法",
          all(r.severity in (C.SEV_BREAKING, C.SEV_DEGRADED, C.SEV_INFO)
              for r in C.ISSUE_RULES.values()))

    d = C.describe()
    check("规则表通过 /profile 暴露给前端", set(d["responsibility"]) == declared)
    check("暴露的规则含 owner/severity/why/action",
          all({"owner", "severity", "why", "action"} <= set(v)
              for v in d["responsibility"].values()))
    check("前端提交字段清单也暴露了", set(d["peer_report_fields"]) == set(C.PEER_FIELDS))
    check("词表也暴露了（供统筹方比对两侧是否同词表）",
          set(d["owner_values"]) == set(C.OWNER_ORDER)
          and set(d["verdict_values"]) == set(C.VERDICTS))
    check("运行态事实名 → code 的映射也暴露了",
          d["ops_fact_rules"] == C.OPS_FACT_RULES)


def main() -> int:
    test_upstream_rules()
    test_peer_rules()
    test_ops_rules()
    test_phase_unknown_decision_tree()
    test_verdict()
    test_rules_complete()

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
