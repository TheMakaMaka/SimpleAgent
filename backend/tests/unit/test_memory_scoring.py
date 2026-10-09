"""P21 载荷 **第四条硬要求**（2026-10-05 追加）门禁：**调用分算法必须与模型无关**。

`WORK-ORDER.md`【P21】★★ 原文逐条落成判据（★ 号标的是**会红**的判据）：

  1. **打分必须是纯函数** `score(unit, query_context) -> float`，不得调用任何模型
     —— 入口恰好两个形参；不读时钟、不读环境、不读网络；不改入参（[V1]/[V2]）
  2. **打分必须可复现**：同输入两次调用**逐位相同**
     —— 无时钟读取；反空洞：换成读时钟/带计数的打分器，**同一条判据立刻判不可复现**（[V2]）
  3. **分数要可解释**：四项构成（词法命中 / 符号命中 / 时间衰减 / 定制加权）
     —— 四项**相加 == 总分**；时间衰减默认关闭、启用后随年龄单调变负（[V3]）
  4. **"定制化需求加权"走显式配置**（谁 / 在什么条件下 / 加多少），不许模型决定
     —— 规则三件必填；未知条件键**结构化拒绝**；配置里不出现模型字段（[V4]）
  5. **校准过程本身必须可复现**
     —— `samples_sha256` / `config_sha256` / `curve_sha256`；同样本同配置 ⇒ 同哈希（[V5]）

★★★（三种 scorer 同台对照）另有一条：**scorer 的选择必须进 `basis`**（与 `model` 并列）。
本文件钉住「`S-A` 是已实现的基线臂、`S-B`/`S-C` 是 **M2 对照臂、未实现**」——
**不假装已有**（[V6]）。

边界（与 `test_memory_store.py` 同）：本包仍是 **M1 独立库** ——
不 import 主链路、不注册成工具、不进 `main.py`、没有阈值参数、不决策。
"""

import ast
import copy
import inspect
import json
import os
import shutil
import socket
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import Checker, ROOT  # noqa: E402

from core.context_store import retrieval  # noqa: E402
from core.context_store.store import ContextStore  # noqa: E402

c = Checker()
TEMPS: list[str] = []

NO_CLOCK_MSG = "打分读了时钟"
NO_NET_MSG = "打分碰了网络"


def fresh_store() -> ContextStore:
    path = tempfile.mkdtemp(prefix="p21_score_", dir=os.path.join(ROOT, ".tmp"))
    TEMPS.append(path)
    return ContextStore(path, allow_inside_repos=True)


def unit_of(store: ContextStore, content: str, **kw) -> dict:
    return store.write(content, **kw)["unit"]


def ctx_of(store: ContextStore, *, query: str = "", symbols=None, now=None,
           config=None) -> dict:
    """按 `recall()` 的同一形状造一个 query_context（显式输入，不带隐藏状态）。"""
    terms = retrieval._query_terms(query)
    kept = [u for u in store.list_units() if u.get("status") == "active"]
    return {
        "query": query,
        "symbols": list(symbols or []),
        "terms": terms,
        "df": retrieval.document_frequency(kept, terms),
        "total": max(1, len(kept)),
        "now": now,
        "config": config,
    }


TWO_PARTS = ("lexical", "symbol", "time_decay", "custom")


# ---------------------------------------------------------------------------
print("=" * 74)
print("[V1] 纯函数入口：score(unit, query_context) -> float，只吃声明的输入")
print("=" * 74)

s = fresh_store()
u = unit_of(s, "reuse 层把 app.route 判成不存在符号", source="T9",
            keywords=["reuse", "false-positive"], symbols=["app.route"])
q = ctx_of(s, query="reuse false-positive", symbols=["app.route"])
SCORE = retrieval.score(u, q)
print(f"  score() = {SCORE!r}  type={type(SCORE).__name__}")
params = list(inspect.signature(retrieval.score).parameters)
print(f"  signature: score{inspect.signature(retrieval.score)}")
c.check("★ score 是函数且**恰好两个形参**（unit, query_context）", len(params) == 2)
c.check("★ 形参名就是 (unit, query_context)",
        params == ["unit", "query_context"])
c.check("★ 返回 float（不是 numpy/Decimal 等第二套数值类型）",
        isinstance(SCORE, float))

