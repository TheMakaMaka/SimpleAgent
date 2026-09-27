"""把契约词汇表钉在 `.interface_contract/` 上。

为什么值得单测
--------------
`bridge/contract_vocab.py` 是**契约的镜像**，不是契约本身。镜像会漂：

- 统筹方改了主本的词表（加一个归属值、把某条改判）→ 镜像不动就静默不一致；
- 镜像被人"顺手优化"（把 `degraded` 写成 `warn`、把 `both` 去掉）→
  归属判定就指错人，而**没有任何测试会红**。

所以这里**直接读契约的 JSON**、逐项比对。契约是唯一事实源，
本模块只是它的一份可执行副本。读到不一致就 FAIL——那是契约变更的信号，
不是"顺手改一下词表"的理由（契约 README §3：镜像只读，改动走统筹方）。

运行：python tests/unit/test_contract_vocab.py
"""

import io
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401

from bridge.contract_vocab import (  # noqa: E402
    CONTRACT_FALLBACK_VERSION,
    NON_BLOCKING_SEVERITIES,
    OWNERS,
    REATTRIBUTED,
    REATTRIBUTED_KEEP_BACKEND,
    SEVERITIES,
    SEVERITY_LEGACY,
    VERDICTS,
    owner_of,
    severity_of,
    verdict_for,
)

checks: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))


CONTRACT_JSON = os.path.join(ROOT, ".interface_contract", "interface-contract.json")
if not os.path.isfile(CONTRACT_JSON):
    check("找得到契约主本镜像", False, CONTRACT_JSON)
    raise SystemExit(1)

C = json.load(io.open(CONTRACT_JSON, encoding="utf-8"))
print(f"契约版本：{C['contract']['version']}  （{CONTRACT_JSON}）")


# ============================================================
print("\n" + "=" * 74)
print("[1] 归属词表 == 契约 owner_vocabulary（4 值）")
print("=" * 74)
want_owners = list(C["owner_vocabulary"]["values"])
check("归属值集合完全一致", set(OWNERS) == set(want_owners),
      f"契约={want_owners} 镜像={sorted(OWNERS)}")
check("归属值个数 == 4", len(OWNERS) == 4, str(len(OWNERS)))
check("每个归属都带（中文名, 该谁改）",
      all(isinstance(v, tuple) and len(v) == 2 and all(v) for v in OWNERS.values()))
check("★ both 存在（bridge 原先缺这个值）", "both" in OWNERS)
check("★ ops 存在", "ops" in OWNERS)
# 边界定义：bridge/ 属于 frontend。镜像的 frontend 建议里必须说到 bridge。
check("frontend 的行动指引点明 bridge/ 也归它",
      "bridge" in OWNERS["frontend"][1], OWNERS["frontend"][1])
check("backend 的行动指引指向 SimpleAgent2_Cycle",
      "SimpleAgent2_Cycle" in OWNERS["backend"][1], OWNERS["backend"][1])


# ============================================================
print("\n" + "=" * 74)
print("[2] 严重度词表 == 契约 severity_vocabulary（3 档）")
print("=" * 74)
want_sev = list(C["severity_vocabulary"]["values"])
check("严重度集合完全一致", set(SEVERITIES) == set(want_sev),
      f"契约={want_sev} 镜像={sorted(SEVERITIES)}")
check("严重度 == {breaking, degraded, info}",
      set(SEVERITIES) == {"breaking", "degraded", "info"}, str(sorted(SEVERITIES)))

# legacy 映射取自契约的 source_mapping.bridge
sm = C["severity_vocabulary"]["source_mapping"]["bridge"]
want_legacy = {k: v for k, v in sm.items() if k != "(none)"}
check("legacy 映射与契约 source_mapping 一致",
      SEVERITY_LEGACY == want_legacy, f"契约={want_legacy} 镜像={SEVERITY_LEGACY}")
check("fail -> breaking", SEVERITY_LEGACY.get("fail") == "breaking")
check("warn -> degraded", SEVERITY_LEGACY.get("warn") == "degraded")
check("(none) -> info", sm.get("(none)") == "info", sm.get("(none)"))

# ★ 本契约最重要的一条纪律：info 不参与 verdict
check("★ 只有 info 不参与 verdict",
      NON_BLOCKING_SEVERITIES == frozenset({"info"}), str(NON_BLOCKING_SEVERITIES))
check("契约明写 info 不参与 verdict",
      "不参与" in C["severity_vocabulary"]["values"]["info"]
      and "verdict" in C["severity_vocabulary"]["values"]["info"],
      C["severity_vocabulary"]["values"]["info"])


