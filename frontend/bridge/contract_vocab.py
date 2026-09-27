"""契约词汇表：与 `.interface_contract/` 定义的取值保持一一对应。

**这个模块是契约的镜像，不是契约本身。**

`.interface_contract/` 是只读资产（其 README §3 明令不得编辑）。需要改动时：
写进本仓库 `docs/CHANGELOG.md` 或回复，由统筹方改主本再同步镜像。
所以这里的每个取值都必须能指回契约里的定义处——改了就是违约，不是"优化"。

对应关系（下表按**字段路径**索引，不写契约版本号）：

| 本模块 | 契约字段 |
|---|---|
| `OWNERS` | `owner_vocabulary.values` |
| `SEVERITIES` | `severity_vocabulary.values` |
| `VERDICTS` | `verdict_vocabulary.values` |
| `REATTRIBUTED` | `rule_crosswalk.bridge_backend_prefixed_reclassified` |
| `load_upstream_rules()` | `rule_crosswalk.upstream_only` |
| `CONTRACT_FALLBACK_VERSION` | `version_axes.CONTRACT_VERSION.observed_value` |

> 这张表早先写的是"契约 v1.0.1" —— **那是个会过期的路标**（契约已经走到
> v1.0.19，而注释还停在 v1.0.1）。字段路径不会过期，版本号会。
> 而**运行时读契约**的那几条（`owner_of` / `severity_of` / `upstream_rule`）
> 本来就不需要版本号：它们读的就是当下的契约。

`CONTRACT_FALLBACK_VERSION` 这个名字是刻意的：**契约的版本值由 backend 拥有**
（`CONTRACT_VERSION` 在上游 `core/contract.py`）。bridge 只有在读不到上游时才用它，
且必须同时把 `implements_contract_version` 的**来源**标出来——见 `spec.build_spec()`。
"""

from typing import Literal

import os

# ============================================================
# 归属（4 值）—— 契约 owner_vocabulary
# ============================================================
#: ★ 边界定义（契约 boundary_definition，本契约最重要的一条）：
#:   backend  = SimpleAgent2_Cycle 仓库内的一切
#:   frontend = SimpleAgent2_Cycle_VueWeb 仓库内的一切 —— **bridge/ 与 frontend/ 同等**
#:   ops      = 环境与运行态
#:   both     = 无法从事实源单方面判定，需人工协商
#:
#: 直接后果：**`bridge/` 里的问题算 frontend 的问题。**
#: 这正是历史上一批 `backend.*` 判定被改判的原因（见下方 REATTRIBUTED）。
Owner = Literal["backend", "frontend", "ops", "both"]

OWNERS: dict[str, tuple[str, str]] = {
    "backend": ("后端（上游仓库）", "改 SimpleAgent2_Cycle：事实源、EVENTS 词表、ISSUE_RULES"),
    "frontend": ("前端（bridge + Vue）", "改 SimpleAgent2_Cycle_VueWeb：bridge/ 的声明与代码，或 frontend/ 的渲染"),
    "ops": ("运维/环境", "与双方契约无关：把服务起起来、把前端构建好、修配置"),
    "both": ("双方协商", "无法从事实源单方面判定——通常要先定契约版本，需人工协商"),
}

# ============================================================
# 严重度（3 值）—— 契约 severity_vocabulary
# ============================================================
#: bridge 原来的两档（fail/warn）信息量更少，统一成上游三档：
#:   fail → breaking, warn → degraded, （无）→ info
Severity = Literal["breaking", "degraded", "info"]

SEVERITIES: dict[str, str] = {
    "breaking": "前端会真的看不到 / 画错，必须有人改",
    "degraded": "前端有兜底（降级显示），但应当修；不阻断",
    "info": "只是提醒，多数为 additive 新增；**不参与 verdict**",
}

#: 旧 → 新。迁移期用；新代码一律直接写统一值。
SEVERITY_LEGACY = {"fail": "breaking", "warn": "degraded"}

