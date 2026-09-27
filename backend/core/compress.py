"""结构化上下文压缩：把原始事件压成可回溯的结构化视图。

核心纪律（这一层存在的全部理由）
--------------------------------
**压缩的输入只能是被程序校验过的结果，不能是模型的自由摘要。**

第一轮尝试的是"让模型做前后文压缩"，但模型自由摘要的幻觉率太高——那等于
新增一个幻觉源，还会把错误固化下来。所以这里改成：由程序从事件流里**提取**
结构化事实，每个事实必须带 `source`（可回溯到哪条事件）和 `confidence`：

  verified  程序实测（verify 退出码、manifest 文件存在性、语法检查）
  assumed   模型自述（任务 output 摘要）——**不算事实，不可作为判据**
  declared  计划里声明过（例如"要产出 X"）——意图，不是现实

压缩是**派生视图**：原始事件永不改写，快照随时可从事件重算。
这样"丢信息"是可回滚的，而不是不可逆的。
"""

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from storage.store import Event

SCHEMA_VERSION = "1.0"

# 事实来源 → 可信度
_SOURCE_CONFIDENCE = {
    "verify": "verified",       # 验证命令退出码
    "manifest": "verified",     # 文件存在性 / 符号存在性（AST 实测）
    "syntax": "verified",       # 语法检查
    "lint": "verified",         # lint（注意 skipped 时不算通过）
    "task_output": "assumed",   # 模型自述
    "plan": "declared",         # 计划声明
}


@dataclass
class Fact:
    text: str
    source: str                  # 溯源：事件 kind 或 "cycle/<id>/<seq>"
    confidence: str              # verified | assumed | declared
    cycle_id: str = ""
    seq: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FileFact:
    path: str
    role: str = ""
    symbols: list[str] = field(default_factory=list)
    status: str = "declared"     # declared | exists | missing
    sha1: str = ""
    source: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FailureFact:
    what: str
    reason: str
    reason_hash: str
    count: int = 1
    cycle_id: str = ""
    source: str = ""
    avoid: str = ""              # 给模型的"不要再这样做"提示

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Snapshot:
    """喂给模型的结构化上下文。**只含经过整理的字段，不含自由文本摘要。**"""

    cycle_id: str
    goal: str
    schema_version: str = SCHEMA_VERSION
    status: str = "unknown"      # passed | failed | unknown
    facts: list[Fact] = field(default_factory=list)
    files: list[FileFact] = field(default_factory=list)
    failures: list[FailureFact] = field(default_factory=list)
    attempts: int = 0
    verify_command: str = ""
    commit: str = ""

    def verified_facts(self) -> list[Fact]:
        return [f for f in self.facts if f.confidence == "verified"]

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "cycle_id": self.cycle_id,
            "goal": self.goal,
            "status": self.status,
            "attempts": self.attempts,
            "verify_command": self.verify_command,
            "commit": self.commit,
            "facts": [f.to_dict() for f in self.facts],
            "files": [f.to_dict() for f in self.files],
            "failures": [f.to_dict() for f in self.failures],
        }

    def to_prompt(self, max_facts: int = 12) -> str:
        """渲染成给模型的紧凑文本。只呈现 verified 与 declared，assumed 单列。"""
        lines = [f"目标: {self.goal}", f"状态: {self.status}"]

        verified = [f for f in self.facts if f.confidence == "verified"]
        assumed = [f for f in self.facts if f.confidence == "assumed"]
        declared = [f for f in self.facts if f.confidence == "declared"]

        if verified:
            lines.append("已实测确认（可信）:")
            for f in verified[:max_facts]:
                lines.append(f"  - {f.text}  [来源 {f.source}]")

        if declared:
            lines.append("计划声明（尚未确认为现实）:")
            for f in declared[:max_facts]:
                lines.append(f"  - {f.text}")

        if self.files:
            lines.append("文件:")
            for ff in self.files:
                mark = {"exists": "有", "missing": "缺", "declared": "计划"}.get(ff.status, ff.status)
                sym = f" 符号[{', '.join(ff.symbols)}]" if ff.symbols else ""
                lines.append(f"  - [{mark}] {ff.path}{sym}")

        if self.failures:
            lines.append("失败记录（不要原样重试）:")
            for fl in self.failures:
                times = f"×{fl.count}" if fl.count > 1 else ""
                lines.append(f"  - {fl.what}{times}: {fl.reason[:100]}")
                if fl.avoid:
                    lines.append(f"    → {fl.avoid}")

        if assumed:
            lines.append("模型自述（**未经校验，不可作为判据**）:")
            for f in assumed[:6]:
                lines.append(f"  - {f.text[:100]}")

        return "\n".join(lines)


