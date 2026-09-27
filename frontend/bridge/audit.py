"""责任自审查：把问题判到「谁该改」。

**边界定义（`.interface_contract` 的 boundary_definition，本契约最重要的一条）**

    backend  = SimpleAgent2_Cycle 仓库内的一切
    frontend = SimpleAgent2_Cycle_VueWeb 仓库内的一切 —— **bridge/ 与 frontend/ 同等**
    ops      = 环境与运行态
    both     = 无法从事实源单方面判定，需人工协商

直接后果，也是本模块历史上最大的一个错：**`bridge/` 里的问题算 frontend 的问题。**
先前 `OWNERS["backend"]` 写着「改 `bridge/spec.py` 的声明」——那按边界是 frontend。
11 条 `backend.*` 判定里有 8 条被改判（见 `contract_vocab.REATTRIBUTED`）。

**判定分界线是「声明」，不是「实现」**：服务是黑盒，前端唯一能依赖的就是它声明了什么。

    服务声明了 X，前端不认识 X   → frontend（服务守约了）
    服务声明了 X，实际不做 X     → backend（自相矛盾）
    服务不可达 / 前端没构建      → ops
    无法单方面判定               → both

词汇表（归属 4 值 / 严重度 3 值 / 结论 6 值）在 `contract_vocab.py`，
**是契约的镜像，不许擅自改** —— 要改走本仓库 `docs/CHANGELOG.md`，
由统筹方改主本再同步。
"""

from dataclasses import dataclass, field
from typing import Any

from .contract_vocab import (
    NON_BLOCKING_SEVERITIES,
    OWNERS,
    REATTRIBUTED,
    SEVERITIES,
    SEVERITY_LEGACY,
    VERDICTS,
    Owner,
    Severity,
    code_of,
    owner_of,
    severity_of,
    upstream_rule,
    verdict_for,
)

# 兼容旧名：外部（doctor / 测试）可能还在用
__all__ = [
    "AUTHORITY",
    "AUTHORITY_NOTE",
    "OPS_FACT_CODES",
    "OPS_STALE_BY_TRANSPORT",
    "OWNERS",
    "SEVERITIES",
    "VERDICTS",
    "DEVIATIONS",
    "UPSTREAM_RULES",
    "Audit",
    "Issue",
    "run",
]

# ============================================================
# 权威范围自述（架构清单 A1a）
# ============================================================
#: 本入口的权威范围。**响应里必须带这两个字段** ——
#: 两个对账入口并存时，读响应的人有权知道"这一份管哪一段"。
AUTHORITY = "local-self-check"

#: 跨侧归属该问谁。A1a 的决定是**按职责切分**，不是合并。
AUTHORITY_NOTE = (
    "本入口只对 bridge 自身的声明/实现/本地环境负责。"
    "跨侧归属（backend.*/frontend.*、both 协商项）以上游 `POST /contract/check` 为准 —— "
    "本入口的跨侧判定只**引用**上游规则的 code，不另立判据。"
)


@dataclass
class Issue:
    """一条判定。**必须能指回证据**，否则就是猜。"""

    id: str
    owner: Owner
    severity: Severity
    title: str
    detail: str = ""
    evidence: list[str] = field(default_factory=list)
    fix: str = ""
    #: 契约对账表里的原 id（若该条被改判过）。保留它是为了能追到 rule_crosswalk。
    crosswalk_id: str = ""
    #: ★ 上游规则表里的 code（契约 `upstream_equivalent`）。架构清单 A1a：
    #: 跨侧归属要**引用**上游 code，而不是自造名字。上游确实没有对应规则时为空。
    code: str = ""

    @property
    def owner_label(self) -> str:
        return OWNERS.get(self.owner, ("?", ""))[0]

    @property
    def blocking(self) -> bool:
        """是否参与结论判定。`info` 不参与——契约 severity_vocabulary 的明规。"""
        return self.severity not in NON_BLOCKING_SEVERITIES

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "owner": self.owner,
            "owner_label": self.owner_label,
            "severity": self.severity,
            "blocking": self.blocking,
            "title": self.title,
            "detail": self.detail,
            "evidence": self.evidence[:10],
            "fix": self.fix or OWNERS.get(self.owner, ("", ""))[1],
            "crosswalk_id": self.crosswalk_id or self.id,
            # 空字符串 = 上游确实没有对应规则（契约写 `无`），不是"忘了填"
            "code": self.code or code_of(self.crosswalk_id or self.id),
        }


