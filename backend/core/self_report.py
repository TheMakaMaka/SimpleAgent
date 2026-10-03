"""收尾自述的**交叉核对**（`TRANSPARENCY-BACKEND` C1/C2）。

为什么单独一个模块
------------------
自述如果不被核对，它就是**第二个"模型自嗨"通道**：一份漂亮的总结会让
"没做"看起来像"做了"（统筹方原话：「没有 C2，`self_report` 就是第二个自嗨通道」）。

触发它的真实运行：用户那条"保证连通 / 连续测试验证 / 生成报告"的指令报了
`status=passed`，而机械事实是**没跑过测试、没有报告、有个 `np` 未定义的文件**。

设计纪律
--------
1. **只做可判定的对照**：把自述里的 `claims` 与机械事实**逐条相等比较**，
   不做语义相似、不做关键词猜测 —— 猜测会把核对本身变成又一个不可信环节。
2. **绝不改判 cycle 结果**：它是**报告**，不是门禁。核对出的矛盾只进
   `self_report.fact_check`，不改 `phase`、不改 `verify`、不改 `commit`。
   （唯一例外是它自己明确的失败：自述生成失败会记 `ok=false`，同样不改判定。）
3. **矛盾要能直接读**：每条含"自述说了什么 / 机械事实是什么 / 差在哪"。
"""

from __future__ import annotations

import os
from typing import Any

#: 自述的必需字段（缺哪条就在 `fact_check.missing_fields` 里点名）。
REQUIRED_FIELDS = (
    "done", "not_done", "why", "reflections", "approach",
    "confidence", "open_questions",
)

#: 每条 requirement 的合法状态。
REQUIREMENT_STATUS = ("done", "not_done", "unknown")


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return [v for v in value if v not in (None, "")]
    if value in (None, ""):
        return []
    return [value]


def normalize(raw: Any) -> dict:
    """把模型输出规整成固定形状 —— 缺字段**补空**，不做语义推断。"""
    src = raw if isinstance(raw, dict) else {}
    conf = src.get("confidence")
    if not isinstance(conf, dict):
        conf = {"level": str(conf or "unknown"), "basis": ""}
    reqs: list[dict] = []
    for item in _as_list(src.get("requirements")):
        if isinstance(item, dict):
            text = str(item.get("text") or "").strip()
            status = str(item.get("status") or "").strip().lower()
            if status not in REQUIREMENT_STATUS:
                status = "unknown"
            reqs.append({
                "text": text,
                "status": status,
                "evidence": str(item.get("evidence") or "")[:300],
            })
        elif isinstance(item, str) and item.strip():
            reqs.append({"text": item.strip(), "status": "unknown", "evidence": ""})
    claims = src.get("claims")
    if not isinstance(claims, dict):
        claims = {}
    return {
        "done": [str(x)[:300] for x in _as_list(src.get("done"))],
        "not_done": [str(x)[:300] for x in _as_list(src.get("not_done"))],
        "why": [str(x)[:300] for x in _as_list(src.get("why"))],
        "reflections": [str(x)[:300] for x in _as_list(src.get("reflections"))],
        "approach": [str(x)[:300] for x in _as_list(src.get("approach"))],
        "confidence": {
            "level": str(conf.get("level") or "unknown")[:20],
            "basis": str(conf.get("basis") or "")[:300],
        },
        "open_questions": [str(x)[:300] for x in _as_list(src.get("open_questions"))],
        "requirements": reqs[:20],
        "claims": {
            "verify_passed": claims.get("verify_passed", None),
            "check_passed": claims.get("check_passed", None),
            "artifacts": [str(x).replace("\\", "/")[:200]
                          for x in _as_list(claims.get("artifacts"))][:20],
        },
    }


