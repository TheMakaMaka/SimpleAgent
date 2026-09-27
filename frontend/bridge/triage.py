"""失败归因：从事件流里读出「为什么失败」，而不是等人写报告。

要解决的问题
------------
一次 cycle 失败会产生几十条事件、一段 verify 输出、若干清单缺口。
人要把这些整理成一份能看的报告，再把报告交给别人判断——
这个来回本身就是瓶颈，而且**整理过程会丢信息**。

所以把归因做成程序：输入就是事件流（`data/storage_data/runs/<id>/events.jsonl`），
输出是**分好类、带证据、带建议**的结论。

分类沿用项目自己的口径（见 `能力评估报告.md` / `CYCLE.md` §12）：
**模型能力类**（规格已写清，模型没做到）vs **架构缺口类**（系统没有该信息的显式模型）。
这两类的应对完全不同——前者换模型，后者补机制——所以不能混为一谈。

本模块是**纯函数**：不读文件、不联网、不调模型。可离线测。
"""

from dataclasses import dataclass, field
from typing import Any

#: 归因类别 → (中文名, 该找谁)
CATEGORIES: dict[str, tuple[str, str]] = {
    "model_capability": (
        "模型能力类",
        "规格已写清但模型没做到 → 换更强模型；不适合在工作流里打补丁",
    ),
    "architecture_gap": (
        "架构缺口类",
        "系统缺少某个显式模型（例如没声明该产出哪些文件）→ 补机制，不是换模型",
    ),
    "budget": (
        "预算耗尽",
        "轮次 / 步数 / 重试次数用完了 → 调 ModelLimits 或缩小任务粒度",
    ),
    "environment": (
        "环境问题",
        "依赖缺失、路径不对、模型服务不可达 → 与模型能力和工作流都无关",
    ),
    "planning": (
        "规划失败",
        "主循环没能把目标拆成可执行任务 → 多半是提示词或目标描述太含糊",
    ),
    "verify_spec": (
        "验收标准问题",
        "验收命令本身有问题（写错、恒真、用不可能成立的断言）→ 检查调用方给的 verify",
    ),
    "cancelled": ("人工取消", "流程按请求中止，不是失败"),
    "unknown": ("未归类", "证据不足 → 需要看原始事件流"),
}


@dataclass
class Finding:
    """一条归因结论。**必须带证据**——没证据的结论等于猜。"""

    category: str
    summary: str
    evidence: list[str] = field(default_factory=list)
    detail: str = ""

    @property
    def label(self) -> str:
        return CATEGORIES.get(self.category, CATEGORIES["unknown"])[0]

    @property
    def action(self) -> str:
        return CATEGORIES.get(self.category, CATEGORIES["unknown"])[1]

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "label": self.label,
            "summary": self.summary,
            "detail": self.detail,
            "evidence": self.evidence[:8],
            "action": self.action,
        }


@dataclass
class Triage:
    """一次运行的归因结果。"""

    run_id: str
    goal: str = ""
    status: str = "unknown"
    attempts: int = 0
    rolled_back: bool = False
    failed_at: str = ""
    findings: list[Finding] = field(default_factory=list)
    timeline: list[str] = field(default_factory=list)

    @property
    def primary(self) -> Finding | None:
        return self.findings[0] if self.findings else None

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "goal": self.goal,
            "status": self.status,
            "attempts": self.attempts,
            "rolled_back": self.rolled_back,
            "failed_at": self.failed_at,
            "findings": [f.to_dict() for f in self.findings],
            "timeline": self.timeline,
        }

    def to_markdown(self) -> str:
        lines = [
            f"# 失败归因：{self.run_id}",
            "",
            f"- 目标：{self.goal or '（未记录）'}",
            f"- 终态：`{self.status}` · 尝试 {self.attempts} 次"
            + (" · **已回退**" if self.rolled_back else ""),
            f"- 首次失败阶段：`{self.failed_at or '未知'}`",
            "",
        ]
        if not self.findings:
            lines.append("**没有发现失败证据**——要么这次是成功的，要么事件流不完整。")
        for i, f in enumerate(self.findings, 1):
            lines += [
                f"## {i}. {f.label} — {f.summary}",
                "",
                f"**应对**：{f.action}",
                "",
            ]
            if f.detail:
                lines += ["```", f.detail[:800], "```", ""]
            if f.evidence:
                lines.append("证据：")
                lines += [f"- `{e}`" for e in f.evidence[:8]]
                lines.append("")
        if self.timeline:
            lines += ["## 关键时间线", "", "```", *self.timeline[-30:], "```"]
        return "\n".join(lines)


# ============================================================
# 关键事件提取
# ============================================================
#: 归因只看这几类事件，其余是噪音
KEY_KINDS = {
    "run_start", "cycle_end", "manifest", "syntax", "lint",
    "verify", "verify_probe", "rollback", "retry", "phase",
    "attempt_start", "plan", "task_start", "task_done", "decision_action",
    "cancelled", "error", "run_end",
}


def _p(ev: dict) -> dict:
    return ev if isinstance(ev, dict) else {}