bd = retrieval.score_breakdown(u, q)
c.check("★ score() == score_breakdown()['score']（唯一实现，不是两份算法）",
        SCORE == bd["score"])

before_unit = copy.deepcopy(u)
before_ctx = copy.deepcopy(q)
retrieval.score(u, q)
retrieval.score_breakdown(u, q)
c.check("★ 不改入参：调用后 unit / query_context 逐字不变",
        u == before_unit and q == before_ctx)

# 只吃声明的输入：换掉环境变量与一批无关全局，分数不变（不是"顺手读了别的东西"）
probe_before = retrieval.score(u, q)
os.environ["AGENT_P21_SCORING_TRIPWIRE"] = "1"
try:
    probe_after = retrieval.score(u, q)
finally:
    os.environ.pop("AGENT_P21_SCORING_TRIPWIRE", None)
c.check("★ 不读环境：改环境变量后同输入同分数",
        probe_before == probe_after)

# 缺 config 时用默认配置；显式 config 放进 query_context（第三条输入）
c.check("query_context 里可以带显式 config（权重是声明的输入之一）",
        "config" in q and retrieval.canonical_config(q["config"]) ==
        retrieval.canonical_config(None))


# ---------------------------------------------------------------------------
print("\n" + "=" * 74)
print("[V2] 可复现 + 不读时钟 + 不碰网络（含**反空洞**：判据必须有牙）")
print("=" * 74)

runs = [retrieval.score(u, q) for _ in range(5)]
print(f"  同输入 5 次: {runs}")
c.check("★ 同输入两次 ⇒ **逐位相同**（浮点也一样）",
        all(x == runs[0] for x in runs) and len(set(runs)) == 1)
c.check("★ 逐位相同是 repr 级相同（不是「差不多」）",
        len({repr(x) for x in runs}) == 1)

# 时钟 tripwire：把 retrieval.datetime 换成一个 now() 会炸的类
real_datetime = retrieval.datetime


class _NoClock(real_datetime):  # type: ignore[misc, valid-type]
    @classmethod
    def now(cls, tz=None):
        raise AssertionError(NO_CLOCK_MSG)


# 网络 tripwire：把 socket.socket 换成会炸的构造器
real_socket = socket.socket


def _no_net(*a, **kw):
    raise AssertionError(NO_NET_MSG)


retrieval.datetime = _NoClock
socket.socket = _no_net
try:
    frozen = [retrieval.score(u, q) for _ in range(2)]
    decay_frozen = retrieval.time_decay_factor("2020-01-01T00:00:00",
                                               "2026-01-01T00:00:00",
                                               {"time_decay": {"half_life_days": 365}})
finally:
    retrieval.datetime = real_datetime
    socket.socket = real_socket
print(f"  时钟/网络双 tripwire 下: {frozen}  decay={decay_frozen['factor']}")
c.check("★ 时钟 tripwire 下仍算得出分 ⇒ 打分不读时钟", frozen == [runs[0], runs[0]])
c.check("★ 网络 tripwire 下仍算得出分 ⇒ 打分不碰网络", frozen == [runs[0], runs[0]])
c.check("时间解析仍可用（tripwire 只封 now()，不封 fromisoformat）",
        decay_frozen["applied"] is True and decay_frozen["factor"] < 1.0)

# ★ 反空洞 1：把时间衰减换成"带计数"的打分 ⇒ 同一判据必须判不可复现
real_decay = retrieval.time_decay_factor
state = {"n": 0}


def _drifting_decay(created_at, now, config=None):
    state["n"] += 1
    return {"factor": min(1.0, 0.90 + 0.01 * state["n"]), "applied": True,
            "age_days": 1.0, "half_life_days": 365.0, "why": "故意漂移"}


retrieval.time_decay_factor = _drifting_decay
try:
    drift = [retrieval.score(u, q) for _ in range(2)]
finally:
    retrieval.time_decay_factor = real_decay
print(f"  反空洞：故意漂移的打分器两次 = {drift}")
c.check("★★ 反空洞：换成非确定性打分器 ⇒ 同一条『逐位相同』判据立刻为假",
        drift[0] != drift[1])
c.check("★ 恢复真打分器后判据回到为真（证明红/绿同源）",
        retrieval.score(u, q) == retrieval.score(u, q))

