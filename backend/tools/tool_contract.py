"""工具调用的**规范形**（P9 · 契约 `tool_call_contract`，加性）。

模型只需要判断「做什么 / 怎么做 / 调用哪个工具」；**键名、类型、缺省、别名**
由这一层统一成 canonical 形式。目标不是"更严格"，而是
**同一意图只有一个形状** —— 没有 canonical 形式就无法比较两次调用、
无法复用，也无法做能力测量（实测：同一意图出现过
`{"filename":…,"content":…}` 与 `{"code":…}` 两种形状）。

三层职责
--------
1. `normalize_args(name, args)` —— 实参归一，位于 `Worker._parse_args`
   **之后**、执行**之前**：

   ============  ==========================================================
   别名归一       `ALIASES` 表（**声明在表里，不藏在代码里**）
   未知键拒绝     结构化报错，**不静默丢弃、不塞 kwargs**
   类型强制       可判定的才强制（`"3"→3`）；判不了就报错，**不猜**
   缺省填充       schema 里写了 `default` 的键补上
   必需键校验     `required` 里的键必须出现
   ============  ==========================================================

2. `validate_result(name, result)` —— **工具产出检验**：

   · 新协议：`{ok, kind, data, error}`（`ok=false` 时 `error` 必填）；
   · 旧协议：纯字符串（含 `Error:` 前缀）仍**必须可读** ——
     失败判定仍走 `tools.registry.is_error_result()` 的回退路径，
     本模块**不改**它的语义。

3. `build_envelope(name, result)` —— **把产出套成信封**（`ENVELOPE_TOOLS`
   里登记的工具才套）。`audit().envelope_tools` 非空 = 产出检验**真的接上了**，
   而不是"机制建好了没人用"（统筹方 2026-10-03 的追加验收 ③）。

4. `audit()` —— 把「声明 vs 实现」变成机判事实
   （18 个工具是否都封闭、别名是否指向真实属性、必需键是否都在 properties 里、
   产出检验接到了哪些工具上）。

为什么"未知键"必须是**结构化**拒绝
----------------------------------
静默忽略会让模型无法从错误里学习：它看不到自己键名写错了，
只会看到"工具没反应"。结构化拒绝把 `{code, message, hint}` 回灌给模型，
它下一轮才知道该改哪个键。
"""

import json
from typing import Any

from .registry import TOOLS_MAP, is_error_result

# ---------------------------------------------------------------------------
# 1) 别名表（声明式）
# ---------------------------------------------------------------------------
#: 每个工具的**同义键名 → canonical 键名**。只做"同一个语义参数的不同写法"，
#: **不**做跨语义的猜测（例如不会把 `url` 归一成 `filename`）。
#: 规则：canonical 名一律取 `parameters.properties` 里已有的那个；
#: 别名不得与任何 canonical 名冲突（`audit()` 会机械核对）。
ALIASES: dict[str, dict[str, str]] = {
    "get_weather": {"location": "city", "place": "city", "town": "city"},
    "calculate": {"expr": "expression", "formula": "expression", "math": "expression"},
    "read_file": {
        "file": "filename", "filepath": "filename", "file_name": "filename",
        "path": "filename", "name": "filename",
    },
    "write_file": {
        "file": "filename", "filepath": "filename", "file_name": "filename",
        "path": "filename",
        # ★ 实测的"同义不同形"就是这一条：{"filename":…,"content":…} vs {"code":…}
        "code": "content", "text": "content", "body": "content",
        "contents": "content", "data": "content",
    },
    "fetch_url": {"link": "url", "uri": "url", "address": "url"},
    "get_architecture": {"max": "limit", "top": "limit", "count": "limit"},
    "get_module": {
        "file": "path", "filename": "path", "filepath": "path",
        "module": "path", "name": "path",
    },
    "find_symbol": {
        "symbol": "name", "symbol_name": "name", "func": "name", "function": "name",
    },
    "review_document": {
        "file": "path", "filename": "path", "document": "path", "doc": "path",
    },
    "run_python": {"source": "code", "script": "code", "python_code": "code"},
    "check_syntax": {"source": "code", "script": "code", "text": "code"},
    "run_lint": {"source": "code", "script": "code", "text": "code"},
    "review_code": {"source": "code", "script": "code", "text": "code"},
    "check_and_run": {
        "source": "code", "script": "code", "text": "code",
        "expected_exit": "expect_exit",
    },
    "parse_python_error": {"text": "raw", "traceback": "raw", "error": "raw"},
    "reflect_on_history": {
        "limit": "limit_cycles", "cycles": "limit_cycles", "count": "limit_cycles",
    },
}

