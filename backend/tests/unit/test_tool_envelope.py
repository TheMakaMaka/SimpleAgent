"""`P9` 追加验收 ③：**产出检验必须真的接到工具上**（D33 后半）。

背景（统筹方 2026-10-03 独立复验，不看自述）
--------------------------------------------
`v1.25` 把实参侧的规范化交付了，但产出侧只**建好了机制**：

    audit().envelope_tools == []      ← 空集

也就是说 `validate_result` / `_envelope_problems` 是准备好的能力，**没有任何
工具的结果会被校验**。统筹方那句话说得准：**「机制存在」不等于「机制接上了」** ——
这正是本项目反复栽的形状。他的门禁因此补了不变式 F（`envelope_tools` 非空）
并**重新变红**。

本文件是那半边的自检，判据全部机器可判：

  [1] 登记面非空，且登记的工具真实存在、`audit()` 自洽
  [2] ★ 端到端：经 `Worker._invoke` 的产出**就是**合规信封（不是内部变量）
  [3] ★ 反空洞：把登记摘掉 ⇒ 同一判据立刻变红（证明 [1][2] 不是摆设）
  [4] 产出检验**有牙齿**：半成品信封被 reject（不会被当成成功读）
  [5] 旧字符串结果仍被 `is_error_result()` 正确识别（回退路径未动）
  [6] 兼容：信封不挡其余读法（`data` 里有工具原产出；未登记工具不受影响）

★ 反空洞说明：[3] 就是"**把检查关掉**"与"真接上"的分界线 —— 如果哪天有人
把 `ENVELOPE_TOOLS` 清空（回到 v1.25 的状态），[1][2] 会立刻失败。
"""

import asyncio
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import Checker  # noqa: E402

from core.worker import Worker  # noqa: E402
from tools import TOOLS_MAP  # noqa: E402
from tools.registry import is_error_result  # noqa: E402
from tools.tool_contract import (  # noqa: E402
    ENVELOPE_TOOLS,
    audit,
    build_envelope,
    describe_contract,
    envelope_of,
    envelope_policy,
    unwrap_payload,
    validate_result,
)

OK = Checker()
WORKER = Worker.__new__(Worker)          # _invoke 不需要 llm/limits


def invoke(tool: str, args: dict) -> str:
    return asyncio.run(Worker._invoke(WORKER, tool, json.dumps(args)))


# ===========================================================================
# [1] 登记面：产出检验接到了谁身上
# ===========================================================================
print("=" * 74)
print("[1] 结果信封的**登记面**（门禁不变式 F：envelope_tools 必须非空）")
print("=" * 74)
a = audit()
policy = envelope_policy()
print(f"  audit().envelope_tools        = {a['envelope_tools']}")
print(f"  audit().envelope_tool_count   = {a.get('envelope_tool_count')}")
print(f"  audit().unknown_envelope_tools= {a['unknown_envelope_tools']}")
print(f"  audit().bad_envelope_kinds    = {a.get('bad_envelope_kinds')}")
print(f"  未登记的工具数                 = {len(policy['remaining'])}")

OK.check("★ envelope_tools **非空**（v1.25 的门禁红点就是这里）",
         bool(a["envelope_tools"]))
OK.check("audit() 对登记面自洽（工具存在 + 类别名有效）",
         a["ok"] and not a["unknown_envelope_tools"] and not a.get("bad_envelope_kinds"))
OK.check("登记的工具都真实存在于 TOOLS_MAP",
         all(n in TOOLS_MAP for n in ENVELOPE_TOOLS))
OK.check("每个登记的工具都声明了结果类别（kind）",
         all(isinstance(k, str) and k.strip() for k in ENVELOPE_TOOLS.values()))
OK.check("登记面不是摆设：确实有工具在其中（防空集回归）",
         len(ENVELOPE_TOOLS) >= 1 and "check_and_run" in ENVELOPE_TOOLS)
OK.check("分阶段策略被公开声明（未登记的工具各有理由）",
         policy["registered_count"] == len(ENVELOPE_TOOLS)
         and all(policy["remaining_reasons"].get(n) for n in policy["remaining"]))