# ============================================================
print("\n" + "=" * 74)
print("[3] 结论词表 == 契约 verdict_vocabulary（6 值）")
print("=" * 74)
want_verdicts = C["verdict_vocabulary"]["values"]
check("结论集合完全一致", set(VERDICTS) == set(want_verdicts),
      f"契约={want_verdicts} 镜像={sorted(VERDICTS)}")
check("结论值个数 == 6", len(VERDICTS) == 6, str(len(VERDICTS)))
check("★ ops-action 存在", "ops-action" in VERDICTS)
check("★ need-negotiation 存在", "need-negotiation" in VERDICTS)
check("★ multi-action 存在", "multi-action" in VERDICTS)
check("bridge 旧结论名已弃用（backend_contract 不在词表里）",
      "backend_contract" not in VERDICTS)


# ============================================================
print("\n" + "=" * 74)
print("[4] verdict_for：归属集合 → 结论（含 ops 优先）")
print("=" * 74)
check("空集 → ok", verdict_for(set()) == "ok", verdict_for(set()))
check("{ops} → ops-action", verdict_for({"ops"}) == "ops-action")
check("{backend} → backend-action", verdict_for({"backend"}) == "backend-action")
check("{frontend} → frontend-action", verdict_for({"frontend"}) == "frontend-action")
check("{both} → need-negotiation", verdict_for({"both"}) == "need-negotiation")
check("{backend,frontend} → multi-action",
      verdict_for({"backend", "frontend"}) == "multi-action")
# ★ ops 优先：环境没弄好，后面判什么都没意义
check("★ {ops,frontend} → ops-action（ops 优先）",
      verdict_for({"ops", "frontend"}) == "ops-action",
      verdict_for({"ops", "frontend"}))
check("★ {ops,backend,both} → ops-action（ops 压过 both 协商）",
      verdict_for({"ops", "backend", "both"}) == "ops-action",
      verdict_for({"ops", "backend", "both"}))
check("★ both 参与且无 ops → need-negotiation（协商优先于单侧）",
      verdict_for({"both", "frontend"}) == "need-negotiation",
      verdict_for({"both", "frontend"}))
check("返回值永远是契约 6 值之一",
      all(verdict_for({o}) in VERDICTS for o in OWNERS))


# ============================================================
print("\n" + "=" * 74)
print("[5] 改判表 == 契约 rule_crosswalk（逐条比对）")
print("=" * 74)
# 契约里这一段在 1.0.3 里被截断过（字段名不全），两种键名都容忍
cross = C["rule_crosswalk"]
raw = (cross.get("bridge_backend_prefixed_reclassified")
       or cross.get("bridge_backend_prefixed_reclass")
       or [])
check("契约里能取到改判表", bool(raw), str(list(cross))[:120])

if raw:
    want_map: dict[str, tuple[str, str]] = {}
    for row in raw:
        bid = row.get("bridge_id") or row.get("id")
        owner = row.get("unified_owner") or row.get("owner")
        sev = row.get("severity") or row.get("unified_severity")
        # ★ 契约 JSON 这一格实测是 `SPLIT(见 note)`（带括号说明），
        #   而镜像里存哨兵 `SPLIT`。按**前缀**归一 —— 全等比较会因为
        #   统筹方在括号里补一句说明就误报漂移（这个坑已实测踩到）。
        if owner and str(owner).strip().upper().startswith("SPLIT"):
            owner = "SPLIT"
        if bid:
            want_map[bid] = (owner, sev)

    check("改判表条数一致（11 条）",
          len(REATTRIBUTED) == len(want_map) == 11,
          f"契约={len(want_map)} 镜像={len(REATTRIBUTED)}")

    # ★ v1.0.4 修正：unified_owner 里的哨兵值已是**裸 `SPLIT`**（说明移入 note）。
    #   本工作流报过"`SPLIT(见 note)` 与散文的 `SPLIT（按事件来源）` 不是同一字符串，
    #   消费方得猜括号"。这条断言把"修正确实落地"钉住 —— 一旦回退成带括号的形态，
    #   它就会红（而不是靠 `is_split()` 的前缀容错悄悄盖过去）。
    raw_split = [row for row in raw
                 if str(row.get("unified_owner") or row.get("owner") or "")
                 .strip().upper().startswith("SPLIT")]
    check("契约里确有 SPLIT 条目", len(raw_split) == 1, str(len(raw_split)))
    check("★ 哨兵值是裸 `SPLIT`（v1.0.4 已修正，说明移入 note）",
          all(str(r.get("unified_owner") or r.get("owner")).strip() == "SPLIT"
              for r in raw_split),
          str([r.get("unified_owner") or r.get("owner") for r in raw_split]))

    mism = {k: (want_map.get(k), REATTRIBUTED.get(k))
            for k in set(want_map) | set(REATTRIBUTED)
            if want_map.get(k) != REATTRIBUTED.get(k)}
    check("★ 每一条的归属与严重度都与契约一致", not mism, str(mism)[:400])

