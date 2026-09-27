"""上游 → 前端的**兼容契约**：声明 + 自扫描。

为什么需要这一层
----------------
前端（`bridge/spec.py`）的做法是：**把上游的事实扫出来**，自己不含任何后端事实。
它扫五处，其中四处在上游：

| 事实 | 上游来源 |
|---|---|
| 阶段清单 | `core.cycle.PHASE_ORDER` |
| 事件词表 | 上游 `_emit(...)` 调用点（AST 扫字面量） |
| 工具清单 | `tools.registry.TOOLS_MAP` |
| 运行报告 | `core.cycle.CycleReport.to_dict()` |

这意味着上游**每次改动都在无声地改契约**：删一个事件、改一个 payload 键、
把阶段改名，前端不会报错（它按纪律"认不出就降级显示"），
但会静默少显示东西——这正是 SPEC §1 里那个"两边各手写一份"的老问题换了个方向。

所以本模块做两件事：

1. **声明**：把上游会改动的面写下来（`EVENTS` / `FROZEN_*`），
   让"改契约"变成一个需要**显式编辑**的动作，而不是顺手就改了；
2. **自扫描**：用与前端**同样的技术**（AST 扫 `_emit` 字面量）扫自己，
   在 `audit()` 里对比"声明 vs 实际"，任何不一致都点名。

纪律：**只增不减**（additive-only）
----------------------------------
前端对新增是自动跟上的（新阶段/新事件/新工具都会自动多一个节点或自动生成名字），
对**删除和改名**则只能降级显示。所以：

  ✅ 加事件、加 payload 键、加工具、加阶段、加报告字段 —— 安全
  ⚠️ 删/改名 —— 破坏性。必须先标 `status="deprecated"` 保留**至少一个版本**，
     让前端的 `dead_calibrations` 诊断能提示出来，再删。

`audit()` 的每一项都能机器判定，所以能作门禁（见
`tests/unit/test_frontend_contract.py`）。**语义是否贴切**仍要人判断。
"""

from __future__ import annotations

import ast
import hashlib
import os
from dataclasses import dataclass, field

# 契约版本：**上游与前端各自声明**。前端 spec 里若也带版本号，
# 两边不一致时人一眼能看出"哪边没跟上"。
# 规则：只增不减的改动**不必**升版本；破坏性改动必须升。
#
# `1.0` → `1.1`（2026-09-26）：`decision_opened` 的 payload 键 `kind` → `decision_kind`。
# **为什么算破坏性**（统筹方裁决，我原先漏判了）：前端 `bridge/runner.py` 把事件
# **扁平化**成 `{seq, ts, kind, **payload}`，payload **在后展开** —— 所以改名前
# payload 的 `kind` **覆盖**了记录的 `kind`（`ev.kind` = 决策种类）；
# 改名后不再覆盖（`ev.kind` = `'decision_opened'`），前端的 `run.ts` 会把
# 决策种类显示成事件名。**确实有消费方要跟着改**（前端已立 D8）。
# 我原先"已核实前端未读该键"的结论**不完整** —— 只查了显式读取，漏了扁平化覆盖。
CONTRACT_VERSION = "1.1"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: 允许调用 `_emit` 的文件（相对仓库根）。前端只扫这里 ——
#: 所以在别处发事件等于**前端看不见**，必须往这里加而不是新开文件。
EMIT_SOURCES: tuple[str, ...] = ("core/coding_cycle.py",)

#: `_emit` 签名统一带上的键（属于**事件记录**字段，不属于某个事件的 payload）。
#: 前端从记录的 `goal` 取，不必在每个 payload 里重复声明。
EMIT_COMMON_KEYS: tuple[str, ...] = ("goal",)

#: 前端把事件记录**扁平化**时排在 payload **之前**的字段
#: （`bridge/runner.py`：`record = {seq, ts, kind, run_id, goal, attempt, **payload}`）。
#: payload **后展开** ⇒ **payload 键能覆盖它们**。所以 payload 里必须避开这些名字。
#:
#: 这是统筹方在 D10 里指出的另一类（与"撞 `_emit` 参数名"同型但后果不同）：
#: 撞参数名 → **调用点直接抛 TypeError**（可见）；
#: 撞记录字段 → **不报错**，但前端的 `ev.<字段>` 拿到的是 payload 的值，
#: **静默改变语义** —— `decision_opened.kind` 就是这一类的真实事故（CHANGELOG §29）。
RECORD_FIELDS: tuple[str, ...] = ("seq", "ts", "kind", "run_id", "goal", "attempt")

#: 故意与记录字段共用的 payload 键 —— **必须显式列理由**，不许默默放行。
#: 现状：值相同、无可观测危害，但结构上同型，所以由门禁逐条盯着
#: （`tests/unit/test_frontend_contract.py` [2.5]）。
PAYLOAD_SHARED_KEYS: dict[str, str] = {
    "goal": "整条链路（Event / 前端记录 / 归因）都要它；"
            "值恒等于记录的 goal，覆盖后无差别",
    "attempt": "cycle 级尝试序号；前端记录里同名同义，覆盖后无差别",
}

#: 事实源清单（改路径/改名字 = 破坏前端扫描，属破坏性变更）
FACT_SOURCES: dict[str, str] = {
    "phases": "core.cycle.PHASE_ORDER",
    "events": "CodingCycle._emit 调用点（见 EMIT_SOURCES，AST 扫字面量）",
    "tools": "tools.registry.TOOLS_MAP",
    "report": "core.cycle.CycleReport.to_dict",
    "event_record": "storage.store.Event",
    "snapshot": "core.compress.Snapshot.to_dict + SCHEMA_VERSION",
}


@dataclass(frozen=True)
class EventSpec:
    """一个事件种类的契约。

    `payload` 是**该事件至少会出现的键**（多个发出点的并集；不含
    `EMIT_COMMON_KEYS` 里的 `goal` ——它由 `_emit` 的签名统一带上）。
    声明它的价值在于：删键/改键名会被 `audit()` 抓出来，而前端对 payload 是
    "自动挑一个可读字段"，键名一改它就挑不到了。
    """

    kind: str
    payload: tuple[str, ...]
    status: str = "active"          # active | deprecated
    since: str = ""                 # 契约版本
    note: str = ""