def _relabel(bridge_id: str, **kw) -> Issue:
    """按契约对账表造一条 Issue：归属、严重度、上游 code **都从表里取**。

    这样"改判"只有一处定义（契约），改表即改全部 —— A1a 要的正是这一点。
    """
    return Issue(
        id=bridge_id,
        owner=owner_of(bridge_id),          # type: ignore[arg-type]
        severity=severity_of(bridge_id),    # type: ignore[arg-type]
        crosswalk_id=bridge_id,
        code=code_of(bridge_id),
        **kw,
    )


#: 契约 `rule_crosswalk.upstream_only` 里「跨侧」那几条：code → (owner, severity)。
#:
#: ★ A1a：跨侧归属**只有一个判据**，就是契约。`_cross()` 会**优先读契约 JSON**
#: （`contract_vocab.upstream_rule`），这张表只是**离线回退**（契约镜像不在时）。
#: 它必须与契约逐条一致 —— `test_audit_authority.py` 钉住这一点。
UPSTREAM_RULES: dict[str, tuple[str, str]] = {
    "P-version-behind": ("frontend", "degraded"),
    "P-version-ahead": ("backend", "breaking"),
    "P-version-unparsable": ("both", "degraded"),
    "P-event-unknown-to-frontend": ("frontend", "degraded"),
    "P-event-gone-upstream": ("both", "degraded"),
    "P-phase-missing": ("frontend", "degraded"),
    # ★ 2026-09-26 裁决（契约 v1.0.7）：由 backend/breaking **改判 both/degraded**。
    #   理由：「前端自造了一个节点」与「上游删了一个阶段」现象完全相同，
    #   事实源判不出方向 —— 按 boundary_definition 归 both。
    #   这条原本记在本模块的 DEVIATIONS 里，裁决后**偏离已撤销**。
    "P-phase-unknown": ("both", "degraded"),
    "P-report-key-missing": ("frontend", "degraded"),
    "P-endpoint-missing": ("backend", "breaking"),
    "P-endpoint-added": ("frontend", "info"),
    "P-schema-behind": ("frontend", "degraded"),
    "P-schema-ahead": ("backend", "breaking"),
    "P-schema-mismatch": ("both", "degraded"),
    "P-missing-field": ("frontend", "info"),
}

#: ★ **声明的偏离**：契约说一套、本模块按更好的判据判另一套的地方。
#:
#: 不静默照抄、也不静默改判 —— 列在这里，并写清理由，请统筹方裁决。
#: `test_audit_authority.py` 断言"偏离集合恰好是这些"，所以它**长不大**。
#:
#: **当前为空**：唯一那条（`P-phase-unknown` 判 `both`）已被契约 v1.0.7 采纳，
#: 不再算偏离。空表本身也是有意义的断言 —— 它说明两侧判据一致。
DEVIATIONS: dict[str, tuple[str, str, str]] = {}


def _cross(code: str, *, id: str = "", **kw) -> Issue:
    """造一条**跨侧**判定：归属与严重度**引用契约**的 `upstream_only` 规则。

    A1a 的核心：跨侧归属只有一个判据。取值顺序：

        ① 契约 JSON（`contract_vocab.upstream_rule`）—— 权威
        ② `DEVIATIONS` —— 声明过的偏离（当前为空）
        ③ `UPSTREAM_RULES` —— 离线回退（契约镜像不在时）

    ★ ①在②之前是刻意的：偏离必须**显式**才生效，不能因为读到契约就悄悄失效。
    """
    dev = DEVIATIONS.get(code)
    if dev:
        owner, severity = dev[0], dev[1]
    else:
        got = upstream_rule(code)
        owner, severity = got if got else UPSTREAM_RULES.get(code, ("both", "degraded"))
    return Issue(
        id=id or code,
        owner=owner,                        # type: ignore[arg-type]
        severity=severity,                  # type: ignore[arg-type]
        crosswalk_id=code,
        code=code,
        **kw,
    )


def _version_lt(a: str, b: str) -> bool:
    """`a < b` 的**保守**版本比较：只比数字段，形状不同就放弃（返回 False）。

    "判不出来"与"不小于"是两件事，所以这个函数只回答"确定更小吗"。
    两侧都解析不了时返回 False，让调用方走 `P-version-unparsable` 分支。
    """
    def parts(v: str) -> list[int] | None:
        segs = str(v).strip().lstrip("v").split(".")
        out = []
        for s in segs:
            digits = "".join(ch for ch in s if ch.isdigit())
            if not digits:
                return None
            out.append(int(digits))
        return out or None

    pa, pb = parts(a), parts(b)
    if pa is None or pb is None:
        return False
    n = max(len(pa), len(pb))
    pa += [0] * (n - len(pa))
    pb += [0] * (n - len(pb))
    return pa < pb