def key_timeline(events: list[dict], limit: int = 40) -> list[str]:
    out: list[str] = []
    for ev in events:
        kind = str(_p(ev).get("kind") or "")
        if kind not in KEY_KINDS:
            continue
        ts = str(_p(ev).get("ts") or "")[11:19]
        bits = [f"{ts} {kind}"]
        for k in ("phase", "status", "passed", "attempt", "error", "detail", "path"):
            v = _p(ev).get(k)
            if v not in (None, "", [], {}):
                bits.append(f"{k}={str(v)[:90]}")
        out.append("  ".join(bits))
    return out[-limit:]


# ============================================================
# 分类规则
# ============================================================
def _classify_manifest(ev: dict) -> Finding | None:
    """manifest 校验失败 → 归因。

    **口径必须跟项目自己的一致**（见 `CYCLE.md` §12 / `能力评估报告.md`）：

      架构缺口类 = 系统缺少某个**显式模型**。manifest 本身就是为补这个缺口做的，
                   所以「manifest 已执行、但内容不合格」**不是**架构缺口。
      模型能力类 = 规格已写清（清单就在那儿），模型没做到。

    早先这里把 `declared-broken`（写出来的文件语法都错）也归成架构缺口，是错的——
    那是模型写坏了，不是系统缺机制。**这个错是在真实失败运行上被 doctor 发现的。**
    """
    if not _p(ev).get("checked"):
        # 模型压根没声明该产出什么 → 系统拿不到「交付契约」→ 这才是架构缺口
        return Finding(
            category="architecture_gap",
            summary="本轮没有可校验的交付声明（declared 为空，checked=False）",
            detail="manifest 的判据是「声明 vs 实际」；没有声明就没有判据。",
            evidence=["manifest.checked=False"],
        )

    violations = _p(ev).get("violations") or []
    if _p(ev).get("passed") or not violations:
        return None

    blocking = [
        v for v in violations
        if isinstance(v, dict)
        and v.get("kind") in ("declared-missing", "symbol-missing", "declared-broken")
    ]
    evid = [
        f"{v.get('kind')}: {v.get('path') or v.get('from') or ''} "
        f"{(v.get('message') or '')[:110]}"
        for v in blocking[:6]
    ]
    if not blocking:
        # 只剩 warning 类（例如多写了未声明的文件），不是失败主因
        return Finding(
            category="model_capability",
            summary="交付清单有告警（未声明的多余文件），未阻塞门禁",
            evidence=[
                f"{v.get('kind')}: {v.get('path') or ''}"
                for v in violations[:6] if isinstance(v, dict)
            ],
        )

    kinds = {str(v.get("kind")) for v in blocking}
    if kinds == {"declared-missing"}:
        return Finding(
            category="model_capability",
            summary="计划声明要产出的文件压根没写出来",
            detail="manifest 已把这种失败提前暴露（不必等到 ModuleNotFoundError）。",
            evidence=evid,
        )
    if "declared-broken" in kinds:
        return Finding(
            category="model_capability",
            summary="产出的文件无法解析（语法错误）",
            evidence=evid,
        )
    return Finding(
        category="model_capability",
        summary="文件写了，但缺少声明的符号 / 交付不完整",
        evidence=evid,
    )


def _classify_check(ev: dict) -> Finding | None:
    if _p(ev).get("ok") is not False and _p(ev).get("status") != "failed":
        return None
    msg = str(_p(ev).get("message") or _p(ev).get("reason") or "")[:200]
    return Finding(
        category="model_capability",
        summary=f"静态检查未通过（{_p(ev).get('kind')}）：{_p(ev).get('path') or ''}",
        detail=msg,
        evidence=[f"{_p(ev).get('kind')} {_p(ev).get('path')}"],
    )


def _classify_verify(ev: dict) -> Finding | None:
    if _p(ev).get("passed") is not False:
        return None
    detail = str(_p(ev).get("detail") or "")
    command = str(_p(ev).get("command") or "")
    low = detail.lower()

    # 验收命令本身有问题：恒真、语法错、不可能成立的断言
    if "syntaxerror" in low or "invalid syntax" in low:
        return Finding(
            category="verify_spec",
            summary="验收命令本身语法错误（不是实现的错）",
            detail=detail[:400],
            evidence=[f"command={command[:160]}"],
        )
    if "modulenotfounderror" in low or "no module named" in low:
        return Finding(
            category="architecture_gap",
            summary="验收时找不到模块——该产出的文件不在，或路径没对齐",
            detail=detail[:400],
            evidence=[f"command={command[:160]}"],
        )
    if "timeout" in low or "超时" in low:
        return Finding(
            category="environment",
            summary="验收命令超时",
            detail=detail[:400],
            evidence=[f"command={command[:160]}"],
        )
    if "assertionerror" in low or "assert" in low:
        return Finding(
            category="model_capability",
            summary="验收断言未通过——实现语义与规格不符",
            detail=detail[:400],
            evidence=[f"command={command[:160]}"],
        )
    return Finding(
        category="model_capability",
        summary="验收命令退出码非 0",
        detail=detail[:400],
        evidence=[f"command={command[:160]}"],
    )


