"""反思分析器：从历史执行里提取可复用的模式。

定位（与相邻角色区分）
----------------------
  审查角色   单文件 / 单 diff 的质量        → 建议：改这段代码
  反思角色   跨 cycle 的执行模式            → 建议：改策略 / prompt / 预算
  架构跟踪   跨 session 的长期漂移          → 建议：重构方向

**本模块只产出建议，绝不自动应用。** 「建议」与「执行修改」分离是刻意设计：
一个会自己改自己 prompt 的 agent，最大风险不是改坏，而是改得看不出好坏。

核心纪律：只用 verified 事实
----------------------------
反思的质量上限由原料决定。若让模型"回顾刚才发生了什么"，它会基于**自己的记忆**
反思——而模型对自身行为的记忆极不可靠（本项目实测：模型声称建了 3 个文件，
实际只建了 1 个）。

所以本模块的每个检测器**只读程序校验过的结果**：
  - `Snapshot` 里 confidence=verified 的事实
  - 事件流里由程序产生的事件（verify / syntax / lint / manifest / rollback）
  - 结构化的失败记录（带 reason_hash）

模型自述（confidence=assumed）**不作为证据**，只在需要指出"声称与现实矛盾"时
才被提及。这是从构造上杜绝幻觉，而不是靠提示词约束。

纯函数、无副作用、不调用模型。
"""

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from .compress import Snapshot, cross_cycle_failures

# 证据强度：决定这条建议有多值得看
Confidence = str   # "high" | "medium" | "low"


@dataclass
class Evidence:
    """一条证据必须能指回具体事件，否则就是猜测。"""

    cycle_id: str = ""
    seq: int = 0
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def label(self) -> str:
        """人类可读的证据位置。

        seq 为 0 时只给 cycle —— **不要渲染成 "#0"**，那看起来像精确位置，
        实际是编的。证据的价值全在于可回溯，宁可少说也不能假指。
        """
        if not self.cycle_id:
            return "(全局)"
        if self.seq:
            return f"{self.cycle_id[:18]}#{self.seq}"
        return self.cycle_id[:24]


@dataclass
class Pattern:
    """一条被发现的模式。"""

    kind: str
    title: str
    detail: str
    confidence: Confidence = "medium"
    occurrences: int = 1
    cycles: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    suggestion: str = ""
    target: str = ""          # 建议修改的对象：prompt / pipeline / config / none

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "title": self.title,
            "detail": self.detail,
            "confidence": self.confidence,
            "occurrences": self.occurrences,
            "cycles": self.cycles,
            "evidence": [e.to_dict() for e in self.evidence],
            "suggestion": self.suggestion,
            "target": self.target,
        }


@dataclass
class ReflectionReport:
    """一次反思的产出。**只读、只建议。**"""

    cycles_analyzed: int = 0
    patterns: list[Pattern] = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    def by_confidence(self, level: str) -> list[Pattern]:
        return [p for p in self.patterns if p.confidence == level]

    def to_dict(self) -> dict:
        return {
            "cycles_analyzed": self.cycles_analyzed,
            "summary": self.summary,
            "patterns": [p.to_dict() for p in self.patterns],
        }

    def to_markdown(self) -> str:
        lines = [
            "# 反思报告（仅供参考，未自动应用任何修改）",
            "",
            f"- 分析周期数：{self.cycles_analyzed}",
            f"- 通过 / 失败：{self.summary.get('passed', 0)} / {self.summary.get('failed', 0)}",
            f"- 平均尝试次数：{self.summary.get('avg_attempts', 0)}",
            f"- 发现模式：{len(self.patterns)} 条",
            "",
        ]
        if not self.patterns:
            lines.append("未发现值得行动的模式。")
            return "\n".join(lines)

        order = {"high": 0, "medium": 1, "low": 2}
        for p in sorted(self.patterns, key=lambda x: (order.get(x.confidence, 3), -x.occurrences)):
            lines.append(f"## [{p.confidence}] {p.title}")
            lines.append(f"- 出现次数：{p.occurrences}（涉及 {len(p.cycles)} 个 cycle）")
            lines.append(f"- 说明：{p.detail}")
            if p.suggestion:
                lines.append(f"- 建议：{p.suggestion}" + (f"（改动对象：{p.target}）" if p.target else ""))
            if p.evidence:
                ev = ", ".join(e.label() for e in p.evidence[:6])
                lines.append(f"- 证据：{ev}")
            lines.append("")
        return "\n".join(lines)


# ============================================================
# 工具
# ============================================================
_PATH_RE = re.compile(r"([\w./\\-]+\.py)")


def _path_of(text: str) -> str:
    m = _PATH_RE.search(text or "")
    return m.group(1).replace("\\", "/") if m else ""


def _failure_events(events: Iterable) -> list:
    """只取程序产生的失败类事件——不含模型自述。"""
    return [e for e in events if e.kind in ("verify", "syntax", "lint", "manifest")]