@dataclass
class Audit:
    """一次自审查的结论。"""

    spec_version: str = ""
    contract_version: str = ""
    contract_version_source: str = ""
    issues: list[Issue] = field(default_factory=list)
    checked: list[str] = field(default_factory=list)
    client_reported: bool = False
    client_legacy_shape: bool = False
    #: ★ 非阻塞的语义提示。契约 v1.0.5 `response_contract.warnings`。
    #:
    #: 当前唯一来源：**被传输层证伪的 ops 事实**（请求已成功送达，却报了
    #: `service_down`）。这类事实不参与 verdict，所以只看 verdict 的消费方
    #: 会看到 `ok` 而看不到那条标志 —— 契约因此立了一条**消费方义务**：
    #: 「展示 verdict 的消费方应当同时展示 warnings」。
    warnings: list[str] = field(default_factory=list)
    #: `ops` 栏：**全部**被上报的运行态事实（含未参与判定的），
    #: 便于运维看到"上次已知状态"（契约 `response_contract.ops_column`）。
    ops_reported: dict[str, bool] = field(default_factory=dict)

    @property
    def fails(self) -> list[Issue]:
        """参与判定的问题（`info` 不算）。"""
        return [i for i in self.issues if i.blocking and i.severity == "breaking"]

    @property
    def blocking_issues(self) -> list[Issue]:
        return [i for i in self.issues if i.blocking]

    @property
    def verdict(self) -> str:
        """契约 6 值之一。

        ★ 只有 **blocking** 的问题参与判定；`info` 一律不计
        （否则"上游新增端点"会被误报成"有事要改"——契约 S1 实测验证过）。
        """
        blocking = self.blocking_issues
        if not blocking:
            return "ok"
        return verdict_for({i.owner for i in blocking})

    @property
    def verdict_text(self) -> str:
        v = self.verdict
        if v == "ok":
            if not self.client_reported:
                return "服务自洽（未收到前端期望，只审了「声明 vs 实现」）"
            return "服务与前端兼容，无需改动"
        parts = []
        for o in ("ops", "backend", "frontend", "both"):
            if any(i.owner == o and i.blocking for i in self.issues):
                parts.append(OWNERS[o][0])
        return "需要改动：" + " + ".join(parts)

    def by_owner(self) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {k: [] for k in OWNERS}
        for i in self.issues:
            out.setdefault(i.owner, []).append(i.to_dict())
        return out

    def to_dict(self) -> dict:
        nonblocking = [i for i in self.issues if not i.blocking]
        return {
            # ★ 权威范围自述（A1a）：两个入口并存，读的人有权知道这份管哪一段
            "authority": AUTHORITY,
            "authority_note": AUTHORITY_NOTE,
            "spec_version": self.spec_version,
            "implements_contract_version": self.contract_version,
            "contract_version_source": self.contract_version_source,
            "client_reported": self.client_reported,
            "client_legacy_shape": self.client_legacy_shape,
            "verdict": self.verdict,
            "verdict_text": self.verdict_text,
            "fail_count": len(self.fails),
            "blocking_count": len(self.blocking_issues),
            "info_count": len(nonblocking),
            "issue_count": len(self.issues),
            "responsibility": self.by_owner(),
            # ★ 契约 response_contract：additive；缺失时按 [] 处理。
            #   与 verdict 一起展示是**消费方义务**——因为被传输层证伪的
            #   ops 事实不参与 verdict，只看 verdict 会看不到那条标志。
            "warnings": list(self.warnings),
            "ops": dict(self.ops_reported),
            "checked": self.checked,
        }

    def to_markdown(self) -> str:
        lines = [
            "# 责任自审查",
            "",
            f"> **权威范围**：`{AUTHORITY}` —— {AUTHORITY_NOTE}",
            "",
            f"**结论**：`{self.verdict}` — {self.verdict_text}",
            f"（SPEC_VERSION `{self.spec_version}` · "
            f"CONTRACT_VERSION `{self.contract_version or '未声明'}`"
            f"[{self.contract_version_source or '?'}]"
            + ("· 前端已上报期望" if self.client_reported else "· 前端未上报期望")
            + "）",
            "",
        ]
        # ★ warnings 与 verdict 一起给出（契约要求的消费方义务）。
        #   它不影响结论，但**只看结论会漏掉它** —— 所以不能藏在附录里。
        if self.warnings:
            lines.append("## ⚠ 提示（不参与结论，但应当一并展示）")
            lines.append("")
            lines += [f"- {w}" for w in self.warnings]
            lines.append("")
        if not self.issues:
            lines.append("没有问题。")
            return "\n".join(lines)
        for owner in ("ops", "backend", "frontend", "both"):
            items = [i for i in self.issues if i.owner == owner]
            if not items:
                continue
            label, action = OWNERS[owner]
            lines += [f"## {label}（{len(items)} 项）", "", f"> {action}", ""]
            for i in items:
                mark = {"breaking": "✗", "degraded": "!", "info": "·"}[i.severity]
                lines.append(f"- {mark} **{i.title}**  `{i.severity}`")
                if i.detail:
                    lines.append(f"  {i.detail}")
                for e in i.evidence[:6]:
                    lines.append(f"  - `{e}`")
            lines.append("")
        lines += ["## 已核对", "", *[f"- {c}" for c in self.checked]]
        return "\n".join(lines)


