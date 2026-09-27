"""契约相关的分区推导：事件、阶段、端点各分两侧。

为什么分区要**推导**而不是硬编码
--------------------------------
契约（`.interface_contract/interface-contract.json`）定义了三条分区规则，
但它们都指向**上游的事实源**，所以可以从代码里算出来：

| 分区 | 事实源 | 契约字段 |
|---|---|---|
| 事件 属上游 | 上游 `core/coding_cycle.py` 的 `_emit` 调用点 | `event_partition.origin_rule` |
| 阶段 属上游 | 上游 `core/cycle.PHASE_ORDER` | `phases_partition.upstream_pipeline_phases` |
| 端点 属上游 | 上游 `main.py` 路由 | `fact_sources.endpoints_upstream` |

硬编码一份名单一定会漂；而且漂了以后**归因会指错人** ——
契约里 G2/G3 两个缺口就是这么来的（把 bridge 自己补的东西当成上游的上报，
于是结论变成"让后端去恢复一个它从未拥有的东西"）。

所以这里全部从事实源推导，并用契约记录的观测值做**校验**（见 `check_against_contract`）。
"""

import os
import re

from . import paths

# ============================================================
# 契约记录的快照（**校验**用，不是运行时事实源）
#
# ★ 这三个值**从契约 JSON 读**，不再写死。
#
# 为什么（一次真实的假警报）：它们原先硬编码成 12 / 5 / 33。
# 上游按规矩**加性新增**了一个事件（`verify_skipped`），契约跟着升到
# `34 = 13 + 21` —— 而红的是**我的常数**，不是上游的接口。
# **写死的期望值会把"契约更新"误报成"接口回归"。**
#
# 与 `contract_vocab` 的 `owner_of()` / `upstream_rule()` 是同一个模式：
# 能读契约就读契约，读不到才回退到下面这份离线快照
# （`bridge/` 可能被单独拿走用，那时没有契约镜像）。
# ============================================================
#: 读不到契约时的**离线回退**快照。值必须与契约一致，
#: `tests/unit/test_partition.py` 断言回退表与契约逐条相同。
CONTRACT_FALLBACK_UPSTREAM_EVENTS = frozenset({
    "cycle_end", "cycle_start", "decision_action", "decision_notified",
    "decision_opened", "lint", "manifest", "plan", "rollback_denied",
    "syntax", "task_result", "verify",
    # `verify_skipped` 是上游 v1.1 加性新增的（`core/contract.py` 的
    # `EventSpec(..., since="1.1")`）：把「有验证命令、却没有 pipeline，
    # 于是验证回流整块被跳过」变成显式事实。契约随之 33 → 34。
    "verify_skipped",
})
CONTRACT_FALLBACK_UPSTREAM_PHASES = frozenset(
    {"plan", "write", "check", "verify", "record"}
)
CONTRACT_FALLBACK_TOTAL_EVENTS = 34

#: 契约主本镜像（与 `contract_vocab.CONTRACT_JSON` 同一处）
CONTRACT_JSON = os.path.join(paths.ROOT, ".interface_contract",
                             "interface-contract.json")

_recorded: dict | None = None


def recorded_snapshot(reload: bool = False) -> dict:
    """契约 `event_partition.observed` + `phases_partition` 记录的观测值。

    读不到就回退到 `CONTRACT_FALLBACK_*`。返回
    `{upstream_events, upstream_phases, total_events, source}`。
    """
    global _recorded
    if _recorded is not None and not reload:
        return _recorded

    out = {
        "upstream_events": CONTRACT_FALLBACK_UPSTREAM_EVENTS,
        "upstream_phases": CONTRACT_FALLBACK_UPSTREAM_PHASES,
        "total_events": CONTRACT_FALLBACK_TOTAL_EVENTS,
        "source": "fallback",
    }
    try:
        import json

        with open(CONTRACT_JSON, encoding="utf-8") as f:
            data = json.load(f)
        obs = (data.get("event_partition") or {}).get("observed") or {}
        ev = obs.get("upstream_kinds")
        tot = obs.get("union_count")
        ph = (data.get("phases_partition") or {}).get("upstream_pipeline_phases")
        if ev and tot:
            out = {
                "upstream_events": frozenset(ev),
                "upstream_phases": frozenset(ph or CONTRACT_FALLBACK_UPSTREAM_PHASES),
                "total_events": int(tot),
                "source": "contract",
            }
    except Exception:  # noqa: BLE001
        pass
    _recorded = out
    return out


