"""`tool_call_contract`（P9）自检 —— 工具调用的规范形 + 产出检验。

这一轮治的是「**同义不同形**」：JSON Schema 默认 `additionalProperties: true`，
所以 18 个工具**全都接受任意键**，传错了不报错、被静默忽略。
"每次生成的东西不一样"能一路走到工具，机制性原因就在这一层。

本文件按统筹方验收条件逐条自检：

  ① 18 个工具全部显式 `additionalProperties: false`（无参工具也要）；
  ② `required ⊆ properties`、`parameters.type == "object"`；
  ③ 未知键**结构化拒绝**（不是静默丢弃 —— 用"间谍工具"证明它没被执行）；
  ④ 类型强制 / 缺省填充 / 别名归一都真的生效；
  ⑤ 结果信封 `{ok, kind, data, error}` 会硬校验；
  ⑥ **旧字符串结果仍可读**（`is_error_result()` 回退路径保留）。

★ 反空洞：③⑤ 两条都**故意构造会红的输入**；若实现被换成"一律放行"，
本文件的断言会立刻失败。
"""

import asyncio
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import Checker, ROOT  # noqa: E402

from core.worker import Worker  # noqa: E402
from tools import TOOLS_MAP, tool_schemas  # noqa: E402
from tools.registry import is_error_result  # noqa: E402
from tools.tool_contract import (  # noqa: E402
    ALIASES,
    ENVELOPE_TOOLS,
    ToolArgError,
    audit,
    describe_contract,
    normalize_args,
    validate_result,
)

OK = Checker()
OK.check("确实加载到了工具注册表（否则整份检查空转）", len(TOOLS_MAP) >= 18)
OK.check("确实加载到了别名表（否则整份检查空转）", len(ALIASES) >= 10)


def rejected(tool: str, args: dict) -> ToolArgError | None:
    try:
        normalize_args(tool, args)
    except ToolArgError as e:
        return e
    return None


# ===========================================================================
# [1] 声明面：18 个工具全部封闭（门禁读的就是 tool_schemas(None)）
# ===========================================================================
print("=" * 74)
print("[1] 声明面：每个工具的实参形状都是封闭的")
print("=" * 74)
schemas = tool_schemas(None)
not_closed, bad_type, bad_required = [], [], []
for s in schemas:
    fn = s["function"]
    name = fn["name"]
    params = fn["parameters"]
    if params.get("additionalProperties") is not False:
        not_closed.append(name)
    if params.get("type") != "object":
        bad_type.append(name)
    props = params.get("properties") or {}
    for key in params.get("required") or []:
        if key not in props:
            bad_required.append(f"{name}:{key}")

print(f"  模型可见 schema 数: {len(schemas)}")
print(f"  未声明 additionalProperties:false 的: {not_closed or '无'}")
print(f"  type 不是 object 的: {bad_type or '无'}")
print(f"  required ⊄ properties 的: {bad_required or '无'}")
OK.check("18/18 工具显式 additionalProperties:false", not not_closed)
OK.check("18/18 工具 parameters.type == object", not bad_type)
OK.check("required ⊆ properties", not bad_required)
OK.check("无参工具同样封闭（get_system_info / list_workspace）",
          all(s["function"]["parameters"]["additionalProperties"] is False
              for s in schemas
              if s["function"]["name"] in ("get_system_info", "list_workspace")))
a = audit()
print(f"  audit.ok={a['ok']}  alias_tools={a['alias_tool_count']}")
OK.check("audit() 自洽（含别名指向真实属性）", a["ok"])

# 别名表**声明**出来了（不是在代码里藏着）
desc = describe_contract()
OK.check("describe_contract() 公开了别名表",
          desc["aliases"].get("write_file", {}).get("code") == "content")
OK.check("归一化四条规则逐条可读", len(desc["normalization_rules"]) == 4)

# ===========================================================================
# [2] 别名归一：同一意图的两种写法收敛到同一 canonical 形状
# ===========================================================================
print("\n" + "=" * 74)
print("[2] 别名归一（实测的 `{filename,content}` vs `{code}` 两种形状）")
print("=" * 74)
canonical_write = normalize_args("write_file", {"filename": "a.py", "content": "x = 1"})
alias_write = normalize_args("write_file", {"filename": "a.py", "code": "x = 1"})
print(f"  canonical: {canonical_write}")
print(f"  别名写法 : {alias_write}")
OK.check("★ 两种写法归一后**逐字节相同**（同义不同形被治掉）",
          canonical_write == alias_write == {"filename": "a.py", "content": "x = 1"})