#: **不参与 verdict 的严重度**。
#:
#: 这条纪律有实测支撑（契约 empirical_evidence.S1）：上游新增 28 个端点，
#: 全部是 `P-endpoint-added`(info)，verdict 仍然是 `ok`。
#: 如果 info 参与判定，"上游加东西"就会变成"有事要改"，低定制立刻退化成
#: 每次加东西都要两边同步。
NON_BLOCKING_SEVERITIES = frozenset({"info"})

# ============================================================
# 结论（6 值）—— 契约 verdict_vocabulary
# ============================================================
#: 优先级：**先判 ops**（服务不可达时后面一切不成立）→ 再按归属集合落到单侧/双侧。
VERDICTS: tuple[str, ...] = (
    "ok",
    "ops-action",
    "backend-action",
    "frontend-action",
    "need-negotiation",
    "multi-action",
)

#: 归属集合 → verdict。`both` 单独存在时是 need-negotiation。
_VERDICT_BY_OWNERS: dict[frozenset[str], str] = {
    frozenset(): "ok",
    frozenset({"ops"}): "ops-action",
    frozenset({"backend"}): "backend-action",
    frozenset({"frontend"}): "frontend-action",
    frozenset({"both"}): "need-negotiation",
}


def verdict_for(owners: set[str]) -> str:
    """按契约规则把归属集合翻成 verdict。

    ★ 顺序取自契约 `verdict_vocabulary.priority`：
      「**先判 ops**（服务不可达时后面一切都不成立）→ 再按 owner 落到单侧/双侧。」

    所以 ops 的检查在 both 之前。反过来的话，一条 ops 问题会被 `both` 的
    `need-negotiation` 盖住 —— 而 ops-action 的下一步文案是"这一条修好之前
    后面都不成立"，被盖住就等于没人去修环境。
    """
    if not owners:
        return "ok"
    if "ops" in owners:
        # ops 最优先：环境没弄好，后面判什么都没意义
        return "ops-action"
    if "both" in owners:
        # 契约 owner_vocabulary：both = 无法从事实源单方面判定
        return "need-negotiation"
    known = frozenset(owners)
    if known in _VERDICT_BY_OWNERS:
        return _VERDICT_BY_OWNERS[known]
    return "multi-action"


# ============================================================
# 改判表 —— 契约 rule_crosswalk.bridge_backend_prefixed_reclassified
# ============================================================
#: bridge 的 11 条 `backend.*` 判定按边界重新归属。
#:
#: **id 保持原样不改名**：契约的对账表是按 `bridge_id` 索引的，
#: 改名会把两套规则之间唯一的链接弄断。前缀 `backend.` 是历史遗留，
#: 真实归属看这里。（是否改名属契约变更，已记入本仓库 CHANGELOG 待统筹方裁决。）
REATTRIBUTED: dict[str, tuple[str, str]] = {
    # bridge_id                          → (统一归属, 统一严重度)
    "backend.stage_mismatch":            ("frontend", "breaking"),
    "backend.phase_order_unreadable":    ("backend", "breaking"),
    "backend.endpoint_missing":          ("frontend", "breaking"),
    "backend.endpoint_undeclared":       ("frontend", "degraded"),
    "backend.dead_event":                ("SPLIT", "degraded"),   # 按事件来源拆
    "backend.uncalibrated_event":        ("frontend", "degraded"),
    "backend.override_broken":           ("frontend", "breaking"),
    "backend.no_events":                 ("frontend", "breaking"),
    "backend.upstream_contract":         ("backend", "breaking"),
    "backend.hooks_not_installed":       ("frontend", "breaking"),
    "backend.version_lying":             ("frontend", "breaking"),
}

#: 只有这两条真的指向上游 —— 它们的**事实源**在上游（PHASE_ORDER / 上游接口）。
REATTRIBUTED_KEEP_BACKEND = frozenset({
    "backend.phase_order_unreadable",
    "backend.upstream_contract",
})


