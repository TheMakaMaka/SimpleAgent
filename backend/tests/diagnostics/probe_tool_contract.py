"""`P9` 探针 —— 工具调用规范化 + 产出检验的**机械输出**。

用途：把本轮验收需要的原始证据一次打印出来，便于统筹方逐字复核
（不依赖我的概括）。五段：

  [1] 18 个工具的实参形状**封闭**（= 统筹方门禁 tool-contract-lint.py 的判据）
  [2] ★ 反空洞：临时去掉一个工具的封闭声明 ⇒ 同一判据**立刻变红**（证明它不是空转）
  [3] ★ 传未声明键 ⇒ 结构化拒绝（原始 JSON），且工具函数**没有被执行**
  [4] 结果信封会硬校验；旧字符串结果仍被 `is_error_result()` 正确识别
  [5] ★ 产出检验**真的接上了**（统筹方追加验收 ③）：`audit().envelope_tools`
      非空、经 `Worker._invoke` 的产出就是信封本体、**摘掉登记立刻变红**

用法：`python tests/diagnostics/probe_tool_contract.py`
"""

import asyncio
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from core.worker import Worker  # noqa: E402
from tools import TOOLS_MAP, tool_schemas  # noqa: E402
from tools.registry import is_error_result  # noqa: E402
from tools.tool_contract import (  # noqa: E402
    ENVELOPE_TOOLS,
    audit,
    envelope_of,
    envelope_policy,
    error_result,
    normalize_args,
    ToolArgError,
    validate_result,
)

FAILS: list[str] = []


def check(name: str, ok: bool) -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        FAILS.append(name)


def gate_judgement(schemas: list[dict]) -> list[str]:
    """复刻统筹方门禁 `tool-contract-lint.py` 的 B 判据（additionalProperties）。"""
    no_ap = []
    for s in schemas:
        fn = s.get("function") or {}
        params = fn.get("parameters") or {}
        if "additionalProperties" not in params or params["additionalProperties"] is not False:
            no_ap.append(fn.get("name") or "<unnamed>")
    return no_ap


print("=" * 78)
print("[1] 18 个工具的实参形状封闭（模型可见 schema）")
print("=" * 78)
schemas = tool_schemas(None)
no_ap = gate_judgement(schemas)
print(f"  工具总数                        : {len(schemas)}")
print(f"  parameters.type == object       : "
      f"{sum(1 for s in schemas if s['function']['parameters'].get('type') == 'object')}")
print(f"  未声明 additionalProperties:false: {len(no_ap)}")
for s in schemas:
    p = s["function"]["parameters"]
    print(f"    {s['function']['name']:<22} closed={p.get('additionalProperties') is False} "
          f"keys={sorted(p.get('properties') or {})} required={p.get('required') or []}")
check("18/18 工具显式 additionalProperties:false（门禁由红转绿）", not no_ap)
check("工具数 >= 18（门禁的反空洞下限）", len(schemas) >= 18)

print()
print("=" * 78)
print("[2] ★ 反空洞：去掉一个工具的封闭声明，同一判据立刻变红")
print("=" * 78)
victim = TOOLS_MAP["read_file"]["parameters"]
saved = victim.pop("additionalProperties", None)
try:
    red = gate_judgement(tool_schemas(None))
    print(f"  临时去掉 read_file 的声明后，门禁判据变红的工具: {red}")
    check("去掉声明 ⇒ 判据**会红**（证明 [1] 不是空转）", red == ["read_file"])
    check("工具自己的 audit() 也如实报红", "read_file" in audit()["not_closed"])
finally:
    if saved is not None:
        victim["additionalProperties"] = saved
green = gate_judgement(tool_schemas(None))
check("恢复声明 ⇒ 判据回到全绿", green == [])

print()
print("=" * 78)
print("[3] ★ 传未声明键 ⇒ 结构化拒绝（且工具函数没有被执行）")
print("=" * 78)
try:
    normalize_args("read_file", {"filename": "a.py", "bogus": 1})
    check("未声明键被拒绝", False)
except ToolArgError as e:
    raw = error_result("read_file", e)
    print(f"  normalize_args 抛错: code={e.code}")
    print(f"  回灌给模型的原始 JSON: {raw}")
    payload = json.loads(raw)
    check("拒绝是结构化的（ok=false + error.code=unknown-key）",
          payload["ok"] is False and payload["error"]["code"] == "unknown-key")
    check("提示里给了可用键（模型能改对）", "filename" in payload["error"]["hint"])

CALLS: list[str] = []


async def _spy(code: str = "") -> str:
    CALLS.append(code)
    return json.dumps({"ok": True, "kind": "text", "data": "spy"})


TOOLS_MAP["__probe_spy__"] = {
    "function": _spy,
    "description": "probe",
    "parameters": {"type": "object", "properties": {"code": {"type": "string"}},
                   "required": ["code"], "additionalProperties": False},
    "profiles": ("any",),
}
ENVELOPE_TOOLS["__probe_spy__"] = "probe"
try:
    w = Worker.__new__(Worker)
    out = asyncio.run(Worker._invoke(w, "__probe_spy__", json.dumps({"code": "x", "typo": 1})))
    print(f"  Worker._invoke 的原始返回: {out}")
    print(f"  工具函数被调用次数: {len(CALLS)}")
    check("经 Worker._invoke 也被结构化拒绝", json.loads(out)["error"]["code"] == "unknown-key")
    check("★ 被拒时工具函数一次都没执行（不是'接受后忽略'）", CALLS == [])
finally:
    TOOLS_MAP.pop("__probe_spy__", None)
    ENVELOPE_TOOLS.pop("__probe_spy__", None)

