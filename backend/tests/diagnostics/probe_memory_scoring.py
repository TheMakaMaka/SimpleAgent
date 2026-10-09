"""P21 ★★ 诊断探针：**「调用分算法必须与模型无关」的机械取证**。

与 `tests/unit/test_memory_scoring.py` 的分工：
  · 单测 = **门禁**（会红/会绿）；
  · 本探针 = **取证**（原始回显，供评估文档 §4 逐段粘贴）。

六段，与 `WORK-ORDER.md`【P21】★★ 的五条硬要求 + ★★★ 的归因条一一对应：

  [F1] 纯函数入口       —— `score(unit, query_context) -> float`（恰好两个形参、不改入参）
  [F2] 可复现 + 不读时钟/不碰网络 —— 含**反空洞**：换成漂移打分器 ⇒ 同判据立刻红
  [F3] 四项构成相加 == 总分 —— 词法 / 符号 / 时间衰减 / 定制加权
  [F4] 定制加权 = 显式配置 —— 谁 / 在什么条件下 / 加多少；非法配置结构化拒绝
  [F5] 校准过程可复现     —— samples/config/curve 三个 sha256
  [F6] scorer 身份进 basis —— S-A 已实现；S-B/S-C 如实标未实现；仍是 M1（不接主链路）

用法（仓库根目录）：

    D:\\PythonProject\\SimpleAgent2_Cycle_VueWeb\\.venv\\Scripts\\python.exe tests\\diagnostics\\probe_memory_scoring.py
"""

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

from _bootstrap import ROOT  # noqa: E402

from core.context_store import retrieval  # noqa: E402
from core.context_store.store import ContextStore  # noqa: E402

TEMPS: list[str] = []
FAILED: list[str] = []


def tmp_root() -> str:
    path = tempfile.mkdtemp(prefix="p21_score_probe_", dir=os.path.join(ROOT, ".tmp"))
    TEMPS.append(path)
    return path


def store() -> ContextStore:
    # 本轮硬边界只许写本仓库 ⇒ 探针库根造在 .tmp/（显式逃生口，生产不传）。
    return ContextStore(tmp_root(), allow_inside_repos=True)


def show(title: str) -> None:
    print("\n" + "=" * 74)
    print(title)
    print("=" * 74)


def ok(name: str, condition: bool, extra: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}" + (f"   {extra}" if extra else ""))
    if not condition:
        FAILED.append(name)


def ctx_of(st: ContextStore, *, query="", symbols=None, now=None, config=None) -> dict:
    terms = retrieval._query_terms(query)
    kept = [u for u in st.list_units() if u.get("status") == "active"]
    return {"query": query, "symbols": list(symbols or []), "terms": terms,
            "df": retrieval.document_frequency(kept, terms),
            "total": max(1, len(kept)), "now": now, "config": config}