# ============================================================
# 检测器：每个只读 verified 事实
# ============================================================
def detect_repeated_failures(events, snaps: dict[str, Snapshot], min_cycles: int = 2) -> list[Pattern]:
    """反复出现的同一种失败 → 系统性问题，而非偶发。"""
    out: list[Pattern] = []
    for item in cross_cycle_failures(snaps, min_count=min_cycles):
        n = len(item["cycles"])
        out.append(Pattern(
            kind="repeated_failure",
            title=f"同一种失败反复出现：{item['reason'][:60]}",
            detail=(
                f"在 {n} 个 cycle 里出现同一种失败（按原因哈希归并），"
                f"累计 {item['total']} 次。这说明不是偶发，而是系统性原因。"
            ),
            confidence="high" if n >= 3 else "medium",
            occurrences=item["total"],
            cycles=item["cycles"],
            evidence=[Evidence(cycle_id=c, seq=item.get("seq", 0),
                               detail=item["reason"][:80]) for c in item["cycles"][:6]],
            suggestion="定位该失败的共同根因（是模型能力、还是流程/工具缺陷），不要靠增加重试次数掩盖",
            target="pipeline",
        ))
    return out


def detect_retry_hotspots(events, snaps: dict[str, Snapshot]) -> list[Pattern]:
    """尝试次数偏高的 cycle → 任务或流程有问题。"""
    out: list[Pattern] = []
    for cid, s in snaps.items():
        if s.attempts >= 2 and s.status != "passed":
            out.append(Pattern(
                kind="retry_hotspot",
                title=f"cycle 用了 {s.attempts} 次尝试仍未通过",
                detail=f"目标「{s.goal[:60]}」在 {s.attempts} 次尝试后状态为 {s.status}。",
                confidence="medium",
                occurrences=s.attempts,
                cycles=[cid],
                evidence=[Evidence(cycle_id=cid, detail=f"attempts={s.attempts}, status={s.status}")],
                suggestion="检查该目标是否超出当前模型能力；考虑拆小任务或换模型",
                target="config",
            ))
    return out


def detect_false_claims(events, snaps: dict[str, Snapshot]) -> list[Pattern]:
    """模型声称完成、但验证未通过 —— 假成功的直接证据。

    这是模型自述唯一被引用的地方，且只用来**指出矛盾**，不当作事实依据。
    """
    out: list[Pattern] = []
    for cid, s in snaps.items():
        claimed_ok = [f for f in s.facts
                      if f.confidence == "assumed" and "成功" in f.text]
        verify_failed = [f for f in s.facts
                         if f.confidence == "verified" and "验证命令 未通过" in f.text]
        if claimed_ok and verify_failed:
            out.append(Pattern(
                kind="false_claim",
                title="模型声称成功，但验证未通过",
                detail=(
                    "模型自述认为完成了任务，而程序验证判定未通过。"
                    "这正是「不能采信模型自述」的直接证据。"
                ),
                confidence="high",
                occurrences=len(claimed_ok),
                cycles=[cid],
                evidence=[Evidence(cycle_id=cid, seq=f.seq, detail=f.text[:70])
                          for f in (verify_failed + claimed_ok)[:4]],
                suggestion="保持验证门禁为唯一判据；不要引入基于模型自述的完成判定",
                target="none",
            ))
    return out


def detect_persistent_manifest_gaps(events, snaps: dict[str, Snapshot]) -> list[Pattern]:
    """清单缺口在多个 cycle 里重复 → 交付契约形同虚设或模型总漏文件。"""
    by_kind: dict[str, list[tuple[str, int, str]]] = {}
    for cid, s in snaps.items():
        for f in s.facts:
            if f.confidence != "verified":
                continue
            for key in ("应产出但不存在", "缺少符号", "导入了不存在的模块"):
                if key in f.text:
                    by_kind.setdefault(key, []).append((cid, f.seq, f.text))

    out: list[Pattern] = []
    for key, hits in by_kind.items():
        cycles = sorted({c for c, _, _ in hits})
        if len(cycles) < 2:
            continue
        out.append(Pattern(
            kind="manifest_gap",
            title=f"交付清单问题重复出现：{key}",
            detail=f"「{key}」在 {len(cycles)} 个 cycle 里出现，累计 {len(hits)} 次。",
            confidence="medium",
            occurrences=len(hits),
            cycles=cycles,
            evidence=[Evidence(cycle_id=c, seq=q, detail=t[:70]) for c, q, t in hits[:6]],
            suggestion="检查计划声明与实际产出的落差是否集中在某类文件/符号上",
            target="prompt",
        ))
    return out