OK.check("run_python: script → code",
          normalize_args("run_python", {"script": "print(1)"}) == {"code": "print(1)"})
OK.check("check_and_run: expected_exit → expect_exit",
          normalize_args("check_and_run", {"code": "x", "expected_exit": 1})
          == {"code": "x", "expect_exit": 1})
ambiguous = rejected("write_file", {"filename": "a.py", "content": "A", "code": "B"})
print(f"  同归一键取值冲突: {ambiguous.code if ambiguous else '未拒绝'}")
OK.check("同归一键取值冲突 → ambiguous-key（不猜、不静默取一个）",
          ambiguous is not None and ambiguous.code == "ambiguous-key")

# ===========================================================================
# [3] 类型强制 / 缺省填充 / 必需键
# ===========================================================================
print("\n" + "=" * 74)
print("[3] 类型强制 与 缺省填充")
print("=" * 74)
OK.check('"3" → 3（可判定则强制）',
          normalize_args("get_architecture", {"limit": "3"})["limit"] == 3)
OK.check("3.0 → 3（整数值浮点）",
          normalize_args("get_architecture", {"limit": 3.0})["limit"] == 3)
bad_int = rejected("get_architecture", {"limit": "abc"})
print(f"  limit='abc' → {bad_int.code if bad_int else '未拒绝'}")
OK.check("无法判定为整数 → type-mismatch（不猜）",
          bad_int is not None and bad_int.code == "type-mismatch")
bad_str = rejected("run_python", {"code": {"nested": 1}})
OK.check("string 参数收到 dict → type-mismatch",
          bad_str is not None and bad_str.code == "type-mismatch")
bad_bool = rejected("get_architecture", {"limit": True})
OK.check("integer 参数收到 bool → type-mismatch（bool 是独立类型）",
          bad_bool is not None and bad_bool.code == "type-mismatch")
print(f"  省略 limit → {normalize_args('get_architecture', {})}（缺省填充）")
OK.check("缺省填充：省略 == 显式给默认值",
          normalize_args("get_architecture", {}) == normalize_args("get_architecture", {"limit": 20}))
OK.check("缺省填充：review_document.path 默认空串",
          normalize_args("review_document", {}) == {"path": ""})
missing = rejected("run_python", {})
print(f"  缺 code → {missing.code if missing else '未拒绝'}")
OK.check("必需键缺失 → missing-required",
          missing is not None and missing.code == "missing-required")

# ===========================================================================
# [4] ★ 未知键结构化拒绝（反空洞：证明"不是静默忽略"）
# ===========================================================================
print("\n" + "=" * 74)
print("[4] ★ 未知键必须被**结构化拒绝**，而不是静默丢弃")
print("=" * 74)
err = rejected("read_file", {"filename": "a.py", "unknown_key": 1})
print(f"  code    = {err.code}")
print(f"  message = {err.message}")
print(f"  hint    = {err.hint}")
OK.check("未知键 → code=unknown-key", err is not None and err.code == "unknown-key")
OK.check("拒绝信息里点明了未知键名", err is not None and "unknown_key" in err.message)
OK.check("拒绝信息里给了可用键（模型下一轮能改对）",
          err is not None and "filename" in err.hint)
OK.check("无参工具收到任意键也会拒绝",
          rejected("list_workspace", {"anything": 1}) is not None)

# --- 端到端：经 Worker._invoke，且**证明工具函数没有被执行** ---
CALLS: list[dict] = []


async def _spy(a: str, b: str = "") -> str:
    CALLS.append({"a": a, "b": b})
    return json.dumps({"ok": True, "kind": "text", "data": "spy-ok"})