#: 归一化的四条规则（与契约 `tool_call_contract.normalization_rules` 逐条对应）。
NORMALIZATION_RULES: tuple[str, ...] = (
    "1 类型强制：按 schema 做可判定的强制（如 \"3\"→3）；不可判定的不猜，报错。",
    "2 缺省填充：schema 有 default 的键补上，使「省略」与「显式给默认值」等价。",
    "3 别名归一：已知同义键名收敛到一个 canonical 名（映射表见 ALIASES）。",
    "4 未知键拒绝：不在 properties 里的键结构化报错，不得静默丢弃、不得塞进 kwargs。",
)

# ---------------------------------------------------------------------------
# 2) 结果信封（新协议）与旧协议兼容
# ---------------------------------------------------------------------------
#: 结果信封的必需键（契约 `tool_call_contract.result_envelope.required`）。
RESULT_ENVELOPE_KEYS: tuple[str, ...] = ("ok", "kind", "data", "error")

#: 已登记结果信封的**现役工具** → 该工具成功产出的 `kind`（结果类别）。
#:
#: ★ 2026-10-03 追加验收（统筹方复验 D33）：`validate_result` 建好了，但
#: `envelope_tools` 是**空集** ⇒ **没有任何工具的结果会被校验** ——
#: 「机制存在」不等于「机制接上了」。所以这张表必须非空，且 `audit()` 会
#: 机械报告它接到了谁身上。
#:
#: 登记 = 承诺：该工具经 `Worker._invoke` 的产出**一定是合规信封**
#: （`{ok, kind, data, error}`）；不合规会被 `validate_result` 判 `reject`，
#: 回灌 `tool-result-invalid`，模型不会把它当成功读。
ENVELOPE_TOOLS: dict[str, str] = {
    # 复合工具：语法检查 + 执行 + traceback 解析；它的结构化产出本来就是
    # `{ok, syntax_passed, run_ok, parsed_error}`，套信封是**分类**而不是改语义。
    "check_and_run": "verification",
}

#: 尚未登记的工具 → **为什么**（分阶段迁移的判据，写在这里而不是口头说）。
#: 判据只有一条：**产出形状**。工具自己已经返回自解释 JSON 的，套信封要动
#: 到别人的读法（例如 `pipeline` 的 check 阶段读 `run_lint` 的 `ok`），
#: 所以先只接"形状天然一致"的那一类，其余逐个按同一张表登记。
#: 新增工具必须直接登记（契约：新工具走结构化）。
STAGED_OUT_OF_ENVELOPE: dict[str, str] = {
    "run_lint": "产出 {ok,issues}，pipeline.run_check 直接读它的 ok（先动读法再登记）",
    "check_syntax": "产出 {ok} / {ok,error:{...}}，pipeline.run_check 直接读（同上）",
    "list_workspace": "产出 {ok,workspace,files}，形状接近信封（下一批）",
    "parse_python_error": "产出解析结果 dict，无 ok 键（下一批）",
    "find_symbol": "产出 {ok,found,...} / {ok,error:字符串}（error 形状要先统一）",
    "get_module": "产出 {ok,path,...} / {ok,error:字符串}（同上）",
    "run_python": "产出纯文本（stdout），是 Core 交付物的主要来源（最后一批）",
    "write_file": "产出 OK:FILE| 文本流，worker._maybe_artifact 与前端都在读（最后一批）",
    "read_file": "产出纯文本（无 ok 键），模型按文本读（最后一批）",
    "review_code": "产出 {ok,issues,metrics}，建议性结论（下一批）",
    "get_architecture": "产出派生架构视图文本（最后一批）",
    "review_document": "产出机械检查报告文本（最后一批）",
    "reflect_on_history": "产出只读分析文本（最后一批）",
    "calculate": "产出纯数字文本；失败走 Error: 前缀（下一批）",
    "get_weather": "占位工具，产出纯文本（下一批）",
    "fetch_url": "产出网页文本（最后一批）",
    "get_system_info": "产出自解释 JSON（键是中文），无 ok 键（下一批）",
}