# ---------- 事件词表（当前 13 种，全部来自 core/coding_cycle.py）----------
EVENTS: dict[str, EventSpec] = {
    "cycle_start": EventSpec(
        "cycle_start", ("backend", "prior_files", "code_dir", "code_fingerprint"),
        since="1.1",
        note="一轮 cycle 开始；prior_files 是开始前 workspace 已有的文件。"
             "`backend` 是**检查点后端**（git/snapshot），不是代码来源；"
             "代码来源看 `code_dir` / `code_fingerprint`（上游代码内容的 8 位指纹）"
             "—— 用来回答『这次跑的是哪一份上游』（CHANGELOG §31）"),
    "plan": EventSpec(
        "plan", ("attempt", "declared", "intent", "tasks", "verify_command"),
        since="1.0",
        note="计划（意图，不是现实）。declared 与 intent 都是声明；"
             "intent 里的 expected_output 是自由文本，前端只宜展示不宜判定"),
    "task_result": EventSpec(
        "task_result", ("description", "error", "ok", "output", "task_id"),
        since="1.0", note="子任务结果；output 是模型自述"),
    "manifest": EventSpec(
        "manifest", ("actual_files", "checked", "passed", "violations"),
        since="1.0", note="交付清单校验；violations 是结构化数组"),
    "syntax": EventSpec(
        "syntax", ("message", "ok", "path"), since="1.0"),
    "lint": EventSpec(
        "lint", ("issues", "path", "reason", "status"), since="1.0",
        note="status 三态：passed / failed / skipped。"
             "skipped **不等于通过**，前端不要染成绿色"),
    "verify": EventSpec(
        "verify", ("command", "detail", "passed", "source"), since="1.0",
        note="验证结论，判据级事实。`source` 是判据来源（`caller` / `model`，"
             "于 `VERIFY-VACUOUS` 追加）：调用方给的判据是权威的，模型自拟的"
             "必须先过可采性下限；两者可信度差很远，前端可用它区分显示，"
             "**但不要**因为 `model` 就忽略 `passed`（判定只看退出码）"),
    "verify_skipped": EventSpec(
        "verify_skipped", ("reason", "command"), since="1.1",
        note="★ 有验证命令却**没执行**（`FIX-VERIFY-WIRING` 附 1）。"
             "原来这种跳过完全静默，上层因此把它误诊成「缺少验证命令」。"
             "正常情况下不应出现；出现即表示主循环缺 pipeline（未注入）"),
    "rollback_denied": EventSpec(
        "rollback_denied", ("ref",), since="1.0"),
    "decision_opened": EventSpec(
        "decision_opened",
        ("decision_id", "decision_kind", "default", "options", "question"),
        since="1.0",
        note="★ payload 键 `kind` 于 2026-09-26 改名为 `decision_kind`："
             "`kind` 与 `_emit` 的**参数名**冲突，会让调用点在参数绑定阶段抛 "
             "TypeError（决策路径 100% 不可用，见 CHANGELOG §29）。"
             "消费方若读过 `payload.kind`，请改读 `decision_kind`。"),
    "decision_notified": EventSpec(
        "decision_notified",
        ("channel", "decision_id", "detail", "ok"), since="1.0"),
    "decision_action": EventSpec(
        "decision_action", ("action",), since="1.0"),
    "cycle_end": EventSpec(
        "cycle_end", ("attempt", "commit", "error", "status"), since="1.0",
        note="结束。status 与 CycleReport.phase 同源；"
             "失败分支带 error，成功分支带 commit"),
}

# ---------- 冻结面：只增不减 ----------
#: `CycleReport.to_dict()` 必须始终包含这些键（可新增）
FROZEN_REPORT_KEYS: frozenset[str] = frozenset({
    "cycle_id", "goal", "phase", "transitions", "attempts", "check_steps",
    "check", "manifest", "verify", "touched_files", "rolled_back", "commit",
    "error",
})

#: `Snapshot.to_dict()` 必须始终包含这些键（可新增）
FROZEN_SNAPSHOT_KEYS: frozenset[str] = frozenset({
    "schema_version", "cycle_id", "goal", "status", "attempts",
    "verify_command", "commit", "facts", "files", "failures",
})

#: 事件记录本身的字段（`storage.store.Event`）
FROZEN_EVENT_FIELDS: frozenset[str] = frozenset({
    "kind", "cycle_id", "ts", "seq", "goal", "payload",
})

#: `TOOLS_MAP[name]` 必须始终包含这些键（前端读 description / profiles）
FROZEN_TOOL_INFO_KEYS: frozenset[str] = frozenset({
    "description", "function", "parameters", "profiles",
})

#: 现有阶段必须保留（**可以新增** —— 前端会自动多一个节点）
FROZEN_PHASES: frozenset[str] = frozenset({
    "plan", "write", "check", "verify", "record", "failed",
})


def capabilities() -> dict[str, dict]:
    """能力声明：前端据此决定"显示还是隐藏某个面板"。

    **能推导的一律推导**，不手写布尔值 —— 手写的会漂（前端 SPEC 里
    `DEFAULT_SPEC` 那条教训就是这个：兜底值和真值之间没有类型系统帮忙）。
    推导不出来的（尚未实现的）才显式写 `False` 并说明原因。
    """
    from core.config import role_available

    return {
        "vision": {
            "supported": role_available("vision"),
            "why": "取决于 VISION_* 是否配置（未配置即未启用，不静默降级成文本）",
        },
        "structured_snapshot": {
            "supported": True,
            "why": "core/compress.py 的 Snapshot 带 schema_version，可直接展示",
        },
        "decisions": {
            "supported": True,
            "why": "远程人工决策；**通道是否可用**另看 /profile 的 decision_channel",
        },
        "skills": {"supported": True, "why": "core/skills.py + /skills"},
        "candidate_packages": {
            "supported": True, "why": "core/package.py + /candidates",
        },
        "reflection": {"supported": True, "why": "core/reflect.py + /reflect"},
        "database_storage": {
            "supported": False,
            "why": "按计划只留 Storage Protocol，本地文件是唯一实现",
        },
        "parallel_tasks": {
            "supported": False, "why": "子任务串行执行（未在计划中）",
        },
    }


# ---------- 自扫描（与前端同款技术）----------
def _py_files() -> list[str]:
    out: list[str] = []
    skip = {".git", "workspace", "storage_data", "__pycache__", ".venv",
            "node_modules", "tests", ".mypy_cache", ".ruff_cache"}
    for root, dirs, names in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in skip]
        for n in names:
            if n.endswith(".py"):
                out.append(os.path.join(root, n))
    return sorted(out)


def scan_emit_sites() -> dict[str, dict]:
    """AST 扫出所有 `_emit(<字面量>, ...)` 调用点。

    返回 `{kind: {"payload": [键...], "sites": ["文件:行"...], "files": [...]}}`。
    **只认字面量**：`_emit(some_var, ...)` 会被记进 `nonliteral`，
    因为前端扫不到它（那等于发了一个前端永远不认识的事件）。
    """
    found: dict[str, dict] = {}
    for path in _py_files():
        try:
            with open(path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read())
        except (SyntaxError, UnicodeDecodeError):
            continue
        rel = os.path.relpath(path, ROOT).replace("\\", "/")
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = getattr(fn, "attr", None) or getattr(fn, "id", None)
            if name != "_emit" or not node.args:
                continue
            first = node.args[0]
            site = f"{rel}:{node.lineno}"
            if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                found.setdefault("__nonliteral__", {"payload": [], "sites": [],
                                                    "files": []})
                found["__nonliteral__"]["sites"].append(site)
                found["__nonliteral__"]["files"].append(rel)
                continue
            kind = first.value
            entry = found.setdefault(kind, {"payload": [], "sites": [], "files": []})
            entry["sites"].append(site)
            entry["files"].append(rel)
            for kw in node.keywords:
                if kw.arg and kw.arg not in entry["payload"]:
                    entry["payload"].append(kw.arg)
    for entry in found.values():
        entry["payload"] = sorted(entry["payload"])
        entry["files"] = sorted(set(entry["files"]))
    return found