# ★ 反空洞 2：读时钟的打分器必须被 tripwire 抓住
def _clock_reading(created_at, now, config=None):
    stamp = retrieval.datetime.now().microsecond
    return {"factor": 0.5 ** ((stamp % 1000) / 1000.0), "applied": True,
            "age_days": 0.0, "half_life_days": 1.0, "why": "读时钟"}


retrieval.time_decay_factor = _clock_reading
retrieval.datetime = _NoClock
try:
    try:
        retrieval.score(u, q)
        clock_caught = False
    except AssertionError as exc:
        clock_caught = NO_CLOCK_MSG in str(exc)
finally:
    retrieval.time_decay_factor = real_decay
    retrieval.datetime = real_datetime
c.check("★★ 反空洞：读时钟的打分器被时钟 tripwire 抓住（判据不是摆设）",
        clock_caught)

# 静态判据：包内不许出现模型/网络模块
pkg = os.path.join(ROOT, "core", "context_store")
mods: list[str] = []
for fname in sorted(os.listdir(pkg)):
    if fname.endswith(".py"):
        tree = ast.parse(open(os.path.join(pkg, fname), encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods += [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods.append((node.module or "").split(".")[0])
banned = sorted({m for m in mods if m in {
    "openai", "anthropic", "requests", "urllib", "http", "socket", "llm",
    "model", "transformers", "numpy", "torch", "core", "tools",
}})
print(f"  包内 import 的顶层模块: {sorted(set(mods))}")
c.check("★ 打分路径没有任何模型/网络/主链路模块可 import", not banned)


# ---------------------------------------------------------------------------
print("\n" + "=" * 74)
print("[V3] 分数可解释：四项构成**相加 == 总分**，时间衰减单调且默认关闭")
print("=" * 74)

s3 = fresh_store()
u3 = unit_of(s3, "auth token 过期导致登录失败", source="T9",
             keywords=["auth", "token"], symbols=["app.route"],
             created_at="2020-01-01T00:00:00")
cfg3 = {"time_decay": {"half_life_days": 365.0},
        "custom": [{"why": "用户定制：T9 相关记忆加权", "add": 0.25,
                    "when": {"source": ["T9"]}}]}
q3 = ctx_of(s3, query="auth token", symbols=["app.route"], now="2026-01-01T00:00:00",
            config=cfg3)
bd3 = retrieval.score_breakdown(u3, q3)
parts = bd3["parts"]
print(f"  parts = {json.dumps(parts, ensure_ascii=False)}  score = {bd3['score']}")
c.check("★ 分数构成**恰好四项**（词法/符号/时间衰减/定制加权）",
        set(parts) == set(TWO_PARTS))
c.check("★ 四项相加 == 总分（可解释 = 可对账，不是四个各说各话的数）",
        abs(sum(parts.values()) - bd3["score"]) < 1e-9)
c.check("★ 词法命中贡献 > 0（有查询词命中）", parts["lexical"] > 0)
c.check("★ 符号命中贡献 > 0（第二路真的有分）", parts["symbol"] > 0)
c.check("★ 定制加权贡献 == 规则里的 add（谁加多少是可核对的事实）",
        parts["custom"] == 0.25)
c.check("★ 时间衰减贡献 < 0（衰减是「扣分」，且方向不让读的人猜）",
        parts["time_decay"] < 0)
c.check("每项都带理由（词面 which / 符号 which / 衰减 why / 定制 why）",
        bd3["detail"]["lexical"]["why"] and isinstance(bd3["detail"]["time_decay"], dict)
        and bd3["detail"]["custom"]["matched"][0]["why"] == "用户定制：T9 相关记忆加权")

# 默认关闭：不给 half_life ⇒ 贡献恒为 0.0（阈值类参数第一阶段不许拍）
q3_off = ctx_of(s3, query="auth token", symbols=["app.route"],
                now="2026-01-01T00:00:00")
off = retrieval.score_breakdown(u3, q3_off)
c.check("★ 默认配置里时间衰减**关闭**（half_life_days=None，没有拍参数）",
        retrieval.DEFAULT_CONFIG["time_decay"]["half_life_days"] is None
        and off["parts"]["time_decay"] == 0.0
        and off["detail"]["time_decay"]["applied"] is False)
c.check("关闭衰减时总分 == 词法 + 符号 + 定制（与旧读数一致）",
        abs(off["score"] - (off["parts"]["lexical"] + off["parts"]["symbol"]
                            + off["parts"]["custom"])) < 1e-9)

# 单调性：半衰期越短（衰减越狠）⇒ 时间衰减项越负
neg = []
for hl in (3650.0, 730.0, 365.0, 30.0):
    d = retrieval.time_decay_factor("2020-01-01T00:00:00", "2026-01-01T00:00:00",
                                    {"time_decay": {"half_life_days": hl}})
    neg.append(d["factor"])
print(f"  half_life → factor: {neg}")
c.check("★ 时间衰减随半衰期变短而单调变小（0 ≤ f ≤ 1，不是拍脑袋的曲线）",
        all(0.0 <= f <= 1.0 for f in neg) and neg == sorted(neg, reverse=True)
        and neg[0] > neg[-1])
c.check("★ 未过期不扣分（age<=0 ⇒ factor=1）",
        retrieval.time_decay_factor("2027-01-01T00:00:00", "2026-01-01T00:00:00",
                                    {"time_decay": {"half_life_days": 365}})["factor"] == 1.0)
floor = retrieval.time_decay_factor("2000-01-01T00:00:00", "2026-01-01T00:00:00",
                                    {"time_decay": {"half_life_days": 1.0,
                                                    "min_factor": 0.25}})
c.check("★ 下限 min_factor 生效（不许衰减到 0 把单元悄悄删掉）",
        floor["factor"] == 0.25)

# ★ 反空洞：四项对账判据必须抓得住"少算了一项"
broken = dict(parts)
broken["custom"] += 0.001
c.check("★★ 反空洞：把某一项改掉 ⇒ 同一条『相加==总分』判据立刻为假",
        abs(sum(broken.values()) - bd3["score"]) > 1e-9)


# ---------------------------------------------------------------------------
print("\n" + "=" * 74)
print("[V4] 定制加权 = **显式配置**（谁 / 在什么条件下 / 加多少），模型无权决定")
print("=" * 74)

s4 = fresh_store()
u4 = unit_of(s4, "T9 的误判记录", source="T9", keywords=["reuse"])
base_cfg = None
no_rule = retrieval.score(u4, ctx_of(s4, query="reuse", config=base_cfg))
with_rule = retrieval.score(u4, ctx_of(s4, query="reuse", config={
    "custom": [{"why": "用户定制：T9 相关记忆加权", "add": 0.25,
                "when": {"source": ["T9"]}}]}))
print(f"  无规则 {no_rule} → 有规则 {with_rule}")
c.check("★ 默认没有任何定制规则（权重不是藏起来的默认值）",
        retrieval.DEFAULT_CONFIG["custom"] == [])
c.check("★ 加一条规则 ⇒ 分数**恰好**加 add（可对账）",
        abs((with_rule - no_rule) - 0.25) < 1e-9)
c.check("不命中条件时规则不加分（条件真的在判）",
        retrieval.score(u4, ctx_of(s4, query="reuse", config={
            "custom": [{"why": "只给 V2", "add": 9.0, "when": {"source": ["V2"]}}]}
        )) == no_rule)

for bad, why in (
    ({"custom": [{"add": 0.25, "when": {"source": ["T9"]}}]}, "缺 why（『谁』不许省）"),
    ({"custom": [{"why": "x", "add": 0.25, "when": {"module": ["a"]}}]}, "未知条件键"),
    ({"custom": [{"why": "x", "add": 0.25, "when": {"source": "T9"}}]}, "条件值不是列表"),
    ({"custom": [{"why": "x", "add": 0.25, "when": {}}]}, "空条件"),
    ({"time_decay": {"half_life_days": -1}}, "负半衰期"),
    ({"time_decay": {"min_factor": 2}}, "下限越界"),
    ({"weights": {"lexical": "0.5"}}, "权重不是数字"),
    ({"weights": {"unknown": 1.0}}, "未声明权重键"),
    ({"custom": [{"why": "x", "add": 0.25, "when": {"source": ["T9"]}, "extra": 1}]},
     "规则里出现未声明键"),
):
    try:
        retrieval.canonical_config(bad)
        raised = None
    except ValueError as exc:
        raised = exc
    c.check(f"★ 结构不合法 ⇒ 结构化拒绝（{why}）", raised is not None)
    if raised is None:
        print(f"  FAIL  没有被拒: {bad}")

cfg4 = retrieval.canonical_config({"custom": [
    {"why": "用户定制：T9 相关记忆加权", "add": 0.25, "when": {"source": ["T9"]}}],
    "time_decay": {"half_life_days": 365.0}})
blob = json.dumps(cfg4, ensure_ascii=False, sort_keys=True)
c.check("★ 配置可 JSON 往返（可落盘、可哈希、可复核）",
        json.loads(blob) == cfg4)
c.check("★ 配置里没有任何模型字段（模型无权决定权重）",
        not [k for k in ("model", "llm", "prompt", "embedding", "provider") if k in blob])
c.check("配置指纹对配置敏感：改一个权重 ⇒ 哈希变",
        retrieval.config_sha256(cfg4) != retrieval.config_sha256(
            {"custom": cfg4["custom"], "time_decay": {"half_life_days": 730.0}}))


# ---------------------------------------------------------------------------
print("\n" + "=" * 74)
print("[V5] 校准过程**可复现**：同样本 + 同配置 ⇒ 同曲线哈希")
print("=" * 74)

s5 = fresh_store()
A = unit_of(s5, "reuse 层把 app.route 判成不存在符号", source="T9",
            keywords=["reuse", "false-positive"], symbols=["app.route"])["id"]
B = unit_of(s5, "占位说明（线索在结构引用里）", source="T9b",
            symbols=["build_index_report"])["id"]
D = unit_of(s5, "无关清理脚本", source="D", keywords=["cleanup"])["id"]

default_cases = lambda: [
    {"id": "关键词命中", "relevant": [A], "result": s5.recall(query="reuse")},
    {"id": "符号命中", "relevant": [B], "result": s5.recall(symbols=["build_index_report"])},
    {"id": "误召", "relevant": [A], "result": s5.recall(query="cleanup")},
    {"id": "漏召", "relevant": [A], "result": s5.recall(symbols=["nope"])},
]
rep1 = s5.calibrate(default_cases())
rep2 = s5.calibrate(default_cases())
cal1, cal2 = rep1["calibration"], rep2["calibration"]
print(f"  context/config/curve sha: {cal1['config_sha256'][:12]} / "
      f"{cal1['samples_sha256'][:12]} / {cal1['curve_sha256'][:12]}")
c.check("★ 同样本同配置两次校准 ⇒ config_sha256 相同",
        cal1["config_sha256"] == cal2["config_sha256"])
c.check("★ ⇒ samples_sha256 相同（记录里点名了用哪些样本）",
        cal1["samples_sha256"] == cal2["samples_sha256"]
        and [x["id"] for x in cal1["samples"]] == [x["id"] for x in rep1["cases"]]
        and all("relevant" in x for x in cal1["samples"]))
c.check("★ ⇒ curve_sha256 相同（校准曲线逐字节可复现）",
        cal1["curve_sha256"] == cal2["curve_sha256"])
c.check("校准记录带 scorer 身份与复现说明（换 scorer 也能归因）",
        cal1["scorer"]["id"] == retrieval.SCORER_ID
        and cal1["scorer"]["model"] is None and "curve_sha256" in cal1["reproduce"])

# 换配置（并且真的用新配置重算过召回）⇒ 曲线哈希必须变
cfg5 = {"weights": {"lexical": 1.0, "symbol": 0.4}}
cases_new = [
    {"id": "关键词命中", "relevant": [A], "result": s5.recall(query="reuse", config=cfg5)},
    {"id": "符号命中", "relevant": [B],
     "result": s5.recall(symbols=["build_index_report"], config=cfg5)},
    {"id": "误召", "relevant": [A], "result": s5.recall(query="cleanup", config=cfg5)},
    {"id": "漏召", "relevant": [A], "result": s5.recall(symbols=["nope"], config=cfg5)},
]
rep3 = s5.calibrate(cases_new, config=cfg5)
print(f"  换权重后: config={rep3['calibration']['config_sha256'][:12]} "
      f"curve={rep3['calibration']['curve_sha256'][:12]}")
c.check("★ 换配置 ⇒ config_sha256 变（指纹对配置敏感）",
        rep3["calibration"]["config_sha256"] != cal1["config_sha256"])
c.check("★ 换配置且重算召回 ⇒ curve_sha256 也变（不是只换个哈希标签）",
        rep3["calibration"]["curve_sha256"] != cal1["curve_sha256"])

# ★ 反空洞：改一个样本的标注 ⇒ samples_sha256 必须变（指纹覆盖样本集）
cases_perturbed = default_cases()
cases_perturbed[0]["relevant"] = [A, D]
rep4 = s5.calibrate(cases_perturbed)
c.check("★★ 反空洞：改一条样本的标注 ⇒ samples_sha256 变（指纹真的覆盖样本集）",
        rep4["calibration"]["samples_sha256"] != cal1["samples_sha256"])
c.check("★ 校准仍**不推荐阈值**（阈值是 M2/M3 的事，第一阶段只记分）",
        rep1["recommended_threshold"] is None
        and rep3["recommended_threshold"] is None)


# ---------------------------------------------------------------------------
print("\n" + "=" * 74)
print("[V6] scorer 身份进 basis；S-B/S-C 如实标『未实现』；仍是 M1（不接主链路）")
print("=" * 74)

res = s5.recall(query="reuse false-positive", symbols=["app.route"])
basis = res["basis"]
print(f"  basis = {json.dumps(basis, ensure_ascii=False)}")
c.check("★ 召回结果带 basis（scorer 与 model 并列 —— 换 scorer 不会被误读成换模型）",
        basis["scorer"] == retrieval.SCORER_ID
        and basis["model"] is None
        and basis["scorer_kind"] == retrieval.SCORER_KIND == "deterministic")
c.check("★ basis 带配置指纹（同一 scorer 的不同权重也能区分）",
        basis["config_sha256"] == retrieval.config_sha256(res["config"]))
c.check("★ 每条候选都带四项构成（不是只有总分）",
        all(set(r["score_parts"]) == set(TWO_PARTS) for r in res["results"]))

desc = retrieval.describe()
arms = desc["scorer"]["arms"]
print(f"  arms = {json.dumps(arms, ensure_ascii=False)}")
c.check("★ 契约面声明 S-A 已实现（基线臂）",
        "已实现" in arms["S-A"] and retrieval.SCORER_ID == "S-A")
c.check("★ S-B/S-C 如实标『未实现』（不许假装已有三条臂）",
        "未实现" in arms["S-B"] and "未实现" in arms["S-C"])
c.check("★ describe() 声明与本模块同源：basis.scorer == scorer.id",
        desc["basis"]["scorer"] == desc["scorer"]["id"] == retrieval.SCORER_ID)
c.check("scoring_profile：纯函数 / 不依赖模型 / 不读时钟 / 四项构成 / 可复现",
        desc["scoring"]["pure"] is True
        and desc["scoring"]["model_free"] is True
        and desc["scoring"]["clock_free"] is True
        and desc["scoring"]["score_parts"] == list(TWO_PARTS)
        and bool(desc["scoring"]["reproducible"]))

prof = s5.profile()
c.check("★ profile() 暴露 scoring 段并对齐包级 describe()",
        prof["scoring"]["scorer"]["id"] == retrieval.SCORER_ID
        and prof["scoring"]["config_sha256"] == retrieval.config_sha256(None))
c.check("★ 仍是 M1：不接主链路、阶段 M1、没有阈值参数、不决策",
        prof["phase"] == "M1" and prof["wired_into_main_chain"] is False
        and "threshold" not in inspect.signature(s5.recall).parameters
        and res["threshold"] is None and res["decision"] == "none")

main_src = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
pkg_src = "\n".join(open(os.path.join(pkg, f), encoding="utf-8").read()
                    for f in sorted(os.listdir(pkg)) if f.endswith(".py"))
c.check("★ main.py 仍未引用 context_store（M1 不接入）",
        "context_store" not in main_src)
c.check("★ 包内没有注册成工具 / 没有 @register",
        "@register" not in pkg_src and "register(" not in pkg_src)

for p in TEMPS:
    shutil.rmtree(p, ignore_errors=True)
print()
raise SystemExit(c.report())