# ============================================================
# 服务端自审：声明 vs 实现
# ============================================================
def backend_checks(spec: dict, *, contract_report=None, hooks_report=None,
                   routes: set[str] | None = None) -> tuple[list[Issue], list[str]]:
    """服务自己审自己：我声明的，我真的做到了吗？

    ★ 归属按契约边界：**声明在 `bridge/` 的，出问题算 frontend**。
    只有事实源在上游的（`PHASE_ORDER`、上游接口）才算 backend。
    """
    issues: list[Issue] = []
    checked: list[str] = []

    pipeline = spec.get("pipeline") or {}
    stages = pipeline.get("stages") or []
    diagnostics = spec.get("diagnostics") or {}
    endpoints = spec.get("endpoints") or {}
    events = spec.get("events") or {}

    # ---- 阶段：声明 == 上游 PHASE_ORDER ----
    # 事实源在上游，但**声明**在 bridge/spec.py → 不一致时该改的是 bridge。
    checked.append("阶段声明 == 上游 PHASE_ORDER")
    try:
        from core.cycle import PHASE_ORDER

        want = [p.value for p in PHASE_ORDER]
        got = [s["id"] for s in stages if s.get("kind") == "phase"]
        if got != want:
            issues.append(_relabel(
                "backend.stage_mismatch",
                title="标定声明的阶段与上游 PHASE_ORDER 不一致",
                detail="两份声明互相矛盾——前端无法判断该信哪个。声明在 bridge/spec.py，故改这边。",
                evidence=[f"spec={got}", f"PHASE_ORDER={want}"],
                fix="改 bridge/spec.py 的 pipeline_stages 推导，不动上游",
            ))
    except Exception as e:  # noqa: BLE001
        # 事实源读不到 = 上游破约（契约把这条保持 backend）
        issues.append(_relabel(
            "backend.phase_order_unreadable",
            title="读不到上游 PHASE_ORDER",
            detail="上游承诺的事实源缺失，标定的阶段清单没有依据。",
            evidence=[f"{type(e).__name__}: {e}"],
        ))

    # ---- 端点：声明的都注册了（声明与注册都在 bridge）----
    checked.append("声明的端点都已注册")
    if routes is not None:
        declared = set(endpoints.values())
        miss = sorted(declared - routes)
        if miss:
            issues.append(_relabel(
                "backend.endpoint_missing",
                title=f"声明了 {len(miss)} 个端点，但没注册",
                detail="前端照着声明去调会 404。ENDPOINTS 与路由都在 bridge，故改这边。",
                evidence=miss,
                fix="改 bridge/spec.py 的 ENDPOINTS 或补上路由",
            ))
        extra = sorted(r for r in routes if r not in declared)
        if extra:
            issues.append(_relabel(
                "backend.endpoint_undeclared",
                title=f"{len(extra)} 个端点已注册但没进声明",
                detail="前端拿不到它们的路径（它只从声明里取）。",
                evidence=extra,
            ))

    # ---- 上游端点：bridge 声称重新暴露的，上游必须真的有 ----
    checked.append("bridge 重新暴露的上游端点仍在上游")
    from . import partition as partition_mod

    declared_upstream = (spec.get("endpoint_partition") or {}).get("upstream") or []
    real_upstream = partition_mod.upstream_routes()
    if declared_upstream and real_upstream:
        gone = sorted(set(declared_upstream) - set(real_upstream))
        if gone:
            issues.append(Issue(
                id="bridge.upstream_endpoint_gone",
                owner="backend", severity="breaking",
                title=f"bridge 重新暴露的 {len(gone)} 个上游端点，上游没有了",
                detail="上游删了它承诺过的面（对应契约 P-endpoint-missing）。",
                evidence=gone,
                fix="上游恢复该端点，或 bridge 停止声称暴露它",
            ))

    # ---- 事件：声明 == 实际会发 ----
    checked.append("声明的事件 == 代码实际会发的")
    dead = diagnostics.get("dead_calibrations") or []
    if dead:
        # ★ 按事件来源拆分（契约 rule_crosswalk 的 SPLIT）：
        #   上游事件不再发 → backend；bridge 事件不再发 → frontend
        ep = partition_mod.event_partition()
        up_set, fe_set = set(ep["upstream"]), set(ep["frontend"])
        up_dead = [k for k in dead if k in up_set]
        fe_dead = [k for k in dead if k in fe_set]
        unknown_dead = [k for k in dead if k not in up_set and k not in fe_set]

        if up_dead or unknown_dead:
            # 严重度取契约（`U-dead-event`）。契约 v1.0.7 把 `backend.dead_event`
            # 那一行的 breaking 与 `upstream_only` 的 degraded **统一为 degraded**
            # —— 同一底层状况在两个 code 上级别必须一致（本仓库报的缺陷）。
            issues.append(Issue(
                id="U-dead-event", owner="backend",
                severity=severity_of("backend.dead_event"),
                title=f"声明了 {len(up_dead) + len(unknown_dead)} 个**上游**事件，但代码从不发",
                detail="上游 EVENTS 词表与实现不符。",
                evidence=sorted(up_dead + unknown_dead),
                crosswalk_id="backend.dead_event",
                code="U-dead-event",
            ))
        if fe_dead:
            issues.append(Issue(
                id="bridge.dead_event", owner="frontend",
                severity=severity_of("backend.dead_event"),
                title=f"声明了 {len(fe_dead)} 个 **bridge 自产**事件，但代码从不发",
                detail="标定表在 bridge/spec.py，故改这边。",
                evidence=sorted(fe_dead),
                crosswalk_id="backend.dead_event",
                # bridge 自产事件死了，上游没有对应规则 → code 留空（契约写「无」那种）
            ))

    uncal = diagnostics.get("uncalibrated_events") or []
    if uncal:
        issues.append(_relabel(
            "backend.uncalibrated_event",
            title=f"{len(uncal)} 个事件会发但没标定",
            detail="前端会显示成自动生成的名字——能用，但不好看。标定表在 bridge/spec.py。",
            evidence=uncal,
        ))
    if diagnostics.get("errors"):
        issues.append(_relabel(
            "backend.override_broken",
            title="标定覆盖文件写错了",
            detail="spec.override.json 的格式由 bridge 定义。",
            evidence=list(diagnostics["errors"]),
        ))

    checked.append("事件清单来自代码扫描")
    if not events:
        issues.append(_relabel(
            "backend.no_events",
            title="声明里一个事件都没有",
            detail="前端什么都画不出来。事件扫描是 bridge 的职责。",
        ))

    # ---- 上游契约（bridge 依赖的上游接口缺失 → 真的指向上游）----
    checked.append("bridge 依赖的上游接口")
    if contract_report is not None and not contract_report.ok:
        issues.append(_relabel(
            "backend.upstream_contract",
            title=f"缺少 {len(contract_report.missing)} 个上游接口",
            detail="bridge 依赖它们产出事件；缺了对应面板会一直空着。",
            evidence=contract_report.missing,
        ))
    if hooks_report is not None and not hooks_report.get("installed"):
        issues.append(_relabel(
            "backend.hooks_not_installed",
            title="进度挂钩没装上",
            detail="挂钩是 bridge 的代码；上游挂钩点消失的情况已由 upstream_contract 覆盖。",
        ))

    return issues, checked