def _classify_cycle_end(ev: dict, attempts: int, max_attempts: int, failed_phases: list[str]) -> Finding | None:
    status = str(_p(ev).get("status") or "")
    if status in ("passed", "relaxed"):
        return None
    err = str(_p(ev).get("error") or "")

    if "缺少可机器判定的验证命令" in err:
        return Finding(
            category="verify_spec",
            summary="没有可判定的验收标准，流程拒绝判成功",
            detail=err,
            evidence=["cycle_end error"],
        )
    if attempts >= max_attempts and max_attempts > 0:
        return Finding(
            category="budget",
            summary=f"重试预算耗尽（{attempts}/{max_attempts} 次尝试都没过门禁）",
            detail=err[:400],
            evidence=[f"失败阶段={failed_phases or ['未知']}"],
        )
    return Finding(
        category="unknown",
        summary=f"未能通过门禁（失败阶段 {failed_phases or ['未知']}）",
        detail=err[:400],
    )


def triage(run_id: str, events: list[dict], *, max_attempts: int = 0) -> Triage:
    """把一次运行的事件流归因。

    `max_attempts` 可选；给了才能判定"预算耗尽"。
    """
    t = Triage(run_id=run_id)
    failed_phases: list[str] = []
    last_phase = ""
    findings: list[Finding] = []
    seen: set[str] = set()

    def add(f: Finding | None) -> None:
        if f is None:
            return
        key = f"{f.category}:{f.summary}"
        if key in seen:
            return
        seen.add(key)
        findings.append(f)

    for raw in events:
        ev = _p(raw)
        kind = str(ev.get("kind") or "")

        if kind in ("queued", "run_start"):
            t.goal = t.goal or str(ev.get("goal") or "")
            if kind == "run_start":
                t.attempts = max(t.attempts, 1)
        elif kind == "attempt_start":
            t.attempts = max(t.attempts, int(ev.get("attempt") or 0))
            if not max_attempts:
                max_attempts = int(ev.get("max_attempts") or 0)
        elif kind == "phase":
            phase = str(ev.get("phase") or "")
            if phase == "failed":
                t.failed_at = t.failed_at or f"attempt {ev.get('attempt')}"
                # 失败时 transitions 的倒数第二项就是"卡在哪一步"
                trans = ev.get("transitions") or []
                prev = trans[-2] if len(trans) >= 2 else last_phase
                failed_phases.append(str(prev or "未知"))
            else:
                last_phase = phase
        elif kind == "manifest":
            add(_classify_manifest(ev))
        elif kind in ("syntax", "lint"):
            add(_classify_check(ev))
        elif kind in ("verify", "verify_probe"):
            add(_classify_verify(ev))
        elif kind == "rollback":
            t.rolled_back = bool(ev.get("ok"))
        elif kind == "cancelled":
            add(Finding(
                category="cancelled", summary="运行被取消",
                evidence=[str(ev.get("message") or "")[:200]],
            ))
        elif kind == "error":
            msg = str(ev.get("message") or "")
            add(Finding(
                category="environment",
                summary="运行期异常",
                detail=msg[:400],
                # 消息本身就是证据——归因必须能指回原始文本
                evidence=[msg.splitlines()[0][:200]] if msg else [],
            ))
        elif kind == "decision_action":
            add(Finding(
                category="model_capability",
                summary=f"人工介入后选择了 {ev.get('action')}",
                evidence=[f"action={ev.get('action')}"],
            ))
        elif kind == "cycle_end":
            status = str(ev.get("status") or "")
            if status and status != "passed":
                t.status = status
            if not t.goal:
                t.goal = str(ev.get("goal") or "")

    # run_end 是权威终态
    for raw in events:
        ev = _p(raw)
        if str(ev.get("kind")) == "run_end":
            t.status = str(ev.get("status") or t.status)

    # 「预算耗尽 / 未归类」只在最后判——它需要 attempts 与 max_attempts 都已知。
    # **且只在已经有具体证据时才补"预算耗尽"**：已经有明确根因了，
    # 再叠一条"未归类"是噪音（实测输出里就是这样变的难读）。
    if t.status in ("failed", "error"):
        if findings:
            if t.attempts and max_attempts and t.attempts >= max_attempts:
                add(Finding(
                    category="budget",
                    summary=f"重试预算耗尽（{t.attempts}/{max_attempts} 次尝试都没过门禁）",
                    evidence=[f"失败阶段={failed_phases or ['未知']}"],
                ))
        else:
            add(Finding(
                category="unknown",
                summary=f"未能通过门禁（失败阶段 {failed_phases or ['未知']}）",
                evidence=[f"events={len(events)}"],
                detail="事件流里没有可归因的具体证据。",
            ))

    if not findings and t.status in ("failed", "error"):
        add(Finding(
            category="unknown",
            summary="失败了，但事件流里没有可归因的证据",
            evidence=[f"events={len(events)}"],
            detail="可能是事件流被截断，或失败发生在事件记录之外。",
        ))

    t.findings = findings
    t.timeline = key_timeline(events)
    return t