def audit() -> dict:
    """声明 vs 实际。每个字段都能机器判定，供测试作门禁。"""
    from core.compress import SCHEMA_VERSION, Snapshot
    from core.cycle import PHASE_ORDER, CyclePhase, CycleReport
    from storage.store import Event
    from tools.registry import TOOLS_MAP

    scanned = scan_emit_sites()
    nonliteral = scanned.pop("__nonliteral__", {"sites": [], "files": []})

    declared_active = {k for k, s in EVENTS.items() if s.status == "active"}
    declared_deprecated = {k for k, s in EVENTS.items() if s.status != "active"}
    emitted = set(scanned)

    # payload 键：只检查"声明了但实际再也扫不到"的键（= 键被删/改名）
    payload_drift: dict[str, list[str]] = {}
    for kind, spec in EVENTS.items():
        if kind not in scanned:
            continue
        seen = set(scanned[kind]["payload"])
        lost = sorted(set(spec.payload) - seen)
        if lost:
            payload_drift[kind] = lost

    report_keys = set(CycleReport(cycle_id="cy_audit", goal="").to_dict())
    snapshot_keys = set(Snapshot(cycle_id="cy_audit", goal="").to_dict())
    event_fields = set(Event.__dataclass_fields__)
    tool_info: set[str] = set()
    for info in TOOLS_MAP.values():
        tool_info |= set(info)
    real_phases = {p.value for p in CyclePhase}

    emit_files = sorted({f for e in scanned.values() for f in e["files"]})
    result = {
        "contract_version": CONTRACT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "emit_sources": list(EMIT_SOURCES),
        "emit_files": emit_files,
        "emit_sources_ok": emit_files == sorted(EMIT_SOURCES),
        "common_keys": list(EMIT_COMMON_KEYS),
        "nonliteral_kinds": sorted(nonliteral["sites"]),
        "event_count": len(emitted),
        "declared_count": len(declared_active),
        "undeclared_events": sorted(emitted - declared_active - declared_deprecated),
        "dead_events": sorted(declared_active - emitted),
        "deprecated_still_emitted": sorted(declared_deprecated & emitted),
        "payload_drift": payload_drift,
        "phases": sorted(real_phases),
        "removed_phases": sorted(FROZEN_PHASES - real_phases),
        "removed_report_keys": sorted(FROZEN_REPORT_KEYS - report_keys),
        "removed_snapshot_keys": sorted(FROZEN_SNAPSHOT_KEYS - snapshot_keys),
        "removed_event_fields": sorted(FROZEN_EVENT_FIELDS - event_fields),
        "removed_tool_info_keys": sorted(FROZEN_TOOL_INFO_KEYS - tool_info),
        "tool_count": len(TOOLS_MAP),
    }
    blocking = ("nonliteral_kinds", "undeclared_events", "dead_events",
                "deprecated_still_emitted", "payload_drift", "removed_phases",
                "removed_report_keys", "removed_snapshot_keys",
                "removed_event_fields", "removed_tool_info_keys")
    result["ok"] = (not result["removed_phases"]
                    and result["emit_sources_ok"]
                    and all(not result[k] for k in blocking))
    return result


def describe() -> dict:
    """给 bridge / `/profile` 用的紧凑视图（不含扫描细节）。"""
    return {
        "contract_version": CONTRACT_VERSION,
        "policy": "additive-only：新增安全，删除/改名必须先标 deprecated",
        "fact_sources": dict(FACT_SOURCES),
        "emit_sources": list(EMIT_SOURCES),
        # 前端扁平化时 payload 能覆盖的记录字段（供 wiring 核对与门禁）
        "event_record_fields": list(RECORD_FIELDS),
        "payload_shared_keys": dict(PAYLOAD_SHARED_KEYS),
        "event_kinds": sorted(EVENTS),
        "frozen_report_keys": sorted(FROZEN_REPORT_KEYS),
        "frozen_snapshot_keys": sorted(FROZEN_SNAPSHOT_KEYS),
        "frozen_phases": sorted(FROZEN_PHASES),
        "capabilities": capabilities(),
        # 责任划分规则表：前端可以**离线**用它自己归因，不必猜。
        "responsibility": {c: r.to_dict() for c, r in ISSUE_RULES.items()},
        # 规则表的完整性与稳定性凭据（前端引用 code 时用它判断"表变了没有"）
        "responsibility_count": len(ISSUE_RULES),
        "responsibility_fingerprint": responsibility_fingerprint(),
        # 本入口的权威范围自述（A1b）
        "authority": dict(AUTHORITY_SCOPE),
        # 词表本身也暴露：统筹方的漂移检查要能比对两侧是否同一套词表
        "owner_values": list(OWNER_ORDER),
        "verdict_values": list(VERDICTS),
        # 运行态事实名 → code（事实由能看见环境的一侧上报，code 由本表定义）
        "ops_fact_rules": dict(OPS_FACT_RULES),
        # 经同步通道上报时不可能是"当前值"的事实（信息保留但不驱动结论）
        "ops_stale_by_transport": sorted(OPS_STALE_BY_TRANSPORT),
        # 前端对账时要提交的字段（多给无妨，少给会降低归因精度）
        "peer_report_fields": dict(PEER_FIELDS),
    }


# ============================================================================
# 责任划分：对不上时，**谁去改**
# ============================================================================
# 判定原则（就一条，其余都是它的展开）：
#
#   **事实源在哪一侧，责任就在哪一侧。**
#
#   · 上游发出/声明的东西与上游自己的代码不符  → 后端
#   · 上游已声明并正常发出，前端不认识         → 前端
#   · 上游删/改了前端在用的东西却没标废弃      → 后端（破坏性变更没走流程）
#   · 两边对同一事实的理解不同，且无法从事实源判定 → 双方协商（人工定契约版本）
#
# 为什么要把规则**声明成表**而不是写在代码注释里：前端也在做归因
# （它有自己的运维机制），两边各写一套必然分歧。这张表通过
# `/profile` 的 `contract.responsibility` 暴露出去，前端直接用即可。
#
# 归属词表与结论词表经**统筹契约 v1.0.5** 统一（`owner_vocabulary` /
# `verdict_vocabulary`）：本仓库原有 3 个归属（缺 `ops`）、5 个结论（缺 `ops-action`），
# 本次补齐。21 条既有规则的归属与级别**一条都没有改判**。

OWNER_OPS = "ops"                # 环境/运行态（服务没起、前端没构建、配置坏）
OWNER_BACKEND = "backend"        # 上游（本仓库）改
OWNER_FRONTEND = "frontend"      # 前端改
OWNER_BOTH = "both"              # 需协商（通常要人工确认契约版本）

#: 归属判定顺序：**ops 优先**（服务不可达时后面一切不成立）
OWNER_ORDER: tuple[str, ...] = (OWNER_OPS, OWNER_BACKEND, OWNER_FRONTEND, OWNER_BOTH)

