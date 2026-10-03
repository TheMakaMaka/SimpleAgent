"""结局四值 + 判据来源进判定链（`TRANSPARENCY2-BACKEND` P1 / 工作单 D19）。

**为什么必须有 `abstain` 与 `invalid`**（统筹方原话）：

> 没有 `invalid`，"任务/判据写错了"会被记成"模型不行"，**污染整个能力画像**；
> 没有 `abstain`，用户要的「知道**不能做什么**」**无处安放**。

四值的含义（**这是"这台仪表读数是什么"的问题，不是"过没过"**）：

| 结局 | 含义 | 什么时候 |
|---|---|---|
| `pass` | 达成，且有判据为证 | verify 通过 |
| `fail` | **试过了，结论是没达成** | 代码崩了 / 判据没过 / 交付缺口 / 卡死 |
| `abstain` | **说不出"什么叫对"，或模型声明做不到** | 没有可用判据；判据全被拒；模型 blocked |
| `invalid` | **判据自己坏了 / 环境缺东西** —— 这次读数无效，不能算模型不行 | 判据语法错、引用不存在的符号、缺依赖、接线坏了 |

**判据来源进判定链（P1-b）**：模型自拟判据的"通过"与调用方判据的"通过"
**不得同形**。所以 `verdict` 里带 `criterion_source`（`caller`/`model`/空）
与 `criterion_trust`（`caller-authoritative`/`model-self-authored`/`none`）。
实测依据：39 条运行里**判据来自调用方的是 0 条** —— 这台仪表到今天没被真正用过，
所以"模型自拟"必须一眼可辨，否则能力画像里的通过率是虚的。
"""

from __future__ import annotations

OUTCOMES = ("pass", "fail", "abstain", "invalid")

#: 失败**原因种类** → 结局。每种都在 cycle 的某个分支上被显式设置，
#: 不靠猜错误字符串（字符串只用于**再细分** verify 失败的成因）。
KIND_TO_OUTCOME: dict[str, str] = {
    # —— 达成 ——
    "verified": "pass",
    # —— 试过了，没达成（算模型头上） ——
    "delivery-gap": "fail",          # 声明要产出但没产出/缺符号
    "code-broken": "fail",           # 语法/静态检查不过
    "reuse-violation": "fail",       # 交付物自身调用了不存在的符号等
    "verify-failed": "fail",         # 判据真跑过、真断言失败
    "no-tasks": "fail",              # 模型没给出可执行任务
    "stalled": "fail",               # 任务全被去重拒绝、原地打转
    "relaxed": "fail",               # 人工放宽验收（**没有验证通过**）
    # —— 说不出"什么叫对" / 自己声明做不到 ——
    "no-criterion": "abstain",           # 压根没有可机器判定的判据
    "no-admissible-criterion": "abstain",  # 有候选，但都不合格（不引用/不调用交付物等）
    "model-blocked": "abstain",          # 模型声明受阻
    # —— 判据/环境坏了：这次读数无效 ——
    "criterion-broken": "invalid",       # 判据自身语法错、引用不存在的符号
    "environment-missing": "invalid",    # 缺依赖（U7：应声明做不到，而不是硬写）
    "wiring": "invalid",                 # 有命令却没被执行（接线问题）
    # ★ P6（`TRANSPARENCY3-BACKEND`）：**判词必须描述产物**。
    # 验证时哈希 ≠ 交付时哈希 ⇒ 这次读数**无效** —— 不是模型失败。
    # 实测后果：两个任务报 `fail`，而归档产物是对的（离线重跑同一判据都 PASS）。
    "artifact-mismatch": "invalid",
    # ★ P17（`pass_evidence`）：**要记 pass，必须带机械证据**。
    # `checked_by=model` 且没有 `evidence_kind` ⇒ 这次"通过"只有模型自述，
    # 没有任何可复核的执行/产物事实 ⇒ **不得记 pass**。
    # 选 `invalid`（而不是 `abstain`）：读数本身不成立 —— 有判据、也"通过"了，
    # 但执行/证据链断了，属于**测量工装**的问题（与 `artifact-mismatch` 同族）。
    # 契约允许 `invalid` 或 `abstain`；这里取 `invalid` 并显式记下理由。
    "unsubstantiated-pass": "invalid",
}

#: 这些异常名出现在 verify 的 `detail` 里 → **判据自己坏了**（不是模型没做到）。
#: 依据：`standard §1.1 U7` / 工作单 P1-a「构造一次判据写错/环境缺依赖 → invalid」。
_CRITERION_BROKEN_MARKERS = ("SyntaxError", "IndentationError", "TabError")
_ENV_MISSING_MARKERS = ("ModuleNotFoundError", "ImportError")


def classify_verify_detail(detail: str) -> tuple[str, str]:
    """把 verify 的失败细节再细分成 **invalid / fail** 两种。

    返回 `(kind, why)`。判据自身写错或环境缺依赖 → 这次读数**无效**（invalid），
    不能记成"模型不行"。
    """
    text = str(detail or "")
    for m in _CRITERION_BROKEN_MARKERS:
        if m in text:
            return "criterion-broken", f"判据自身有语法错误（{m}）—— 这次读数无效"
    for m in _ENV_MISSING_MARKERS:
        if m in text:
            return "environment-missing", f"环境缺依赖（{m}）—— 这次读数无效"
    return "verify-failed", "判据执行了、断言没通过"


def outcome_of(kind: str) -> str:
    """原因种类 → 四值之一。未知种类**默认 fail**（不默认 pass，也不默认 abstain）。"""
    return KIND_TO_OUTCOME.get(str(kind or ""), "fail")


def criterion_trust(source: str, outcome: str) -> str:
    """判据的可信档位 —— 让"模型自拟判据通过"**一眼区别于**"调用方判据通过"。"""
    if outcome != "pass":
        return "none"
    if source == "caller":
        return "caller-authoritative"
    if source == "model":
        return "model-self-authored"
    return "none"


def build_verdict(
    kind: str, reason: str, verify: dict | None, *, extra: str = ""
) -> dict:
    """组装 `CycleReport.verdict` —— 结局 + 可读理由 + 判据来源档位。"""
    outcome = outcome_of(kind)
    source = str((verify or {}).get("source") or "")
    return {
        "outcome": outcome,
        "outcome_kind": str(kind or ""),
        "reason": str(reason or "")[:400],
        "criterion_source": source,
        "criterion_trust": criterion_trust(source, outcome),
        # 判据是不是**独立第三方**给的？自拟判据永远不是（P1-b 的核心）。
        "criterion_independent": source == "caller",
        "note": extra[:300],
    }


def is_success(outcome: str) -> bool:
    """只有 `pass` 算"达成"。`invalid` **不算**失败、也**不算**达成 —— 它是无效读数。"""
    return str(outcome or "") == "pass"