def _hash_reason(text: str) -> str:
    return hashlib.sha1((text or "").strip().lower().encode("utf-8")).hexdigest()[:8]


def _fact_from_event(ev: Event, text: str, source_key: str) -> Fact:
    confidence = _SOURCE_CONFIDENCE.get(source_key, "assumed")
    return Fact(
        text=text,
        source=f"{ev.kind}@{ev.cycle_id}#{ev.seq}",
        confidence=confidence,
        cycle_id=ev.cycle_id,
        seq=ev.seq,
    )


def reduce_cycle(events: Iterable[Event], cycle_id: str) -> Snapshot:
    """把某个 cycle 的事件压成 Snapshot。

    纯函数：同样的输入必得同样的输出，可反复重算，不需要模型参与。
    """
    evs = [e for e in events if e.cycle_id == cycle_id]
    if not evs:
        return Snapshot(cycle_id=cycle_id, goal="", status="unknown")

    goal = next((e.goal for e in evs if e.goal), "")
    snap = Snapshot(cycle_id=cycle_id, goal=goal)
    failure_index: dict[str, FailureFact] = {}
    declared_paths: dict[str, FileFact] = {}

    for ev in evs:
        p = ev.payload or {}

        if ev.kind == "plan":
            snap.attempts = max(snap.attempts, int(p.get("attempt", 0)))
            if p.get("verify_command"):
                snap.verify_command = p["verify_command"]
            # 计划声明：意图，不是现实
            for d in p.get("declared") or []:
                path = d.get("path") or ""
                if not path:
                    continue
                ff = declared_paths.get(path) or FileFact(path=path, source=f"plan#{ev.seq}")
                ff.role = d.get("role", "") or ff.role
                ff.symbols = list(d.get("symbols") or [])
                ff.status = "declared"
                declared_paths[path] = ff
                snap.facts.append(_fact_from_event(
                    ev, f"计划产出 {path}", "plan"))

            # 任务的 expected_output 是**自由文本**，所以只能作 declared 事实
            # （可回溯、可提醒），绝不做门禁——门禁判据必须能机器判定。
            for it in p.get("intent") or []:
                expected = (it.get("expected_output") or "").strip()
                if not expected:
                    continue
                snap.facts.append(_fact_from_event(
                    ev, f"任务 {it.get('id')} 期望产出: {expected}", "plan"))

        elif ev.kind == "task_result":
            ok = bool(p.get("ok"))
            out = (p.get("output") or "").strip()
            if out:
                # 模型自述：只作参考，绝不作为判据
                snap.facts.append(_fact_from_event(
                    ev, f"任务 {p.get('task_id')} {'成功' if ok else '失败'}: {out[:150]}",
                    "task_output"))
            if not ok:
                reason = p.get("error") or out or "未知原因"
                h = _hash_reason(str(reason))
                key = f"{p.get('task_id')}::{h}"
                if key in failure_index:
                    failure_index[key].count += 1
                else:
                    ff = FailureFact(
                        what=str(p.get("task_id") or "任务"),
                        reason=str(reason)[:200],
                        reason_hash=h,
                        cycle_id=cycle_id,
                        source=f"task_result#{ev.seq}",
                        avoid="换实现思路或先修正根因，不要提交相同代码",
                    )
                    failure_index[key] = ff
                    snap.failures.append(ff)

        elif ev.kind == "syntax":
            ok = bool(p.get("ok"))
            snap.facts.append(_fact_from_event(
                ev, f"语法检查 {'通过' if ok else '未通过'} {p.get('path', '')}", "syntax"))
            if not ok:
                msg = str(p.get("message") or "")
                h = _hash_reason(msg)
                key = f"syntax::{p.get('path')}::{h}"
                if key not in failure_index:
                    ff = FailureFact(
                        what=f"语法检查 {p.get('path', '')}",
                        reason=msg[:200], reason_hash=h,
                        cycle_id=cycle_id, source=f"syntax#{ev.seq}",
                        avoid="先修正语法，其余检查在语法通过后才有意义",
                    )
                    failure_index[key] = ff
                    snap.failures.append(ff)

        elif ev.kind == "lint":
            status = p.get("status") or ("passed" if p.get("ok") else "failed")
            if status == "skipped":
                # 没执行 ≠ 通过，这一条以前踩过坑
                snap.facts.append(_fact_from_event(
                    ev, f"lint 未执行（{p.get('reason', 'ruff 不可用')}）——不代表通过",
                    "task_output"))
            else:
                snap.facts.append(_fact_from_event(
                    ev, f"lint {'通过' if status == 'passed' else '未通过'}", "lint"))

        elif ev.kind == "manifest":
            for v in p.get("violations") or []:
                kind = v.get("kind")
                path = v.get("path") or v.get("from") or ""
                if kind == "declared-missing":
                    snap.facts.append(_fact_from_event(
                        ev, f"{path} 应产出但不存在", "manifest"))
                    if path in declared_paths:
                        declared_paths[path].status = "missing"
                elif kind == "symbol-missing":
                    missing = ", ".join(v.get("missing") or [])
                    snap.facts.append(_fact_from_event(
                        ev, f"{path} 缺少符号: {missing}", "manifest"))
                elif kind in ("dangling-import", "imports-missing-declared-module"):
                    snap.facts.append(_fact_from_event(
                        ev, f"{path} 导入了不存在的模块 {v.get('import', '')}", "manifest"))

        elif ev.kind == "verify":
            ok = bool(p.get("passed"))
            detail = str(p.get("detail") or "")[:200]
            snap.facts.append(_fact_from_event(
                ev, f"验证命令 {'通过' if ok else '未通过'}: {detail}", "verify"))
            if not ok:
                h = _hash_reason(detail)
                key = f"verify::{h}"
                if key not in failure_index:
                    ff = FailureFact(
                        what="验证命令", reason=detail, reason_hash=h,
                        cycle_id=cycle_id, source=f"verify#{ev.seq}",
                        avoid="按失败细节定向修复，不要重复已做过且无效的动作",
                    )
                    failure_index[key] = ff
                    snap.failures.append(ff)

        elif ev.kind == "rollback":
            snap.facts.append(_fact_from_event(
                ev, f"已回退到检查点 {p.get('ref', '')}", "manifest"))

        elif ev.kind == "cycle_end":
            snap.status = p.get("status", "unknown")
            snap.commit = p.get("commit") or ""

    # 文件清单：把声明的与实测的合并
    existed = {}
    for ev in evs:
        for f in (ev.payload or {}).get("actual_files") or []:
            existed[f.get("path")] = f

    merged: list[FileFact] = []
    for path, ff in declared_paths.items():
        if path in existed:
            ff.status = "exists"
            ff.sha1 = existed[path].get("sha1", "")
        merged.append(ff)
    for path, info in existed.items():
        if path not in declared_paths:
            merged.append(FileFact(
                path=path, status="exists", sha1=info.get("sha1", ""),
                source="scan",
            ))
    snap.files = merged

    return snap