class ToolArgError(Exception):
    """实参不合规 —— 结构化拒绝（不是"静默忽略"）。"""

    def __init__(self, code: str, message: str, hint: str = ""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint

    def to_dict(self) -> dict:
        out = {"code": self.code, "message": self.message}
        if self.hint:
            out["hint"] = self.hint
        return out


def error_result(tool_name: str, err: ToolArgError) -> str:
    """把结构化拒绝渲染成**结果信封**（`ok=false` + `error`）。"""
    return json.dumps(
        {
            "ok": False,
            "kind": "error",
            "error": err.to_dict(),
            "tool": tool_name,
        },
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# 3) 实参归一
# ---------------------------------------------------------------------------
def _schema_of(tool_name: str) -> dict | None:
    info = TOOLS_MAP.get(tool_name)
    if not info:
        return None
    params = info.get("parameters")
    return params if isinstance(params, dict) else None


def _coerce(tool_name: str, key: str, value: Any, spec: dict) -> Any:
    """按 schema 做**可判定**的类型强制；判不了就报错（不猜）。"""
    typ = spec.get("type")
    if typ in (None, "any"):
        return value

    if typ == "string":
        if isinstance(value, str):
            return value
        # bool 是独立 JSON 类型，转成 "True" 属于猜测 —— 拒绝。
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
        raise ToolArgError(
            "type-mismatch",
            f"工具 {tool_name} 的 {key} 需要 string，收到 {type(value).__name__}",
            hint=f"把它写成字符串，例如 {{\"{key}\": \"...\"}}",
        )

    if typ == "integer":
        if isinstance(value, bool):
            raise ToolArgError("type-mismatch",
                               f"工具 {tool_name} 的 {key} 需要 integer，收到 boolean")
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str):
            s = value.strip()
            try:
                return int(s)
            except ValueError:
                raise ToolArgError(
                    "type-mismatch",
                    f"工具 {tool_name} 的 {key} 需要 integer，无法从 {value!r} 判定",
                    hint="只接受整数或整数字符串（如 \"3\"）；小数不接受",
                ) from None
        raise ToolArgError("type-mismatch",
                           f"工具 {tool_name} 的 {key} 需要 integer，收到 {type(value).__name__}")

    if typ == "number":
        if isinstance(value, bool):
            raise ToolArgError("type-mismatch",
                               f"工具 {tool_name} 的 {key} 需要 number，收到 boolean")
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            try:
                return float(value.strip())
            except ValueError:
                raise ToolArgError("type-mismatch",
                                   f"工具 {tool_name} 的 {key} 需要 number，无法从 {value!r} 判定") from None
        raise ToolArgError("type-mismatch",
                           f"工具 {tool_name} 的 {key} 需要 number，收到 {type(value).__name__}")

    if typ == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in ("true", "false"):
            return value.strip().lower() == "true"
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
        raise ToolArgError("type-mismatch",
                           f"工具 {tool_name} 的 {key} 需要 boolean，收到 {value!r}")

    if typ in ("object", "array"):
        want = dict if typ == "object" else list
        if isinstance(value, want):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, want):
                return parsed
        raise ToolArgError("type-mismatch",
                           f"工具 {tool_name} 的 {key} 需要 {typ}，收到 {type(value).__name__}")

    return value