SEV_BREAKING = "breaking"        # 前端会真的看不到 / 画错，必须有人改
SEV_DEGRADED = "degraded"        # 前端有兜底（降级显示），但应当修
SEV_INFO = "info"                # 只是提醒，不影响渲染

#: 结论词表（6 个，取自统筹契约 `verdict_vocabulary.values`）
VERDICTS: tuple[str, ...] = (
    "ok", "ops-action", "backend-action", "frontend-action",
    "need-negotiation", "multi-action",
)

#: 运行态事实 → code。**分工**：code 由本表定义（单一词表），
#: 观测由能看见环境的一侧上报（上游在服务活着时无法观测"服务不可达"）。
#: 事实名取 bridge 侧既有写法（`ops.service_down` / `ops.frontend_not_built`）。
OPS_FACT_RULES: dict[str, str] = {
    "service_down": "O-service-down",
    "frontend_not_built": "O-frontend-not-built",
}

#: **本入口的权威范围自述**（架构清单 A1b）。
#:
#: 背景：两侧各有一个对账入口。统筹方（已获用户批准的架构清单 A1）决定
#: **按职责切分而不是合并** —— 本入口管跨侧归属，`/api/audit` 管本地自检。
#: 于是两个入口都必须**自述权威范围**，否则消费方无从判断该信谁。
#:
#: 为什么切分比合并正确：`/api/audit` 看得见本入口**看不见**的东西
#: （前端是否构建、钩子是否装上、bridge 自身声明是否自洽）——
#: 那些事实本来就无法由上游观测。硬合并会丢掉这些观测能力。
AUTHORITY_SCOPE: dict = {
    "id": "cross-side",
    "role": "authoritative-for-cross-side-attribution",
    "covers": [
        "归属（owner：ops / backend / frontend / both）",
        "严重度（severity：breaking / degraded / info）",
        "结论（verdict：6 个取值）",
        "`both` 协商项",
        "运行态 ops 事实的 code 与归属",
    ],
    "not_covers": [
        "本地环境细节：前端是否构建、钩子是否装上、bridge 自身声明是否自洽"
        " —— 那是 `/api/audit` 的权威范围",
    ],
    "rule_source": "/profile → contract.responsibility（机器可读的完整规则表，"
                   "23 条，随本入口一起发布）",
    "counterpart": {
        "entry": "/api/audit",
        "authority": "local-self-check",
        "cross_side_attribution": "以本入口为准（bridge 应引用本入口的 code 与 owner）",
    },
    "policy": "同一件跨侧不一致只有一个判据；两个入口给出同一 owner。",
}


def responsibility_fingerprint() -> str:
    """规则表的**内容指纹**（8 位）。

    用途：前端引用本入口的 code 时，要能判断"规则表变了没有"。
    指纹只覆盖 **code|owner|severity** 三元组（不含 why/action 文案），
    所以文案修订不会惊动消费方，而**增删规则或改归属/级别一定会变**。

    稳定性承诺：指纹变了 = 契约变了，必须同步升 `CONTRACT_VERSION`；
    由 `tests/unit/test_contract_conformance.py` 与契约原文对账守着。
    """
    payload = "\n".join(
        f"{code}|{r.owner}|{r.severity}" for code, r in sorted(ISSUE_RULES.items())
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:8]

#: **经同步通道上报时不可能为"当前值"的运行态事实。**
#:
#: 判据是传输层事实：`POST /contract/check` **能成功送达**，就已经证明上游可达。
#: 所以随请求一起报上来的 `service_down=true` 只能是"**上次已知状态**"
#: （或外部监视者的观测），不可能是此刻的状态。
#:
#: 因此它：**照常出现在 `ops` 栏（信息不丢）**，但**不驱动 `verdict`**。
#: 理由：`ops` 优先判定的前提是"服务不可达时后面一切不成立"，
#: 而请求成功恰恰把这个前提证伪了 —— 此时后面那些结论**是成立的**。
#: 真·服务不可达只能在**本地**发现（前端根本发不出这个请求，由 bridge 自己的
#: 本地自检负责），所以在这条通道上排除它不会漏掉任何真实故障。
#:
#: 注意：这里**没有**改契约定义的规则本身（`O-service-down` 仍是 ops / breaking），
#: 改的只是"它在什么条件下算当前值"—— 那正是契约里留待本侧确认的部分。
OPS_STALE_BY_TRANSPORT: frozenset[str] = frozenset({"O-service-down"})


@dataclass(frozen=True)
class IssueRule:
    """一类对不上的**归属规则**。code 稳定，可被前端日志/工单引用。"""

    code: str
    owner: str
    severity: str
    why: str
    action: str

    def to_dict(self) -> dict:
        return {
            "owner": self.owner,
            "severity": self.severity,
            "why": self.why,
            "action": self.action,
        }