def reduce_all(events: Iterable[Event], limit_cycles: int = 20) -> dict[str, Snapshot]:
    """把事件流按 cycle 分组压缩。用于"架构跟踪"这类跨周期视角。"""
    order: list[str] = []
    for ev in events:
        if ev.cycle_id and ev.cycle_id not in order:
            order.append(ev.cycle_id)
    out: dict[str, Snapshot] = {}
    for cid in order[-limit_cycles:]:
        out[cid] = reduce_cycle(events, cid)
    return out


def _seq_of(failure) -> int:
    """从 FailureFact.source（形如 "verify@cyA#7"）解析出事件序号。

    FailureFact 本身不存 seq —— 它是按 reason_hash 去重后的产物。
    位置只能从 source 反解；解析不出就返回 0，由渲染层显示为「仅 cycle」，
    不允许编造一个看起来精确的位置。
    """
    m = re.search(r"#(\d+)\s*$", getattr(failure, "source", "") or "")
    return int(m.group(1)) if m else 0


def cross_cycle_failures(snapshots: dict[str, Snapshot], min_count: int = 2) -> list[dict]:
    """跨周期聚合反复出现的失败模式。

    这是「架构跟踪」的雏形：同一个 reason_hash 在多轮里反复出现，
    说明是系统性问题，而不是偶发。
    """
    agg: dict[str, dict] = {}
    for cid, snap in snapshots.items():
        for f in snap.failures:
            item = agg.setdefault(f.reason_hash, {
                "reason_hash": f.reason_hash,
                "reason": f.reason,
                "cycles": [],
                "total": 0,
                # 保留首条来源，便于反思层把证据指回具体事件
                "seq": _seq_of(f),
                "source": f.source,
            })
            item["total"] += f.count
            if cid not in item["cycles"]:
                item["cycles"].append(cid)

    recurring = [v for v in agg.values() if len(v["cycles"]) >= min_count]
    recurring.sort(key=lambda x: (-len(x["cycles"]), -x["total"]))
    return recurring