def normalize_args(tool_name: str, args: Any) -> dict:
    """把模型给的实参归一成 canonical 形式；不合规抛 `ToolArgError`。

    顺序就是契约里那四条：别名归一 → 未知键拒绝 → 类型强制 → 必需键校验
    → 缺省填充。顺序有讲究：先归一再判未知，否则 `{"code": …}` 这种别名
    会被当成未知键拒掉。
    """
    if tool_name not in TOOLS_MAP:
        raise ToolArgError("unknown-tool", f"未知工具 {tool_name}")

    schema = _schema_of(tool_name) or {}
    props: dict = schema.get("properties") or {}
    required: list = schema.get("required") or []
    alias_map = ALIASES.get(tool_name, {})

    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise ToolArgError(
            "invalid-arguments",
            f"工具 {tool_name} 的实参必须是 JSON 对象，收到 {type(args).__name__}",
        )

    # --- 规则 3：别名归一（canonical 名优先；同归一键取值冲突即拒绝）---
    out: dict = {}
    for key, value in args.items():
        canonical = alias_map.get(key, key)
        if canonical in out:
            if out[canonical] != value:
                raise ToolArgError(
                    "ambiguous-key",
                    f"键 {key!r} 与 {canonical!r} 归一后取值不同，无法判定用哪个",
                    hint=f"只保留 {canonical!r} 一个键",
                )
            continue
        out[canonical] = value

    # --- 规则 4：未知键结构化拒绝（不静默丢弃）---
    unknown = [k for k in out if k not in props]
    if unknown:
        hint_parts = [f"可用键: {sorted(props) or '（无，此工具不收参数）'}"]
        if alias_map:
            hint_parts.append(f"已知别名: {sorted(alias_map)}")
        raise ToolArgError(
            "unknown-key",
            f"工具 {tool_name} 不认识键 {sorted(unknown)}；未声明的键一律拒绝，不会静默忽略",
            hint="；".join(hint_parts),
        )

    # --- 规则 1：类型强制 ---
    for key in list(out):
        out[key] = _coerce(tool_name, key, out[key], props[key])

    # --- 必需键 ---
    missing = [k for k in required if k not in out]
    if missing:
        raise ToolArgError(
            "missing-required",
            f"工具 {tool_name} 缺少必需参数 {missing}",
            hint=f"必需: {sorted(required)}",
        )

    # --- 规则 2：缺省填充（schema 里写了 default 的键）---
    for key, spec in props.items():
        if key not in out and isinstance(spec, dict) and "default" in spec:
            out[key] = spec["default"]

    return out


def try_normalize(tool_name: str, args: Any) -> tuple[dict | None, ToolArgError | None]:
    """不抛异常的版本，便于"读参数"的旁路（去重、存档）使用。"""
    try:
        return normalize_args(tool_name, args), None
    except ToolArgError as e:
        return None, e


# ---------------------------------------------------------------------------
# 4) 结果检验
# ---------------------------------------------------------------------------
def _as_json_object(text: str) -> dict | None:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _envelope_problems(parsed: dict) -> list[str]:
    """检查 `{ok, kind, data, error}` 形状；返回问题清单（空 = 合规）。"""
    problems: list[str] = []
    if not isinstance(parsed.get("ok"), bool):
        problems.append("ok 必须是布尔")
    if not isinstance(parsed.get("kind"), str) or not parsed.get("kind", "").strip():
        problems.append("kind 必须是非空字符串")
    if parsed.get("ok") is True and "data" not in parsed:
        problems.append("ok=true 时必须带 data")
    if parsed.get("ok") is False:
        err = parsed.get("error")
        if not isinstance(err, dict) or not err.get("code") or not err.get("message"):
            problems.append("ok=false 时 error 必须含 code/message")
    return problems


def validate_result(tool_name: str, result: Any) -> dict:
    """检验工具产出；返回可机器读的报告。

    兼容纪律：**旧字符串结果必须仍可读**。所以只有
    `ENVELOPE_TOOLS` 里登记的工具、且产出明显是"半成品信封"时，
    `action` 才是 `reject`；纯字符串一律 `accept`（判定仍走 `is_error_result`）。
    """
    text = result if isinstance(result, str) else str(result)
    report = {
        "tool": tool_name,
        "protocol": "plain-string",
        "conforms": True,
        "problems": [],
        "action": "accept",
        "is_error": is_error_result(text),
        "error_result": None,
    }

    parsed = _as_json_object(text)
    if parsed is None:
        return report

    if not isinstance(parsed.get("ok"), bool):
        # 自解释 JSON（如 get_system_info / parse_python_error）—— 旧协议，照读
        report["protocol"] = "json"
        return report

    envelope_required = tool_name in ENVELOPE_TOOLS
    problems = _envelope_problems(parsed)
    if not problems:
        report["protocol"] = "envelope"
        return report

    report["conforms"] = False
    report["problems"] = problems
    report["protocol"] = "envelope" if envelope_required else "legacy-json"
    if envelope_required:
        report["action"] = "reject"
        report["error_result"] = json.dumps(
            {
                "ok": False,
                "kind": "error",
                "error": {
                    "code": "tool-result-invalid",
                    "message": f"工具 {tool_name} 的产出不符合结果信封：" + "；".join(problems),
                    "hint": "新工具必须返回 {ok, kind, data, error}；ok=false 时 error 必填",
                },
                "tool": tool_name,
            },
            ensure_ascii=False,
        )
    return report