#: 兼容旧名（外部/测试可能还在 import）。**模块加载时求值一次**，
#: 读不到契约时自动回退 —— 语义与 `recorded_snapshot()` 一致。
CONTRACT_RECORDED_UPSTREAM_EVENTS = recorded_snapshot()["upstream_events"]
CONTRACT_RECORDED_UPSTREAM_PHASES = recorded_snapshot()["upstream_phases"]
CONTRACT_RECORDED_TOTAL_EVENTS = recorded_snapshot()["total_events"]


# ============================================================
# 事件分区
# ============================================================
def event_partition() -> dict:
    """按**发出方**把事件分到两侧。

    判据就是契约的 `origin_rule`：属上游当且仅当它由上游
    `core/coding_cycle.py` 的 `_emit` 发出（`spec.event_kinds()` 的 `upstream` 标记）。
    """
    from .spec import event_kinds

    kinds = event_kinds()
    upstream = sorted(k for k, tags in kinds.items() if "upstream" in tags)
    frontend = sorted(k for k, tags in kinds.items() if "upstream" not in tags)
    overlap = sorted(set(upstream) & set(frontend))   # 按定义恒空，留作断言
    return {
        "upstream": upstream,
        "frontend": frontend,
        "total": len(kinds),
        "overlap": overlap,
    }


# ============================================================
# 阶段分区
# ============================================================
def phases_partition(stages: list[dict]) -> dict:
    """上游阶段 vs bridge 自补的门禁节点。

    ★ 这是契约 gap_G3：`manifest` 是 bridge 在 write 与 check 之间**自补**的
    门禁节点，上游没有。若把它当 `phases` 上报，上游会报
    `P-phase-unknown(breaking, owner=backend)` —— **让后端去恢复一个它从未拥有的阶段**。
    """
    upstream = [s["id"] for s in stages if s.get("kind") == "phase"]
    gate = [s["id"] for s in stages if s.get("kind") == "gate"]
    other = [s["id"] for s in stages if s.get("kind") not in ("phase", "gate")]
    return {
        "upstream": upstream,
        "bridge_gate_steps": gate,
        "other": other,
        "drawn": [s["id"] for s in stages],
    }


# ============================================================
# 端点分区
# ============================================================
#: bridge 重新暴露了哪些**上游** HTTP 能力（key = bridge 端点 key，value = 上游路径）。
#:
#: 契约 `client_report_schema.canonical_fields.upstream_endpoints` 的定义是
#: 「前端要代理的**上游**端点」。bridge 并不真的反向代理（它在同进程里调用上游），
#: 但它的这几个 `/api/*` 确实是上游同名能力的对外入口——声明它们才有意义：
#: 上游若删掉 `/profile`，bridge 的 `/api/profile` 就失去依据，那是**后端破约**。
#:
#: **只列真的对应的。** bridge 独有的（spec / audit / health / run* / workspace*）
#: 一律不列——把它们混进 upstream 就是 G3 的同型错误。
UPSTREAM_ENDPOINT_MAP: dict[str, str] = {
    "profile": "/profile",
    "reflect": "/reflect",
    "decisions": "/decisions",
}

