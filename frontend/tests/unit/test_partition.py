"""把三条分区与版本轴钉在 `.interface_contract/` 的实测快照上。

为什么值得单测
--------------
分区是「哪些东西属上游」的判据，而**归因指错人**正是契约记的三处缺口的共同
根因（G1/G2/G3）。分区一旦静默漂掉：

- 事件分区少了 → bridge 自产事件被当上游事件上报，凭空 21 条 `P-event-gone-upstream`；
- 阶段分区把 `manifest` 算成上游 → 让后端去恢复一个它从未拥有的阶段；
- 端点分区把 bridge 自己的 `/api/*` 算成上游 → 11 条 `P-endpoint-missing` 诬告后端。

三种都不会让界面报错，只会让"该谁改"指错人。所以这里逐项钉死，
并**与契约记录的实测值比对**（契约 `event_partition.observed` /
`phases_partition.upstream_pipeline_phases`）。

运行：python tests/unit/test_partition.py
"""

import io
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401

from bridge import partition as P  # noqa: E402

checks: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))


CONTRACT_JSON = os.path.join(ROOT, ".interface_contract", "interface-contract.json")
C = json.load(io.open(CONTRACT_JSON, encoding="utf-8"))

import bridge.bootstrap as bootstrap  # noqa: E402

bootstrap.install()
from bridge.spec import build_spec, event_kinds, pipeline_stages  # noqa: E402


# ============================================================
print("=" * 74)
print("[1] 事件分区：上游 + bridge，两者不相交，且与**契约声明**一致")
print("=" * 74)
ep = P.event_partition()
obs = C["event_partition"]["observed"]
snap = P.recorded_snapshot()

# ★ 期望值**从契约读**，不写死。
#   实测教训：上游按规矩加性新增了一个事件（`verify_skipped`），契约升到
#   `34 = 13 + 21` —— 而红的是写死的常数，不是接口。
#   **写死的期望值会把"契约更新"误报成"接口回归"。**
check("契约快照是从契约 JSON 读到的（不是写死的常量）",
      snap["source"] == "contract", snap["source"])
check("离线回退表与契约一致（回退不许给出不同答案）",
      set(P.CONTRACT_FALLBACK_UPSTREAM_EVENTS) == set(snap["upstream_events"])
      and P.CONTRACT_FALLBACK_TOTAL_EVENTS == snap["total_events"],
      f"回退={len(P.CONTRACT_FALLBACK_UPSTREAM_EVENTS)}/"
      f"{P.CONTRACT_FALLBACK_TOTAL_EVENTS} "
      f"契约={len(snap['upstream_events'])}/{snap['total_events']}")

# ★ 推导 vs 契约：**只在当前上游与契约同步时**才有可比性。
#   自带副本是旧的（少一个事件），那时两边必然不等 ——
#   那是"你这份上游落后于契约"这个**真实且有用**的信号，
#   但它不是分区逻辑的缺陷，所以这里按配置 SKIP（由 doctor/诊断去报）。
from bridge import staleness as _staleness  # noqa: E402

_stale = _staleness.probe()["stale"]
if _stale:
    missing = sorted(set(snap["upstream_events"]) - set(ep["upstream"]))
    print(f"  SKIP  推导 == 契约（当前上游落后，契约声明比它多 {missing}）")
    print("       → 设 AGENT_BACKEND_DIR 指向真上游即可验这一条")
    check("★ 落后的差集**正是**契约新增的那一个（不是别的漂移）",
          missing == ["verify_skipped"], str(missing))
else:
    check("上游事件数 == 契约 observed.upstream_count",
          len(ep["upstream"]) == obs["upstream_count"],
          f"推导={len(ep['upstream'])} 契约={obs['upstream_count']}")
    check("总数 == 契约 observed.union_count",
          ep["total"] == obs["union_count"],
          f"推导={ep['total']} 契约={obs['union_count']}")
    check("上游事件名单与契约逐条一致",
          ep["upstream"] == sorted(obs["upstream_kinds"]),
          f"推导={ep['upstream']}")

# 下面这些与"上游新旧"无关，任何配置下都必须成立
check("bridge 事件数 == 契约 observed.bridge_count",
      len(ep["frontend"]) == obs["bridge_count"],
      f"推导={len(ep['frontend'])} 契约={obs['bridge_count']}")
check("重叠数 == 契约 observed.overlap（0）",
      len(ep["overlap"]) == obs["overlap"] == 0, str(ep["overlap"]))
check("★ 两侧集合确实不相交", not ep["overlap"])

