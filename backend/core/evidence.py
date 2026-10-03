"""`P17`：**pass 的机械证据**（`checked_by` + `evidence_kind`）。

来源（用户 2026-10-03 定的这一轮目的 + 统筹方实测）
----------------------------------------------------

用户原话：**「在换模型之前，先把这些功能开发好，验证好边界，模型即插即用」**。
统筹方做了「即插即用」的机判标准（`SWAP-READY`，8 条），跑出来 **6/8**，
其中 **S3 = pass 必须有机械证据** 是红的：

    结局分布        : {"pass": 8, "invalid": 2, "fail": 1}
    真的跑过代码    : 4/11
    8 个 pass 里    : 只有 1 个有执行证据（T11）
    产出 self_report: 11/11

⇒ **换模型时，一个更爱自我宣称的模型会拿到更高的分** —— 那测的是它
**愿意怎么说话**，不是它**能不能做**。**读数不可比，即插即用在测量层就断了。**

三类证据（契约 `pass_evidence`，加性）
--------------------------------------

======================  ==========================================  ===========  ================================
`evidence_kind`         结构                                        `checked_by`  含义
======================  ==========================================  ===========  ================================
`executed`              `{command, exit_code, expect_exit?}`        `tool`       判据**真的被执行**，退出码被记录
`artifacts`             `[{path, sha256, size}]`                    `tool`       交付物在**输出根内**且哈希可核
`static_declared`       `{reason}`（必须有可复核理由）              `model`      静态交付物，调用方声明，无执行判据
======================  ==========================================  ===========  ================================

**硬规则（P17 要求 2）**：`checked_by == "model"` 且 `evidence_kind` 为空
⇒ **不得记 `pass`**（可记 `invalid` / `abstain`）。本模块只给判据，
不自己改结局 —— 由 `CodingCycle` 在**唯一的 pass 出口**上执行。

为什么要 `exit_code`
--------------------

`executed` 证据要求**退出码真的被记录**，而不是"有一条命令就算执行过"。
判词必须描述产物（P6 同族）：没有退出码的 `passed=True` 说明**执行事实缺失**，
那正是本次要拦的形状。真实 `CheckPipeline.run_verify` 走 `check_and_run`，
成功时必然带 `exit_code`；因此这条判据在正常路径上恒真，
**只有在执行记录缺失时才变红**（`tests/unit/test_pass_evidence.py` 构造的就是这一向）。

`artifacts` 为什么必须在**输出根**内
------------------------------------

与 `P14` 一致：工作区是草稿区（可以乱），**输出根是交付物该去的地方**，
所以只有落在输出根里的产物才能充当"交付证据"。落在工作区/目标根里的产物
**不丢弃**，而是逐条记进 `excluded_artifacts` 并写明理由 ——
「没算证据」与「没看见」不是一回事。
"""

from __future__ import annotations

#: 允许的证据类别（契约载荷）。
EVIDENCE_KINDS: tuple[str, ...] = ("executed", "artifacts", "static_declared")

#: 谁给的证据：`tool` = 程序测出来的；`model` = 模型/调用方声明的。
CHECKED_BY: tuple[str, ...] = ("tool", "model")

#: 拒绝 pass 时用的原因种类（在 `core.outcome.KIND_TO_OUTCOME` 里登记为 `invalid`）。
UNSUBSTANTIATED_KIND = "unsubstantiated-pass"


def _as_int(value):
    """能转 int 就转，否则 None（**不把缺值当 0** —— 那会把缺失伪装成事实）。"""
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _artifact_rows(deliverables: dict | None) -> list[dict]:
    """把 `P14` 的 `deliverables.actual` 归一成带 `abs_path` 的行。"""
    rows: list[dict] = []
    for item in (deliverables or {}).get("actual") or []:
        if not isinstance(item, dict):
            continue
        rows.append({
            "path": str(item.get("path") or ""),
            "exists": bool(item.get("exists")),
            "sha256": item.get("sha256"),
            "size": item.get("size"),
            "root": item.get("root") or "",
            "abs_path": str(item.get("abs_path") or ""),
        })
    return rows