# ============================================================
# 兼容性：前端上报的期望 vs 服务声明
# ============================================================
def compat_checks(spec: dict, client: dict) -> tuple[list[Issue], list[str]]:
    """前端把「我按什么写死的」报上来，服务判它对不对。

    `client` 用契约 `client_report_schema.canonical_fields` 的字段名，
    由前端**构建期从源码生成**（`frontend/src/generated/expectations.ts`），
    不是手写的——手写的一定会漂，那时审查会给出错误的责任判定。

    ★ 事件与阶段必须**按来源分开**（gap_G2 / gap_G3）：
    平铺上报会让上游对 bridge 自产的事件/自补的门禁节点报"上游没有"，
    进而把 frontend 的问题判成 backend。
    """
    issues: list[Issue] = []
    checked: list[str] = []

    server_events = set((spec.get("events") or {}).keys())
    server_stages = {s["id"] for s in (spec.get("pipeline") or {}).get("stages") or []}
    server_endpoints = set((spec.get("endpoints") or {}).keys())

    # 客户端按契约字段名上报；同时容忍旧格式（见 api 层的 legacy 映射）
    client_up_events = set(client.get("upstream_event_kinds") or [])
    client_fe_events = set(client.get("frontend_event_kinds") or [])
    client_events = client_up_events | client_fe_events
    client_phases = set(client.get("phases") or [])
    client_gates = set(client.get("bridge_gate_steps") or [])
    client_stages = client_phases | client_gates
    client_up_endpoints = set(client.get("upstream_endpoints") or [])
    client_fe_endpoints = set(client.get("frontend_endpoints") or [])
    client_version = str(client.get("contract_version") or "")
    server_version = str(spec.get("implements_contract_version") or "")

    # ---- 契约版本 ----
    checked.append("契约版本可比较")
    if not client_version:
        # ★ 契约 `client_report_schema.absence_policy` 明写：字段全部可选，
        #   少给只降精度 → **`P-missing-field`（frontend, info）**。
        #   我原来判 degraded（blocking），与契约冲突。按契约改成 info。
        #   （G1 的紧迫性是真的，但"字段可选"是契约的明确裁决，不擅自加码。）
        issues.append(_cross(
            "P-missing-field",
            title="前端没有上报它实现的契约版本",
            detail=("上游的 P-version-* 三条规则因此永远不会触发——"
                    "不是『没问题』，是『判不出来』。契约把「少给字段」定为 info："
                    "它只降低归因精度，不构成阻塞。"),
            fix="前端上报 contract_version（取自 spec.implements_contract_version）",
        ))
    elif server_version and client_version != server_version:
        # ★ 方向必须分开（契约 `rule_crosswalk.upstream_only` 有两条不同的规则）：
        #   前端落后 → `P-version-behind`（frontend, degraded）：重新构建即可
        #   前端领先 → `P-version-ahead`（**backend**, breaking）：后端没跟上
        #   我原来不分方向、一律判前端 —— 那会把"后端落后"判成"前端要改"。
        behind = _version_lt(client_version, server_version)
        if behind:
            issues.append(_cross(
                "P-version-behind",
                title=f"前端按契约 {client_version} 构建，服务已实现 {server_version}",
                detail="前端落后：重新构建即可对齐。",
                fix="重新构建前端（npm run build）",
            ))
        elif _version_lt(server_version, client_version):
            issues.append(_cross(
                "P-version-ahead",
                title=f"前端按契约 {client_version} 构建，服务只实现 {server_version}",
                detail=("前端**领先**：后端没跟上。方向与「前端落后」相反，"
                        "该改的是后端 —— 按契约这条归属 backend/breaking。"),
                fix="后端升 CONTRACT_VERSION 并实现对应规则",
            ))
        else:
            # 两个字符串不相等但比不出大小（例如 "1.0" vs "1.0.0-rc1"）
            issues.append(_cross(
                "P-version-unparsable",
                title=f"契约版本无法比较：前端 {client_version} / 服务 {server_version}",
                detail="版本号形状对不上，判不出谁落后 —— 需人工协商。",
                fix="两侧统一版本号书写格式",
            ))

    # ---- 事件（按来源分开比）----
    checked.append("前端认得服务声明的全部事件")
    server_up = set((spec.get("event_partition") or {}).get("upstream") or [])
    server_fe = set((spec.get("event_partition") or {}).get("frontend") or [])
    if not server_up and not server_fe:
        server_up, server_fe = server_events, set()

    miss_up = sorted(server_up - client_up_events)
    if miss_up:
        issues.append(_cross(
            "P-event-unknown-to-frontend",
            title=f"服务声明了 {len(miss_up)} 个上游事件，前端不认识",
            detail="服务守约了；前端没跟上。这些事件会退化成时间线上的裸文本行。",
            evidence=miss_up,
            fix="在 frontend/src/store/run.ts 的 switch 里补 case",
        ))

    # 孤儿：客户端认得、服务不声明。
    # ★ 契约裁决：**both + degraded**（上游无法单方面判定该事件历史上是否属自己）。
    #   我原先判 frontend+warn，以契约为准。
    orphan = sorted(client_events - server_events)
    if orphan:
        issues.append(_cross(
            "P-event-gone-upstream",
            title=f"前端认得 {len(orphan)} 个服务不声明的事件",
            detail=("无法从事实源单方面判定：可能是前端死代码，"
                    "也可能是上游删了事件却没升版本。需人工协商。"),
            evidence=orphan,
        ))

    # ---- 阶段 ----
    checked.append("前端认得服务声明的全部上游阶段")
    server_phase_ids = set((spec.get("pipeline") or {}).get("upstream_phases") or [])
    if not server_phase_ids:
        server_phase_ids = {s["id"] for s in (spec.get("pipeline") or {}).get("stages") or []
                            if s.get("kind") == "phase"}
    miss_ph = sorted(server_phase_ids - client_phases)
    if miss_ph:
        issues.append(_cross(
            "P-phase-missing",
            title=f"上游有 {len(miss_ph)} 个阶段，前端没画",
            evidence=miss_ph,
        ))

    # 前端画了上游没有的阶段。**自补门禁节点不算**——那正是 gap_G3 的教训。
    server_gates = set((spec.get("pipeline") or {}).get("bridge_gate_steps") or [])
    unknown_phases = sorted(client_phases - server_phase_ids - server_gates)
    if unknown_phases:
        issues.append(_cross(
            "P-phase-unknown",
            title=f"前端画了 {len(unknown_phases)} 个双方都没有的阶段",
            evidence=unknown_phases,
            detail=("既不在上游 PHASE_ORDER，也不是 bridge 自补的门禁节点。"
                    "方向判不出来：前端新画的、和上游删了前端还在画的，现象一样 —— "
                    "故本模块判 both（与契约的 backend 不同，见 DEVIATIONS）。"),
        ))

    # ---- 端点 ----
    checked.append("前端要代理的上游端点仍在上游")
    from . import partition as partition_mod

    real_upstream = set(partition_mod.upstream_routes())
    if client_up_endpoints and real_upstream:
        gone = sorted(client_up_endpoints - real_upstream)
        if gone:
            issues.append(_cross(
                "P-endpoint-missing",
                title=f"前端要代理的 {len(gone)} 个上游端点不存在",
                evidence=gone,
            ))

    # 前端自己的端点：**仅信息**（契约：additive 新增不该被当成"有事要改"）
    checked.append("前端自产端点（仅信息）")
    extra_fe = sorted(server_endpoints - client_fe_endpoints)
    if extra_fe:
        issues.append(_cross(
            "P-endpoint-added",
            title=f"服务有 {len(extra_fe)} 个前端还没用到的端点",
            detail="不是错——只是前端还没用到这些能力。additive 变更不参与结论。",
            evidence=extra_fe,
        ))

    # ---- 运行态观测（契约第 9 个字段 `ops`）----
    # 语义已由后端裁定（契约 v1.0.5 `response_contract`）：**被传输层证伪的 ops
    # 事实不参与 verdict**。判定放在 `run()` 里做——因为"能不能证伪"取决于
    # 请求是否真的送达，那只有入口层知道。这里只把事实原样带上，供 `ops` 栏展示。
    checked.append("运行态观测（归入 ops 栏）")

    return issues, checked


