"""对账入口的**职责切分**（架构清单 **A1a**）。

决定
----
保留两个入口，但把职责切开并各自声明，不再让它们对同一件事给两个答案：

| 入口 | 权威范围 | 明确**不**负责 |
|---|---|---|
| `POST /contract/check`（上游） | 跨侧对账：归属、严重度、结论、`both` 协商项 | 本地环境细节 |
| `POST /api/audit`（bridge） | 本地自检：bridge 声明 vs 实现 vs 环境 | **跨侧归属**（应引用上游 code） |

这个测试钉住三件事
------------------
1. `/api/audit` 的响应**自述**权威范围（字段可被断言）；
2. bridge 的**跨侧**归属**引用**上游 `code`，不另立判据
   —— 归属直接从契约 `rule_crosswalk` 取，镜像表只是离线回退；
3. **两个入口对同一跨侧不一致给出同一个 owner**。

第 3 条的离线形式在这里（拿契约当唯一判据比）；**在线**形式在
`tests/diagnostics/check_contract_report.py`（真打上游 `/contract/check` 对账）。

运行：python tests/unit/test_audit_authority.py
"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401

from bridge import contract_vocab as CV  # noqa: E402
from bridge.audit import (  # noqa: E402
    AUTHORITY, AUTHORITY_NOTE, DEVIATIONS, OWNERS, REATTRIBUTED,
    UPSTREAM_RULES, run as run_audit,
)

checks: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))


from core.cycle import PHASE_ORDER  # noqa: E402

REAL_STAGES = tuple(p.value for p in PHASE_ORDER)

spec = {
    "spec_version": "1.0",
    "implements_contract_version": "1.0",
    "implements_contract_version_source": "upstream",
    "schema_version": "1.0",
    "schema_version_source": "upstream",
    "pipeline": {
        "stages": [{"id": s, "kind": "phase"} for s in REAL_STAGES],
        "failure_phase": "failed",
        "upstream_phases": list(REAL_STAGES),
        "bridge_gate_steps": [],
    },
    "endpoints": {"spec": "/api/spec", "runs": "/api/runs"},
    "endpoint_partition": {"upstream": [], "frontend": ["/api/spec", "/api/runs"],
                           "mapped": {}, "proxied_upstream": []},
    "event_partition": {"upstream": ["a", "b", "c"], "frontend": [],
                        "total": 3, "overlap": []},
    "events": {e: {"label": e, "tone": "info", "panel": "t"} for e in ("a", "b", "c")},
    "statuses": {}, "tools": [], "ui": {},
    "diagnostics": {"event_count": 3, "uncalibrated_events": [],
                    "dead_calibrations": [], "override_file": None,
                    "errors": []},
}


def client(**over):
    c = {
        "spec_version": "1.0", "contract_version": "1.0", "schema_version": "1.0",
        "upstream_event_kinds": ["a", "b", "c"], "frontend_event_kinds": [],
        "phases": list(REAL_STAGES), "bridge_gate_steps": [],
        "frontend_endpoints": ["spec", "runs"], "upstream_endpoints": [],
    }
    c.update(over)
    return c


# ============================================================
print("=" * 74)
print("[1] `/api/audit` 自述权威范围（A1a 验收 1）")
print("=" * 74)
a = run_audit(spec, client())
d = a.to_dict()
check("响应含 authority 字段", "authority" in d, str(sorted(d))[:100])
check("★ authority 的值说明它是本地自检",
      d["authority"] == AUTHORITY == "local-self-check", d["authority"])
check("响应含 authority_note（说明跨侧该问谁）", bool(d.get("authority_note")))
check("★ note 里点名上游 `/contract/check` 是跨侧权威",
      "/contract/check" in AUTHORITY_NOTE, AUTHORITY_NOTE[:60])
check("note 里说明本入口只引用上游 code、不另立判据",
      "引用" in AUTHORITY_NOTE and "code" in AUTHORITY_NOTE)
check("markdown 里也自述了权威范围",
      AUTHORITY in a.to_markdown(), a.to_markdown()[:120])


# ============================================================
print("\n" + "=" * 74)
print("[2] 跨侧归属**引用**契约，而不是自行下结论（A1a 验收 2）")
print("=" * 74)
cw = CV.load_crosswalk()
check("读到了契约对账表", bool(cw), f"{len(cw)} 条")
check("契约对账表比镜像表更全（镜像只是离线回退）",
      len(cw) >= len(REATTRIBUTED), f"契约 {len(cw)} / 镜像 {len(REATTRIBUTED)}")

# ★ 镜像表必须与契约**逐条一致**，否则"回退"会给出与契约不同的答案
bad = {k: (v, (CV.owner_of(k), CV.severity_of(k)))
       for k, v in REATTRIBUTED.items()
       if v[0] != "SPLIT" and (CV.owner_of(k), CV.severity_of(k)) != v}
check("★ 镜像回退表与契约逐条一致", not bad, str(bad)[:200])

check("owner_of 现在从契约取（改契约即改判定）",
      CV.owner_of("frontend.orphan_events") == cw["frontend.orphan_events"]["owner"],
      CV.owner_of("frontend.orphan_events"))

# 上游 code：契约对账表按 **bridge_id** 索引，所以 code 要用 bridge_id 查
check("★ 有上游对应规则的判定取得到 code",
      CV.code_of("frontend.missing_events") == "P-event-unknown-to-frontend",
      CV.code_of("frontend.missing_events"))
check("★ code 是纯 code，不带契约那一列的限定语",
      " " not in CV.code_of("backend.upstream_contract")
      and CV.code_of("backend.upstream_contract") == "U-removed-surface",
      CV.code_of("backend.upstream_contract"))
check("契约写「无」时 code 为空（不是编一个）",
      CV.code_of("backend.endpoint_missing") == "",
      repr(CV.code_of("backend.endpoint_missing")))

# 每条 issue 都带 code（有就填，没有就空）
a2 = run_audit(spec, client(upstream_event_kinds=["a"]))
check("该场景确实产生了判定（否则下面的断言是空的）", bool(a2.issues), str(len(a2.issues)))
iss = a2.issues[0]
check("★ Issue 带 code 字段并进了 to_dict",
      "code" in iss.to_dict(), str(sorted(iss.to_dict())))
check("★ 跨侧判定的 id 就是契约的 rule code（同一件事只有一个名字）",
      iss.id == "P-event-unknown-to-frontend", f"id={iss.id}")


# ============================================================
print("\n" + "=" * 74)
print("[3] 跨侧判定：**没有**自造的 `backend.`/`frontend.` 名字（A1a 验收 2）")
print("=" * 74)
# 造一堆场景，把所有会出现的跨侧判定都逼出来。
# 注意 `client(**over)` 收的是**契约 canonical 字段名**（不是简写）。
scenarios = [
    ("一致", client()),
    ("缺上游事件", client(upstream_event_kinds=["a"])),
    ("孤儿事件", client(frontend_event_kinds=["ghost"])),
    ("漏画阶段", client(phases=["plan"])),
    ("未知阶段", client(phases=list(REAL_STAGES) + ["invented"])),
    ("契约版本缺失", client(contract_version="")),
    ("版本落后", client(contract_version="0.9")),
    ("版本领先", client(contract_version="9.9")),
]
seen: set[str] = set()
for name, c in scenarios:
    seen |= {i.id for i in run_audit(spec, c).issues}
seen |= {i.id for i in run_audit(spec, client(), routes={"/api/spec"}).issues}
seen |= {i.id for i in run_audit(spec, client(), frontend_built=False).issues}
seen |= {i.id for i in run_audit(spec, client(), service_reachable=False).issues}
seen |= {i.id for i in run_audit(
    {**spec, "diagnostics": {**spec["diagnostics"],
                             "dead_calibrations": ["ghost_event", "tool_call"]}},
    client()).issues}
seen |= {i.id for i in run_audit(spec, None).issues}   # 旧格式由 api 层加，这里只跑自审

# 「合法名字」只有两类：
#   (a) 契约的 rule code（`P-`/`U-`/`O-`）—— 契约定义过的判定
#   (b) `bridge.` 前缀 —— 契约**没有**定义、纯属本适配层自己的判定
# 再加上**历史遗留**：契约对账表按 bridge_id 索引的那 11 条 `backend.*`
# （统筹方明确采纳"id 保持稳定、归属查表"，见契约 CHANGELOG 1.0.3）。
LEGACY = set(REATTRIBUTED)
bad = sorted(
    i for i in seen
    if not (i.startswith(("P-", "U-", "O-", "bridge.")) or i in LEGACY)
)
check(f"跑出 {len(seen)} 种判定", len(seen) >= 10, str(sorted(seen)))
check("★ 没有自造的 backend./frontend. 跨侧名字（除契约索引的历史 11 条）",
      not bad, str(bad))
check("★ 每个跨侧判定要么是契约 code，要么是 bridge. 本地判定，要么是历史 id",
      all(i.startswith(("P-", "U-", "O-", "bridge.")) or i in LEGACY for i in seen),
      str(sorted(seen)))


# ============================================================
print("\n" + "=" * 74)
print("[4] ★ 两个入口对同一跨侧不一致给出**同一个 owner**（A1a 验收 3）")
print("=" * 74)
# 离线形式：契约是唯一判据，所以"bridge 给出的归属"必须等于"契约记的归属"。
# 在线形式见 tests/diagnostics/check_contract_report.py（真打上游 /contract/check）。
by_code: dict[str, tuple[str, str]] = {}
for name, c in scenarios:
    for i in run_audit(spec, c).issues:
        if i.id in LEGACY:      # 历史 bridge_id：归属查契约对账表
            continue
        if i.id in UPSTREAM_RULES or i.id in DEVIATIONS:
            by_code.setdefault(i.id, (i.owner, i.severity))

check("覆盖到了多条契约规则", len(by_code) >= 6, str(sorted(by_code)))
mism = {k: (v, (DEVIATIONS.get(k) or UPSTREAM_RULES.get(k))[:2])
        for k, v in by_code.items()
        if v != tuple((DEVIATIONS.get(k) or UPSTREAM_RULES.get(k))[:2])}
check("★ 每条跨侧判定的 (owner, severity) 都等于契约（或已声明偏离）",
      not mism, str(mism)[:300])
check("★ 声明偏离表现在是**空**的（唯一那条已被契约 v1.0.7 采纳）",
      DEVIATIONS == {}, str(sorted(DEVIATIONS)))

# 逐条正面校验几个代表（含"bridge/ 的声明问题算前端"这条边界）
cases = [
    ("P-event-unknown-to-frontend", "frontend", "degraded"),
    ("P-event-gone-upstream", "both", "degraded"),
    ("P-phase-missing", "frontend", "degraded"),
    ("P-endpoint-missing", "backend", "breaking"),
    ("P-endpoint-added", "frontend", "info"),
    ("P-missing-field", "frontend", "info"),
    ("P-version-behind", "frontend", "degraded"),
    ("P-version-ahead", "backend", "breaking"),    # ★ 方向不同，归属不同
    ("P-version-unparsable", "both", "degraded"),
]
for code, want_owner, want_sev in cases:
    got = UPSTREAM_RULES.get(code)
    check(f"{code} == ({want_owner}, {want_sev})",
          got == (want_owner, want_sev), str(got))

# 历史 11 条仍按契约对账表判归属（含"bridge/ 的声明问题算前端"）
for bid, want in [("backend.endpoint_missing", "frontend"),
                  ("backend.upstream_contract", "backend")]:
    check(f"{bid} 归属 == {want}", CV.owner_of(bid) == want, CV.owner_of(bid))

check("归属值都合法",
      all(i.owner in OWNERS
          for i in run_audit(spec, client(upstream_event_kinds=["a"])).issues))


# ============================================================
print("\n" + "=" * 74)
print("断言检查")
print("=" * 74)
failed = [n for n, ok in checks if not ok]
print(f"通过 {len(checks) - len(failed)}/{len(checks)}")
if failed:
    print("失败: " + "; ".join(failed))
raise SystemExit(1 if failed else 0)