def main() -> int:
    st = store()
    unit = st.write("reuse 层把 app.route 判成不存在符号", source="T9",
                    keywords=["reuse", "false-positive"],
                    symbols=["app.route"],
                    created_at="2020-01-01T00:00:00")["unit"]
    cfg = {"time_decay": {"half_life_days": 365.0},
           "custom": [{"why": "用户定制：T9 相关记忆加权", "add": 0.25,
                       "when": {"source": ["T9"]}}]}
    ctx = ctx_of(st, query="reuse false-positive", symbols=["app.route"],
                 now="2026-01-01T00:00:00", config=cfg)

    # ------------------------------------------------------------------ F1
    show("[F1] 纯函数入口：score(unit, query_context) -> float")
    sig = inspect.signature(retrieval.score)
    print(f"  score 签名      : score{sig}")
    print(f"  形参            : {list(sig.parameters)}")
    value = retrieval.score(unit, ctx)
    print(f"  score() 返回值  : {value!r}  ({type(value).__name__})")
    bd = retrieval.score_breakdown(unit, ctx)
    before_u, before_c = copy.deepcopy(unit), copy.deepcopy(ctx)
    retrieval.score(unit, ctx)
    print(f"  score == breakdown.score : {value == bd['score']}")
    print(f"  调用后入参未被改         : {unit == before_u and ctx == before_c}")
    print(f"  配置权重是声明输入之一   : {'config' in ctx} "
          f"(config_sha256={retrieval.config_sha256(cfg)[:16]})")
    ok("score 恰好两个形参 (unit, query_context)", list(sig.parameters) == ["unit", "query_context"])
    ok("score 返回 float（唯一实现：== score_breakdown）",
       isinstance(value, float) and value == bd["score"])
    ok("不改入参（纯函数）", unit == before_u and ctx == before_c)

    # ------------------------------------------------------------------ F2
    show("[F2] 可复现：同输入逐位相同 · 不读时钟 · 不碰网络（含反空洞）")
    runs = [retrieval.score(unit, ctx) for _ in range(5)]
    print(f"  同输入 5 次      : {runs}")
    print(f"  repr 集合大小    : {len({repr(x) for x in runs })}")
    ok("同输入两次 ⇒ 逐位相同", len({repr(x) for x in runs}) == 1)

    real_datetime, real_socket = retrieval.datetime, socket.socket

    class _NoClock(real_datetime):  # type: ignore[misc, valid-type]
        @classmethod
        def now(cls, tz=None):
            raise AssertionError("打分读了时钟")

    def _no_net(*a, **kw):
        raise AssertionError("打分碰了网络")

    retrieval.datetime, socket.socket = _NoClock, _no_net
    try:
        frozen = [retrieval.score(unit, ctx) for _ in range(2)]
        decay_ok = retrieval.time_decay_factor("2020-01-01T00:00:00",
                                               "2026-01-01T00:00:00",
                                               {"time_decay": {"half_life_days": 365}})
    finally:
        retrieval.datetime, socket.socket = real_datetime, real_socket
    print(f"  时钟+网络双 tripwire 下 : {frozen}")
    print(f"  时间衰减仍可算          : factor={decay_ok['factor']}")
    ok("时钟 tripwire 下仍算得出 ⇒ 不读时钟", frozen == [runs[0], runs[0]])
    ok("网络 tripwire 下仍算得出 ⇒ 不碰网络", frozen == [runs[0], runs[0]])

    real_decay = retrieval.time_decay_factor
    state = {"n": 0}

    def _drifting(created_at, now, config=None):
        state["n"] += 1
        return {"factor": min(1.0, 0.90 + 0.01 * state["n"]), "applied": True,
                "age_days": 1.0, "half_life_days": 365.0, "why": "故意漂移"}

    retrieval.time_decay_factor = _drifting
    try:
        drift = [retrieval.score(unit, ctx) for _ in range(2)]
    finally:
        retrieval.time_decay_factor = real_decay
    print(f"  ★ 反空洞：换成漂移打分器 ⇒ {drift}  （同一条判据判不可复现: "
          f"{drift[0] != drift[1]}）")
    ok("★ 反空洞：非确定性打分器被同一条判据判红", drift[0] != drift[1])
    ok("★ 恢复真打分器 ⇒ 判据回到绿（红/绿同源）",
       retrieval.score(unit, ctx) == retrieval.score(unit, ctx))

    def _clock_reading(created_at, now, config=None):
        return {"factor": 0.5 ** ((retrieval.datetime.now().microsecond % 1000) / 1000.0),
                "applied": True, "age_days": 0.0, "half_life_days": 1.0, "why": "读时钟"}

    retrieval.time_decay_factor, retrieval.datetime = _clock_reading, _NoClock
    try:
        try:
            retrieval.score(unit, ctx)
            caught = False
        except AssertionError as exc:
            caught = "时钟" in str(exc)
    finally:
        retrieval.time_decay_factor, retrieval.datetime = real_decay, real_datetime
    ok("★ 反空洞：读时钟的打分器被 tripwire 抓住", caught)

    # ------------------------------------------------------------------ F3
    show("[F3] 分数可解释：四项构成相加 == 总分")
    parts = bd["parts"]
    print(f"  单元文本        : {unit['content']}")
    print(f"  构成            : {json.dumps(parts, ensure_ascii=False)}")
    print(f"  四项之和        : {round(sum(parts.values()), 9)}")
    print(f"  总分            : {bd['score']}")
    print(f"  逐项理由        : lexical={bd['detail']['lexical']['why']} "
          f"symbol={bd['detail']['symbol']['symbols']}")
    print(f"                    time_decay={bd['detail']['time_decay']['why']} "
          f"factor={bd['detail']['time_decay']['factor']}")
    print(f"                    custom={[m['why'] for m in bd['detail']['custom']['matched']]}")
    ok("构成恰好四项（lexical/symbol/time_decay/custom）",
       set(parts) == {"lexical", "symbol", "time_decay", "custom"})
    ok("四项相加 == 总分", abs(sum(parts.values()) - bd["score"]) < 1e-9)
    ok("四项都有理由可读（可解释，不是黑箱）",
       bool(bd["detail"]["lexical"]["why"]) and bool(bd["detail"]["time_decay"]["why"])
       and bool(bd["detail"]["custom"]["matched"]))

    off = retrieval.score_breakdown(unit, ctx_of(st, query="reuse", symbols=["app.route"],
                                                 now="2026-01-01T00:00:00"))
    print(f"  默认（half_life=None）: time_decay={off['parts']['time_decay']} "
          f"applied={off['detail']['time_decay']['applied']}")
    ok("★ 默认配置时间衰减关闭（half_life 参数没被拍死）",
       retrieval.DEFAULT_CONFIG["time_decay"]["half_life_days"] is None
       and off["parts"]["time_decay"] == 0.0)
    factors = [(hl, retrieval.time_decay_factor(
        "2020-01-01T00:00:00", "2026-01-01T00:00:00",
        {"time_decay": {"half_life_days": hl}})["factor"]) for hl in (3650.0, 730.0, 365.0, 30.0)]
    print(f"  半衰期 → 因子   : {factors}")
    ok("时间衰减随半衰期单调减小（形状可预期）",
       [f for _, f in factors] == sorted([f for _, f in factors], reverse=True))
    floor = retrieval.time_decay_factor("2000-01-01T00:00:00", "2026-01-01T00:00:00",
                                        {"time_decay": {"half_life_days": 1.0,
                                                        "min_factor": 0.25}})
    print(f"  下限 min_factor : {floor['factor']}（配置 0.25）")
    ok("min_factor 下限生效（可配置成「不许衰减到 0」）", floor["factor"] == 0.25)

    broken = dict(parts)
    broken["custom"] += 0.001
    ok("★ 反空洞：改掉某一项 ⇒ 同一条对账判据判红",
       abs(sum(broken.values()) - bd["score"]) > 1e-9)

    # ------------------------------------------------------------------ F4
    show("[F4] 定制加权 = 显式配置（谁 / 在什么条件下 / 加多少）")
    no_rule = retrieval.score(unit, ctx_of(st, query="reuse"))
    one_rule = retrieval.score(unit, ctx_of(st, query="reuse", config={
        "custom": [{"why": "用户定制：T9 相关记忆加权", "add": 0.25,
                    "when": {"source": ["T9"]}}]}))
    print(f"  无规则 → 有规则 : {no_rule} → {one_rule}（差 {round(one_rule - no_rule, 9)}）")
    print(f"  默认规则表      : {retrieval.DEFAULT_CONFIG['custom']}")
    ok("默认没有任何定制规则（权重不是藏起来的默认值）",
       retrieval.DEFAULT_CONFIG["custom"] == [])
    ok("加一条规则 ⇒ 分数恰好加 add", abs((one_rule - no_rule) - 0.25) < 1e-9)

    bad_cases = [
        ("缺 why（『谁』不许省）", {"custom": [{"add": 0.25, "when": {"source": ["T9"]}}]}),
        ("未知条件键", {"custom": [{"why": "x", "add": 0.25, "when": {"module": ["a"]}}]}),
        ("条件值不是列表", {"custom": [{"why": "x", "add": 0.25, "when": {"source": "T9"}}]}),
        ("空条件", {"custom": [{"why": "x", "add": 0.25, "when": {}}]}),
        ("负半衰期", {"time_decay": {"half_life_days": -1}}),
        ("下限越界", {"time_decay": {"min_factor": 2}}),
        ("权重不是数字", {"weights": {"lexical": "0.5"}}),
        ("未声明权重键", {"weights": {"unknown": 1.0}}),
        ("规则里出现未声明键",
         {"custom": [{"why": "x", "add": 0.25, "when": {"source": ["T9"]}, "extra": 1}]}),
    ]
    for why, bad in bad_cases:
        try:
            retrieval.canonical_config(bad)
            print(f"  FAIL  没有被拒: {why}  {json.dumps(bad, ensure_ascii=False)}")
            FAILED.append(f"配置拒绝-{why}")
        except ValueError as exc:
            print(f"  PASS  {why:22s} ⇒ ValueError: {str(exc)[:70]}")
    blob = json.dumps(retrieval.canonical_config(cfg), ensure_ascii=False, sort_keys=True)
    print(f"  规范化配置      : {blob}")
    ok("配置可 JSON 往返 & 不含任何模型字段",
       json.loads(blob) == retrieval.canonical_config(cfg)
       and not [k for k in ("model", "llm", "prompt", "embedding", "provider") if k in blob])
    ok("配置指纹对配置敏感",
       retrieval.config_sha256(cfg) != retrieval.config_sha256(
           {"time_decay": {"half_life_days": 30.0}, "custom": cfg["custom"]}))

    # ------------------------------------------------------------------ F5
    show("[F5] 校准过程可复现：samples / config / curve 三个指纹")
    st5 = store()
    A = st5.write("reuse 层把 app.route 判成不存在符号", source="T9",
                  keywords=["reuse", "false-positive"], symbols=["app.route"])["id"]
    B = st5.write("占位说明（线索在结构引用里）", source="T9b",
                  symbols=["build_index_report"])["id"]
    D = st5.write("无关清理脚本", source="D", keywords=["cleanup"])["id"]

    def cases(cfg_=None):
        return [
            {"id": "关键词命中", "relevant": [A], "result": st5.recall(query="reuse", config=cfg_)},
            {"id": "符号命中", "relevant": [B],
             "result": st5.recall(symbols=["build_index_report"], config=cfg_)},
            {"id": "误召", "relevant": [A], "result": st5.recall(query="cleanup", config=cfg_)},
            {"id": "漏召", "relevant": [A], "result": st5.recall(symbols=["nope"], config=cfg_)},
        ]

    r1 = st5.calibrate(cases())["calibration"]
    r2 = st5.calibrate(cases())["calibration"]
    cfg_new = {"weights": {"lexical": 1.0, "symbol": 0.4}}
    r3 = st5.calibrate(cases(cfg_new), config=cfg_new)["calibration"]
    for tag, rec in (("第 1 次", r1), ("第 2 次", r2), ("换权重", r3)):
        print(f"  {tag:6s} config={rec['config_sha256'][:16]} "
              f"samples={rec['samples_sha256'][:16]} curve={rec['curve_sha256'][:16]}")
    print(f"  样本清单        : {json.dumps(r1['samples'], ensure_ascii=False)}")
    ok("同样本同配置两次 ⇒ 三个指纹全部相同",
       r1["config_sha256"] == r2["config_sha256"]
       and r1["samples_sha256"] == r2["samples_sha256"]
       and r1["curve_sha256"] == r2["curve_sha256"])
    ok("记录点名了用哪些样本（可复现的样本集）",
       [x["id"] for x in r1["samples"]] == [c_["id"] for c_ in st5.calibrate(cases())["cases"]])
    ok("★ 换配置且重算召回 ⇒ config 与 curve 指纹都变",
       r3["config_sha256"] != r1["config_sha256"]
       and r3["curve_sha256"] != r1["curve_sha256"])
    perturbed = cases()
    perturbed[0]["relevant"] = [A, D]
    r4 = st5.calibrate(perturbed)["calibration"]
    ok("★ 反空洞：改一条样本的标注 ⇒ samples 指纹变", 
       r4["samples_sha256"] != r1["samples_sha256"])
    print(f"  recommended_threshold = {st5.calibrate(cases())['recommended_threshold']}")
    ok("校准仍不推荐阈值（第一阶段只记分）",
       st5.calibrate(cases())["recommended_threshold"] is None)

    # ------------------------------------------------------------------ F6
    show("[F6] scorer 身份进 basis；S-B/S-C 如实标未实现；仍是 M1")
    res = st5.recall(query="reuse", symbols=["app.route"])
    desc = retrieval.describe()
    prof = st5.profile()
    print(f"  basis           : {json.dumps(res['basis'], ensure_ascii=False)}")
    print(f"  describe.scorer : {json.dumps(desc['scorer'], ensure_ascii=False)}")
    print(f"  profile.scoring : scorer={prof['scoring']['scorer']['id']} "
          f"pure={prof['scoring']['pure']} model_free={prof['scoring']['model_free']} "
          f"clock_free={prof['scoring']['clock_free']}")
    print(f"  score_parts     : {prof['scoring']['score_parts']}")
    print(f"  phase / wired   : {prof['phase']} / {prof['wired_into_main_chain']} "
          f"(threshold={res['threshold']}, decision={res['decision']})")
    ok("basis: scorer 与 model 并列（scorer=S-A, model=None）",
       res["basis"]["scorer"] == "S-A" and res["basis"]["model"] is None)
    ok("basis 带配置指纹", res["basis"]["config_sha256"] == retrieval.config_sha256(res["config"]))
    ok("S-A 标已实现；S-B/S-C 标未实现（不假装三条臂都有）",
       "已实现" in desc["scorer"]["arms"]["S-A"]
       and "未实现" in desc["scorer"]["arms"]["S-B"]
       and "未实现" in desc["scorer"]["arms"]["S-C"])
    ok("每条候选都带四项构成", all(set(r["score_parts"]) ==
                                  {"lexical", "symbol", "time_decay", "custom"}
                                  for r in res["results"]))
    ok("仍是 M1：不接主链路 / 没有阈值参数 / 不决策",
       prof["phase"] == "M1" and prof["wired_into_main_chain"] is False
       and "threshold" not in inspect.signature(st5.recall).parameters
       and res["threshold"] is None and res["decision"] == "none")
    ok("main.py 未引用 context_store", "context_store" not in
       open(os.path.join(ROOT, "main.py"), encoding="utf-8").read())

    for p in TEMPS:
        shutil.rmtree(p, ignore_errors=True)
    print("\n探针结束（临时库根已清理；默认库根未被创建）")
    if FAILED:
        print("失败项: " + ", ".join(FAILED))
        return 1
    print("全部 PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