# ============================================================
# 汇总入口
# ============================================================
#: 契约 `response_contract.profile_additions.ops_stale_by_transport` 列的、
#: **不驱动 verdict** 的 ops code（当前只有 `service_down`）。
#: 同步通道发出请求成功 = 服务可达，所以这条事实**被传输层证伪**。
OPS_STALE_BY_TRANSPORT = frozenset({"O-service-down"})

#: 客户端能上报的 ops 事实名 → 契约 code
OPS_FACT_CODES = {
    "service_down": "O-service-down",
    "frontend_not_built": "O-frontend-not-built",
}


def run(spec: dict, client: dict | None = None, *,
        contract_report=None, hooks_report=None,
        routes: set[str] | None = None,
        service_reachable: bool = True, frontend_built: bool | None = None,
        client_legacy_shape: bool = False) -> Audit:
    """跑完整自审查。`client` 为 None 时只审服务自洽性。

    ★ 契约 v1.0.5 `response_contract`：被传输层证伪的 ops 事实
    （请求已成功送达，却报了 `service_down`）**不参与 verdict**，
    只进 `warnings` 与 `ops` 栏。理由是"只看 verdict 的消费方会看到 ok，
    从而看不到那条陈旧标志" —— 所以还要有 `warnings` 这条兜底，
    并**要求消费方展示它**。

    > 本函数**没有**"离线代别人上报上次已知状态"的开关：那个场景目前不存在，
    > 加一个恒为真的参数只会制造"某条事实被静默丢弃"的缝。真需要时再加，
    > 且要有真实调用方。
    """
    audit = Audit(
        spec_version=str(spec.get("spec_version") or ""),
        contract_version=str(spec.get("implements_contract_version") or ""),
        contract_version_source=str(spec.get("implements_contract_version_source") or ""),
        client_legacy_shape=client_legacy_shape,
    )

    # ---- 服务自己观测到的运行态（可以驱动 verdict）----
    # id 用契约采纳的 code（`O-service-down` / `O-frontend-not-built`）——
    # 与跨侧判定同一条规则：**一个判定只有一个名字**，那个名字就是契约 code。
    # 契约 `rule_crosswalk.bridge_only_reclassified` 记的正是
    # `ops.service_down → O-service-down` 这次采纳。
    ops_issues: list[Issue] = []
    if not service_reachable:
        ops_issues.append(Issue(
            id=OPS_FACT_CODES["service_down"], owner="ops", severity="breaking",
            title="服务不可达",
            detail="先把它起起来；这一条修好之前，后面都不成立。",
            fix="先把服务起起来；这条修好之前后面都不成立",
            crosswalk_id=OPS_FACT_CODES["service_down"],
        ))
    if frontend_built is False:
        ops_issues.append(Issue(
            id=OPS_FACT_CODES["frontend_not_built"], owner="ops", severity="breaking",
            title="前端没有构建产物",
            detail="`/app` 不会注册。",
            fix="npm run build",
            crosswalk_id=OPS_FACT_CODES["frontend_not_built"],
        ))

    # ---- 客户端上报的运行态 ----
    # `ops` 栏保留**全部**被上报的事实（含未参与判定的），便于运维看到
    # "上次已知状态"——契约 `response_contract.ops_column` 的明规。
    client_ops = (client or {}).get("ops") or {}
    for fact, value in sorted(client_ops.items()):
        code = OPS_FACT_CODES.get(fact)
        if code is None:
            continue                      # 未知事实名忽略（契约 additive 安全）
        audit.ops_reported[fact] = bool(value)
        if not value:
            continue                      # 报 false 不构成事实

        if code in OPS_STALE_BY_TRANSPORT:
            # 同步入口：请求送达就证明服务可达 → 该事实被传输层证伪。
            audit.warnings.append(
                f"客户端上报 {fact}=true，但该请求已成功送达本服务 —— "
                f"这条 ops 事实被传输层证伪（code={code}），未参与判定。"
            )
            continue

        if fact == "frontend_not_built" and frontend_built:
            # 本地看得见构建产物 → 与上报矛盾，同样不参与判定。
            audit.warnings.append(
                f"客户端上报 {fact}=true，但本服务看得到构建产物 —— "
                f"这条 ops 事实与本地观测矛盾（code={code}），未参与判定。"
            )
            continue

        # 服务侧可能已经独立观测到同一条（例如 dist 确实不存在）—— 那时不重复计。
        # ★ 必须同时查 `ops_issues`：它此刻**还没**并进 `audit.issues`
        #   （合并发生在后面），只查 `audit.issues` 会漏掉服务侧那一条，
        #   于是同一条运行态事实在 `responsibility` 里出现两次。
        if any(i.id == code for i in (*audit.issues, *ops_issues)):
            continue

        # 未被证伪 → 按契约参与判定。
        # ★ 这里**不能**用 `_relabel`：那张表按 bridge_id 索引，传契约 code
        #   会查不到而落到默认归属（frontend），把 ops 判成前端。
        ops_issues.append(Issue(
            id=code, owner="ops", severity="breaking",
            title=f"客户端上报运行态：{fact}=true",
            detail="该事实未被本地观测证伪，按契约参与判定。",
            fix=OWNERS["ops"][1],
            evidence=[f"{fact}=true"],
            crosswalk_id=code,
        ))

    b_issues, b_checked = backend_checks(
        spec, contract_report=contract_report, hooks_report=hooks_report, routes=routes,
    )
    audit.issues += ops_issues + b_issues
    audit.checked += b_checked

    if client:
        audit.client_reported = True
        c_issues, c_checked = compat_checks(spec, client)
        audit.issues += c_issues
        audit.checked += c_checked

    return audit