desc = describe_contract()["result_envelope"]
OK.check("describe_contract() 里也能读到登记面（不是藏在代码里）",
         desc["envelope_tools"] == sorted(ENVELOPE_TOOLS)
         and desc.get("built_by", "").startswith("tools.tool_contract.build_envelope"))

# ===========================================================================
# [2] ★ 端到端：模型看到的就是信封本体
# ===========================================================================
print("\n" + "=" * 74)
print("[2] ★ 端到端：经 Worker._invoke 的产出**就是**合规信封")
print("=" * 74)
out_ok = invoke("check_and_run", {"code": "print(1 + 1)"})
print(f"  成功产出: {out_ok}")
env_ok = envelope_of(out_ok)
OK.check("成功产出是信封（不是旧形状）", env_ok is not None)
OK.check("成功信封 ok=true 且带 data",
         bool(env_ok) and env_ok["ok"] is True and "data" in env_ok)
OK.check("成功信封的 kind 是登记类别（verification）",
         bool(env_ok) and env_ok["kind"] == ENVELOPE_TOOLS["check_and_run"])
OK.check("工具原产出原样在 data 里（没有丢信息）",
         bool(env_ok) and env_ok["data"].get("output") == "2"
         and env_ok["data"].get("run_ok") is True)
OK.check("信封经 validate_result 判为合规",
         validate_result("check_and_run", out_ok)["action"] == "accept")

out_bad = invoke("check_and_run", {"code": 'assert 1 == 2, "boom"'})
print(f"  失败产出: {out_bad[:220]}...")
env_bad = envelope_of(out_bad)
OK.check("失败产出也是信封，且 ok=false", bool(env_bad) and env_bad["ok"] is False)
OK.check("失败信封带结构化 error（code/message 不空）",
         bool(env_bad) and env_bad["error"].get("code") == "AssertionError"
         and env_bad["error"].get("message") == "boom")
OK.check("★ error 描述的是**真实失败**，不是占位文案",
         bool(env_bad) and "工具报错" not in env_bad["error"]["message"])
OK.check("失败细节没丢（data.parsed_error 仍可读）",
         bool(env_bad)
         and env_bad["data"]["parsed_error"]["error_type"] == "AssertionError")

# ===========================================================================
# [3] ★ 反空洞：摘掉登记 ⇒ 判据立刻变红
# ===========================================================================
print("\n" + "=" * 74)
print("[3] ★ 反空洞：摘掉登记，同一判据立刻变红（证明不是'把检查关掉'）")
print("=" * 74)
saved_kind = ENVELOPE_TOOLS.pop("check_and_run")
try:
    a_off = audit()
    policy_off = envelope_policy()
    print(f"  摘掉 check_and_run 后 audit().envelope_tools = {a_off['envelope_tools']}")
    print(f"  未登记理由表: {policy_off['remaining_reasons'].get('check_and_run')}")
    OK.check("摘掉登记 ⇒ envelope_tools 变空（= v1.25 被退回的那个状态）",
             a_off["envelope_tools"] == [])
    OK.check("摘掉登记 ⇒ 门禁的 F 判据会红（bool([]) is False）",
             not bool(a_off["envelope_tools"]))
    untracked = json.loads(invoke("check_and_run", {"code": "print(1)"}))
    OK.check("摘掉登记 ⇒ Worker 不再套信封（回到旧形状 {ok,syntax_passed,...}）",
             "kind" not in untracked and "data" not in untracked)
finally:
    ENVELOPE_TOOLS["check_and_run"] = saved_kind
OK.check("恢复登记 ⇒ audit 回到非空、且自洽",
         bool(audit()["envelope_tools"]) and audit()["ok"])