ISSUE_RULES: dict[str, IssueRule] = {
    # ---------- 上游自查就能发现（后端责任）----------
    "U-emit-nonliteral": IssueRule(
        "U-emit-nonliteral", OWNER_BACKEND, SEV_BREAKING,
        "上游 `_emit(<非字面量>)` —— 前端 AST 扫不到，等于发了隐身事件",
        "改回字面量（事件种类不允许动态拼）",
    ),
    "U-emit-source": IssueRule(
        "U-emit-source", OWNER_BACKEND, SEV_BREAKING,
        "有人在 `EMIT_SOURCES` 之外发事件 —— 前端只扫声明的那个文件",
        "把发出点挪回声明文件，或扩充 EMIT_SOURCES 并通知前端",
    ),
    "U-undeclared-event": IssueRule(
        "U-undeclared-event", OWNER_BACKEND, SEV_DEGRADED,
        "上游发了未声明的事件 —— 词表被改了却没说，前端只能用自动生成的名字",
        "补进 core/contract.py 的 EVENTS 声明（additive，不需升版本）",
    ),
    "U-dead-event": IssueRule(
        "U-dead-event", OWNER_BACKEND, SEV_DEGRADED,
        "声明 active 但已不再发出 —— 前端会一直保留一个永不点亮的标定",
        "删除声明，或改 status=deprecated 并说明替代",
    ),
    "U-deprecated-emitted": IssueRule(
        "U-deprecated-emitted", OWNER_BACKEND, SEV_BREAKING,
        "标了废弃却仍在发出 —— 前端会同时看到新旧两套",
        "两边只留一套：要么去掉发出点，要么撤销 deprecated 标记",
    ),
    "U-payload-drift": IssueRule(
        "U-payload-drift", OWNER_BACKEND, SEV_BREAKING,
        "声明过的 payload 键被删/改名 —— 前端'自动挑可读字段'就挑不到了",
        "恢复该键，或作为破坏性变更走废弃流程",
    ),
    "U-removed-surface": IssueRule(
        "U-removed-surface", OWNER_BACKEND, SEV_BREAKING,
        "冻结面里已有阶段/字段被删除 —— 这是破坏性变更",
        "恢复它，或按 docs/FRONTEND_CONTRACT.md §3 走废弃流程并升 CONTRACT_VERSION",
    ),
    # ---------- 需要前端提交它那一侧才能判定 ----------
    "P-missing-field": IssueRule(
        "P-missing-field", OWNER_FRONTEND, SEV_INFO,
        "前端没提交某项声明 —— 少了它无法判定该项，归因精度下降",
        "在运维检查里补上该字段（见 PEER_FIELDS）",
    ),
    "P-version-behind": IssueRule(
        "P-version-behind", OWNER_FRONTEND, SEV_DEGRADED,
        "前端的 CONTRACT_VERSION 落后于上游",
        "前端按 CHANGELOG 补齐；若它已能正确渲染，把版本号跟上即可",
    ),
    "P-version-ahead": IssueRule(
        "P-version-ahead", OWNER_BACKEND, SEV_BREAKING,
        "前端的 CONTRACT_VERSION 领先于上游 —— 后端没跟上",
        "后端补上该版本承诺的改动，或与前端确认版本号是否标错",
    ),
    "P-version-unparsable": IssueRule(
        "P-version-unparsable", OWNER_BOTH, SEV_DEGRADED,
        "契约版本号无法比较（缺失或格式不同）—— 版本对不上就没法判定谁落后，"
        "整套对账的可信度都受影响",
        "约定统一格式（建议 `MAJOR.MINOR`）；在那之前需人工确认以哪一版为准",
    ),
    "P-event-unknown-to-frontend": IssueRule(
        "P-event-unknown-to-frontend", OWNER_FRONTEND, SEV_DEGRADED,
        "上游**已声明并正常发出**该事件，前端不认识 —— 前端落后",
        "前端补标定；不补也会降级显示（自动生成名字）",
    ),
    "P-event-gone-upstream": IssueRule(
        "P-event-gone-upstream", OWNER_BOTH, SEV_DEGRADED,
        "前端把该事件当作**上游**事件在用，但上游没有这个声明。"
        "上游无法单方面判断历史（可能是有意删除后连声明一起删了，"
        "也可能是前端把自己发的事件误标成了上游的）",
        "先确认它是否曾属上游：是 → 后端补 `status=\"deprecated\"`；"
        "否 → 前端把它从 `upstream_event_kinds` 移到 `frontend_event_kinds`",
    ),
    "P-phase-missing": IssueRule(
        "P-phase-missing", OWNER_FRONTEND, SEV_DEGRADED,
        "上游有这个阶段，前端没画 —— 前端落后（本应自动补节点）",
        "前端补上（正常应自动补，说明它的兜底没生效）",
    ),
    # ★ 2026-09-26 裁决（契约 v1.0.7，变更编号 ARCH-D1）：由 backend/breaking
    # 改判为 both/degraded。理由（统筹方裁定，前端在 EVALUATION-ARCH-A1A-A4
    # §7-1 提出，本侧接受）：
    #   「前端自造了一个节点」与「上游删了一个阶段」**现象完全相同** ——
    #   只看得见"对端报了一个我没有的阶段"，事实源判不出方向。
    #   本契约 boundary_definition 明写这种情形归 `both`（无法单方面判定）。
    #   且 empirical_evidence.S2 已实证：原判会把责任推给后端，
    #   而那个 `manifest` 其实是 bridge 自补的门禁节点。
    # **不因此丢失检测**：真正的"上游删了阶段"由 `U-removed-surface`
    #   （backend / breaking）覆盖 —— 它比对的是**本侧冻结面**，
    #   不依赖对端上报，所以删除动作永远会被本侧自己抓到。
    "P-phase-unknown": IssueRule(
        "P-phase-unknown", OWNER_BOTH, SEV_DEGRADED,
        "前端在画一个上游没有的阶段 —— 但**方向判不出来**："
        "可能是前端自造了节点（bridge 自补门禁节点），也可能是上游删了阶段。"
        "两者现象完全相同，本侧单方面无法区分",
        "先确认方向：若该阶段是前端自补的门禁节点 → 前端上报时过滤"
        "（或另用字段，如 `bridge_gate_steps`）；若上游确实删过阶段 → "
        "后端恢复（阶段只增不减）。真正的删除由 `U-removed-surface` 兜底检测",
    ),
    "P-report-key-missing": IssueRule(
        "P-report-key-missing", OWNER_FRONTEND, SEV_DEGRADED,
        "前端在读一个上游从未承诺的 CycleReport 字段",
        "前端改用已承诺字段，或与后端确认后补进 FROZEN_REPORT_KEYS",
    ),
    "P-endpoint-missing": IssueRule(
        "P-endpoint-missing", OWNER_BACKEND, SEV_BREAKING,
        "前端要代理一个上游端点，但上游没有这个路由",
        "后端补路由，或确认端点是否在 bridge 自己名下（那就不该由上游提供）",
    ),
    "P-endpoint-added": IssueRule(
        "P-endpoint-added", OWNER_FRONTEND, SEV_INFO,
        "上游新增了一个端点，前端列表里没有",
        "前端登记进 bridge 的 ENDPOINTS，或明确忽略（新增是 additive，不阻断）",
    ),
    "P-schema-behind": IssueRule(
        "P-schema-behind", OWNER_FRONTEND, SEV_DEGRADED,
        "前端的快照 SCHEMA_VERSION 落后于上游",
        "前端更新解析逻辑；落后时建议只显示它认识的部分",
    ),
    "P-schema-ahead": IssueRule(
        "P-schema-ahead", OWNER_BACKEND, SEV_BREAKING,
        "前端的快照 SCHEMA_VERSION 领先 —— 后端没跟上",
        "后端补上承诺的快照结构",
    ),
    "P-schema-mismatch": IssueRule(
        "P-schema-mismatch", OWNER_BOTH, SEV_DEGRADED,
        "快照 SCHEMA_VERSION 不一致且无法比较大小",
        "两边确认以哪一版为准（通常取更高者并要求另一侧跟上）",
    ),
    # ---------- 运行态（ops）：来源 bridge 的 ops.*，两侧原先都没有 ----------
    # 这两条把"服务没起来 / 前端没构建"从 backend/frontend 里救出来：
    # 它们与双方契约都无关，以前只能被塞进某一侧 —— 归错人。
    "O-service-down": IssueRule(
        "O-service-down", OWNER_OPS, SEV_BREAKING,
        "服务不可达 —— 与双方契约无关，属环境/运行态",
        # action 文案取统筹契约 new_rules_required.O1 原文
        "先把服务起起来；这一条修好之前后面都不成立",
    ),
    "O-frontend-not-built": IssueRule(
        "O-frontend-not-built", OWNER_OPS, SEV_BREAKING,
        "无前端构建产物（`/app` 不注册）—— 属环境/运行态，不是契约问题",
        # action 文案取统筹契约 new_rules_required.O2 原文
        "npm run build",
    ),
}