#: 前端 dev server 的代理配置——**它才是"前端要代理的上游端点"的事实源**。
#:
#: ★ 这一点花了代价才弄清：只从 `bridge/spec.py` 的 `ENDPOINTS` 反推，
#: 只能得到 3 条（bridge 显式转发的那些）。但 `vite.config.ts` 的 proxy 表
#: 直接代理了 **7** 条上游路径给上游（`/skills` `/candidates` `/encode` `/run`
#: 不走 bridge）。那 4 条同样是前端**真实依赖**的上游面：上游一删，
#: 前端就静默少一块，而**没有任何一条判定会指向上游**。
#:
#: 统筹方的契约测试用的正是这张表（`FRONTEND_PROXIED_UPSTREAM`），
#: 事实源标注为 `frontend/vite.config.ts`。所以这里也必须以它为准。
#:
#: 解析失败（文件不在 / 格式变了）时返回空——**不猜**，只降级。
VITE_CONFIG = os.path.join(paths.FRONTEND_DIR, "vite.config.ts")

#: proxy 表里 bridge 自己的前缀，**不是**上游路径
_BRIDGE_PREFIX = "/api"


def proxied_upstream() -> list[str]:
    """从 `vite.config.ts` 的 proxy 表里取出**上游**路径。

    只认数组字面量里的字符串——不做通用 TS 解析（那会引入一个解析器依赖，
    而且格式一变就会静默解析出错误结果）。取不到就返回空。
    """
    try:
        with open(VITE_CONFIG, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return []

    # 找 proxy 的那个数组：`Object.fromEntries(\n  [ ... ].map(`
    m = re.search(r"Object\.fromEntries\(\s*\[(.*?)\]\s*\.map", text, re.S)
    if not m:
        return []
    found = re.findall(r"'([^']+)'", m.group(1))
    return sorted(p for p in found if p.startswith("/") and p != _BRIDGE_PREFIX)


def endpoint_partition(endpoints: dict[str, str]) -> dict:
    """bridge 自己的端点 vs 前端要代理的上游端点。

    `upstream` = bridge 转发的（`UPSTREAM_ENDPOINT_MAP`）∪ 前端 dev server
    直接代理的（`vite.config.ts`）。两个来源都是真依赖，取并集才不丢。
    """
    mapped = {k: v for k, v in UPSTREAM_ENDPOINT_MAP.items() if k in endpoints}
    proxied = proxied_upstream()
    upstream = sorted(set(mapped.values()) | set(proxied))
    return {
        "upstream": upstream,
        "frontend": sorted(endpoints.values()),
        "mapped": mapped,
        "proxied_upstream": proxied,
    }


def upstream_routes() -> list[str]:
    """上游真实路由（从上游 app 推导）。拿不到就返回空。

    这是 `endpoint_partition.upstream` 的**校验**依据：
    bridge 声明的上游端点必须真的在上游 app 上。
    """
    try:
        from main import app as upstream_app  # 上游 main.py，bootstrap 已放好 sys.path

        out = set()
        for r in getattr(upstream_app, "routes", []):
            p = getattr(r, "path", "")
            if p and not p.startswith(("/docs", "/openapi", "/redoc")):
                out.add(p)
        return sorted(out)
    except Exception:
        return []


# ============================================================
# 契约版本
# ============================================================
def contract_version() -> tuple[str, str]:
    """上游 `CONTRACT_VERSION` 的值与**来源**。

    ★ 契约 `version_axes.CONTRACT_VERSION.owner` = **backend**。
    bridge 抄一份就会说谎——所以能读上游就读上游，读不到才回退，
    并且**必须把来源一起上报**（见 `spec.build_spec()` 的
    `implements_contract_version_source`）。

    读不到时的行为：回退值 + source=`fallback`。此时上游侧会走
    `P-version-unparsable`(owner=both) 或降级为 `P-missing-field`(info)——
    两条都是契约允许的降级路径，比 bridge 假装知道要好。
    """
    try:
        from core.contract import CONTRACT_VERSION  # 上游 core/contract.py

        value = str(CONTRACT_VERSION).strip()
        if value:
            return value, "upstream"
    except Exception:
        pass
    from .contract_vocab import CONTRACT_FALLBACK_VERSION

    return CONTRACT_FALLBACK_VERSION, "fallback"


def schema_version() -> tuple[str, str]:
    """上游 `SCHEMA_VERSION`（快照结构版本）。拿不到就留空。"""
    try:
        from core.compress import SCHEMA_VERSION  # type: ignore

        value = str(SCHEMA_VERSION).strip()
        if value:
            return value, "upstream"
    except Exception:
        pass
    return "", "absent"


# ============================================================
# 自检
# ============================================================
def check_against_contract() -> dict:
    """拿契约记录的观测值校验推导结果。

    不抛异常——调用方（`/api/audit`、`doctor`、测试）自己决定怎么用。
    """
    from .spec import pipeline_stages

    ep = event_partition()
    pp = phases_partition(pipeline_stages())
    derived_upstream = set(ep["upstream"])
    recorded = set(CONTRACT_RECORDED_UPSTREAM_EVENTS)

    issues: list[str] = []
    if derived_upstream != recorded:
        issues.append(
            "上游事件集合与契约快照不一致："
            f"多 {sorted(derived_upstream - recorded)} "
            f"少 {sorted(recorded - derived_upstream)}"
        )
    if ep["total"] != CONTRACT_RECORDED_TOTAL_EVENTS:
        issues.append(
            f"事件总数 {ep['total']} != 契约快照 {CONTRACT_RECORDED_TOTAL_EVENTS}"
        )
    if ep["overlap"]:
        issues.append(f"两侧事件重叠（契约要求不相交）: {ep['overlap']}")
    if set(pp["upstream"]) != CONTRACT_RECORDED_UPSTREAM_PHASES:
        issues.append(
            f"上游阶段与契约快照不一致: {sorted(set(pp['upstream']))}"
        )

    # 端点分区：声明的上游端点必须真的在上游 app 上（拿不到路由就跳过）
    proxied = proxied_upstream()
    routes = upstream_routes()
    epart = endpoint_partition(_bridge_endpoints())
    if routes:
        gone = sorted(set(epart["upstream"]) - set(routes))
        if gone:
            issues.append(f"声明的上游端点不存在于上游 app: {gone}")
    if not proxied:
        # 前端 proxy 表读不到 → 上游面**被低估**（不是错，但归因会偏保守）
        issues.append(
            "读不到 frontend/vite.config.ts 的 proxy 表——"
            "上报的上游端点会少算（上游破约时可能没人被指到）"
        )

    return {
        "ok": not issues,
        "issues": issues,
        "event_partition": ep,
        "phases_partition": pp,
        "endpoint_partition": epart,
        "contract_recorded": {
            "upstream_events": sorted(recorded),
            "upstream_phases": sorted(CONTRACT_RECORDED_UPSTREAM_PHASES),
            "total_events": CONTRACT_RECORDED_TOTAL_EVENTS,
        },
        "upstream_routes": routes,
        "backend_dir": paths.BACKEND_DIR,
        "backend_is_bundled": paths.BACKEND_IS_BUNDLED,
    }


def _bridge_endpoints() -> dict[str, str]:
    """bridge 自己声明的端点表（延迟 import，避免与 spec 循环依赖）。"""
    from .spec import ENDPOINTS

    return ENDPOINTS


__all__ = [
    "CONTRACT_FALLBACK_TOTAL_EVENTS",
    "CONTRACT_FALLBACK_UPSTREAM_EVENTS",
    "CONTRACT_FALLBACK_UPSTREAM_PHASES",
    "CONTRACT_JSON",
    "CONTRACT_RECORDED_TOTAL_EVENTS",
    "CONTRACT_RECORDED_UPSTREAM_EVENTS",
    "CONTRACT_RECORDED_UPSTREAM_PHASES",
    "UPSTREAM_ENDPOINT_MAP",
    "VITE_CONFIG",
    "check_against_contract",
    "contract_version",
    "endpoint_partition",
    "event_partition",
    "phases_partition",
    "proxied_upstream",
    "recorded_snapshot",
    "schema_version",
    "upstream_routes",
]