# 内部自洽：推导总数 == 两侧之和（与契约版本无关的硬不变量）
check("推导总数 == 上游 + bridge",
      ep["total"] == len(ep["upstream"]) + len(ep["frontend"]),
      f"{ep['total']} vs {len(ep['upstream'])}+{len(ep['frontend'])}")
check("bridge 侧 == 契约声明（它由本仓库代码决定，与上游新旧无关）",
      set(ep["frontend"]) == set(obs["bridge_kinds"]),
      str(set(ep["frontend"]) ^ set(obs["bridge_kinds"])))

check("bridge 事件名单与契约逐条一致",
      ep["frontend"] == sorted(obs["bridge_kinds"]),
      f"差异={set(ep['frontend']) ^ set(obs['bridge_kinds'])}")

# 「推导 == 记录的快照」同样只在两者**可比**时成立：记录的快照来自契约，
# 而推导来自当前生效的上游。上游落后于契约时它们必然不等 ——
# 那是"上游落后"这个真信号，不是分区逻辑错。
if _stale:
    print("  SKIP  推导 == 快照常量（上游落后于契约，二者不可比）")
else:
    check("推导结果与模块内记录的快照一致",
          set(ep["upstream"]) == set(P.CONTRACT_RECORDED_UPSTREAM_EVENTS))
    check("总数常量与记录一致（且 == 契约）",
          ep["total"] == P.CONTRACT_RECORDED_TOTAL_EVENTS == obs["union_count"],
          f"{ep['total']} / {P.CONTRACT_RECORDED_TOTAL_EVENTS} / {obs['union_count']}")

# 判据必须来自「发出方」，不是硬编码名单
kinds = event_kinds()
tagged_up = sorted(k for k, t in kinds.items() if "upstream" in t)
check("分区判据来自 event_kinds 的 upstream 标记",
      tagged_up == ep["upstream"])
check("每个事件都恰好属于一侧",
      all((k in ep["upstream"]) ^ (k in ep["frontend"]) for k in kinds),
      str([k for k in kinds
           if not ((k in ep["upstream"]) ^ (k in ep["frontend"]))]))


# ============================================================
print("\n" + "=" * 74)
print("[2] 阶段分区：5 上游 + 1 自补门禁（gap_G3）")
print("=" * 74)
stages = pipeline_stages()
pp = P.phases_partition(stages)
check("上游阶段 == 契约 phases_partition.upstream_pipeline_phases",
      pp["upstream"] == C["phases_partition"]["upstream_pipeline_phases"],
      f"推导={pp['upstream']}")
check("上游阶段 == 契约快照常量",
      set(pp["upstream"]) == set(P.CONTRACT_RECORDED_UPSTREAM_PHASES))
check("★ 自补门禁恰好是 ['manifest']",
      pp["bridge_gate_steps"] == ["manifest"], str(pp["bridge_gate_steps"]))
check("★ 两者不重叠", not (set(pp["upstream"]) & set(pp["bridge_gate_steps"])))
check("★ 并集 == 前端要画的全部节点（6 个）",
      sorted(pp["upstream"] + pp["bridge_gate_steps"]) == sorted(pp["drawn"]),
      f"并集={sorted(pp['upstream'] + pp['bridge_gate_steps'])} 全部={sorted(pp['drawn'])}")
check("画出来的节点数 == 契约 bridge_spec_stages（6）",
      len(pp["drawn"]) == len(C["phases_partition"]["bridge_spec_stages"]) == 6,
      f"{len(pp['drawn'])}")
check("画的顺序与契约 bridge_spec_stages 一致",
      pp["drawn"] == C["phases_partition"]["bridge_spec_stages"], str(pp["drawn"]))
check("没有第三类节点（kind 只允许 phase / gate）",
      not pp["other"], str(pp["other"]))


# ============================================================
print("\n" + "=" * 74)
print("[3] 端点分区：bridge 自己的 14 个 vs 前端真要代理的 7 个上游面")
print("=" * 74)
spec = build_spec()
eps = spec["endpoints"]
epart = spec["endpoint_partition"]
# 统筹方契约测试用的就是这张表（FRONTEND_PROXIED_UPSTREAM，事实源 vite.config.ts）。
# 漏一条 = 上游删了它却没有任何判定指向上游（前端只会静默少一块）。
CONTRACT_PROXIED_UPSTREAM = [
    "/decisions", "/profile", "/skills", "/candidates",
    "/reflect", "/encode", "/run",
]
check("frontend 侧 == 全部端点（bridge 自己的，仅信息）",
      sorted(epart["frontend"]) == sorted(eps.values()),
      f"{len(epart['frontend'])} vs {len(eps)}")
check("★ proxied_upstream == vite.config.ts 的 proxy 表（7 条）",
      epart["proxied_upstream"] == sorted(CONTRACT_PROXIED_UPSTREAM),
      f"推导={epart['proxied_upstream']}")