#: 前端对账时应提交的字段（多给无妨；少给会降级为 `P-missing-field` 仅提示）。
#: 该集合**与契约 `client_report_schema.canonical_fields` 必须相等** ——
#: 由 `tests/unit/test_contract_conformance.py` 每次跑测试时核对。
PEER_FIELDS: dict[str, str] = {
    "contract_version": "前端支持的契约版本，如 \"1.0\"",
    "schema_version": "前端能解析的快照版本",
    "upstream_event_kinds": "前端认得的**上游**事件（不含 bridge 自己发的）",
    "phases": "前端画的阶段",
    "report_keys": "前端会读的 CycleReport 字段",
    "upstream_endpoints": "前端要代理的**上游**端点",
    "frontend_event_kinds": "（仅信息）前端自己发的事件",
    "frontend_endpoints": "（仅信息）前端自己的端点",
    # 【可选，但建议提供】bridge 自补的门禁节点（当前 ["manifest"]）——
    # 由前端在 spec.pipeline.bridge_gate_steps 暴露。上游据此可**机械判定**
    # `P-phase-unknown` 的方向（见 PHASE_UNKNOWN_DECISION_TREE）。
    # 缺省不影响判定，只降低精度（与其它字段同纪律）。
    "bridge_gate_steps": "（可选）bridge 自补的门禁节点，如 [\"manifest\"]；"
                         "有了它上游就能锐化「未知阶段」的 action 文案",
    # `ops` 已被契约收进 canonical_fields（v1.0.2 起），所以它也在这里。
    # 它与上面 8 项的**类别**不同：那 8 项是"前端按什么写死的"**声明**，
    # `ops` 是运行态**观测**——但既然在同一个上报体里，就同属这套字段。
    #
    # 我早先把它排除在外（理由是"加进去会让契约的 canonical_fields 过期"）
    # 是**错的**：契约早就收了它，结果变成我这边的 `describe().peer_report_fields`
    # 与契约对不上。由 test_contract_conformance.py 第一次运行抓出来。
    "ops": "（观测）运行态事实 {service_down, frontend_not_built}；"
           "未知事实名必须被忽略（additive 安全）",
}

#: `client_report_schema.phase_unknown_decision_tree` 的**机械实现依据**。
#:
#: 契约原文（v1.0.7）：
#:   1) 未知阶段 ∈ peer.bridge_gate_steps → **frontend**（bridge 自补节点被当阶段上报）
#:   2) 未知阶段 ∈ 上游 FROZEN_PHASES 但 ∉ 当前 PHASE_ORDER → **backend**（上游删了冻结阶段）
#:   3) 其余 → **both**（确实判不出方向）
#:
#: `effect_on_owner` **明确要求 owner 不变**（仍 `both` / `degraded`，"避免来回改判"）——
#: 这棵树只用于**锐化 `action` 文案**：能判方向时直接指名是哪种情形，别让人猜。
#: `when_absent` 要求 peer 没给 `bridge_gate_steps` 时**保持人工表述，不许伪造方向**。
#:
#: 一个我核过的边界：`failed` 在 `FROZEN_PHASES` 里但不在 `PHASE_ORDER`，
#: 看似会命中情形 2。实际上**不会** —— `P-phase-unknown` 的触发条件是
#: "对端报的阶段 ∉ 全部 `CyclePhase` 值"，而 `failed` 是 `CyclePhase` 的成员，
#: 所以它根本不会触发本条规则。情形 2 只有在**上游真的把某阶段从 `CyclePhase` 删掉**
#: 时才可达 —— 那时判 backend 正确，且 `U-removed-surface` 会同时报警。
PHASE_UNKNOWN_DECISION_TREE: tuple[str, ...] = (
    "peer.bridge_gate_steps 命中 → frontend",
    "∈ FROZEN_PHASES 且 ∉ PHASE_ORDER → backend",
    "其余 → both",
)


@dataclass
class Issue:
    code: str
    detail: str
    evidence: dict = field(default_factory=dict)
    #: 逐条锐化的 `action` 文案（空串表示用规则表里的通用文案）。
    #:
    #: 为什么需要它：契约的 `phase_unknown_decision_tree` 要求"能判出方向时
    #: **直接指名是哪种情形**，而不是让人去猜"，但**不许改 owner**
    #: （`effect_on_owner`：owner 仍 `both`/`degraded`，避免来回改判）。
    #: 于是"方向"只能体现在文案与 evidence 上，不能体现在 owner 上 ——
    #: 这个字段就是那个出口。owner / severity **永远来自规则表**，不可逐条覆盖。
    action_override: str = ""

    @property
    def rule(self) -> IssueRule:
        return ISSUE_RULES[self.code]

    def to_dict(self) -> dict:
        r = self.rule
        return {
            "code": self.code,
            "owner": r.owner,
            "severity": r.severity,
            "detail": self.detail,
            "why": r.why,
            "action": self.action_override or r.action,
            "evidence": self.evidence,
        }


def _phase_unknown_direction(phase: str, peer: dict) -> tuple[str, str]:
    """`PHASE_UNKNOWN_DECISION_TREE` 的机械实现。

    返回 `(direction, sharpened_action)`；`sharpened_action` 为空串表示
    **用规则表的通用文案**（情形 3：确实判不出方向）。

    **owner 不参与**：契约 `effect_on_owner` 要求 owner 保持 `both`/`degraded`，
    这棵树只锐化文案。所以这里的返回值不会、也不该被用来改 owner。
    """
    from core.cycle import PHASE_ORDER

    if phase in set(peer.get("bridge_gate_steps") or []):
        return ("bridge_gate_step",
                f"**方向已定**：`{phase}` 是对端**自己声明的** bridge 自补门禁节点"
                f"（见 `bridge_gate_steps`）→ **前端**：上报 `phases` 时把它过滤掉，"
                f"只保留上游的 5 个阶段（自补节点继续只在 `bridge_gate_steps` 里报）")
    if phase in FROZEN_PHASES and phase not in {p.value for p in PHASE_ORDER}:
        return ("upstream_removed_frozen_phase",
                f"**方向已定**：`{phase}` 在上游**冻结面**里，但已不在 `PHASE_ORDER` "
                f"→ **后端**：恢复该阶段（阶段只增不减）。本条同时会被 "
                f"`U-removed-surface`(backend/breaking) 抓到")
    # 情形 3：不伪造方向（契约 when_absent 的要求）
    return ("undetermined", "")


def _version_tuple(text: str) -> tuple[int, ...] | None:
    parts = str(text or "").strip().split(".")
    if not parts or not all(p.isdigit() for p in parts if p != ""):
        return None
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        return None