# 逐条钉住（即便契约那段读不全，这几条也不许漂）
WANT = {
    "backend.stage_mismatch":         ("frontend", "breaking"),
    "backend.phase_order_unreadable": ("backend", "breaking"),
    "backend.endpoint_missing":       ("frontend", "breaking"),
    "backend.endpoint_undeclared":    ("frontend", "degraded"),
    # ★ v1.0.7 统一为 degraded（原 breaking 与 upstream_only 的 U-dead-event 矛盾）
    "backend.dead_event":             ("SPLIT", "degraded"),
    "backend.uncalibrated_event":     ("frontend", "degraded"),
    "backend.override_broken":        ("frontend", "breaking"),
    "backend.no_events":              ("frontend", "breaking"),
    "backend.upstream_contract":      ("backend", "breaking"),
    "backend.hooks_not_installed":    ("frontend", "breaking"),
    "backend.version_lying":          ("frontend", "breaking"),
}
check("11 条 id 完全一致", set(REATTRIBUTED) == set(WANT),
      str(set(REATTRIBUTED) ^ set(WANT)))
bad = {k: (REATTRIBUTED.get(k), v) for k, v in WANT.items() if REATTRIBUTED.get(k) != v}
check("11 条的（归属, 严重度）逐条一致", not bad, str(bad))

# ★ 只有这两条真的指向上游
check("★ 保留为 backend 的只有 2 条",
      REATTRIBUTED_KEEP_BACKEND == {"backend.phase_order_unreadable",
                                    "backend.upstream_contract"},
      str(sorted(REATTRIBUTED_KEEP_BACKEND)))
check("保留 backend 的都在改判表里且确实是 backend",
      all(REATTRIBUTED[k][0] == "backend" for k in REATTRIBUTED_KEEP_BACKEND))
check("★ 8 条被改判为 frontend（bridge 的声明问题算前端）",
      sum(1 for v in REATTRIBUTED.values() if v[0] == "frontend") == 8,
      str(sum(1 for v in REATTRIBUTED.values() if v[0] == "frontend")))


# ============================================================
print("\n" + "=" * 74)
print("[6] owner_of / severity_of 的查表行为")
print("=" * 74)
check("owner_of('backend.endpoint_missing') == frontend",
      owner_of("backend.endpoint_missing") == "frontend")
check("owner_of('backend.upstream_contract') == backend",
      owner_of("backend.upstream_contract") == "backend")
# SPLIT 条目没有单一归属 → 落到默认值（调用方必须自己拆开，见 audit.py）
check("owner_of 对 SPLIT 条目落默认值（不返回 'SPLIT'）",
      owner_of("backend.dead_event") == "frontend",
      owner_of("backend.dead_event"))
check("表外 id 默认 frontend（bridge 自己的代码）",
      owner_of("frontend.something_new") == "frontend")
check("severity_of('backend.dead_event') == degraded（v1.0.7 统一）",
      severity_of("backend.dead_event") == "degraded",
      severity_of("backend.dead_event"))
check("severity_of 表外 id 默认 degraded",
      severity_of("frontend.something_new") == "degraded")
check("owner_of 结果永远是合法归属",
      all(owner_of(k) in OWNERS for k in REATTRIBUTED))


# ============================================================
print("\n" + "=" * 74)
print("[7] 版本轴：三条轴各有其主，回退值取自契约")
print("=" * 74)
axes = C["version_axes"]["axes"]
check("CONTRACT_VERSION 的 owner == backend",
      axes["CONTRACT_VERSION"]["owner"] == "backend")
check("SCHEMA_VERSION 的 owner == backend",
      axes["SCHEMA_VERSION"]["owner"] == "backend")
check("★ SPEC_VERSION 的 owner == frontend（不是 backend）",
      axes["SPEC_VERSION"]["owner"] == "frontend")