#: ★ 契约 JSON 里这一格的实测值是 **`SPLIT(见 note)`**（带括号说明），
#: 而 §5.2 的散文里写的是 `SPLIT（按事件来源）`。两者都以 `SPLIT` 开头，
#: 所以判据用**前缀**而不是全等 —— 否则统筹方在括号里补一句说明就会
#: 让 `owner_of()` 静默失效（把"需要拆开"当成真实归属返回）。
SPLIT_SENTINEL = "SPLIT"


def is_split(value: str) -> bool:
    """该 owner 格是否是「需按来源拆开」的哨兵值。"""
    return str(value).strip().upper().startswith(SPLIT_SENTINEL)


# ============================================================
# 契约对账表（A1a：跨侧归属**引用**契约，而不是自行下结论）
# ============================================================
#: 契约主本镜像的位置。只读（契约 README §3）。
CONTRACT_JSON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".interface_contract", "interface-contract.json",
)

#: 缓存：`{bridge_id: {"owner", "severity", "code", "why"}}`。
#: `None` = 还没读过；`{}` = 读过但没有（镜像不在）。两者要区分开。
_CROSSWALK: dict[str, dict] | None = None


def _looks_like_code(value: str) -> bool:
    """契约把"上游没有对应规则"写成 `无` / `无（…）` / `None`。

    判据用**形状**而不是枚举那些写法：真 code 都以大写字母或数字开头。
    """
    s = (value or "").strip()
    if not s or s in ("无", "None", "-", "n/a"):
        return False
    if s.startswith("无") or s.startswith("（") or s.startswith("("):
        return False
    return s[0].isupper() or s[0].isdigit()


def extract_code(value: str) -> str:
    """从 `upstream_equivalent` 里取出**纯 code**。

    契约那一列常带限定语，实测有：

        `U-removed-surface (部分)`   → `U-removed-surface`
        `U-dead-event (上游侧)`      → `U-dead-event`
        `无（上游只认 PHASE_ORDER）` → ``（上游确实没有对应规则）

    取第一个空白分隔的 token 即可。**不取整句** —— `code` 是给机器对账用的，
    带限定语的字符串既不能比也不能查。
    """
    s = (value or "").strip()
    if not _looks_like_code(s):
        return ""
    return s.split()[0].strip("（）()[],;，；")


def load_crosswalk(reload: bool = False) -> dict[str, dict]:
    """从契约 JSON 读对账表。

    **读不到就返回空**，调用方回退到镜像表（`REATTRIBUTED`）。
    `bridge/` 可能被单独拿走用，那时没有契约镜像 —— 回退而不是崩。
    """
    global _CROSSWALK
    if _CROSSWALK is not None and not reload:
        return _CROSSWALK

    out: dict[str, dict] = {}
    try:
        import json

        with open(CONTRACT_JSON, encoding="utf-8") as f:
            data = json.load(f)
        rc = data.get("rule_crosswalk") or {}
        for section in ("bridge_backend_prefixed_reclassified",
                        "bridge_frontend_prefixed",
                        "bridge_only_reclassified"):
            for row in rc.get(section) or []:
                bid = row.get("bridge_id") or row.get("id")
                if not bid:
                    continue
                equiv = (row.get("upstream_equivalent")
                         or row.get("unified_code") or "")
                out[bid] = {
                    "owner": row.get("unified_owner") or row.get("owner") or "",
                    "severity": row.get("severity") or "",
                    "code": extract_code(equiv),
                    "upstream_equivalent_raw": equiv,
                    "why": row.get("why") or row.get("note") or "",
                    "section": section,
                }
    except Exception:  # noqa: BLE001
        out = {}
    _CROSSWALK = out
    return out


def crosswalk_of(bridge_id: str) -> dict | None:
    """该 bridge_id 在契约对账表里的那一行（没有则 None）。"""
    return load_crosswalk().get(bridge_id)


#: 缓存：`{code: (owner, severity)}`，来自契约 `rule_crosswalk.upstream_only`。
_UPSTREAM_RULES: dict[str, tuple[str, str]] | None = None