check("★ upstream 侧 == 前端真要代理的 7 条",
      epart["upstream"] == sorted(CONTRACT_PROXIED_UPSTREAM),
      f"推导={epart['upstream']}")
check("★ upstream 侧是上游路径而非 /api/*",
      all(not p.startswith("/api/") for p in epart["upstream"]),
      str(epart["upstream"]))
check("★ bridge 转发的 3 条包含在 upstream 里（取并集，不是二选一）",
      set(P.UPSTREAM_ENDPOINT_MAP.values()) <= set(epart["upstream"]),
      str(sorted(P.UPSTREAM_ENDPOINT_MAP.values())))
check("mapped 只列真的在 ENDPOINTS 里的 key",
      set(epart["mapped"]) <= set(eps), str(sorted(epart["mapped"])))
check("没有把 bridge 自己的 /api/* 混进 upstream",
      not [p for p in epart["upstream"] if p.startswith("/api/")])

# 真·上游路由核对：声明的上游端点必须真的在上游 app 上
routes = set(P.upstream_routes())
check("拿得到上游真实路由（bootstrap 之后）", bool(routes), f"{len(routes)} 条")
if routes:
    gone = sorted(set(epart["upstream"]) - routes)
    check("★ 声明的上游端点都真的存在于上游 app", not gone, str(gone))
    print(f"      上游共 {len(routes)} 条路由；声明要代理 "
          f"{len(epart['upstream'])} 条：{epart['upstream']}")

# ★ 契约 v1.0.4 新增的 `endpoint_partition` 一节 —— 拿它记录的观测值对账。
#   这一节是**本工作流报上去的缺陷**（原 `source_mapping` 把 bridge 自己的
#   端点映射成 upstream_endpoints，会让上游对每条回 P-endpoint-missing）。
#   契约既已记下事实源，推导就必须与它逐条相同，否则漂了没人知道。
epart_contract = C.get("endpoint_partition")
check("契约 v1.0.4 有 endpoint_partition 一节", bool(epart_contract),
      "旧版契约没有这一节；缺了说明镜像没同步")
if epart_contract:
    sets = epart_contract["three_sets"]
    check("★ upstream 侧 == 契约 observed（逐条）",
          epart["upstream"] == sorted(sets["upstream_proxied"]["observed"]),
          f"推导={epart['upstream']} 契约={sorted(sets['upstream_proxied']['observed'])}")
    check("契约 observed_count == 7",
          sets["upstream_proxied"]["observed_count"] == 7)
    check("bridge 自己的端点 == 契约 observed_count（14）",
          len(epart["frontend"]) == sets["bridge_own"]["observed_count"] == 14,
          f"{len(epart['frontend'])}")
    check("契约写明 upstream 的事实源是 vite proxy 去掉 /api",
          "vite.config.ts" in sets["upstream_proxied"]["fact_source"]
          and "/api" in sets["upstream_proxied"]["fact_source"],
          sets["upstream_proxied"]["fact_source"])
    check("★ source_mapping 已修正为 endpoints -> frontend_endpoints（不再是 upstream）",
          "frontend_endpoints" in
          C["client_report_schema"]["source_mapping"]["bridge_AuditRequest"]["endpoints"],
          C["client_report_schema"]["source_mapping"]["bridge_AuditRequest"]["endpoints"])


# ============================================================
print("\n" + "=" * 74)
print("[4] 版本轴：能从上游读就读，读不到才回退并标来源")
print("=" * 74)
cv, cv_src = P.contract_version()
sv, sv_src = P.schema_version()
canon = C["version_axes"]["axes"]
check("契约版本来源是契约允许的取值",
      cv_src in ("upstream", "fallback"), cv_src)
check("schema 版本来源是契约允许的取值",
      sv_src in ("upstream", "absent"), sv_src)
check("spec 里的契约版本与 partition 的推导一致",
      spec["implements_contract_version"] == cv, spec["implements_contract_version"])
check("spec 里带上了来源（不标来源 = 冒充 backend 说话）",
      spec["implements_contract_version_source"] == cv_src,
      spec["implements_contract_version_source"])
check("★ 来源是 upstream 时，值必须等于上游 CONTRACT_VERSION",
      cv_src != "upstream"
      or cv == str(__import__("core.contract", fromlist=["x"]).CONTRACT_VERSION),
      f"{cv} vs 上游")
from bridge.contract_vocab import CONTRACT_FALLBACK_VERSION  # noqa: E402

check("★ 用了回退值就必须标 fallback（不许声称 upstream）",
      cv != CONTRACT_FALLBACK_VERSION or cv_src == "fallback",
      f"值={cv} 来源={cv_src}")