check("★ CONTRACT_FALLBACK_VERSION == 契约 observed_value",
      CONTRACT_FALLBACK_VERSION == axes["CONTRACT_VERSION"]["observed_value"],
      f"契约={axes['CONTRACT_VERSION']['observed_value']} "
      f"镜像={CONTRACT_FALLBACK_VERSION}")
check("契约明写三条轴不可合并",
      "不可合并" in C["version_axes"]["$comment"]
      or "不许合并" in C["version_axes"]["$comment"],
      C["version_axes"]["$comment"][:60])

# SPEC_VERSION 是**本仓库**的，不许出现在契约的 backend 轴里
from bridge.spec import SPEC_VERSION  # noqa: E402

check("bridge 的 SPEC_VERSION 与实际一致（1.0）", SPEC_VERSION == "1.0", SPEC_VERSION)
check("bridge 没有把 SPEC_VERSION 当成契约版本上报",
      "SPEC_VERSION" not in C["client_report_schema"]["canonical_fields"],
      "契约 canonical_fields 里不该有 SPEC_VERSION")


# ============================================================
print("\n" + "=" * 74)
print("[8] 契约 canonical 字段 == AuditRequest 能收下的字段")
print("=" * 74)
from bridge.agent_api import AuditRequest  # noqa: E402

declared = set(C["client_report_schema"]["canonical_fields"])
accepts = set(AuditRequest.model_fields)
missing = sorted(declared - accepts)
check("★ 契约声明的每个 canonical 字段都能被接收", not missing, str(missing))
check("★ ops 字段已接收（契约 v1.0.2 的第 9 个）", "ops" in accepts)
check("契约区分「声明」与「观测」",
      "declaration" in C["client_report_schema"]["two_kinds_of_field"]
      and "observation" in C["client_report_schema"]["two_kinds_of_field"])
check("absence_policy：字段全部可选", not AuditRequest.model_fields[
    "upstream_event_kinds"].is_required())


# ============================================================
print("\n" + "=" * 74)
print("[9] response_contract：warnings 与「消费方义务」（契约 v1.0.5）")
print("=" * 74)
rc = C.get("response_contract")
check("契约 v1.0.5 有 response_contract 一节", bool(rc),
      "旧版没有这一节；缺了说明镜像没同步")
if rc:
    w = rc["warnings"]
    check("warnings 声明为 list[str]", w["type"] == "list[str]", w["type"])
    check("★ additive：缺失时按 [] 处理", w["additive"] is True
          and w["absent_means"].startswith("缺失时按 [] 处理"), w["absent_means"][:40])
    # ★ 这条是**消费方义务**：只看 verdict 的消费方会看到 ok，从而看不到
    #   那条被传输层证伪的 ops 标志。所以必须同时展示 warnings。
    check("★ 写明了消费方义务（展示 verdict 也要展示 warnings）",
          "应当同时展示" in w["consumer_obligation"], w["consumer_obligation"][:60])
    check("义务的理由也写了（否则下一个人会以为可省）",
          "看不到" in w["consumer_obligation"], w["consumer_obligation"][-60:])

    check("ops 栏保留全部上报事实（含未参与判定的）",
          "全部" in rc["ops_column"]["meaning"], rc["ops_column"]["meaning"][:40])

    # 优先级澄清：收窄的是**输入**，不是优先级 —— frontend_not_built 仍判 ops-action
    pc = rc["priority_clarification"]
    check("★ 契约明确：优先级未被削弱（收窄输入而非优先级）",
          "不冲突" in pc["verdict"], pc["verdict"][:40])
    check("★ 举证：frontend_not_built 仍判 ops-action",
          "ops-action" in pc["proof"], pc["proof"][:60])

    # profile 新增项 == 实现里的常量（两处必须同一份名单）
    stale_decl = [s for s in rc.get("profile_additions", [])
                  if "ops_stale_by_transport" in s]
    check("契约 /profile 声明了 ops_stale_by_transport", bool(stale_decl),
          str(rc.get("profile_additions")))
    from bridge.audit import OPS_STALE_BY_TRANSPORT  # noqa: E402

    check("★ 实现里的「不驱动 verdict」清单 == 契约声明",
          OPS_STALE_BY_TRANSPORT == frozenset({"O-service-down"}),
          str(sorted(OPS_STALE_BY_TRANSPORT)))
    check("契约声明里列出的 code 就是它",
          all(c in " ".join(stale_decl) for c in OPS_STALE_BY_TRANSPORT),
          str(stale_decl))