# ---------------------------------------------------------------------------
# 4.5) 产出入信封（**接线**：机制存在的下一步）
# ---------------------------------------------------------------------------
def _parse_payload(result: Any) -> tuple[Any, str]:
    """把工具产出读成 (payload, protocol)；读不出结构化就原样当文本。"""
    text = result if isinstance(result, str) else str(result)
    parsed = _as_json_object(text)
    if parsed is None:
        return text, "plain-string"
    return parsed, "json"


def _error_object(payload: Any, protocol: str) -> dict:
    """从工具的失败产出里**抽出** `{code, message}`（尽量不丢信息、不编造）。"""
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            code = str(err.get("code") or "tool-error")
            msg = str(err.get("message") or err.get("type") or code)
            out = {"code": code, "message": msg}
            if err.get("hint"):
                out["hint"] = str(err["hint"])
            return out
        # check_and_run 这类：失败细节在 parsed_error / message 里
        parsed = payload.get("parsed_error")
        if isinstance(parsed, dict) and (parsed.get("message") or parsed.get("error_type")):
            msg = str(parsed.get("message") or parsed.get("error_type"))
            etype = str(parsed.get("error_type") or "tool-error")
            out = {"code": etype, "message": str(payload.get("message") or msg)}
            cat = parsed.get("category")
            if isinstance(cat, dict) and cat.get("kind"):
                out["category"] = str(cat["kind"])
            return out
        if payload.get("message"):
            return {"code": "tool-error", "message": str(payload["message"])}
        # 自解释 JSON 带 `ok:false` 但没有 error/message：把对象本身当说明
        return {"code": "tool-error",
                "message": json.dumps(payload, ensure_ascii=False, default=str)[:300]}
    if protocol == "json":
        return {"code": "tool-error",
                "message": json.dumps(payload, ensure_ascii=False, default=str)[:300]}
    return {"code": "tool-error", "message": str(payload)[:300]}


def build_envelope(tool_name: str, result: Any) -> str:
    """把工具的产出套成**结果信封**（只对 `ENVELOPE_TOOLS` 里登记的工具）。

    ★ 为什么必须有一个地方真的套 —— 统筹方 2026-10-03 追加验收 ③：
    `validate_result` 是准备好了的能力，但 `envelope_tools` 是空集，
    「工具生成的东西也要做检验」就等于**没有交付**（机制没接上）。

    形状（契约 `tool_call_contract.result_envelope`）：

        {ok, kind, data, error}      ok=false 时 error 必填、ok=true 时 data 必填

    类别规则（机械可判，不猜）：

    ==========================  =============================================
    产出                        信封
    ==========================  =============================================
    `Error:` / `错误：` 前缀      `ok=false, kind="error", error={code,message}`
    JSON 且带布尔 `ok`           `ok=该值`；`data` 是原产出、`error` 由它抽出
    其余（纯文本 / 自解释 JSON） `ok=true, kind=<登记类别>, data=<原产出>`
    ==========================  =============================================

    旧读法仍然可读：错误信封的 `ok=false` 正好是 `is_error_result()` 认的形状；
    成功信封带 `data`，工具自己那份内容**原样**放在里面（不重排、不改写）。
    """
    kind = ENVELOPE_TOOLS[tool_name]
    payload, protocol = _parse_payload(result)

    box: dict = {"tool": tool_name}
    is_dict = isinstance(payload, dict)
    ok = payload.get("ok") if is_dict else None

    if not isinstance(ok, bool):
        ok = not (protocol == "plain-string"
                  and is_error_result(payload if isinstance(payload, str) else str(payload)))

    if ok:
        box["ok"] = True
        box["kind"] = kind
        box["data"] = payload
    else:
        box["ok"] = False
        box["kind"] = "error"
        box["error"] = _error_object(payload, protocol)
        if is_dict:
            # 失败时的结构化细节（frames / category / exit_code）也留着 ——
            # 信封是**分类**，不是把工具已经算出来的事实丢掉。
            box["data"] = payload

    return json.dumps(box, ensure_ascii=False, default=str)


def envelope_of(result: Any) -> dict | None:
    """读出信封对象；不是信封（还是旧协议）返回 `None`。

    判据：带**布尔** `ok` **且**带 `kind`（信封自己的标记），
    所以工具自己的自解释 JSON 不会被误认成信封。
    """
    text = result if isinstance(result, str) else str(result)
    parsed = _as_json_object(text)
    if parsed is None:
        return None
    if not isinstance(parsed.get("ok"), bool) or not isinstance(parsed.get("kind"), str):
        return None
    return parsed