def upstream_issues(a: dict | None = None) -> list[Issue]:
    """只看上游自己就能定的问题（全部 backend 责任）。"""
    a = a or audit()
    out: list[Issue] = []
    if a["nonliteral_kinds"]:
        out.append(Issue("U-emit-nonliteral",
                         f"{len(a['nonliteral_kinds'])} 处 _emit 的种类不是字面量",
                         {"sites": a["nonliteral_kinds"]}))
    if not a["emit_sources_ok"]:
        out.append(Issue("U-emit-source",
                         "事件发出点与声明的 EMIT_SOURCES 不一致",
                         {"declared": a["emit_sources"], "actual": a["emit_files"]}))
    for key, code in (("undeclared_events", "U-undeclared-event"),
                      ("dead_events", "U-dead-event"),
                      ("deprecated_still_emitted", "U-deprecated-emitted")):
        if a[key]:
            out.append(Issue(code, f"{len(a[key])} 个事件：{a[key]}", {"events": a[key]}))
    if a["payload_drift"]:
        out.append(Issue("U-payload-drift", "payload 键被删/改名",
                         {"drift": a["payload_drift"]}))
    removed = {
        "phases": a["removed_phases"],
        "report_keys": a["removed_report_keys"],
        "snapshot_keys": a["removed_snapshot_keys"],
        "event_fields": a["removed_event_fields"],
        "tool_info_keys": a["removed_tool_info_keys"],
    }
    for name, gone in removed.items():
        if gone:
            out.append(Issue("U-removed-surface",
                             f"冻结面中的 {name} 消失：{gone}", {"surface": name,
                                                                "removed": gone}))
    return out


def peer_issues(peer: dict, a: dict | None = None,
                routes: list[str] | None = None) -> list[Issue]:
    """对比前端提交的自述与上游实际。归因规则见 `ISSUE_RULES`。"""
    a = a or audit()
    peer = peer or {}
    out: list[Issue] = []

    # ---- 运行态（ops）：由能看见环境的一侧上报 ----
    # 上游在"服务活着"时无法观测"服务不可达"，所以事实只能来自上报；
    # 但 code 与归属由本表定义（单一词表）。
    # 未知事实名**忽略**（additive 安全），不报错也不产生噪声。
    ops_facts = peer.get("ops") or {}
    if isinstance(ops_facts, dict):
        for fact, code in OPS_FACT_RULES.items():
            if ops_facts.get(fact):
                evidence: dict = {"fact": fact}
                if code in OPS_STALE_BY_TRANSPORT:
                    # 见 OPS_STALE_BY_TRANSPORT 的说明：请求送达即证明上游可达，
                    # 该标志只能是"上次已知状态"。
                    evidence.update({
                        "current": False,
                        "semantics": "last_known_state",
                        "contradicted_by": "request_succeeded",
                    })
                out.append(Issue(code, f"上报的运行态事实：{fact}=true", evidence))

    # ---- 版本 ----
    # 区分"没给"与"给了但看不懂"：前者只说精度下降，后者才要人定格式。
    if "contract_version" not in peer:
        out.append(Issue("P-missing-field", "前端未提交 contract_version",
                         {"field": "contract_version"}))
    else:
        pv = _version_tuple(peer.get("contract_version", ""))
        uv = _version_tuple(CONTRACT_VERSION)
        if pv is None:
            out.append(Issue("P-version-unparsable",
                             f"前端契约版本={peer.get('contract_version')!r} 无法比较"))
        elif uv is not None and pv != uv:
            code = "P-version-behind" if pv < uv else "P-version-ahead"
            out.append(Issue(code, f"前端 {peer.get('contract_version')} "
                                   f"vs 上游 {CONTRACT_VERSION}",
                             {"peer": peer.get("contract_version"),
                              "upstream": CONTRACT_VERSION}))

    if "schema_version" in peer:
        sv = _version_tuple(peer.get("schema_version", ""))
        usv = _version_tuple(a["schema_version"])
        if sv is None or usv is None:
            out.append(Issue("P-schema-mismatch",
                             f"快照版本无法比较：前端 {peer.get('schema_version')!r} "
                             f"vs 上游 {a['schema_version']!r}",
                             {"peer": peer.get("schema_version"),
                              "upstream": a["schema_version"]}))
        elif sv != usv:
            code = "P-schema-behind" if sv < usv else "P-schema-ahead"
            out.append(Issue(code, f"前端快照 schema {peer.get('schema_version')} "
                                   f"vs 上游 {a['schema_version']}",
                             {"peer": peer.get("schema_version"),
                              "upstream": a["schema_version"]}))

    # ---- 事件（只看前端归属给上游的那些）----
    if "upstream_event_kinds" not in peer:
        out.append(Issue("P-missing-field", "前端未提交 upstream_event_kinds",
                         {"field": "upstream_event_kinds"}))
    else:
        peer_kinds = set(peer.get("upstream_event_kinds") or [])
        emitted = {k for k in EVENTS if k in contract_emitted()}
        declared_deprecated = {k for k, s in EVENTS.items() if s.status != "active"}
        for kind in sorted(emitted - peer_kinds):
            out.append(Issue("P-event-unknown-to-frontend",
                             f"上游会发 `{kind}`，前端没把它算进认得的词表",
                             {"kind": kind}))
        for kind in sorted(peer_kinds - set(EVENTS)):
            out.append(Issue("P-event-gone-upstream",
                             f"前端认为 `{kind}` 是上游事件，但上游没有这个声明",
                             {"kind": kind}))
        for kind in sorted(peer_kinds & declared_deprecated):
            out.append(Issue("P-event-gone-upstream",
                             f"`{kind}` 在上游已标废弃，前端仍在用",
                             {"kind": kind}))

    # ---- 阶段 ----
    # "缺失"只看**流水线节点**（PHASE_ORDER）—— `failed` 是终态值，
    # 不是前端要画的节点，用它去比对会产生噪声。
    # "多余"则拿全部 CyclePhase 值比：前端画了一个连上游都没有的阶段才是破坏。
    if "phases" not in peer:
        out.append(Issue("P-missing-field", "前端未提交 phases", {"field": "phases"}))
    else:
        from core.cycle import PHASE_ORDER

        peer_phases = set(peer.get("phases") or [])
        nodes = {p.value for p in PHASE_ORDER}
        all_values = set(a["phases"])
        for ph in sorted(nodes - peer_phases):
            out.append(Issue("P-phase-missing", f"上游流水线有阶段 `{ph}`，前端没画",
                             {"phase": ph}))
        for ph in sorted(peer_phases - all_values):
            direction, sharpened = _phase_unknown_direction(ph, peer)
            out.append(Issue("P-phase-unknown", f"前端在画 `{ph}`，上游没有",
                             {"phase": ph, "direction": direction},
                             action_override=sharpened))

    # ---- 报告字段 ----
    if "report_keys" in peer:
        from core.cycle import CycleReport

        have = set(CycleReport(cycle_id="cy_probe", goal="").to_dict())
        for key in sorted(set(peer.get("report_keys") or []) - have):
            out.append(Issue("P-report-key-missing",
                             f"前端在读 `{key}`，上游报告里没有", {"key": key}))

    # ---- 端点 ----
    if routes is not None and "upstream_endpoints" in peer:
        served = {r.rstrip("/") or "/" for r in routes}
        for ep in sorted(set(peer.get("upstream_endpoints") or [])):
            if (ep.rstrip("/") or "/") not in served:
                out.append(Issue("P-endpoint-missing",
                                 f"前端要代理 `{ep}`，上游没有这个路由", {"endpoint": ep}))
        for ep in sorted(served - {e.rstrip("/") or "/"
                                   for e in (peer.get("upstream_endpoints") or [])}):
            # 健康检查根路径与 FastAPI 自带文档页不必登记
            if ep in ("/", "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"):
                continue
            out.append(Issue("P-endpoint-added",
                             f"上游提供 `{ep}`，前端列表里没有", {"endpoint": ep}))
    return out