# ★ 跨侧规则表（`upstream_only`）也必须与契约一致，且**优先读契约**。
#   这一节是 D2 加的：实测发生过一次"同一底层状况在两个 code 上级别不同"
#   （U-dead-event=degraded vs backend.dead_event=breaking），
#   读契约 + 比对回退表就能让这类漂移当场红。
print("\n" + "-" * 74)
print("跨侧规则表（rule_crosswalk.upstream_only）")
print("-" * 74)
from bridge import contract_vocab as CV2  # noqa: E402
from bridge.audit import UPSTREAM_RULES, DEVIATIONS  # noqa: E402

declared_up = {}
for row in cross.get("upstream_only") or []:
    if row.get("code") and row.get("owner") and row.get("severity"):
        declared_up[row["code"]] = (row["owner"], row["severity"])
check("契约里有 upstream_only 规则", len(declared_up) >= 20, str(len(declared_up)))

live = CV2.load_upstream_rules()
check("★ 实现优先从契约读跨侧规则", bool(live), f"{len(live)} 条")
check("★ 读到的与契约逐条一致",
      all(live.get(k) == v for k, v in declared_up.items()),
      str({k: (live.get(k), v) for k, v in declared_up.items()
           if live.get(k) != v})[:200])

# 离线回退表：必须与契约一致（只在镜像缺失时才用它）
bad_up = {k: (UPSTREAM_RULES.get(k), v) for k, v in UPSTREAM_RULES.items()
          if live.get(k) != v}
check("★ 离线回退表与契约逐条一致（回退不许给出不同答案）", not bad_up,
      str(bad_up)[:300])
check("★ 回退表覆盖了实现会产出的全部跨侧 code",
      set(UPSTREAM_RULES) >= {"P-phase-unknown", "P-version-behind",
                             "P-version-ahead", "P-event-unknown-to-frontend"},
      str(sorted(UPSTREAM_RULES)))

# ★ v1.0.7 的两处裁决，逐条钉住（回退表与契约都要对）
check("★ P-phase-unknown == both/degraded（v1.0.7 改判，本仓库曾记为偏离）",
      live.get("P-phase-unknown") == ("both", "degraded")
      and UPSTREAM_RULES.get("P-phase-unknown") == ("both", "degraded"),
      f"契约={live.get('P-phase-unknown')} 回退={UPSTREAM_RULES.get('P-phase-unknown')}")
check("★ U-dead-event == backend/degraded（v1.0.7 统一级别）",
      live.get("U-dead-event") == ("backend", "degraded"),
      str(live.get("U-dead-event")))
check("★ 声明偏离表为空（唯一那条已被契约采纳）", DEVIATIONS == {},
      str(sorted(DEVIATIONS)))

# ★ 消费方义务要求**前端真的展示**它 —— 光在后端产出不算履约。
#   所以这里跨语言核对：前端源码里确实取了 warnings。
print("\n" + "-" * 74)
print("消费方义务的前端一侧（跨语言核对）")
print("-" * 74)
front_audit = os.path.join(ROOT, "frontend", "src", "api", "audit.ts")
topbar = os.path.join(ROOT, "frontend", "src", "components", "TopBar.vue")
for path, label in ((front_audit, "api/audit.ts"), (topbar, "components/TopBar.vue")):
    check(f"前端 {label} 存在", os.path.isfile(path))
if os.path.isfile(front_audit) and os.path.isfile(topbar):
    fa = io.open(front_audit, encoding="utf-8").read()
    tb = io.open(topbar, encoding="utf-8").read()
    check("api/audit.ts 的响应类型带 warnings", "warnings: string[]" in fa)
    check("api/audit.ts 对缺失的 warnings 兜底成 []",
          "data.warnings = data.warnings ?? []" in fa)
    check("api/audit.ts 导出 auditWarnings()", "export function auditWarnings" in fa)
    check("★ TopBar 渲染 warnings（义务的落点）",
          "warnings" in tb and "auditWarnings" in tb)
    check("★ 徽标本身体现提示条数（否则「✓ 兼容」会盖住它）",
          "提示)" in tb or "提示）" in tb, "auditLabel 里应带提示条数")
    check("ops 栏也在界面上（判断环境问题不能只看 verdict）",
          "auditOps" in tb)


# ============================================================
print("\n" + "=" * 74)
print("断言检查")
print("=" * 74)
failed = [n for n, ok in checks if not ok]
print(f"通过 {len(checks) - len(failed)}/{len(checks)}")
if failed:
    print("失败: " + "; ".join(failed))
raise SystemExit(1 if failed else 0)