def unwrap_payload(result: Any) -> Any:
    """从信封取回工具**原本的产出**；不是信封则原样返回。

    用途：`worker._maybe_artifact` 这类"要读产出内容"的旁路 ——
    登记信封之后，产出内容在 `data` 里，但读法仍然是同一份内容。
    """
    env = envelope_of(result)
    if env is None:
        return result
    return env.get("data")


def envelope_policy() -> dict:
    """分阶段迁移的**声明**（哪些工具已接、哪些没接、判据是什么）。"""
    remaining = sorted(n for n in TOOLS_MAP if n not in ENVELOPE_TOOLS)
    return {
        "registered": {n: ENVELOPE_TOOLS[n] for n in sorted(ENVELOPE_TOOLS)},
        "registered_count": len(ENVELOPE_TOOLS),
        "remaining": remaining,
        "remaining_reasons": {n: STAGED_OUT_OF_ENVELOPE.get(n, "未说明")
                              for n in remaining},
        "criterion": (
            "分阶段迁移的判据是**产出形状**：工具自己已返回自解释 JSON、"
            "且上游另有读法（pipeline.check 等）的先动读法再登记；"
            "新增工具必须直接登记（契约：新工具走结构化）。"
        ),
    }

def audit() -> dict:
    """18 个工具的封闭性 + 别名表自洽 + 信封登记，全部机器可判定。"""
    not_closed: list[str] = []
    bad_type: list[str] = []
    bad_required: list[str] = []
    for name, info in sorted(TOOLS_MAP.items()):
        params = info.get("parameters") or {}
        if params.get("additionalProperties") is not False:
            not_closed.append(name)
        if params.get("type") != "object":
            bad_type.append(name)
        props = params.get("properties") or {}
        for key in params.get("required") or []:
            if key not in props:
                bad_required.append(f"{name}:{key}")

    bad_alias: list[str] = []
    for name, mapping in sorted(ALIASES.items()):
        info = TOOLS_MAP.get(name)
        if not info:
            bad_alias.append(f"{name}: 工具不存在")
            continue
        props = (info.get("parameters") or {}).get("properties") or {}
        for alias, canonical in sorted(mapping.items()):
            if canonical not in props:
                bad_alias.append(f"{name}:{alias}->{canonical}（canonical 不是声明属性）")
            if alias in props:
                bad_alias.append(f"{name}:{alias} 同时是 canonical 属性与别名（歧义）")

    unknown_envelope = sorted(n for n in ENVELOPE_TOOLS if n not in TOOLS_MAP)
    # 登记了信封却没有类别名（kind）⇒ 声明不完整，同样算不通过
    bad_envelope_kind = sorted(
        n for n, k in ENVELOPE_TOOLS.items()
        if not isinstance(k, str) or not k.strip()
    )

    return {
        "tool_count": len(TOOLS_MAP),
        "not_closed": not_closed,
        "bad_type": bad_type,
        "required_not_in_properties": bad_required,
        "bad_alias_targets": bad_alias,
        "envelope_tools": sorted(ENVELOPE_TOOLS),
        "envelope_tool_count": len(ENVELOPE_TOOLS),
        "unknown_envelope_tools": unknown_envelope,
        "bad_envelope_kinds": bad_envelope_kind,
        "alias_tool_count": len(ALIASES),
        "ok": not (not_closed or bad_type or bad_required
                   or bad_alias or unknown_envelope or bad_envelope_kind),
    }


def describe_contract() -> dict:
    """给 `/profile` / 文档用的紧凑视图（别名表在此**公开声明**）。"""
    return {
        "policy": (
            "additive：只收紧形状与校验，不改工具名与参数语义，"
            "不引入第二种传输格式"
        ),
        "normalization_rules": list(NORMALIZATION_RULES),
        "aliases": {k: dict(v) for k, v in sorted(ALIASES.items())},
        "result_envelope": {
            "required": list(RESULT_ENVELOPE_KEYS),
            "compatibility": "旧字符串结果（含 Error: 前缀）仍可读，is_error_result() 回退路径保留",
            "envelope_tools": sorted(ENVELOPE_TOOLS),
            "envelope_tool_count": len(ENVELOPE_TOOLS),
            "built_by": "tools.tool_contract.build_envelope（Worker._invoke 在产出检验之后套上）",
            "staged": envelope_policy(),
        },
        "audit": audit(),
    }