check("★ 三条轴各自独立上报，没有被合并成一个字段",
      {"spec_version", "implements_contract_version", "schema_version"}
      <= set(spec),
      str(sorted(set(spec) & {"spec_version", "implements_contract_version",
                              "schema_version"})))
check("契约版本与 schema 版本的来源分开记录（各有各的主）",
      "schema_version_source" in spec
      and "implements_contract_version_source" in spec,
      f"cv_src={spec['implements_contract_version_source']} "
      f"sv_src={spec['schema_version_source']}")


# ============================================================
print("\n" + "=" * 74)
print("[5] 自检：推导结果与契约记录的快照一致")
print("=" * 74)
chk = P.check_against_contract()
# 自检"通不通过"取决于**当前上游是否与契约同步**：
#   同步 → 必须 ok；
#   落后 → 它**应该**报出"少 verify_skipped"，那是真信号（由 doctor 去说），
#          在单测里按配置分流，而不是让它变成默认红。
if _stale:
    print(f"  SKIP  check_against_contract 通过（上游落后，它本就该报出来）")
    print(f"        {chk['issues']}")
    check("★ 落后时它报的**正是**契约新增的那一个（不是别的漂移）",
          any("verify_skipped" in x for x in chk["issues"]), str(chk["issues"]))
else:
    check("★ check_against_contract 通过", chk["ok"], str(chk["issues"]))
check("自检结果里带上了事件分区", bool(chk["event_partition"]["upstream"]))
check("自检结果里带上了阶段分区", bool(chk["phases_partition"]["upstream"]))
check("自检结果里记录了依据（**从契约读的**快照，不是写死的 33）",
      chk["contract_recorded"]["total_events"] == obs["union_count"],
      f"自检={chk['contract_recorded']['total_events']} 契约={obs['union_count']}")
check("自检结果里带上了后端目录（便于定位）",
      bool(chk["backend_dir"]), chk["backend_dir"])

# 故意造一份错的分区，确认自检真的会红（否则"通过"没有任何意义）
import bridge.spec as spec_mod  # noqa: E402

orig_stages = spec_mod.pipeline_stages
try:
    spec_mod.pipeline_stages = lambda cal=None: (
        [{"id": s, "kind": "phase"} for s in P.CONTRACT_RECORDED_UPSTREAM_PHASES]
        + [{"id": "bogus", "kind": "phase"}]
    )
    bad = P.check_against_contract()
    check("★ 阶段分区错了自检会红（不是恒真）",
          bad["ok"] is False, str(bad["issues"])[:160])

    # 事件分区错了也要红：借 event_kinds 的 upstream 标记做手脚
    orig_kinds = spec_mod.event_kinds
    spec_mod.event_kinds = lambda: {**orig_kinds(), "invented_event": ["upstream"]}
    bad2 = P.check_against_contract()
    check("★ 事件分区错了自检会红",
          bad2["ok"] is False, str(bad2["issues"])[:160])
    spec_mod.event_kinds = orig_kinds
finally:
    spec_mod.pipeline_stages = orig_stages


# ============================================================
print("\n" + "=" * 74)
print("[6] build_spec 里的分区字段形状（前端据此渲染）")
print("=" * 74)
check("pipeline.stages 仍是 6 个（前端画 6 个节点，契约 [C] 组要求）",
      len(spec["pipeline"]["stages"]) == 6,
      str(len(spec["pipeline"]["stages"])))
check("pipeline.upstream_phases 是 5 个",
      len(spec["pipeline"]["upstream_phases"]) == 5)
check("pipeline.bridge_gate_steps 是 ['manifest']",
      spec["pipeline"]["bridge_gate_steps"] == ["manifest"])
check("endpoint_partition 四段齐备",
      set(spec["endpoint_partition"]) == {"upstream", "frontend", "mapped",
                                          "proxied_upstream"},
      str(sorted(spec["endpoint_partition"])))
check("event_partition 四段齐备",
      set(spec["event_partition"]) == {"upstream", "frontend", "total", "overlap"},
      str(sorted(spec["event_partition"])))
check("mapped 只列真的在 ENDPOINTS 里的 key",
      set(spec["endpoint_partition"]["mapped"]) <= set(spec["endpoints"]),
      str(sorted(spec["endpoint_partition"]["mapped"])))


# ============================================================
print("\n" + "=" * 74)
print("断言检查")
print("=" * 74)
failed = [n for n, ok in checks if not ok]
print(f"通过 {len(checks) - len(failed)}/{len(checks)}")
if failed:
    print("失败: " + "; ".join(failed))
raise SystemExit(1 if failed else 0)