def detect_budget_exhaustion(events: Iterable, snaps: dict[str, Snapshot]) -> list[Pattern]:
    """命中轮次/步数上限 → 预算不足或主循环空转。"""
    hits = [(e.cycle_id, e.seq, (e.payload or {}).get("error", ""))
            for e in events
            if e.kind == "cycle_end"
            and any(k in str((e.payload or {}).get("error", ""))
                    for k in ("达到主循环上限", "达到子任务步数上限", "max_steps"))]
    if not hits:
        return []

    cycles = sorted({c for c, _, _ in hits})
    return [Pattern(
        kind="budget_exhaustion",
        title="出现预算耗尽",
        detail=(
            f"有 {len(hits)} 次 cycle 因达到轮次/步数上限而结束。"
            "这通常是主循环空转或任务粒度过大的信号。"
        ),
        confidence="medium" if len(cycles) < 3 else "high",
        occurrences=len(hits),
        cycles=cycles,
        evidence=[Evidence(cycle_id=c, seq=q, detail=str(m)[:70]) for c, q, m in hits[:6]],
        suggestion="检查是否反复规划同类任务；预算不足时优先改任务拆解而非单纯调大上限",
        target="config",
    )]


def detect_failure_clusters(events, snaps: dict[str, Snapshot]) -> list[Pattern]:
    """失败集中在同一文件 → 该文件是难点所在。"""
    per_path: dict[str, list[tuple[str, int, str]]] = {}
    for e in _failure_events(events):
        p = e.payload or {}
        failed = (p.get("ok") is False) or (p.get("passed") is False) \
            or bool(p.get("violations")) or (p.get("status") == "failed")
        if not failed:
            continue
        path = p.get("path") or ""
        if not path:
            for v in (p.get("violations") or []):
                path = v.get("path") or v.get("from") or ""
                if path:
                    break
        path = path or "(未指明文件)"
        per_path.setdefault(path, []).append((e.cycle_id, e.seq, e.kind))

    out: list[Pattern] = []
    for path, hits in per_path.items():
        if len(hits) < 3:
            continue
        out.append(Pattern(
            kind="failure_cluster",
            title=f"失败集中在 {path}",
            detail=f"{path} 相关的失败事件累计 {len(hits)} 次，覆盖 {len({c for c,_,_ in hits})} 个 cycle。",
            confidence="medium",
            occurrences=len(hits),
            cycles=sorted({c for c, _, _ in hits}),
            evidence=[Evidence(cycle_id=c, seq=q, detail=k) for c, q, k in hits[:6]],
            suggestion=f"优先审查 {path} 的实现与调用方式，可能是反复踩同一类坑",
            target="pipeline",
        ))
    return out


# ============================================================
# 入口
# ============================================================
ALL_DETECTORS = (
    detect_repeated_failures,
    detect_retry_hotspots,
    detect_false_claims,
    detect_persistent_manifest_gaps,
    detect_budget_exhaustion,
    detect_failure_clusters,
)


def reflect(events: list, limit_cycles: int = 20) -> ReflectionReport:
    """对历史事件做一次反思。纯函数，不调用模型，不改任何东西。"""
    from .compress import reduce_all

    snaps = reduce_all(events, limit_cycles=limit_cycles)
    report = ReflectionReport(cycles_analyzed=len(snaps))

    passed = sum(1 for s in snaps.values() if s.status == "passed")
    failed = sum(1 for s in snaps.values() if s.status not in ("passed", "unknown"))
    attempts = [s.attempts for s in snaps.values() if s.attempts]
    report.summary = {
        "passed": passed,
        "failed": failed,
        "avg_attempts": round(sum(attempts) / len(attempts), 2) if attempts else 0,
        "by_status": _count_by_status(snaps),
    }

    # 所有检测器统一签名 (events, snaps) → list[Pattern]，
    # 便于新增检测器时不必改分发逻辑。
    for det in ALL_DETECTORS:
        try:
            report.patterns.extend(det(events, snaps))
        except Exception as e:
            # 单个检测器失败不应让整份反思为空
            report.patterns.append(Pattern(
                kind="detector_error",
                title=f"检测器 {det.__name__} 执行失败",
                detail=str(e)[:200],
                confidence="low",
            ))

    report.patterns = _dedupe(report.patterns)
    return report


def _count_by_status(snaps: dict[str, Snapshot]) -> dict[str, int]:
    out: dict[str, int] = {}
    for s in snaps.values():
        out[s.status] = out.get(s.status, 0) + 1
    return out


def _dedupe(patterns: list[Pattern]) -> list[Pattern]:
    seen: dict[tuple, Pattern] = {}
    for p in patterns:
        key = (p.kind, p.title)
        if key in seen:
            seen[key].occurrences += p.occurrences
            seen[key].cycles = sorted(set(seen[key].cycles) | set(p.cycles))
            seen[key].evidence.extend(p.evidence)
        else:
            seen[key] = p
    return list(seen.values())


def reflect_from_storage(storage=None, limit_cycles: int = 20) -> ReflectionReport:
    """从默认存储读取历史并反思。"""
    if storage is None:
        from storage.store import default_storage
        storage = default_storage()
    return reflect(storage.get_events(), limit_cycles=limit_cycles)