def load_upstream_rules(reload: bool = False) -> dict[str, tuple[str, str]]:
    """契约 `rule_crosswalk.upstream_only` → `{code: (owner, severity)}`。

    ★ 这是**跨侧规则**的唯一判据来源（A1a）。读不到契约时返回空，
    调用方回退到 `audit.UPSTREAM_RULES`（离线镜像表）。

    为什么要读契约而不是照抄一份：本表就是"同一件事两个判据"的滋生地 ——
    实测发生过一次（`U-dead-event` 在 `upstream_only` 里是 `degraded`，
    而在 `bridge_backend_prefixed` 那一行里被写成 `breaking`，两者自相矛盾）。
    读契约 + 测试比对回退表**一致**，这类漂移就会当场红。
    """
    global _UPSTREAM_RULES
    if _UPSTREAM_RULES is not None and not reload:
        return _UPSTREAM_RULES

    out: dict[str, tuple[str, str]] = {}
    try:
        import json

        with open(CONTRACT_JSON, encoding="utf-8") as f:
            data = json.load(f)
        for row in (data.get("rule_crosswalk") or {}).get("upstream_only") or []:
            code = row.get("code")
            owner = row.get("owner")
            severity = row.get("severity")
            if code and owner and severity:
                out[code] = (owner, severity)
    except Exception:  # noqa: BLE001
        out = {}
    _UPSTREAM_RULES = out
    return out


def upstream_rule(code: str) -> tuple[str, str] | None:
    """该 code 的（归属, 严重度）——**从契约读**，读不到返回 None。"""
    return load_upstream_rules().get(code)


def code_of(bridge_id: str, default: str = "") -> str:
    """该判定**对应的上游 code**（契约 `upstream_equivalent`）。

    这就是 A1a 要的"引用"：跨侧结论不再自造名字，而是指向上游规则表里的条目。
    上游确实没有对应规则时返回 `default`（空）——那种情况契约写的是 `无`。
    """
    row = crosswalk_of(bridge_id)
    return (row or {}).get("code") or default


def owner_of(bridge_id: str, default: str = "frontend") -> str:
    """查统一归属。**优先契约对账表**，读不到才回退镜像表。

    ★ 架构清单 A1a：跨侧归属应当**引用**契约，而不是各自维护一份判据。
    镜像表（`REATTRIBUTED`）保留为**离线回退** —— 它必须与契约一致，
    `tests/unit/test_contract_vocab.py` 逐条比对钉住这一点。

    `SPLIT` 条目没有单一归属，返回 `default` —— **调用方必须自己按来源拆开**
    （见 `audit.py` 的 `backend.dead_event` 拆成两条）。
    """
    row = crosswalk_of(bridge_id)
    if row and row["owner"]:
        return default if is_split(row["owner"]) else row["owner"]
    got = REATTRIBUTED.get(bridge_id, (default, ""))[0]
    return default if is_split(got) else got


def severity_of(bridge_id: str, default: str = "degraded") -> str:
    row = crosswalk_of(bridge_id)
    if row and row["severity"]:
        return row["severity"]
    return REATTRIBUTED.get(bridge_id, ("", default))[1] or default


# ============================================================
# 版本轴 —— 契约 version_axes（三条轴**不许合并**）
# ============================================================
#: 三条轴是三件事，当前两侧都叫「1.0」纯属巧合，**不可相减**：
#:   CONTRACT_VERSION  backend 拥有 —— 接口兼容性
#:   SCHEMA_VERSION    backend 拥有 —— 快照可解析性
#:   SPEC_VERSION      frontend 拥有 —— bridge 自己的声明修订号（与兼容性无关）
#:
#: 读不到上游时用这个回退值（契约 version_axes.CONTRACT_VERSION.observed_value）。
#: **必须与来源一起上报**，否则等于 bridge 冒充 backend 说话。
CONTRACT_FALLBACK_VERSION = "1.0"