# ===========================================================================
# [4] 产出检验有牙齿：半成品信封被 reject
# ===========================================================================
print("\n" + "=" * 74)
print("[4] 产出检验**有牙齿**：不合规的信封不会被当成成功读")
print("=" * 74)
half = json.dumps({"ok": True, "kind": "verification"})          # 缺 data
report = validate_result("check_and_run", half)
print(f"  半成品信封 → action={report['action']} problems={report['problems']}")
OK.check("登记工具的半成品信封 → reject", report["action"] == "reject")
rejected = json.loads(report["error_result"])
OK.check("拒绝结果本身是合规信封（code=tool-result-invalid）",
         rejected["ok"] is False and rejected["error"]["code"] == "tool-result-invalid")
missing_err = validate_result(
    "check_and_run", json.dumps({"ok": False, "kind": "error"}))
OK.check("ok=false 但没有 error → 也 reject", missing_err["action"] == "reject")
good_env = build_envelope("check_and_run", json.dumps({"ok": True, "output": "x"}))
OK.check("合规信封仍被接受（不是一律拒绝）",
         validate_result("check_and_run", good_env)["action"] == "accept")

# ===========================================================================
# [5] 旧协议兼容：回退路径原样保留
# ===========================================================================
print("\n" + "=" * 74)
print("[5] 兼容：旧字符串结果仍被 is_error_result() 正确识别")
print("=" * 74)
legacy_cases = [
    ("Error: 文件不存在", True),
    ("错误：写入失败", True),
    (json.dumps({"ok": False, "issues": []}), True),
    ("文件 a.py 内容：\nprint(1)", False),
]
for text, want in legacy_cases:
    got = is_error_result(text)
    print(f"  is_error_result({text[:28]!r}) = {got}（期望 {want}）")
    OK.check(f"旧结果判定不变: {text[:20]!r}", got is want)
print(f"  旧字符串产出 action={validate_result('run_python', 'Error: 旧格式')['action']}")
OK.check("未登记工具的旧字符串产出仍 accept（不改判定语义）",
         validate_result("run_python", "Error: 旧格式")["action"] == "accept"
         and validate_result("run_python", "Error: 旧格式")["protocol"] == "plain-string")
legacy_json = validate_result("check_syntax", json.dumps({"ok": True}))
OK.check("未登记工具的自解释 JSON 仍按 legacy-json 可读",
         legacy_json["action"] == "accept"
         and legacy_json["protocol"] == "legacy-json")
OK.check("信封不影响失败判定：错误信封 is_error_result=True",
         is_error_result(out_bad) is True and is_error_result(out_ok) is False)

# ===========================================================================
# [6] 兼容：信封不挡其它读法（data 里有原产出）
# ===========================================================================
print("\n" + "=" * 74)
print("[6] 兼容：要读产出内容的旁路仍读得到（信封的 data 就是原产出）")
print("=" * 74)
OK.check("unwrap_payload(信封) 取回工具原产出",
         unwrap_payload(out_ok).get("output") == "2")
OK.check("unwrap_payload(旧字符串) 原样返回（不是信封就不动）",
         unwrap_payload("File: 旧形状") == "File: 旧形状")
# 未登记的工具完全不受影响：产出原样返回
from tools.registry import TOOLS_MAP as _TM  # noqa: E402


async def _plain(a: str) -> str:
    return "OK:FILE|a.py|5|已写入 a.py"


_TM["__env_probe__"] = {
    "function": _plain, "description": "probe",
    "parameters": {"type": "object", "properties": {"a": {"type": "string"}},
                   "required": ["a"], "additionalProperties": False},
    "profiles": ("any",),
}
try:
    raw_out = invoke("__env_probe__", {"a": "x"})
    print(f"  未登记工具的产出: {raw_out!r}")
    OK.check("未登记的工具产出**原样**返回（分阶段迁移不误伤）",
             raw_out == "OK:FILE|a.py|5|已写入 a.py")
finally:
    _TM.pop("__env_probe__", None)
OK.check("多次调用同一成功意图，信封**逐字节相同**（规范化要的可比性）",
         invoke("check_and_run", {"code": "print(1 + 1)"})
         == invoke("check_and_run", {"code": "print(1 + 1)"}))

raise SystemExit(OK.report())