def build_evidence(
    verify: dict | None,
    deliverables: dict | None,
    *,
    static_reason: str = "",
) -> dict:
    """从**机械事实**里抽出这次 pass 的证据。

    优先级（强 → 弱）：`executed` → `artifacts` → `static_declared`。
    找不到任何可复核证据时返回 `checked_by="model"` + 空 `evidence_kind`
    （由 `pass_allowed()` 拒绝），并把**为什么找不到**写进 `problems`。
    """
    verify = verify or {}
    out: dict = {
        "checked_by": "model",
        "evidence_kind": "",
        "executed": None,
        "artifacts": [],
        "static_declared": None,
        "excluded_artifacts": [],
        "problems": [],
        "note": "",
    }

    # ---------- ① executed：判据真的被执行，且退出码被记录 ----------
    command = str(verify.get("command") or "").strip()
    exit_code = _as_int(verify.get("exit_code"))
    passed = bool(verify.get("passed"))
    if passed and command and exit_code is not None:
        out["checked_by"] = "tool"
        out["evidence_kind"] = "executed"
        out["executed"] = {
            "command": command[:500],
            "exit_code": exit_code,
            "expect_exit": _as_int(verify.get("expect_exit")),
            # 判据来源（caller/model）只作事实留痕：它说明"这条判据是谁写的"，
            # 不改变"它真的被执行过"这个机械事实。
            "criterion_source": str(verify.get("source") or ""),
        }
        out["note"] = ("判据真的被执行（退出码已记录）—— 这是最强的一类机械证据")
        return out
    if passed and command and exit_code is None:
        out["problems"].append(
            "verify 通过，但**执行记录里没有退出码**（exit_code 缺失）"
            "—— 无法证明它真的被执行过"
        )
    if passed and not command:
        out["problems"].append("verify 通过，但**没有命令**记录")

    # ---------- ② artifacts：交付物落在输出根内且哈希可核 ----------
    from . import runtime

    out_root = runtime.output_root()
    kept: list[dict] = []
    excluded: list[dict] = []
    for row in _artifact_rows(deliverables):
        if not row["exists"]:
            continue
        item = {"path": row["path"], "sha256": row["sha256"], "size": row["size"]}
        within = bool(row["abs_path"]) and runtime.is_within(row["abs_path"], out_root)
        if not within:
            excluded.append({**item, "reason": "out-of-output-root",
                             "message": f"产物不在输出根内（{out_root}）"})
        elif not row["sha256"]:
            excluded.append({**item, "reason": "missing-hash",
                             "message": "产物没有内容哈希，无法核对"})
        else:
            kept.append(item)
    out["excluded_artifacts"] = excluded
    if kept:
        out["checked_by"] = "tool"
        out["evidence_kind"] = "artifacts"
        out["artifacts"] = kept
        out["note"] = "交付物在输出根内、内容哈希可核 —— 这类证据来自磁盘事实"
        return out
    if excluded:
        out["problems"].append(
            f"有 {len(excluded)} 个产物存在，但都不在输出根内 / 无哈希，"
            "不能充当交付证据（已逐条记进 excluded_artifacts）"
        )

    # ---------- ③ static_declared：静态交付物，必须有可复核理由 ----------
    reason = str(static_reason or "").strip()
    if reason:
        out["checked_by"] = "model"
        out["evidence_kind"] = "static_declared"
        out["static_declared"] = {"reason": reason[:300]}
        out["note"] = ("这是一次**声明式**通过（没有可执行的机械判据）；"
                       "理由必须可复核，否则不算证据")
        return out

    out["note"] = ("没有任何可复核证据：没有执行记录、没有输出根内的产物、"
                   "也没有声明式的可复核理由 —— 不得记 pass")
    return out


def pass_allowed(evidence: dict | None) -> tuple[bool, str]:
    """P17 的硬判据：这份证据能不能支撑一次 `pass`？

    返回 `(allowed, why)`。拒绝时 `why` 必须能读、能定位（不写"未知原因"）。
    """
    ev = evidence or {}
    kind = str(ev.get("evidence_kind") or "")
    checked = str(ev.get("checked_by") or "")

    if kind in EVIDENCE_KINDS:
        # 类别结构必须齐全 —— "声明了类别" ≠ "结构真的有"。
        if kind == "executed":
            ex = ev.get("executed") or {}
            if ex.get("command") and ex.get("exit_code") is not None:
                return True, ""
            return False, "evidence_kind=executed 但缺少 command / exit_code"
        if kind == "artifacts":
            if ev.get("artifacts"):
                return True, ""
            return False, "evidence_kind=artifacts 但 artifacts 为空"
        # static_declared
        sd = ev.get("static_declared") or {}
        if str(sd.get("reason") or "").strip():
            return True, ""
        return False, "evidence_kind=static_declared 但缺少可复核的理由（reason）"

    # ★ 硬规则：模型声明、又没有任何证据类别 ⇒ 不得 pass。
    if checked == "model" and not kind:
        return False, (
            "checked_by=model 且没有 evidence_kind ⇒ 只有模型自述、"
            "没有任何机械证据，不得记 pass"
        )
    return False, f"没有可识别的 evidence_kind（得到 {kind!r}）"


def summarize(evidence: dict | None) -> str:
    """一行可读摘要（进日志用），让"这次 pass 靠什么"一眼可见。"""
    ev = evidence or {}
    kind = str(ev.get("evidence_kind") or "(无)")
    checked = str(ev.get("checked_by") or "?")
    if kind == "executed":
        ex = ev.get("executed") or {}
        return (f"checked_by={checked} kind=executed "
                f"exit_code={ex.get('exit_code')} command={str(ex.get('command'))[:60]!r}")
    if kind == "artifacts":
        return (f"checked_by={checked} kind=artifacts "
                f"n={len(ev.get('artifacts') or [])}")
    if kind == "static_declared":
        return f"checked_by={checked} kind=static_declared"
    return f"checked_by={checked} kind=(无) problems={ev.get('problems') or []}"


def describe() -> dict:
    """契约面（`/profile` 暴露），让"pass 靠什么"变成**可读事实**而不是约定。"""
    from datetime import datetime

    return {
        "required_on_pass": ["checked_by", "evidence_kind"],
        "checked_by": list(CHECKED_BY),
        "evidence_kinds": {
            "executed": ("{command, exit_code, expect_exit?}；checked_by=tool；"
                         "退出码必须被记录（没有退出码 = 执行事实缺失）"),
            "artifacts": ("[{path, sha256, size}]；checked_by=tool；"
                          "路径必须在输出根内（与 P14 一致）"),
            "static_declared": ("{reason}；checked_by=model；"
                                "reason 必须可复核，否则不算证据"),
        },
        "gate": ("checked_by==model 且无 evidence_kind ⇒ 不得记 pass"
                 f"（记 invalid/{UNSUBSTANTIATED_KIND}）"),
        "why": ("换模型时若 pass 不区分证据，**更爱自我宣称的模型会拿到更高的分**"
                "—— 读数不可比，即插即用在测量层就断了"),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