TOOLS_MAP["__p9_spy__"] = {
    "function": _spy,
    "description": "P9 探针：只接受 a（必需）与 b（可选）",
    "parameters": {
        "type": "object",
        "properties": {
            "a": {"type": "string"},
            "b": {"type": "string", "default": "B"},
        },
        "required": ["a"],
        "additionalProperties": False,
    },
    "profiles": ("any",),
}
ENVELOPE_TOOLS["__p9_spy__"] = "probe"
try:
    w = Worker.__new__(Worker)          # _invoke 不需要 llm/limits
    out = asyncio.run(Worker._invoke(w, "__p9_spy__", json.dumps({"a": "x", "zzz": 1})))
    print(f"  Worker._invoke 传未声明键 → {out}")
    payload = json.loads(out)
    OK.check("★ 未声明键 ⇒ 结构化拒绝（ok=false + error.code）",
              payload["ok"] is False and payload["error"]["code"] == "unknown-key")
    OK.check("★ 被拒时工具函数**一次都没执行**（证明不是静默忽略）",
              CALLS == [])
    ok_out = json.loads(asyncio.run(Worker._invoke(w, "__p9_spy__", json.dumps({"a": "x"}))))
    print(f"  合规调用 → {ok_out}")
    OK.check("合规调用正常执行，且缺省值 b 被填上",
              ok_out.get("ok") is True and CALLS == [{"a": "x", "b": "B"}])
finally:
    TOOLS_MAP.pop("__p9_spy__", None)
    ENVELOPE_TOOLS.pop("__p9_spy__", None)

# ===========================================================================
# [5] ★ 结果信封校验（反空洞：不合规的产出必须被拒）
# ===========================================================================
print("\n" + "=" * 74)
print("[5] ★ 工具产出检验：新协议 `{ok, kind, data, error}`")
print("=" * 74)
ENVELOPE_TOOLS["__p9_envelope__"] = "probe"
try:
    bad = validate_result("__p9_envelope__", json.dumps({"ok": False}))
    print(f"  ok=false 但没有 error → action={bad['action']} problems={bad['problems']}")
    OK.check("★ 半成品信封 → reject（不会被当成成功读）",
              bad["action"] == "reject" and bad["conforms"] is False)
    bad_json = json.loads(bad["error_result"])
    OK.check("拒绝结果本身也是合规信封（code=tool-result-invalid）",
              bad_json["ok"] is False
              and bad_json["error"]["code"] == "tool-result-invalid")
    good = validate_result(
        "__p9_envelope__", json.dumps({"ok": True, "kind": "text", "data": "x"}))
    OK.check("合规信封 → accept",
              good["action"] == "accept" and good["protocol"] == "envelope")
    err_env = validate_result(
        "__p9_envelope__", json.dumps({"ok": False, "kind": "error",
                                       "error": {"code": "x", "message": "y"}}))
    OK.check("合规的错误信封 → accept",
              err_env["action"] == "accept" and err_env["is_error"] is True)
    missing_data = validate_result(
        "__p9_envelope__", json.dumps({"ok": True, "kind": "text"}))
    OK.check("ok=true 但没有 data → reject",
              missing_data["action"] == "reject")
finally:
    ENVELOPE_TOOLS.pop("__p9_envelope__", None)

# ===========================================================================
# [6] 旧协议兼容：旧字符串结果仍可读（回退路径保留）
# ===========================================================================
print("\n" + "=" * 74)
print("[6] 兼容：旧字符串结果仍被 is_error_result() 正确识别")
print("=" * 74)
legacy_cases = [
    ("Error: 文件不存在", True),
    ("错误：写入失败", True),
    (json.dumps({"ok": False, "issues": []}), True),
    (json.dumps({"ok": True, "output": "hi"}), False),
    ("文件 a.py 内容：\nprint(1)", False),
]
for text, want in legacy_cases:
    got = is_error_result(text)
    print(f"  is_error_result({text[:34]!r}) = {got}（期望 {want}）")
    OK.check(f"旧结果判定保持：{text[:24]!r} → {want}", got is want)

print(f"  纯字符串产出: action={validate_result('run_python', 'Error: 旧格式')['action']}")
OK.check("旧字符串产出 validate_result 一律 accept（不改判定语义）",
          validate_result("run_python", "Error: 旧格式")["action"] == "accept"
          and validate_result("run_python", "Error: 旧格式")["protocol"] == "plain-string")
legacy_json = validate_result("check_syntax", json.dumps({"ok": True}))
print(f"  仅含 ok 的旧 JSON: protocol={legacy_json['protocol']} action={legacy_json['action']}")
OK.check("未登记信封的工具，其半成品 JSON 仍可读（legacy-json / accept）",
          legacy_json["action"] == "accept" and legacy_json["protocol"] == "legacy-json")

raise SystemExit(OK.report())
