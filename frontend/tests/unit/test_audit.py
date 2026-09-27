"""离线校验：责任判定的归属是否正确。

为什么值得单测
--------------
"该改前端还是后端接口定义" —— 判错了会让人去修**不该修的那一边**，
比不判定更糟。所以每一类场景都要有明确输入 → 明确归属，写成断言钉住。

## 边界（`.interface_contract` 的 boundary_definition）

    backend  = SimpleAgent2_Cycle 仓库内的一切
    frontend = SimpleAgent2_Cycle_VueWeb 仓库内的一切 —— **bridge/ 与 frontend/ 同等**
    ops      = 环境与运行态
    both     = 无法从事实源单方面判定

直接后果，也是本测试最想钉住的一条：**`bridge/` 的问题算 frontend。**
所以 `backend.endpoint_missing`（两个声明都在 bridge）归属是 **frontend** —— 见 [4]。

## 词汇表

归属 4 值 / 严重度 3 值（breaking·degraded·info）/ 结论 6 值，定义在
`bridge/contract_vocab.py`（契约的镜像）。名称本身由 `test_contract_vocab.py` 把守。

## 上报体形状

`client` 用契约 `client_report_schema.canonical_fields` 的字段名，**事件与阶段
按来源分开**（gap_G2 / gap_G3）。旧格式（`events`/`stages`/`endpoints` 平铺）
由 `test_audit_legacy.py` 覆盖 —— 那条路径**不许猜来源**。

全离线：合成 spec 与 client 期望，断言归属。

运行：python tests/unit/test_audit.py
"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401

from bridge.audit import OWNERS, run as run_audit  # noqa: E402

checks: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))


#: 阶段必须与**真实上游** PHASE_ORDER 一致——否则 `backend.stage_mismatch`
#: 会对每一条合成 spec 都开火，让测试变成"测自己的假数据"。
from core.cycle import PHASE_ORDER  # noqa: E402

REAL_STAGES = tuple(p.value for p in PHASE_ORDER)


def make_spec(events=("a", "b", "c"), stages=REAL_STAGES,
              endpoints=("spec", "runs"), version="1.0",
              contract_version="1.0", cv_source="upstream",
              upstream_endpoints=()):
    """造一份最小但**自洽**的 spec（阶段用真实 PHASE_ORDER）。

    一律带上契约 canonical 字段（分区 / 版本轴来源），否则测的就不是线上形状。
    """
    return {
        "spec_version": version,
        "implements_contract_version": contract_version,
        "implements_contract_version_source": cv_source,
        "schema_version": "1.0",
        "schema_version_source": "upstream",
        "pipeline": {
            "stages": [{"id": s, "kind": "phase"} for s in stages],
            "failure_phase": "failed",
            # 阶段分区（gap_G3）：合成 spec 不带自补门禁节点
            "upstream_phases": list(stages),
            "bridge_gate_steps": [],
        },
        "endpoints": {k: f"/api/{k}" for k in endpoints},
        "endpoint_partition": {
            "upstream": list(upstream_endpoints),
            "frontend": [f"/api/{k}" for k in endpoints],
            "mapped": {k: f"/{k}" for k in endpoints if k in upstream_endpoints},
        },
        # 事件分区（gap_G2）：合成 spec 把事件全算上游，桥自产的在别处测
        "event_partition": {
            "upstream": list(events), "frontend": [],
            "total": len(events), "overlap": [],
        },
        "events": {e: {"label": e, "tone": "info", "panel": "t"} for e in events},
        "statuses": {},
        "tools": [],
        "ui": {},
        "diagnostics": {
            "event_count": len(events), "uncalibrated_events": [],
            "dead_calibrations": [], "override_file": None, "errors": [],
        },
    }


def client_of(spec, *, up_events=None, fe_events=None, phases=None, gates=None,
              fe_endpoints=None, up_endpoints=None,
              contract_version=None, version=None):
    """按契约 canonical 字段造上报体。默认与 spec 完全一致（→ 应当无问题）。"""
    ep = spec["event_partition"]
    return {
        "spec_version": spec["spec_version"] if version is None else version,
        "contract_version": (spec["implements_contract_version"]
                             if contract_version is None else contract_version),
        "schema_version": spec["schema_version"],
        "upstream_event_kinds": list(
            ep["upstream"] if up_events is None else up_events),
        "frontend_event_kinds": list(
            ep["frontend"] if fe_events is None else fe_events),
        "phases": list(spec["pipeline"]["upstream_phases"]
                       if phases is None else phases),
        "bridge_gate_steps": list(spec["pipeline"]["bridge_gate_steps"]
                                  if gates is None else gates),
        "frontend_endpoints": list(spec["endpoints"].keys()
                                   if fe_endpoints is None else fe_endpoints),
        "upstream_endpoints": list(spec["endpoint_partition"]["upstream"]
                                   if up_endpoints is None else up_endpoints),
    }


def ids(a) -> set[str]:
    return {i.id for i in a.issues}


def row(a, issue_id: str):
    return next(i for i in a.issues if i.id == issue_id)


def owners_of(a, issue_id: str) -> str | None:
    for owner, items in a.by_owner().items():
        if any(i["id"] == issue_id for i in items):
            return owner
    return None


spec = make_spec()


# ============================================================
print("=" * 74)
print("[1] 一致 → 无问题，verdict == ok")
print("=" * 74)
a = run_audit(spec, client_of(spec))
check("verdict == ok", a.verdict == "ok", a.verdict)
check("无 issue", not a.issues, str(ids(a)))
check("标注了前端已上报", a.client_reported is True)
check("结论文案说「兼容」", "兼容" in a.verdict_text, a.verdict_text)
check("checked 非空", len(a.checked) >= 4, str(len(a.checked)))


# ============================================================
print("\n" + "=" * 74)
print("[2] 服务声明了、前端不认识 → 归属前端（服务守约了）")
print("=" * 74)
a = run_audit(spec, client_of(spec, up_events=["a", "b"]))   # 少了 c
check("命中 P-event-unknown-to-frontend",
      "P-event-unknown-to-frontend" in ids(a), str(ids(a)))
check("归属标为前端", owners_of(a, "P-event-unknown-to-frontend") == "frontend")
r = row(a, "P-event-unknown-to-frontend")
check("severity == degraded（有兜底，不阻断）", r.severity == "degraded", r.severity)
check("crosswalk 指回契约 id", r.crosswalk_id == "P-event-unknown-to-frontend", r.crosswalk_id)
check("给出了可执行的修法", "case" in r.fix, r.fix)
check("证据里有具体事件名", "c" in r.evidence, str(r.evidence))
check("verdict == frontend-action", a.verdict == "frontend-action", a.verdict)


# ============================================================
print("\n" + "=" * 74)
print("[3] 事件分区：桥自产的事件不该被当成上游的")
print("=" * 74)
# 一份两侧都有事件的 spec：上游 a/b/c，bridge 自产 bridge_only
s_bridge = make_spec()
s_bridge["events"]["bridge_only"] = {"label": "B", "tone": "info", "panel": "t"}
s_bridge["event_partition"]["frontend"] = ["bridge_only"]

# 正确分区：两侧分开报 → 干净
a = run_audit(s_bridge, client_of(s_bridge, up_events=["a", "b", "c"],
                                  fe_events=["bridge_only"]))
check("分区正确时完全无 issue", not a.issues, str(ids(a)))
check("verdict == ok", a.verdict == "ok", a.verdict)

# 反向：bridge 自产的事件被当成上游上报 → 服务端照样认得它（不丢信息），
# 但**不该**因此说"上游缺了它"
a2 = run_audit(s_bridge, client_of(s_bridge, up_events=["a", "b", "c", "bridge_only"]))
check("混报不会触发 missing_upstream_events",
      "P-event-unknown-to-frontend" not in ids(a2), str(ids(a2)))

# 前端认得服务不声明的事件 → both（契约裁决，不是 frontend）
a3 = run_audit(spec, client_of(spec, fe_events=["ghost"]))
check("孤儿事件命中 P-event-gone-upstream",
      "P-event-gone-upstream" in ids(a3), str(ids(a3)))
check("孤儿归属 both 而非 frontend（契约裁决）",
      owners_of(a3, "P-event-gone-upstream") == "both",
      str(owners_of(a3, "P-event-gone-upstream")))
check("孤儿 severity == degraded",
      row(a3, "P-event-gone-upstream").severity == "degraded")
check("孤儿参与结论（degraded 是 blocking）",
      row(a3, "P-event-gone-upstream").blocking is True)
check("verdict == need-negotiation", a3.verdict == "need-negotiation", a3.verdict)


# ============================================================
print("\n" + "=" * 74)
print("[4] 声明在 bridge 的问题 → 归属 frontend，不是 backend")
print("=" * 74)
# 端点的**声明**与**注册**都在 bridge/spec.py → 不一致该改 bridge，按边界是 frontend
a = run_audit(spec, client_of(spec), routes={"/api/spec"})   # runs 没注册
check("命中 backend.endpoint_missing", "backend.endpoint_missing" in ids(a), str(ids(a)))
check("★ 归属是 frontend（bridge 的声明）",
      owners_of(a, "backend.endpoint_missing") == "frontend",
      str(owners_of(a, "backend.endpoint_missing")))
check("id 保留旧前缀（对账表按 bridge_id 索引）",
      row(a, "backend.endpoint_missing").crosswalk_id == "backend.endpoint_missing")
check("缺失端点在证据里", any("runs" in e for i in a.issues for e in i.evidence))
check("verdict == frontend-action（不是 backend-action）",
      a.verdict == "frontend-action", a.verdict)

a2 = run_audit(spec, client_of(spec), routes={"/api/spec", "/api/runs", "/api/extra"})
check("命中 backend.endpoint_undeclared", "backend.endpoint_undeclared" in ids(a2))
check("未声明端点是 degraded 不是 breaking",
      row(a2, "backend.endpoint_undeclared").severity == "degraded")
check("未声明端点归属 frontend",
      owners_of(a2, "backend.endpoint_undeclared") == "frontend")
# `bridge.upstream_endpoint_gone`（真·上游问题）要拿到真实上游路由才判得了，
# 那条路径由 test_partition.py 在 bootstrap 之后覆盖。


# ============================================================
print("\n" + "=" * 74)
print("[5] 声明了却不做 → 归属后端（自相矛盾，事实源在上游）")
print("=" * 74)
s = make_spec()
s["diagnostics"]["dead_calibrations"] = ["ghost_event"]
a = run_audit(s, client_of(s))
check("命中 U-dead-event", "U-dead-event" in ids(a),
      str(ids(a)))
check("归属标为后端", owners_of(a, "U-dead-event") == "backend")
check("severity == degraded（契约 v1.0.7 统一级别，原为 breaking）",
      row(a, "U-dead-event").severity == "degraded",
      row(a, "U-dead-event").severity)
check("crosswalk 指回未拆分的旧 id",
      row(a, "U-dead-event").crosswalk_id == "backend.dead_event")

# 同理，bridge 自产事件死了 → frontend（SPLIT 的另一半）
s2 = make_spec()
s2["diagnostics"]["dead_calibrations"] = ["tool_call"]
a2 = run_audit(s2, client_of(s2))
check("bridge 自产事件死了 → bridge.dead_event",
      "bridge.dead_event" in ids(a2), str(ids(a2)))
check("SPLIT 的另一半归属 frontend",
      owners_of(a2, "bridge.dead_event") == "frontend")
check("两边各自成条，不是一个混合条目",
      "U-dead-event" not in ids(a2), str(ids(a2)))

# 上游契约缺失（事实源真的在上游）→ backend
class FakeReport:
    ok = False
    missing = ["core.foo.Bar  → 前端某面板会一直空着"]
    notes: list[str] = []


a3 = run_audit(spec, client_of(spec), contract_report=FakeReport())
check("命中 backend.upstream_contract", "backend.upstream_contract" in ids(a3))
check("保留为 backend（事实源在上游）",
      owners_of(a3, "backend.upstream_contract") == "backend")
check("缺了会怎样也带上了", any("空着" in e for i in a3.issues for e in i.evidence))


# ============================================================
print("\n" + "=" * 74)
print("[6] 阶段分区（gap_G3）：manifest 不算上游阶段")
print("=" * 74)
# spec 里 manifest 是 bridge 自补的门禁节点，不在 upstream_phases 里
s3 = make_spec()
s3["pipeline"]["stages"] = (
    [{"id": i, "kind": "phase"} for i in REAL_STAGES]
    + [{"id": "manifest", "kind": "gate"}]
)
s3["pipeline"]["upstream_phases"] = list(REAL_STAGES)
s3["pipeline"]["bridge_gate_steps"] = ["manifest"]

ok = client_of(s3)
a = run_audit(s3, ok)
check("上报体里 phases 只有上游那 5 个", len(ok["phases"]) == 5, str(ok["phases"]))
check("manifest 被放进 bridge_gate_steps", ok["bridge_gate_steps"] == ["manifest"])
check("正确分区 → 无 unknown_phases", "P-phase-unknown" not in ids(a), str(ids(a)))

# 宽容性：前端就算把 manifest 混进 phases，**服务端自己认得出那是它的门禁节点**，
# 不会因此开火（服务声明过 `bridge_gate_steps`，无从"无法单方面判定"）。
# ★ 但这只是桥内审查的宽容；**上游的 `/contract/check` 不宽容** —— 那正是 gap_G3
#   的原始缺口（`P-phase-unknown`, owner=backend）。真正的防线是前端上报时
#   按 `spec.pipeline.upstream_phases` 过滤，见上面两条断言。
bad = client_of(s3, phases=list(REAL_STAGES) + ["manifest"])
a2 = run_audit(s3, bad)
check("混进 phases 也不误报（服务认得自己的门禁节点）",
      "P-phase-unknown" not in ids(a2), str(ids(a2)))

# 真正双方都没有的阶段 → both（无法单方面判定）
a2b = run_audit(s3, client_of(s3, phases=list(REAL_STAGES) + ["invented"]))
check("双方都没有的阶段 → P-phase-unknown",
      "P-phase-unknown" in ids(a2b), str(ids(a2b)))
check("unknown_phases 归属 both（无法单方面判定）",
      owners_of(a2b, "P-phase-unknown") == "both")

# 上游有、前端没画 → frontend
a3 = run_audit(s3, client_of(s3, phases=["plan"]))
check("前端漏画上游阶段 → P-phase-missing",
      "P-phase-missing" in ids(a3), str(ids(a3)))
check("missing_stages 归属 frontend",
      owners_of(a3, "P-phase-missing") == "frontend")


# ============================================================
print("\n" + "=" * 74)
print("[7] 契约版本：拿不到就说「判不出来」，不许沉默")
print("=" * 74)
a = run_audit(spec, client_of(spec, contract_version=""))
check("未上报契约版本 → P-missing-field",
      "P-missing-field" in ids(a), str(ids(a)))
check("归属 frontend",
      owners_of(a, "P-missing-field") == "frontend")
check("文案点明是「判不出来」而不是「没问题」",
      "判不出来" in row(a, "P-missing-field").detail)

a2 = run_audit(spec, client_of(spec, contract_version="0.9"))
check("版本错位 → P-version-behind",
      "P-version-behind" in ids(a2), str(ids(a2)))
check("错位是 degraded", row(a2, "P-version-behind").severity == "degraded")
# ★ 只有 `info` 不参与结论（NON_BLOCKING_SEVERITIES）；`degraded` 是参与判定的。
#   "不阻断"指的是前端有兜底、界面不会崩，不是"不进 verdict"。
check("degraded 参与结论 → frontend-action",
      a2.verdict == "frontend-action", a2.verdict)
check("degraded 是 blocking", row(a2, "P-version-behind").blocking is True)

# 三条版本轴不许互相比较：SPEC_VERSION 变了不该触发契约错位
a3 = run_audit(spec, client_of(spec, version="9.9"))
check("只改 spec_version 不触发契约错位",
      "P-version-behind" not in ids(a3), str(ids(a3)))


# ============================================================
print("\n" + "=" * 74)
print("[8] info 不参与结论（契约 empirical_evidence.S1）")
print("=" * 74)
# 服务多了一个前端没用到的端点 → info，verdict 必须仍是 ok
s4 = make_spec(endpoints=("spec", "runs", "extra"))
a = run_audit(s4, client_of(s4, fe_endpoints=["spec", "runs"]))
check("命中 P-endpoint-added", "P-endpoint-added" in ids(a),
      str(ids(a)))
check("severity == info", row(a, "P-endpoint-added").severity == "info")
check("blocking is False", row(a, "P-endpoint-added").blocking is False)
check("★ info 不改变 verdict（仍是 ok）", a.verdict == "ok", a.verdict)
check("info 不阻碍「兼容」文案", "兼容" in a.verdict_text, a.verdict_text)
d = a.to_dict()
check("to_dict 把 info 分开计数", d["info_count"] >= 1 and d["blocking_count"] == 0,
      f"info={d['info_count']} blocking={d['blocking_count']}")


# ============================================================
print("\n" + "=" * 74)
print("[9] ops 优先：环境没弄好，后面判什么都没意义")
print("=" * 74)
a = run_audit(spec, client_of(spec), service_reachable=False)
check("命中 O-service-down", "O-service-down" in ids(a))
check("severity == breaking", row(a, "O-service-down").severity == "breaking")
check("verdict == ops-action", a.verdict == "ops-action", a.verdict)
check("修法是「先起服务」", "起" in row(a, "O-service-down").fix)

# ops 与 frontend 同时有问题 → 仍是 ops-action（ops 优先）
a2 = run_audit(spec, client_of(spec, up_events=["a"]), service_reachable=False)
check("ops + frontend 同时坏 → verdict 仍是 ops-action",
      a2.verdict == "ops-action", a2.verdict)

a3 = run_audit(spec, client_of(spec), frontend_built=False)
check("命中 O-frontend-not-built", "O-frontend-not-built" in ids(a3))
check("修法是「构建」", "build" in row(a3, "O-frontend-not-built").fix)


# ============================================================
print("\n" + "=" * 74)
print("[9b] ops 通道：被传输层证伪的事实不参与 verdict（契约 v1.0.5）")
print("=" * 74)
from bridge.audit import OPS_STALE_BY_TRANSPORT  # noqa: E402
from bridge.contract_vocab import verdict_for  # noqa: E402

# ★ 契约 verdict_vocabulary.priority：「先判 ops」。所以 ops 盖过 both 的协商。
check("★ {ops, both} → ops-action（ops 优先于协商）",
      verdict_for({"ops", "both"}) == "ops-action", verdict_for({"ops", "both"}))
check("★ {ops, backend} → ops-action",
      verdict_for({"ops", "backend"}) == "ops-action")

# --- 关键一条：送达了却报 service_down = 被传输层证伪 ---
c_ops = client_of(spec)
c_ops["ops"] = {"service_down": True}
a = run_audit(spec, c_ops)
check("★ 陈旧 service_down → verdict 仍是 ok（不再驱动判定）",
      a.verdict == "ok", a.verdict)
check("★ 但它必须出现在 warnings 里（消费方义务的兜底）",
      len(a.warnings) == 1, str(a.warnings))
check("warning 文案点明「被传输层证伪」",
      "证伪" in a.warnings[0] and "O-service-down" in a.warnings[0],
      a.warnings[0])
check("★ ops 栏保留该事实（运维要看到「上次已知状态」）",
      a.ops_reported == {"service_down": True}, str(a.ops_reported))
check("不再有一条 ops_report_unconfirmed 的 info 噪音",
      "frontend.ops_report_unconfirmed" not in ids(a), str(ids(a)))
check("warnings 不进 responsibility（它不是「谁的错」）",
      not any(i.id == "O-service-down" for i in a.issues))
check("★ to_dict 带 warnings（additive 字段）",
      a.to_dict()["warnings"] == a.warnings)
check("★ to_dict 带 ops 栏", a.to_dict()["ops"] == {"service_down": True})
check("★ warnings 与 verdict 一起出现在 markdown 里（不能藏在附录）",
      "提示" in a.to_markdown(), "markdown 里应有独立的提示段")
# 有 issue 时，提示段必须在分归属的正文**之前** —— 契约的要求是
# "展示 verdict 的同时展示 warnings"，藏在附录等于没展示。
am = run_audit(spec, dict(client_of(spec, up_events=["a"]),
                          ops={"service_down": True}))
md = am.to_markdown()
check("★ 提示段排在分归属正文之前",
      md.index("提示") < md.index("## 前端（bridge + Vue）"),
      "提示段位置不对")
check("markdown 里也说明了它不参与结论",
      "不参与结论" in md, md[:200])

# --- frontend_not_built：契约实测「仍然判 ops-action」 ---
a2 = run_audit(spec, client_of(spec), frontend_built=False)
check("★ 服务侧观测到未构建 → 仍是 ops-action（ops 优先未被削弱）",
      a2.verdict == "ops-action", a2.verdict)
check("前端未构建不产生 warning（它是**当前**事实，不是陈旧标志）",
      not a2.warnings, str(a2.warnings))

# 客户端报 not_built 但本地看得见产物 → 与本地观测矛盾 → warning，不参与判定
a3 = run_audit(spec, dict(c_ops, ops={"frontend_not_built": True}),
               frontend_built=True)
check("客户端报 not_built 但本地有产物 → warning",
      len(a3.warnings) == 1 and "frontend_not_built" in a3.warnings[0],
      str(a3.warnings))
check("该矛盾不把 verdict 拉成 ops-action", a3.verdict == "ok", a3.verdict)

# 服务侧与客户端同时观测到 not_built → 只算一条（不许重复计）
a4 = run_audit(spec, dict(c_ops, ops={"frontend_not_built": True}),
               frontend_built=False)
check("★ 同一条运行态事实不重复计入 responsibility",
      [i.id for i in a4.issues].count("O-frontend-not-built") == 1,
      str([i.id for i in a4.issues]))
check("无一 issue 重复 id",
      len(a4.issues) == len({i.id for i in a4.issues}))
check("verdict 仍是 ops-action", a4.verdict == "ops-action", a4.verdict)

# --- additive 安全：未知事实名忽略；报 false 不构成事实 ---
a5 = run_audit(spec, dict(c_ops, ops={"service_down": True, "future_thing": True}))
check("★ 未知事实名被忽略（additive 安全）",
      a5.ops_reported == {"service_down": True}, str(a5.ops_reported))
a6 = run_audit(spec, dict(c_ops, ops={"service_down": False}))
check("报 false 不构成事实（不产生 warning、不进判定）",
      not a6.warnings and a6.verdict == "ok", f"{a6.warnings} {a6.verdict}")

check("契约列的「不驱动 verdict」清单 == 实现里的常量",
      OPS_STALE_BY_TRANSPORT == frozenset({"O-service-down"}),
      str(sorted(OPS_STALE_BY_TRANSPORT)))


# ============================================================
print("\n" + "=" * 74)
print("[10] 通用不变式")
print("=" * 74)
a = run_audit(spec, None)      # ← 不传 client，才是"未上报"
check("未上报前端时 client_reported=False", a.client_reported is False)
check("未上报时的文案说清楚只审了自洽", "未收到前端期望" in a.verdict_text,
      a.verdict_text)

# 每条 issue 都必须有归属 / 严重度 / 标题 / 修法
a = run_audit(spec, client_of(spec, up_events=["a"], contract_version="0.9"),
              routes={"/api/nope"}, service_reachable=False, frontend_built=False)
# 注意：`Issue.fix` 可以是空的——那时由 OWNERS 的默认建议兜底（to_dict 里做）。
# 所以这里要按"最终呈现"判断，不是按原始字段。
bad = [i.id for i in a.issues
       if i.owner not in OWNERS or i.severity not in ("breaking", "degraded", "info")
       or not i.title or not (i.fix or OWNERS[i.owner][1])]
check("每条问题都有归属/级别/标题/修法", not bad, str(bad))
check("checked 记录了核对过什么", len(a.checked) >= 4, str(len(a.checked)))

d = a.to_dict()
check("to_dict 四段责任齐备（含 both）",
      set(d["responsibility"]) == {"backend", "frontend", "ops", "both"},
      str(set(d["responsibility"])))
check("to_dict 带 verdict 与文案", bool(d["verdict"]) and bool(d["verdict_text"]))
check("to_dict 带契约版本与来源",
      bool(d["implements_contract_version"]) and bool(d["contract_version_source"]))
check("verdict 是契约 6 值之一",
      d["verdict"] in ("ok", "ops-action", "backend-action", "frontend-action",
                       "need-negotiation", "multi-action"), d["verdict"])
md = a.to_markdown()
check("markdown 按归属分节", "## 前端（bridge + Vue）" in md or "## 后端（上游仓库）" in md)
check("markdown 不出现裸归属代号", "backend_contract" not in md)
check("markdown 用统一严重度记号", "`breaking`" in md or "`degraded`" in md)


# ============================================================
print("\n" + "=" * 74)
print("[11] 拿真实 spec 跑一遍（形状对得上）")
print("=" * 74)
try:
    import bridge.bootstrap as bootstrap

    bootstrap.install()
    from bridge.spec import build_spec

    real = build_spec()
    client = client_of(real)
    a = run_audit(real, client, routes=set(real["endpoints"].values()))

    # ★ 按配置分流：自带副本落后于契约时，标定表里为**新上游**备好的条目
    #   会被判成"死标定" → `U-dead-event`(owner=backend, degraded) →
    #   verdict 变成 backend-action。
    #   那是**上游落后**这个真信号（正是 `U-dead-event` 存在的意义），
    #   不是审计逻辑错。所以在落后配置下不要求 `ok`，而是要求这条判定
    #   **指向契约新增的那一个事件**。
    from bridge import staleness as _staleness  # noqa: E402

    _stale = _staleness.probe()["stale"]
    if _stale:
        print("  （当前上游落后于契约：合法地会出现 U-dead-event）")
        check("★ 落后配置下，判定**解释得通**（指向契约新增的事件）",
              all(i.id == "U-dead-event" for i in a.issues)
              or a.verdict == "ok",
              f"{a.verdict}: {sorted(ids(a))}")
    else:
        check(f"真实 spec（{real['spec_version']}，{len(real['events'])} 事件）可审",
              a.verdict == "ok", f"{a.verdict}: {sorted(ids(a))}")
    check("真实 spec 自洽（无 backend breaking）",
          not [i for i in a.issues if i.owner == "backend" and i.severity == "breaking"],
          str([i.title for i in a.issues if i.owner == "backend"]))
    check("真实 spec 带上契约版本来源",
          real["implements_contract_version_source"] in ("upstream", "fallback"),
          real["implements_contract_version_source"])
    # 真实 spec 的分区必须与契约快照一致（gap_G2/G3 的回归防线）
    check("真实 spec 的上游阶段恰为 5 个",
          len(real["pipeline"]["upstream_phases"]) == 5,
          str(real["pipeline"]["upstream_phases"]))
    check("真实 spec 里 manifest 是自补门禁",
          real["pipeline"]["bridge_gate_steps"] == ["manifest"],
          str(real["pipeline"]["bridge_gate_steps"]))
    # 计数**从契约读**，不写死：上游加性新增事件时，契约会变而常数不会，
    # 那时红的是常数、不是接口（实测踩过：`verify_skipped` 让 33 → 34）。
    import json as _json
    import os as _os

    _cj = _os.path.join(ROOT, ".interface_contract", "interface-contract.json")
    _obs = {}
    if _os.path.isfile(_cj):
        _obs = (_json.load(open(_cj, encoding="utf-8"))
                .get("event_partition") or {}).get("observed") or {}
    _want_up = _obs.get("upstream_count")
    _want_fe = _obs.get("bridge_count")
    if _stale:
        print(f"  SKIP  真实 spec 事件分区 == 契约 {_want_up} + {_want_fe}"
              f"（上游落后，推导会少一个）")
        check("★ bridge 侧计数 == 契约（与上游新旧无关）",
              len(real["event_partition"]["frontend"]) == _want_fe,
              f"{len(real['event_partition']['frontend'])} vs {_want_fe}")
    else:
        check(f"真实 spec 事件分区 {_want_up} + {_want_fe}",
              len(real["event_partition"]["upstream"]) == _want_up
              and len(real["event_partition"]["frontend"]) == _want_fe,
              f"{len(real['event_partition']['upstream'])}+"
              f"{len(real['event_partition']['frontend'])}")
except Exception as e:  # noqa: BLE001
    check("真实 spec 可审", False, f"{type(e).__name__}: {e}")


# ============================================================
print("\n" + "=" * 74)
print("断言检查")
print("=" * 74)
failed = [n for n, ok in checks if not ok]
print(f"通过 {len(checks) - len(failed)}/{len(checks)}")
if failed:
    print("失败: " + "; ".join(failed))
raise SystemExit(1 if failed else 0)
