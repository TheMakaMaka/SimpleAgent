"""两路召回 + **可解释的确定性记分**（P21 / M1 —— 只记分，不决策）。

统筹方 §P21 的三条硬要求逐条对应本模块：

| 硬要求 | 落点 |
|---|---|
| ① 判据要覆盖**漏召 / 误召**，不能只看「调用成功」 | `calibrate()` 算 recall / miss_rate / false_recall_rate，**并逐条列出漏了谁、误召了谁** |
| ② 必须有**第二路召回**，挂在已有结构索引上 | `symbol_hits()` 走 `unit["symbol_refs"]`；M2/M3 拿同一份引用去问 `find_symbol`/`get_module`/`get_architecture`，**不另起关键词库** |
| ③ 阈值第一阶段**不许定死**：只记分、不决策 | `recall()` 返回**全部**带 `score` 的单元，**没有阈值参数**；`calibrate()` 只给分数分布与候选阈值曲线 |

★ 2026-10-05 载荷新增的**第四条硬要求**（`WORK-ORDER.md`【P21】★★）——
「**调用分算法必须与模型无关**」，本模块逐条落地：

| 第四条硬要求 | 落点 |
|---|---|
| 1 **打分必须是纯函数** `score(unit, query_context) -> float`，不得调用任何模型 | `score()` 就是唯一入口（**恰好两个形参**）；配置权重走 `query_context["config"]`；全包**不 import** 任何模型/网络模块（AST 判据见单测） |
| 2 **打分必须可复现**：同输入两次**逐位相同** | 无时钟读取（`now` 必须**显式**给，不给 ⇒ 衰减关闭）；无随机、无环境依赖；分数 `round(...,9)` |
| 3 **分数要可解释** | `score_breakdown()` 给**四项构成**：`lexical`（词法命中）/ `symbol`（符号命中）/ `time_decay`（时间衰减）/ `custom`（定制加权），**四项之和 == 总分** |
| 4 **"定制化需求加权"走显式配置** | `config["custom"]` = `[{why, add, when}]`：**谁（why）在什么条件下（when）加多少（add）**；未知条件键**结构化拒绝**，不静默忽略 |
| 5 **校准过程本身必须可复现** | `calibrate()` 记录 `samples_sha256` + `config_sha256` + `curve_sha256` ⇒ 同样本同配置必得同曲线 |

★ scorer 的身份是**读数的一部分**（★★★：「**scorer 的选择必须进 `basis`**（与 `model` 并列）」）：
本模块只实现 **`S-A`（确定性）**这一条基线臂，`basis = {"scorer": "S-A", "model": None}`。
`S-B`（固定嵌入模型）/ `S-C`（LLM 打分）是 **M2 的对照臂**，本模块**刻意不实现**
（S-B 要引新依赖、S-C 要调模型，都超出 M1「不接模型」的边界）—— 这一点在
`describe()["scorer"]["arms"]` 里如实写出来，不假装已有。

★ 为什么符号路算「第二路」而不是「第三个关键词库」（统筹方硬要求 2）：
它消费的是 **P11 已经可信化的结构索引**（`tools/arch.py` 的 `find_symbol` /
`get_module` / `get_architecture`），原料是同一份 `symbol_refs`，
**没有新建任何词表 / 向量库 / 相似度模型**。
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime

from . import units as units_mod

#: scorer 身份（★★★：这个字符串要进 `basis`，与 `model` 并列）。
SCORER_ID = "S-A"
SCORER_KIND = "deterministic"

#: 分数权重（**公开常量，便于 M2 校准时只改这一处**）。
#: 符号命中权重 > 关键词命中：符号是结构事实，词面只是近似。
W_KEYWORD = 0.5
W_SYMBOL = 0.4

#: 关键词命中的两种形态的权重（显式关键词 > 正文子串）。
K_DECLARED = 1.0
K_CONTENT = 0.6

#: 候选阈值曲线的扫描步长（**只用于给出候选**，不作为决策）。
THRESHOLD_STEP = 0.05

#: 分数保留几位小数。存在的理由只有一个：**浮点也要逐位可复现**。
SCORE_DP = 9

#: 默认配置（**显式**：谁能改权重、时间衰减、定制加权，全在这张表里）。
#:
#: ★ `time_decay.half_life_days = None` 是**刻意**的：时间衰减的"半衰期"是一个
#: 阈值类参数，第一阶段没有数据不许拍（硬要求 3）。默认**关闭**（贡献恒为 0.0），
#: 由 M2 用标注数据校准后再启用。
DEFAULT_CONFIG: dict = {
    "weights": {"lexical": W_KEYWORD, "symbol": W_SYMBOL},
    "lexical": {"declared": K_DECLARED, "content": K_CONTENT},
    "time_decay": {"half_life_days": None, "min_factor": 0.0},
    "custom": [],
}

#: 定制加权规则允许的匹配键（未知键**结构化拒绝**，不静默忽略）。
CUSTOM_MATCH_KEYS = ("id", "source", "keyword", "symbol", "content_contains")


# ---------------------------------------------------------------------------
# 配置：显式、可校验、可哈希（第 4 条硬要求的地基）
# ---------------------------------------------------------------------------
def _num(value, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{what} 必须是数字，收到 {type(value).__name__}")
    return float(value)


def _validate(cfg: dict) -> None:
    """把「配置写错」变成**结构化拒绝**，而不是悄悄用一个默认值。"""
    for group in ("weights", "lexical"):
        for key, value in cfg[group].items():
            _num(value, f"config[{group}][{key}]")
    td = cfg["time_decay"]
    hl = td["half_life_days"]
    if hl is not None:
        hl = _num(hl, "config[time_decay][half_life_days]")
        if hl <= 0:
            raise ValueError("config[time_decay][half_life_days] 必须 > 0（或 None=关闭）")
    mn = _num(td["min_factor"], "config[time_decay][min_factor]")
    if not 0.0 <= mn <= 1.0:
        raise ValueError("config[time_decay][min_factor] 必须落在 [0, 1]")
    for i, rule in enumerate(cfg["custom"]):
        where = f"config[custom][{i}]"
        if not isinstance(rule, dict):
            raise ValueError(f"{where} 必须是对象")
        if set(rule) - {"why", "add", "when"}:
            raise ValueError(f"{where} 出现未声明键 {sorted(set(rule) - {'why', 'add', 'when'})}")
        if not str(rule.get("why") or "").strip():
            raise ValueError(f"{where}.why 必填（'谁在什么条件下加多少'里的『谁』不许省）")
        _num(rule.get("add"), f"{where}.add")
        when = rule.get("when")
        if not isinstance(when, dict) or not when:
            raise ValueError(f"{where}.when 必须是非空对象")
        unknown = sorted(set(when) - set(CUSTOM_MATCH_KEYS))
        if unknown:
            raise ValueError(f"{where}.when 出现未声明条件键 {unknown}（可用 {list(CUSTOM_MATCH_KEYS)}）")
        for key, wanted in when.items():
            if isinstance(wanted, str) or not isinstance(wanted, (list, tuple)):
                raise ValueError(f"{where}.when[{key}] 必须是列表")
            if not wanted:
                raise ValueError(f"{where}.when[{key}] 不能是空列表")


def canonical_config(config: dict | None = None) -> dict:
    """把（可选的）局部覆盖合并进默认配置并校验，返回**规范化**配置。

    规范化 = 只含声明过的键、值都是 JSON 原生类型 ⇒ 可 `json.dumps` 哈希
    （校准记录里的 `config_sha256` 就取自这里）。
    """
    cfg = {
        "weights": dict(DEFAULT_CONFIG["weights"]),
        "lexical": dict(DEFAULT_CONFIG["lexical"]),
        "time_decay": dict(DEFAULT_CONFIG["time_decay"]),
        "custom": [],
    }
    if config:
        for group in ("weights", "lexical", "time_decay"):
            override = config.get(group)
            if override is not None:
                if not isinstance(override, dict):
                    raise ValueError(f"config[{group}] 必须是对象")
                unknown = sorted(set(override) - set(cfg[group]))
                if unknown:
                    raise ValueError(f"config[{group}] 出现未声明键 {unknown}")
                cfg[group].update(override)
        if config.get("custom") is not None:
            cfg["custom"] = [dict(rule) for rule in config["custom"]]
    _validate(cfg)
    return cfg


def _canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def config_sha256(config: dict | None = None) -> str:
    """配置指纹：**同一份配置 ⇒ 同一个哈希**（校准过程可复现的判据之一）。"""
    return hashlib.sha256(_canonical_json(canonical_config(config)).encode("utf-8")).hexdigest()


def _round(value: float) -> float:
    out = round(float(value), SCORE_DP)
    return 0.0 if out == 0 else out


# ---------------------------------------------------------------------------
# 两路召回的原料
# ---------------------------------------------------------------------------
def document_frequency(units: list[dict], terms: dict[str, list[str]]) -> dict[str, int]:
    """每个词命中了多少个单元（`df`）。

    为什么需要：一个词在库里越常见，它越没有区分度（`df=10/10` 的「代码」不该
    和只出现过一次的「auth_token」同权）。这是 **idf 的原料**，
    也是 M2「分数 + 事后判定」落盘时要一起记的事实。
    """
    df: dict[str, int] = {}
    for term in terms:
        n = 0
        for unit in units:
            if term in (unit.get("keywords") or []):
                n += 1
            elif term in str(unit.get("content") or "").lower():
                n += 1
        df[term] = n
    return df


def keyword_hits(unit: dict, terms: dict[str, list[str]],
                 df: dict[str, int], total: int, weights: dict | None = None) -> dict:
    """关键词路：对**每一个**查询词各判一次命中（逐条留痕，便于诊断漏召）。

    纯函数（不改 `unit`）：`why` 作为返回值带回，由 `recall` 决定怎么用。
    """
    w_declared = float((weights or {}).get("declared", K_DECLARED))
    w_content = float((weights or {}).get("content", K_CONTENT))
    kw = set(unit.get("keywords") or [])
    content = str(unit.get("content") or "").lower()
    hit_terms: list[str] = []
    why: dict[str, str] = {}
    score = 0.0
    for term, forms in terms.items():
        forms = [f for f in forms if f]
        if not forms:
            continue
        if term in kw:
            w, how = w_declared, "declared-keyword"
        elif any(f in content for f in forms):
            w, how = w_content, "content-substring"
        else:
            continue
        idf = math.log(1.0 + total / (1.0 + df.get(term, 0)))
        score += w * idf
        hit_terms.append(term)
        why[term] = how
    return {"score": score, "terms": hit_terms, "why": why}


def symbol_hits(unit: dict, symbols: list[str]) -> dict:
    """符号路：查询里的标识符命中单元的 `symbol_refs`（结构引用，不是词面）。"""
    refs = set(unit.get("symbol_refs") or [])
    hits = [s for s in symbols if s and s in refs]
    return {
        "score": float(len(hits)),
        "symbols": hits,
        # M2/M3 的接入点：拿这些名字去问结构索引「它定义在哪」。
        # M1 **不查索引**（独立库、不接主链路），只把原料如实带出来。
        "structure_lookup": {"symbols": hits, "via": "find_symbol|get_module|get_architecture"},
    }


def _query_terms(query: str) -> dict[str, list[str]]:
    """把查询拆成 `{归一化词: [原始形态…]}`。

    原始形态保留是为了「中文短语整体匹配」：归一化后的词在正文里以子串出现
    就算命中（中英混排时不做分词，宁可宽一点，再由分数区分）。
    """
    raw = units_mod._WORD_RE.findall(str(query or ""))
    out: dict[str, list[str]] = {}
    for token in raw:
        low = token.lower()
        if low in units_mod._STOPWORDS:
            continue
        out.setdefault(low, [])
        if token not in out[low]:
            out[low].append(token)
    return out


def _parse_ts(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# 第 3 条硬要求：分数构成四项 —— 时间衰减 / 定制加权
# ---------------------------------------------------------------------------
def time_decay_factor(created_at, now, config: dict | None = None) -> dict:
    """时间衰减因子（**纯函数**：`now` 必须由调用方显式给，不许自己读时钟）。

    ★ 为什么把 `now` 做成显式输入：如果打分函数自己调 `datetime.now()`，
    那么「同一输入两次调用」就不再逐位相同（第 2 条硬要求直接不成立），
    而且**换模型对比时会混入"跑的时刻不同"这个变量**。

    返回 `{factor, applied, age_days, half_life_days, why}`。
    """
    cfg = canonical_config(config)
    td = cfg["time_decay"]
    hl = td["half_life_days"]
    if hl is None:
        return {"factor": 1.0, "applied": False, "age_days": None,
                "half_life_days": None, "why": "half_life_days=None ⇒ 衰减关闭（参数未校准）"}
    if not now or not created_at:
        return {"factor": 1.0, "applied": False, "age_days": None,
                "half_life_days": float(hl), "why": "缺 created_at 或 now ⇒ 不衰减"}
    created, nowdt = _parse_ts(created_at), _parse_ts(now)
    if created is None or nowdt is None:
        return {"factor": 1.0, "applied": False, "age_days": None,
                "half_life_days": float(hl), "why": "时刻解析失败 ⇒ 不衰减"}
    try:
        age_days = (nowdt - created).total_seconds() / 86400.0
    except TypeError:
        # 一个带时区、一个不带 —— 这本身是调用方的事实错误，如实标注而不是猜。
        return {"factor": 1.0, "applied": False, "age_days": None,
                "half_life_days": float(hl), "why": "时区形态不一致 ⇒ 不衰减（请统一 ISO 形态）"}
    if age_days <= 0:
        return {"factor": 1.0, "applied": True, "age_days": round(age_days, 6),
                "half_life_days": float(hl), "why": "未过期（age<=0）"}
    factor = max(float(td["min_factor"]), 0.5 ** (age_days / float(hl)))
    return {"factor": _round(factor), "applied": True, "age_days": round(age_days, 6),
            "half_life_days": float(hl), "why": f"0.5 ** (age/{hl})，下限 min_factor"}


def _rule_matches(unit: dict, when: dict) -> bool:
    """一条定制规则是否命中：`when` 里**每个**键都要满足（键内是"任一"）。"""
    for key, wanted in when.items():
        if key == "id":
            if str(unit.get("id") or "") not in {str(x) for x in wanted}:
                return False
        elif key == "source":
            if str(unit.get("source") or "") not in {str(x) for x in wanted}:
                return False
        elif key == "keyword":
            have = {str(x).lower() for x in (unit.get("keywords") or [])}
            if not have & {str(x).lower() for x in wanted}:
                return False
        elif key == "symbol":
            have = {str(x) for x in (unit.get("symbol_refs") or [])}
            if not have & {str(x) for x in wanted}:
                return False
        elif key == "content_contains":
            content = str(unit.get("content") or "").lower()
            if not any(str(x).lower() in content for x in wanted):
                return False
    return True


def custom_bonus(unit: dict, config: dict | None = None) -> dict:
    """定制化需求加权：**完全由显式配置决定**，模型没有发言权。

    规则形如 `{"why": "用户定制：T9 相关记忆加权", "add": 0.25,
    "when": {"source": ["T9"]}}` —— 「谁 / 在什么条件下 / 加多少」三件都在配置里，
    可 JSON 序列化、可哈希、可复核。
    """
    cfg = canonical_config(config)
    matched: list[dict] = []
    total = 0.0
    for rule in cfg["custom"]:
        if _rule_matches(unit, rule["when"]):
            add = float(rule["add"])
            matched.append({"why": str(rule["why"]), "add": add, "when": dict(rule["when"])})
            total += add
    return {"add": _round(total), "matched": matched}


# ---------------------------------------------------------------------------
# 第 1/2/3 条硬要求：唯一打分入口（纯函数、可复现、可解释）
# ---------------------------------------------------------------------------
def score_breakdown(unit: dict, query_context: dict) -> dict:
    """**唯一**的打分实现：返回总分 + 四项构成 + 逐项理由。

    `query_context`（全部是显式输入，函数不读任何全局状态）：

      `query`    查询正文（未拆词时用）
      `terms`    预拆好的 `{词: [原始形态…]}`（可选；给了就不再拆）
      `symbols`  查询里的符号
      `df`/`total`  语料事实（idf 需要）
      `now`      显式时刻（`None` ⇒ 时间衰减不生效）—— **不许读时钟**
      `config`   配置权重（可选；缺省 = `DEFAULT_CONFIG`）

    `parts` 四项**相加等于总分**：`lexical + symbol + time_decay + custom`。
    """
    if not isinstance(query_context, dict):
        raise ValueError("query_context 必须是对象")
    cfg = canonical_config(query_context.get("config"))
    terms = query_context.get("terms")
    if terms is None:
        terms = _query_terms(query_context.get("query", ""))
    symbols = [str(s).strip() for s in (query_context.get("symbols") or []) if str(s).strip()]
    df = query_context.get("df") or {}
    try:
        total = max(1, int(query_context.get("total") or 1))
    except (TypeError, ValueError):
        total = 1

    kw = keyword_hits(unit, terms, df, total, weights=cfg["lexical"])
    sym = symbol_hits(unit, symbols)

    lexical = _round(float(cfg["weights"]["lexical"]) * kw["score"])
    symbol = _round(float(cfg["weights"]["symbol"]) * sym["score"])
    base = lexical + symbol

    decay = time_decay_factor(unit.get("created_at"), query_context.get("now"), cfg)
    time_decay = _round(base * (decay["factor"] - 1.0))   # ≤ 0，是"被衰减掉的量"
    custom = custom_bonus(unit, cfg)

    parts = {
        "lexical": lexical,
        "symbol": symbol,
        "time_decay": time_decay,
        "custom": custom["add"],
    }
    total_score = _round(lexical + symbol + time_decay + custom["add"])

    return {
        "id": unit.get("id"),
        "score": total_score,
        "parts": parts,
        "detail": {
            "lexical": {"terms": kw["terms"], "why": kw["why"], "raw": _round(kw["score"])},
            "symbol": {"symbols": sym["symbols"], "raw": _round(sym["score"]),
                       "structure_lookup": sym["structure_lookup"]},
            "time_decay": decay,
            "custom": custom,
            "base": _round(base),
        },
        "scorer": {"id": SCORER_ID, "kind": SCORER_KIND, "model": None,
                   "config_sha256": config_sha256(cfg)},
    }


def score(unit: dict, query_context: dict) -> float:
    """**纯函数**打分入口：`score(unit, query_context) -> float`。

    输入只有：单元内容（`unit`）、查询上下文（`query_context`）、
    配置权重（`query_context["config"]`）—— 不读时钟、不读环境、不调模型、
    不改任何入参。同一输入两次调用**逐位相同**。
    """
    return score_breakdown(unit, query_context)["score"]


# ---------------------------------------------------------------------------
# 召回（只记分、不决策）
# ---------------------------------------------------------------------------
def recall(units: list[dict], *, query: str = "", symbols=None, since: str = "",
           until: str = "", source: str = "", limit: int | None = None,
           include_archived: bool = False, config: dict | None = None,
           now: str = "") -> dict:
    """两路召回 + 记分。**没有任何阈值参数** —— 只返回带分数的候选。

    返回：
      `results`  `[{id, score, score_parts, score_explain, paths, …}]`
                  按分数降序、`id` 升序（**确定性排序**，同输入同输出）
      `scores`   全部分数列表 + `{min, max, mean}`（M2 校准的原料）
      `paths`    `{"keyword": n, "symbol": n}` 各自命中了多少条（诊断哪一路失效）
      `basis`    `{scorer, scorer_kind, model, config_sha256}` —— **归因位**：
                 换 scorer 之后读数变了，才不会被误读成"模型变强了"
      `filter`   本次生效的过滤条件（时间/来源/归档）
      `recalled` 本轮参与打分的候选数（过滤之后）
    """
    cfg = canonical_config(config)
    terms = _query_terms(query)
    symbols = [str(s).strip() for s in (symbols or []) if str(s).strip()]
    since_dt, until_dt = _parse_ts(since), _parse_ts(until)

    kept: list[dict] = []
    for unit in units:
        if not include_archived and unit.get("status") != "active":
            continue
        if source and str(unit.get("source") or "") != source:
            continue
        created = _parse_ts(unit.get("created_at"))
        if since_dt and (created is None or created < since_dt):
            continue
        if until_dt and (created is None or created > until_dt):
            continue
        kept.append(dict(unit))

    total = max(1, len(kept))
    df = document_frequency(kept, terms)
    context = {
        "query": query,
        "symbols": symbols,
        "terms": terms,
        "df": df,
        "total": total,
        "now": now or None,
        "config": cfg,
    }

    results: list[dict] = []
    path_counts = {"keyword": 0, "symbol": 0}
    for unit in kept:
        bd = score_breakdown(unit, context)
        detail = bd["detail"]
        kw_terms = detail["lexical"]["terms"]
        sym_hits = detail["symbol"]["symbols"]
        if not kw_terms and not sym_hits and bd["parts"]["custom"] == 0.0:
            continue
        paths: list[str] = []
        if kw_terms:
            paths.append("keyword")
            path_counts["keyword"] += 1
        if sym_hits:
            paths.append("symbol")
            path_counts["symbol"] += 1
        results.append({
            "id": unit.get("id"),
            "score": bd["score"],
            "score_parts": dict(bd["parts"]),
            "score_explain": detail,
            "paths": paths,
            "keyword_terms": kw_terms,
            "keyword_why": detail["lexical"]["why"],
            "symbol_hits": sym_hits,
            "structure_lookup": detail["symbol"]["structure_lookup"],
            "scorer": bd["scorer"],
            "created_at": unit.get("created_at"),
            "source": unit.get("source"),
            "content_head": str(unit.get("content") or "")[:120],
        })

    results.sort(key=lambda r: (-r["score"], str(r["id"])))
    scores = [r["score"] for r in results]
    return {
        "ok": True,
        "query": {"text": query, "symbols": symbols,
                  "terms": sorted(terms), "since": since, "until": until,
                  "source": source, "now": now or None},
        "results": results if limit is None else results[: max(0, int(limit))],
        "scores": {
            "values": scores,
            "count": len(scores),
            "min": min(scores) if scores else 0.0,
            "max": max(scores) if scores else 0.0,
            "mean": round(sum(scores) / len(scores), 6) if scores else 0.0,
        },
        "paths": path_counts,
        "filter": {"since": since, "until": until, "source": source,
                   "include_archived": include_archived},
        "recalled": len(kept),
        "basis": {"scorer": SCORER_ID, "scorer_kind": SCORER_KIND,
                  "model": None, "config_sha256": config_sha256(cfg)},
        "config": cfg,
        "threshold": None,
        "decision": "none",
        "note": (
            "M1/M2 只记分、不决策：本函数**没有阈值参数**，返回全部带分数的候选。"
            "打分是纯函数（不读时钟、不调模型）：同一输入两次调用逐位相同。"
            "阈值要用 calibrate() 的分布与事后判定来校准（M3 才谈接入）"
        ),
    }


# ---------------------------------------------------------------------------
# 校准（第 5 条硬要求：校准过程本身可复现）
# ---------------------------------------------------------------------------
def calibrate(cases: list[dict], *, config: dict | None = None) -> dict:
    """对**带标注**的召回结果算漏召 / 误召，并给出候选阈值曲线（**不选阈值**）。

    `cases` 每项：`{id, relevant: [unit_id…], result: recall(...) 的返回}`。
    `config` 必须是**产出这些 `result` 的那份配置** —— 校准记录要能复现。

    判据（统筹方配套判据逐条对应）：

      漏召（该被调的没被调）  `missed` 非空 ⇒ 这一条的 `failures` 里有 `miss`
      误召（无关历史被调了）  `false_recalled` 非空 ⇒ `failures` 里有 `false-recall`
      只记分不决策            每个阈值只给 `precision`/`recall`/`F1` 的**候选**，
                              **函数不返回"推荐阈值"** —— 选阈值这件事留在 M2/M3
      可复现                  记录 `samples_sha256` / `config_sha256` / `curve_sha256`：
                              **同样本 + 同配置 ⇒ 同曲线哈希**
    """
    cfg = canonical_config(config)
    per_case: list[dict] = []
    samples: list[dict] = []
    for case in cases:
        result = case.get("result") or {}
        relevant = {str(x) for x in (case.get("relevant") or [])}
        retrieved = [r["id"] for r in (result.get("results") or [])]
        hit = [i for i in retrieved if i in relevant]
        missed = sorted(relevant - set(retrieved))
        false_recalled = [i for i in retrieved if i not in relevant]
        failures: list[str] = []
        if relevant and missed:
            failures.append("miss")
        if false_recalled:
            failures.append("false-recall")
        per_case.append({
            "id": case.get("id"),
            "query": (result.get("query") or {}),
            "relevant_count": len(relevant),
            "retrieved_count": len(retrieved),
            "hit": hit,
            "missed": missed,
            "false_recalled": false_recalled,
            "recall": round(len(hit) / len(relevant), 6) if relevant else None,
            "precision": round(len(hit) / len(retrieved), 6) if retrieved else None,
            "scores": result.get("scores") or {},
            "failures": failures,
        })
        samples.append({"id": case.get("id"), "relevant": sorted(relevant)})

    with_labels = [c for c in per_case if c["relevant_count"]]
    mean_recall = (round(sum(c["recall"] for c in with_labels) / len(with_labels), 6)
                   if with_labels else None)
    total_relevant = sum(c["relevant_count"] for c in with_labels)
    total_hit = sum(len(c["hit"]) for c in with_labels)
    total_retrieved = sum(c["retrieved_count"] for c in with_labels)
    total_false = sum(len(c["false_recalled"]) for c in with_labels)

    all_scores = sorted(
        {s for c in per_case for s in (c["scores"].get("values") or [])},
        reverse=True,
    )
    curve: list[dict] = []
    if all_scores:
        lo, hi = min(all_scores), max(all_scores)
        grid: list[float] = []
        steps = int((hi - lo) / THRESHOLD_STEP) + 1
        for k in range(steps + 1):
            grid.append(round(lo + k * THRESHOLD_STEP, 6))
        by_id = {str(x.get("id")): x for x in cases}
        for thr in grid:
            for c in per_case:
                if not c["relevant_count"]:
                    continue
                raw = by_id.get(str(c["id"])) or {}
                relevant = {str(x) for x in (raw.get("relevant") or [])}
                kept_ids = [x["id"] for x in ((raw.get("result") or {}).get("results") or [])
                            if x["score"] >= thr]
                tp = len([i for i in kept_ids if i in relevant])
                fp = len(kept_ids) - tp
                fn = c["relevant_count"] - tp
                p = tp / (tp + fp) if (tp + fp) else 0.0
                rec = tp / (tp + fn) if (tp + fn) else 0.0
                f1 = (2 * p * rec / (p + rec)) if (p + rec) else 0.0
                curve.append({
                    "case": c["id"], "threshold": thr,
                    "kept": len(kept_ids), "tp": tp, "fp": fp, "fn": fn,
                    "precision": round(p, 6), "recall": round(rec, 6),
                    "f1": round(f1, 6),
                })

    curve_sha = hashlib.sha256(_canonical_json(
        {"cases": per_case, "threshold_curve": curve}).encode("utf-8")).hexdigest()

    return {
        "ok": True,
        "cases": per_case,
        "totals": {
            "cases": len(per_case),
            "cases_with_labels": len(with_labels),
            "relevant": total_relevant,
            "hit": total_hit,
            "retrieved": total_retrieved,
            "false_recalled": total_false,
            "micro_recall": (round(total_hit / total_relevant, 6)
                             if total_relevant else None),
            "micro_precision": (round(total_hit / total_retrieved, 6)
                                if total_retrieved else None),
            "macro_recall": mean_recall,
            "miss_rate": (round(sum(1 for c in with_labels if "miss" in c["failures"])
                                / len(with_labels), 6) if with_labels else None),
            "false_recall_rate": (
                round(sum(1 for c in with_labels if "false-recall" in c["failures"])
                      / len(with_labels), 6) if with_labels else None),
        },
        "threshold_curve": curve,
        "recommended_threshold": None,
        # ---- 可复现的校准记录（第 5 条硬要求）----
        "calibration": {
            "scorer": {"id": SCORER_ID, "kind": SCORER_KIND, "model": None},
            "config": cfg,
            "config_sha256": config_sha256(cfg),
            "samples": samples,
            "samples_sha256": hashlib.sha256(
                _canonical_json(samples).encode("utf-8")).hexdigest(),
            "curve_sha256": curve_sha,
            "reproduce": ("同一批 samples + 同一份 config ⇒ 同一个 curve_sha256；"
                          "换配置或换样本 ⇒ 哈希变"),
        },
        "note": (
            "候选曲线只给数据（precision/recall/F1 随阈值的形状），"
            "**本函数不推荐、也不采用任何阈值** —— 阈值待 M2/M3 用更多数据校准"
        ),
    }


def scoring_profile() -> dict:
    """基线 scorer（S-A）的可读事实：纯函数、与模型无关、四项构成、配置指纹。"""
    return {
        "scorer": {"id": SCORER_ID, "kind": SCORER_KIND, "model": None},
        "entry": "retrieval.score(unit, query_context) -> float",
        "pure": True,
        "model_free": True,
        "clock_free": True,
        "score_parts": ["lexical", "symbol", "time_decay", "custom"],
        "additive": "score == parts.lexical + parts.symbol + parts.time_decay + parts.custom",
        "config": canonical_config(None),
        "config_sha256": config_sha256(None),
        "custom_weighting": ("显式配置 config['custom'] = [{why, add, when}]；"
                             "未知条件键结构化拒绝；模型无权决定权重"),
        "time_decay_default": ("half_life_days=None ⇒ 关闭（阈值类参数第一阶段不许拍，"
                               "留待 M2 用标注数据校准）"),
        "calibration": ("calibrate() 记录 samples_sha256 / config_sha256 / curve_sha256 "
                        "⇒ 校准过程可复现"),
        "reproducible": "同输入两次调用逐位相同（无时钟、无随机、无环境、round(...,9)）",
        "threshold": None,
        "decision": "none",
    }


def describe() -> dict:
    """契约面：两路召回、权重、四项构成、scorer 身份、以及「没有阈值」这件事本身。"""
    return {
        "paths": {
            "keyword": {
                "signal": "declared keywords > content substring",
                "weights": {"declared": K_DECLARED, "content": K_CONTENT},
                "blind_spot": "同义不同词（登录 vs 认证）",
            },
            "symbol": {
                "signal": "unit.symbol_refs ∩ query symbols",
                "structure_lookup": "find_symbol|get_module|get_architecture",
                "blind_spot": "长任务因果链（时间分区之外的相关性）",
                "new_keyword_library": False,
            },
        },
        "weights": {"keyword": W_KEYWORD, "symbol": W_SYMBOL},
        "scoring": scoring_profile(),
        # ★★★：scorer 身份与 model 并列 —— 换 scorer 而不换模型时，读数变化有归因。
        "basis": {"scorer": SCORER_ID, "model": None, "scorer_kind": SCORER_KIND},
        "scorer": {
            "id": SCORER_ID,
            "kind": SCORER_KIND,
            "model": None,
            "why": ("确定性算法（词法 + 符号图 + 显式时间衰减 + 显式定制权重）："
                    "完全可复现、零 token、不随模型变、无需新依赖"),
            "arms": {
                "S-A": "确定性（本模块已实现，M1/M2 的基线臂）",
                "S-B": "固定嵌入模型（版本锁定、独立配置）—— **M2 对照臂，未实现**",
                "S-C": "LLM 打分（以工具身份接入）—— **M2 对照臂，未实现**",
            },
            "one_switch": ("M1 未接入主链路；M3 接入时必须可一键关"
                           "（否则分不清「模型变强」还是「记忆层变好」）"),
        },
        "score_parts": ["lexical", "symbol", "time_decay", "custom"],
        "fusion": "两路独立命中后按 id 合并，分数加权求和；`paths` 如实写出走了哪几路",
        "threshold": None,
        "decision": "none (M1: score only; threshold calibration belongs to M2/M3)",
        "leakage_criteria": ["miss（漏召）", "false-recall（误召）"],
        "idf": "log(1 + total/(1+df))；`df` 也随分数一起记录",
        "deterministic": "同输入 ⇒ 同 id 顺序与同分数（排序键 = (-score, id)）",
    }