print()
print("=" * 78)
print("[4] 工具产出检验：信封 `{ok, kind, data, error}` + 旧字符串仍可读")
print("=" * 78)
ENVELOPE_TOOLS["__probe_env__"] = "probe"
try:
    bad = validate_result("__probe_env__", json.dumps({"ok": False}))
    print(f"  半成品信封 → action={bad['action']} problems={bad['problems']}")
    print(f"  拒绝时回灌: {bad['error_result']}")
    check("半成品信封被拒（不会被当成成功读）", bad["action"] == "reject")
    good = validate_result("__probe_env__",
                           json.dumps({"ok": True, "kind": "text", "data": "x"}))
    check("合规信封被接受", good["action"] == "accept")
finally:
    ENVELOPE_TOOLS.pop("__probe_env__", None)

legacy = [
    ("Error: 旧格式失败", True),
    ("错误：旧格式失败", True),
    (json.dumps({"ok": False, "issues": []}), True),
    (json.dumps({"ok": True, "output": "hi"}), False),
    ("文件 a.py 内容：\nprint(1)", False),
]
for text, want in legacy:
    got = is_error_result(text)
    print(f"  is_error_result({text[:30]!r}) = {got}（期望 {want}）")
    check(f"旧结果判定不变: {text[:22]!r}", got is want)
check("旧纯字符串产出 validate_result 仍 accept",
      validate_result("run_python", "Error: 旧格式")["action"] == "accept")
check("未登记信封工具的旧 JSON 仍可读",
      validate_result("check_syntax", json.dumps({"ok": True}))["action"] == "accept")

print()
print("=" * 78)
print("[5] ★ 产出检验**真的接上了**（统筹方追加验收 ③：机制存在 ≠ 机制接上）")
print("=" * 78)
w = Worker.__new__(Worker)
aud = audit()
policy = envelope_policy()
print(f"  audit().envelope_tools      : {aud['envelope_tools']}")
print(f"  audit().envelope_tool_count : {aud.get('envelope_tool_count')}")
print(f"  audit().unknown/bad_kinds   : {aud['unknown_envelope_tools']} / "
      f"{aud.get('bad_envelope_kinds')}")
print(f"  未登记的工具（分阶段）       : {len(policy['remaining'])} 个")
print(f"  分阶段判据                  : {policy['criterion']}")
check("★ envelope_tools **非空**（v1.25 正是红在这里）", bool(aud["envelope_tools"]))
check("登记面自洽（工具存在 + 类别名有效）", aud["ok"])

out_ok = asyncio.run(Worker._invoke(
    w, "check_and_run", json.dumps({"code": "print(1 + 1)"})))
print(f"  Worker._invoke('check_and_run') 成功 → {out_ok}")
env_ok = envelope_of(out_ok)
check("★ 模型看到的就是信封本体（ok/kind/data/error，不是旧形状）",
      env_ok is not None and set(env_ok) >= {"ok", "kind", "data"})
check("工具原产出原样在 data 里（没有丢信息）",
      bool(env_ok) and env_ok["data"]["output"] == "2")

out_bad = asyncio.run(Worker._invoke(
    w, "check_and_run", json.dumps({"code": 'assert 1 == 2, "boom"'})))
env_bad = envelope_of(out_bad)
print(f"  Worker._invoke('check_and_run') 失败 → ok={env_bad['ok']} "
      f"error={json.dumps(env_bad['error'], ensure_ascii=False)}")
check("★ 失败信封的 error 描述**真实失败**（不是占位文案）",
      bool(env_bad) and env_bad["ok"] is False
      and env_bad["error"]["code"] == "AssertionError"
      and env_bad["error"]["message"] == "boom")
check("失败细节没丢（data.parsed_error 仍可读，模型能定位）",
      bool(env_bad) and env_bad["data"]["parsed_error"]["error_type"] == "AssertionError")
check("信封与旧判据兼容：错误信封 is_error_result=True",
      is_error_result(out_bad) is True and is_error_result(out_ok) is False)

print()
print("  ★ 反空洞：摘掉登记 ⇒ 门禁判据**立刻变红**（证明 [5] 不是摆设）")
saved_kind = ENVELOPE_TOOLS.pop("check_and_run")
try:
    aud_off = audit()
    print(f"  摘掉后 envelope_tools = {aud_off['envelope_tools']} ⇒ "
          f"门禁 F 判据 bool(...) = {bool(aud_off['envelope_tools'])}")
    untracked = json.loads(asyncio.run(Worker._invoke(
        w, "check_and_run", json.dumps({"code": "print(1)"}))))
    print(f"  摘掉后 Worker 的返回: {json.dumps(untracked, ensure_ascii=False)[:120]}")
    check("摘掉登记 ⇒ envelope_tools 变空（回到 v1.25 的被退回状态）",
          aud_off["envelope_tools"] == [])
    check("摘掉登记 ⇒ Worker 不再套信封（机制与声明同源）",
          "kind" not in untracked and "data" not in untracked)
finally:
    ENVELOPE_TOOLS["check_and_run"] = saved_kind
check("恢复登记 ⇒ 回到非空且自洽", bool(audit()["envelope_tools"]) and audit()["ok"])

print()
print("=" * 78)
if FAILS:
    print(f"探针失败 {len(FAILS)} 项:")
    for f in FAILS:
        print(f"  - {f}")
    raise SystemExit(1)
print("★ 全部通过：形状封闭 · 未知键结构化拒绝 · 产出检验有牙齿 · 旧结果仍可读 · "
      "信封真的接到工具上")
raise SystemExit(0)