def fact_check(self_report: dict, facts: dict) -> dict:
    """把自述与机械事实逐条对照，返回 `fact_check` 结构。

    `facts` 由 `CodingCycle._machine_facts()` 提供，字段：
        workspace_files / touched_files / manifest_actual / manifest_declared
        verify / check / lint_failed / phase
    """
    contradictions: list[dict] = []
    notes: list[str] = []

    sr = self_report or {}
    on_disk = {p.replace("\\", "/") for p in (facts.get("workspace_files") or [])}
    known = on_disk | {p.replace("\\", "/") for p in (facts.get("manifest_actual") or [])} \
        | {p.replace("\\", "/") for p in (facts.get("touched_files") or [])}
    verify = facts.get("verify") or None
    check = facts.get("check") or {}
    lint_failed = facts.get("lint_failed") or []

    def contradict(kind: str, claim: str, fact: str, severity: str = "high") -> None:
        contradictions.append({
            "kind": kind, "claim": claim, "fact": fact, "severity": severity,
        })

    # ---------- 1. 自称产出的文件是否真在磁盘上 ----------
    for path in (sr.get("claims") or {}).get("artifacts") or []:
        if path not in known:
            contradict(
                "artifact-missing",
                f"自述声称已产出 `{path}`",
                f"磁盘/清单里没有这个文件（实际存在：{sorted(known)[:5]}）",
            )
        else:
            notes.append(f"`{path}` 确实在磁盘上")

    # ---------- 2. 自述的 verify 断言 vs 机械结论 ----------
    claimed_v = (sr.get("claims") or {}).get("verify_passed")
    actual_v = None if verify is None else bool(verify.get("passed"))
    if claimed_v is not None:
        if actual_v is None:
            contradict(
                "verify-claim-vs-fact",
                f"自述声称 verify_passed={claimed_v}",
                "本轮**没有验证结论**（verify=None）—— 无从通过",
            )
        elif bool(claimed_v) != actual_v:
            contradict(
                "verify-claim-vs-fact",
                f"自述声称 verify_passed={claimed_v}",
                f"实际 verify.passed={actual_v}"
                f"（detail: {str((verify or {}).get('detail'))[:120]}）",
            )
        else:
            notes.append(f"verify 断言与事实一致（passed={actual_v}）")

    # ---------- 3. 自述的 check 断言 vs 机械事实（含 lint） ----------
    claimed_c = (sr.get("claims") or {}).get("check_passed")
    check_status = str(check.get("status") or "unknown")
    if claimed_c is not None:
        if bool(claimed_c) and check_status == "skipped":
            contradict(
                "check-claim-vs-fact",
                "自述声称「检查通过」",
                "本轮**静态检查根本没跑**（check.status=skipped：没有 .py 改动）",
                severity="medium",
            )
        elif bool(claimed_c) and check_status == "failed":
            contradict(
                "check-claim-vs-fact",
                "自述声称「检查通过」",
                "实际 check.status=failed",
            )
        elif bool(claimed_c) != (check_status == "passed"):
            contradict(
                "check-claim-vs-fact",
                f"自述声称 check_passed={claimed_c}",
                f"实际 check.status={check_status}",
                severity="medium",
            )
        else:
            notes.append(f"check 断言与事实一致（status={check_status}）")
    # lint 非阻塞，但"说检查通过"在实质上仍是误导 —— 单列一条
    if lint_failed and (claimed_c or (sr.get("done") and not sr.get("not_done"))):
        contradict(
            "lint-failed-not-disclosed",
            "自述给人以「检查通过」的印象",
            f"lint 有 {len(lint_failed)} 处 failed（非阻塞，故 check.passed=true）："
            + "; ".join(str(x)[:80] for x in lint_failed[:3]),
            severity="medium",
        )

    # ---------- 4. 目标要求是否被提及 ----------
    unmentioned: list[str] = []
    for i, req in enumerate(sr.get("requirements") or [], 1):
        text = str(req.get("text") or "").strip()
        if not text:
            continue
        status = str(req.get("status") or "unknown")
        if status == "unknown":
            unmentioned.append(f"要求 {i}（{text[:80]}）：既没写成 done 也没写成 not_done")
            continue
        # status=done 的必须有其 evidence 指向的东西确实存在（若指名了文件）
        ev = str(req.get("evidence") or "")
        for token in _paths_in(ev):
            if token not in known:
                contradict(
                    "requirement-evidence-missing",
                    f"要求 {i} 的自述状态是 done，证据指向 `{token}`",
                    "磁盘/清单里没有这个文件",
                )

    # ---------- 5. 自称 done 的文字里点名的文件必须存在 ----------
    for item in sr.get("done") or []:
        for token in _paths_in(item):
            if token not in known:
                contradict(
                    "done-mentions-missing-file",
                    f"done 里提到 `{token}`",
                    "磁盘/清单里没有这个文件",
                )

    missing_fields = [f for f in REQUIRED_FIELDS if f not in (sr or {})]

    return {
        "checked": True,
        "contradictions": contradictions[:20],
        "unmentioned": unmentioned[:10],
        "notes": notes[:10],
        "missing_fields": missing_fields,
        "facts": {
            "phase": facts.get("phase"),
            "verify_passed": actual_v,
            "verify_source": (verify or {}).get("source") if verify else None,
            "check_status": check_status,
            "lint_failed": len(lint_failed),
            "workspace_files": sorted(on_disk)[:20],
        },
    }


def _paths_in(text: str) -> list[str]:
    """从一句自述里挑出**看起来是文件路径**的片段（用于核对存在性）。

    这是本模块唯一的"猜"，但它的用途是**只增不漏**：猜出来的东西如果不在磁盘上，
    就报一条矛盾；猜错的最坏后果是**多报一条**（不会漏报）。所以这里刻意宽松。
    """
    import re

    out: list[str] = []
    for m in re.finditer(r"[A-Za-z0-9_./\\-]+\.[A-Za-z0-9]{1,5}\b", text or ""):
        token = m.group(0).replace("\\", "/").lstrip("./")
        if token and token not in out:
            out.append(token)
    return out


def exists_in_workspace(rel: str, workspace_dir: str) -> bool:
    """磁盘核对（路径必须落在 workspace 内，防越界）。"""
    norm = (rel or "").replace("\\", "/").lstrip("/")
    if not norm or ".." in norm.split("/"):
        return False
    return os.path.exists(os.path.join(workspace_dir, norm))