def contract_emitted() -> set[str]:
    """上游实际会发出的事件种类（AST 扫出来的，不是声明里的）。"""
    scanned = scan_emit_sites()
    scanned.pop("__nonliteral__", None)
    return set(scanned)


def _pipeline_phases() -> list[str]:
    """前端要画的流水线节点（`PHASE_ORDER`），不含终态 `failed`。"""
    from core.cycle import PHASE_ORDER

    return [p.value for p in PHASE_ORDER]


def compare(peer: dict | None = None, routes: list[str] | None = None) -> dict:
    """产出**责任划分报告**：对不上的每一条，都指明谁去改。

    这是前端运维机制的调用入口（也可离线用 `python -m core.contract`）：

        GET  /contract/check          → 只有上游自检
        POST /contract/check {peer}   → 加上前端自述的完整对账
    """
    a = audit()
    issues = upstream_issues(a) + (peer_issues(peer, a, routes) if peer else [])
    # 四栏（ops 优先）。新增 `ops` 栏是 additive，但**改变了响应结构** ——
    # 消费方（前端）需同步，这一点在统筹契约里已登记为接口变更。
    by_owner: dict[str, list[dict]] = {o: [] for o in OWNER_ORDER}
    for it in issues:
        by_owner[it.rule.owner].append(it.to_dict())

    hard = [i for i in issues if i.rule.severity in (SEV_BREAKING, SEV_DEGRADED)]
    # 经同步通道上报的运行态事实中，**被传输层证伪的那些不驱动结论**
    # （见 OPS_STALE_BY_TRANSPORT）。它们仍出现在 `ops` 栏里，信息不丢。
    stale = [i for i in hard if i.code in OPS_STALE_BY_TRANSPORT]
    driving = [i for i in hard if i.code not in OPS_STALE_BY_TRANSPORT]
    owners = {i.rule.owner for i in driving}
    # 判定顺序：**先判 ops** —— 服务不可达/前端没构建时，后面一切结论都不成立。
    # （统筹契约 verdict_vocabulary.priority）
    if OWNER_OPS in owners:
        verdict = "ops-action"
    elif not driving:
        verdict = "ok"
    elif owners == {OWNER_BACKEND}:
        verdict = "backend-action"
    elif owners == {OWNER_FRONTEND}:
        verdict = "frontend-action"
    elif owners == {OWNER_BOTH}:
        verdict = "need-negotiation"
    else:
        verdict = "multi-action"

    # 可见性：把"标志与本请求可达性矛盾"明说出来，但不让 `verdict` 背这个锅。
    warnings: list[str] = []
    for i in stale:
        warnings.append(
            f"`{i.code}` 报了 true，但**本请求已成功送达** —— 该标志只能是"
            f"「上次已知状态」，不是此刻状态。已按契约语义保留在 ops 栏，"
            f"**未参与结论判定**（真·服务不可达只可能在前端本地发现："
            f"那时它根本发不出这个请求）。"
        )

    next_step = {
        "ok": "契约一致，无需处理。",
        "ops-action": "**运维**改：环境/运行态问题（服务没起 / 前端没构建 / 配置坏）。"
                      "**这一条修好之前，后面所有结论都不成立。**",
        "backend-action": "**后端**改：见 backend 列表（上游自己就与声明不符）。",
        "frontend-action": "**前端**改：见 frontend 列表（上游已声明，前端落后）。",
        "need-negotiation": "**双方协商**：无法从事实源判定，需人工确认契约版本。",
        "multi-action": "**两边都有事**：各自看自己那一栏。",
    }[verdict]
    if stale and verdict == "ok":
        # 结论是 ok，但 ops 栏里躺着一个不会参与判定的标志 —— 说清楚，
        # 否则读报告的人会以为"ok 就等于 ops 栏也空"。
        next_step += "（注意：ops 栏有一条**上次已知状态**的标志未参与判定，见 warnings）"

    return {
        "contract_version": CONTRACT_VERSION,
        "schema_version": a["schema_version"],
        "upstream_ok": a["ok"],
        # ★ A1b：本入口**自述权威范围** —— 消费方据此判断该信谁
        "authority": dict(AUTHORITY_SCOPE),
        "verdict": verdict,
        "next": next_step,
        "warnings": warnings,
        "counts": {k: len(v) for k, v in by_owner.items()},
        "ops": by_owner[OWNER_OPS],
        "backend": by_owner[OWNER_BACKEND],
        "frontend": by_owner[OWNER_FRONTEND],
        "both": by_owner[OWNER_BOTH],
        "issues": [i.to_dict() for i in issues],
        "upstream_facts": {
            "event_kinds": sorted(contract_emitted()),
            "phase_values": a["phases"],
            "pipeline_phases": _pipeline_phases(),
            "endpoints": sorted(routes or []),
        },
        "note": "责任划分规则表见 /profile 的 contract.responsibility；"
                "additive 变更（新增）不属破坏，只作 info 提示。",
    }


def _cli() -> int:
    """`python -m core.contract [--peer peer.json] [--routes /a,/b]`"""
    import argparse
    import json as _json

    ap = argparse.ArgumentParser(description="上游→前端契约对账（责任划分）")
    ap.add_argument("--peer", help="前端自述的 JSON 文件")
    ap.add_argument("--routes", default="", help="上游路由，逗号分隔（可选）")
    ap.add_argument("--json", action="store_true", help="输出原始 JSON")
    args = ap.parse_args()

    peer = None
    if args.peer:
        # utf-8-sig：容忍 BOM。实测踩过 —— Windows PowerShell 5.1 的
        # `Set-Content -Encoding UTF8` 会写入 BOM，`json.load` 遇到它直接抛，
        # 而报错信息完全看不出是 BOM 问题。
        with open(args.peer, "r", encoding="utf-8-sig") as f:
            peer = _json.load(f)
    routes = [r for r in (args.routes or "").split(",") if r.strip()] or None

    report = compare(peer, routes)
    if args.json:
        print(_json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["verdict"] == "ok" else 2

    print("=" * 70)
    print(f"上游→前端契约对账   契约版本 {report['contract_version']}   "
          f"上游自检 {'OK' if report['upstream_ok'] else 'FAIL'}")
    print("=" * 70)
    print(f"结论: {report['verdict']}（ops {report['counts']['ops']} / "
          f"backend {report['counts']['backend']} / "
          f"frontend {report['counts']['frontend']} / "
          f"both {report['counts']['both']}）")
    print(f"下一步: {report['next']}\n")
    for title, key in (("【运维改】", "ops"), ("【后端改】", "backend"),
                       ("【前端改】", "frontend"), ("【双方协商】", "both")):
        items = report[key]
        if not items:
            continue
        print(title)
        for it in items:
            print(f"  [{it['severity']}] {it['code']}: {it['detail']}")
            print(f"      → {it['action']}")
        print()
    if report["verdict"] == "ok":
        print("（无待处理项）")
    return 0 if report["verdict"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(_cli())
