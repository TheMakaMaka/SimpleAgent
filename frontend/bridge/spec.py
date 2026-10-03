"""标定方案：后端把「自己长什么样」声明出来，前端照单渲染。

为什么要有这个
--------------
在这之前，前端的"低定制"是假的：阶段名、事件词表、工具名、状态色
**全写死在前端代码里**。后端一改（加阶段、改事件名、加工具），前端就得跟着改。

现在反过来：

    后端（bridge/spec.py）  ──GET /api/spec──▶  前端
    声明：有哪些阶段、哪些事件、哪些工具      照单渲染，自己不写死任何后端事实

于是：
  - 后端加一个阶段（例如 CYCLE.md §11.2 规划的 REVIEW）→ 前端自动多一个节点；
  - 后端加一个事件 → 前端按声明的 label/tone 渲染，不再出现裸 kind；
  - 工具改了 → 前端从 spec 拿中文标签。

三件事刻意分开
--------------
| 层 | 内容 | 谁维护 |
|---|---|---|
| **事实** | 有哪些阶段、哪些事件、有哪些工具 | **从代码里扫出来**（AST / `PHASE_ORDER` / `TOOLS_MAP`），不手写 |
| **标定** | 每个事实的中文名、色调、归到哪个面板 | 本模块的 `CALIBRATION`，可被 `spec.override.json` 覆盖 |
| **渲染** | 怎么画 | 前端，不含任何后端事实 |

事实**从代码扫**而不是手写，是因为手写的一定会漂移——这正是 §17 那个
「前端认的事件和后端发的不一致」问题的根因。现在 spec 只能反映现实。

未标定的事实不会让前端崩
------------------------
扫到但没标定的事件，会自动生成一个像样的默认值（label 由 kind 推导、tone=info），
并出现在 `uncalibrated` 列表里。**降级可见，而不是静默丢失。**
"""

import ast
import io
import json
import os
import re
from datetime import datetime
from typing import Any

from . import paths

SPEC_VERSION = "1.0"

#: 标定覆盖文件（可选）。放仓库根，用户自己改，不碰代码。
OVERRIDE_FILE = os.path.join(paths.ROOT, "spec.override.json")


# ============================================================
# 事实：从代码里扫
# ============================================================
def _scan_calls(path: str, func_names: set[str]) -> list[tuple[str, int]]:
    """AST 扫出 `func("kind", ...)` 的第一参数，返回 [(kind, lineno)]。

    认三种写法（**都出现过，扫描器必须跟着代码走**）：

        emit_progress("phase", ...)            ← 直接调用
        _safe(emit_progress, "phase", ...)     ← 早期写法（实参在保护之外）
        emit_safe("phase", _build, ...)        ← 现行写法（payload 构造也在保护内）

    ★ 最后一种是 P6（`_safe` 契约）引入的。**漏认它会让 `/api/spec` 少认 5 个 bridge 事件**
    —— 实测：只认前两种时 bridge 侧从 21 掉到 **0**（`phase`/`files`/`task_start`/
    `tool_call`/`verify_probe` 全没了，`files`/`tool_start` 这类就再也不显示）。
    这个漏洞是**我自己的门禁**（`test_partition` / `test_spec` / `test_event_contract`）抓到的。
    """
    if not os.path.isfile(path):
        return []
    try:
        tree = ast.parse(io.open(path, encoding="utf-8").read())
    except SyntaxError:
        return []

    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        fn = node.func
        name = getattr(fn, "attr", None) or getattr(fn, "id", None)

        target = None
        if name in func_names:
            target = node.args[0]
        elif name == "emit_safe" and len(node.args) >= 2:
            # `emit_safe(kind, build, *args)` —— 首参就是 kind
            target = node.args[0]
        elif name == "_safe" and len(node.args) >= 2:
            first = node.args[0]
            if getattr(first, "id", None) in func_names:
                target = node.args[1]

        if isinstance(target, ast.Constant) and isinstance(target.value, str):
            out.append((target.value, node.lineno))
    return out


def event_kinds() -> dict[str, list[str]]:
    """扫出后端实际会发的每一个事件 kind，附来源文件。

    三处都要扫，缺一处就有事件在 spec 里消失：
      1. `backend/core/coding_cycle.py` —— 上游自带的 cycle 级事件
      2. `bridge/hooks.py`             —— 挂钩补出来的事件
      3. `bridge/runner.py`            —— 运行管理器自己的事件
    """
    sources = [
        (os.path.join(paths.BACKEND_DIR, "core", "coding_cycle.py"), {"_emit"}, "upstream"),
        (os.path.join(paths.BRIDGE_DIR, "hooks.py"), {"emit_progress"}, "hooks"),
        (os.path.join(paths.BRIDGE_DIR, "runner.py"), {"append"}, "runner"),
    ]
    out: dict[str, list[str]] = {}
    for path, funcs, tag in sources:
        for kind, _line in _scan_calls(path, funcs):
            bucket = out.setdefault(kind, [])
            if tag not in bucket:
                bucket.append(tag)
    return out


def pipeline_stages(cal: dict | None = None) -> list[dict]:
    """阶段清单。**从上游的 `PHASE_ORDER` 派生**，不手写。

    上游加一个阶段（比如 REVIEW），`PHASE_ORDER` 一变这里就多一项，
    前端自动多画一个节点——这就是「预留接口」。

    `cal` 必须是**合并过覆盖文件的**标定。早先这里读的是内置 `CALIBRATION`，
    结果 `spec.override.json` 改的阶段中文名不生效（实测被 test_spec 抓到）。
    """
    cal = cal if cal is not None else CALIBRATION

    try:
        from core.cycle import PHASE_ORDER
    except Exception:
        # 上游还没加载好（例如单独跑 spec 自检）：退化为空，由调用方提示
        return []

    gate_after = dict(cal.get("gate_after", {}))
    default_labels = dict(cal.get("stage_labels", {}))
    default_hints = dict(cal.get("stage_hints", {}))
    default_icons = dict(cal.get("stage_icons", {}))

    def _stage(sid: str, kind: str) -> dict:
        return {
            "id": sid,
            "label": default_labels.get(sid, sid.upper()),
            "hint": default_hints.get(sid, ""),
            "icon": default_icons.get(sid, "generic"),
            "kind": kind,
        }

    # 把「门禁步骤」插到它该在的阶段后面。门禁不是 CyclePhase，
    # 是程序驱动的一步（如 manifest 校验），所以单独声明插入点。
    stages: list[dict] = []
    for phase in PHASE_ORDER:
        pid = phase.value
        stages.append(_stage(pid, "phase"))
        for gate_id, after in gate_after.items():
            if after == pid:
                stages.append(_stage(gate_id, "gate"))
    return stages


def tool_catalog() -> list[dict]:
    """工具清单。从上游注册表读，不手写。"""
    try:
        from tools.registry import TOOLS_MAP
    except Exception:
        return []

    labels = dict(CALIBRATION.get("tool_labels", {}))
    out: list[dict] = []
    for name, info in sorted(TOOLS_MAP.items()):
        out.append({
            "name": name,
            "label": labels.get(name, name),
            # 上游的英文描述原样带上——它描述的是"这工具干什么"，比中文短标签信息多
            "description": str(info.get("description") or "")[:240],
            "profiles": list(info.get("profiles") or ()),
            "calibrated": name in labels,
        })
    return out


# ============================================================
# 标定：中文名、色调、归到哪个面板
#
# 这一层是**可改的**（也可以被 spec.override.json 覆盖）。
# 事实层不许改——它是扫出来的。
# ============================================================
CALIBRATION: dict[str, Any] = {
    # 门禁步骤插在哪个阶段之后（不是 CyclePhase，所以单独声明）
    "gate_after": {"manifest": "write"},

    "stage_labels": {
        "plan": "PLAN", "write": "WRITE", "manifest": "MANIFEST",
        "check": "CHECK", "verify": "VERIFY", "record": "RECORD",
        "review": "REVIEW",
    },
    "stage_hints": {
        "plan": "主模型拆解目标",
        "write": "子模型调用工具落盘",
        "manifest": "声明的交付 vs 实际产出",
        "check": "语法 / lint · 由程序把关",
        "verify": "验收命令退出码",
        "record": "检查点 · 失败则回退",
        "review": "审查角色（预留）",
    },
    # 图标名 → 前端的内置图标库。认不出的名字前端会回退到通用图标，
    # 所以这里加新名字不会让界面崩。
    "stage_icons": {
        "plan": "route", "write": "pencil", "manifest": "clipboard",
        "check": "shield", "verify": "terminal", "record": "bookmark",
        "review": "magnifier",
    },

    # 事件 → {label, tone, panel, title?, detail?}
    #   tone    决定颜色：info / ok / warn / error / model / tool / phase
    #   panel   它主要被哪个面板消费
    #   title   可选模板，`{字段}` 会被事件 payload 里的同名字段替换
    #   detail  同上，用于第二行
    #
    # 没写 title/detail 的事件，前端会**自动**从常见字段里挑一个可读的
    # （detail / error / output / message / description / preview / reason / question）。
    # 所以新增事件即使不标定也不会显示成裸 kind。
    "events": {
        # 运行生命周期
        "queued": {"label": "已入队", "tone": "info", "panel": "timeline",
                   "detail": "等待工作线程接管"},
        "run_start": {"label": "开始执行", "tone": "info", "panel": "timeline",
                      "detail": "检查点后端 {backend} · 最多 {max_attempts} 次尝试"},
        "run_end": {"label": "运行结束", "tone": "ok", "panel": "timeline",
                    "detail": "{status}"},
        "cancel_requested": {"label": "收到取消请求", "tone": "warn", "panel": "timeline",
                             "detail": "将在下一个进度点生效"},
        "cancelled": {"label": "运行已取消", "tone": "error", "panel": "timeline",
                      "detail": "{message}"},
        "error": {"label": "运行出错", "tone": "error", "panel": "timeline",
                  "detail": "{message}"},
        "baseline": {"label": "记录基线检查点", "tone": "info", "panel": "timeline",
                     "detail": "{ref}"},
        "cycle_start": {"label": "cycle 开始", "tone": "info", "panel": "timeline"},
        "cycle_end": {"label": "cycle 结束", "tone": "ok", "panel": "timeline",
                      "detail": "{error}"},

        # 阶段与尝试
        "phase": {"label": "进入 {phase}", "tone": "phase", "panel": "pipeline"},
        "attempt_start": {"label": "第 {attempt} 次尝试", "tone": "phase", "panel": "attempts"},
        "retry": {"label": "准备重试（第 {attempt} 次）", "tone": "warn", "panel": "attempts",
                  "detail": "{reason}"},
        "rollback": {"label": "已回退到基线", "tone": "warn", "panel": "attempts",
                     "detail": "ref={ref}"},
        "rollback_denied": {"label": "未获准回退", "tone": "warn", "panel": "attempts",
                            "detail": "保留当前改动"},

        # 计划与任务
        "round_start": {"label": "主循环第 {round} 轮", "tone": "info", "panel": "timeline",
                        "detail": "上限 {max_rounds} 轮"},
        "orchestrator_decision": {"label": "主模型决策 → {status}", "tone": "model",
                                  "panel": "reasoning", "detail": "{reasoning}"},
        "plan": {"label": "计划声明", "tone": "info", "panel": "plan",
                 "detail": "{verify_command}"},
        "task_start": {"label": "派发任务 {task_id}", "tone": "info", "panel": "tasks",
                       "detail": "{description}"},
        "task_done": {"label": "任务 {task_id} 结束", "tone": "ok", "panel": "tasks",
                      "detail": "{error}"},
        "task_result": {"label": "任务 {task_id} 自述", "tone": "info", "panel": "tasks",
                        "detail": "{error}"},

        # 子循环与工具
        "worker_step": {"label": "子循环第 {step} 步", "tone": "tool", "panel": "tasks"},
        "model_reply": {"label": "子模型响应（{tool_calls} 个工具调用）", "tone": "model",
                        "panel": "timeline", "detail": "{content}"},
        "tool_call": {"label": "调用 {tool}", "tone": "tool", "panel": "tools"},
        "tool_result": {"label": "{tool} 返回", "tone": "tool", "panel": "tools",
                        "detail": "{preview}"},
        "files": {"label": "本轮产物 {count} 个文件", "tone": "info", "panel": "artifacts"},

        # 门禁
        "manifest": {"label": "交付清单校验", "tone": "ok", "panel": "gate"},
        "syntax": {"label": "语法检查 {path}", "tone": "ok", "panel": "gate",
                   "detail": "{message}"},
        "lint": {"label": "lint {path}", "tone": "ok", "panel": "gate",
                 "detail": "{reason}"},
        "verify_probe": {"label": "循环内验证回流", "tone": "ok", "panel": "gate",
                         "detail": "{detail}"},
        "verify": {"label": "验收命令", "tone": "ok", "panel": "gate",
                   "detail": "{detail}"},
        # ★ 上游 `FIX-VERIFY-WIRING` 加性新增（`core/contract.py` 的
        #   `EventSpec("verify_skipped", ("reason","command"), since="1.1")`）。
        #   它把「**有验证命令、却没有 pipeline**，于是验证回流整块被跳过」
        #   从"静默"变成**显式事实** —— 因为静默跳过会让上层误诊成
        #   "缺少验证命令"，把定位带偏一整轮。
        #
        #   标 `warn` 而不是 `ok`：它是**跳过了一次安全检查**，不是通过。
        #   也刻意不是 `error`：cycle 本身没失败，跳过的原因由上游在
        #   `reason` 里说清（可能是"未注入 pipeline"，也可能是"自拟判据被拒"）。
        "verify_skipped": {"label": "⚠ 验证被跳过", "tone": "warn", "panel": "gate",
                           "detail": "{reason}"},

        # ================= TRANSPARENCY-BACKEND（上游 `since="1.2"`）=================
        # ★ 这三个是**上游已经实装、但契约主本（v1.0.24）还没声明**的加性事件
        #   （`D:\PythonProject\SimpleAgent2_Cycle\core\contract.py:172/181/189`）。
        #   实测（2026-09-27，真上游）：不标定它们，`/api/spec` 就报
        #   `uncalibrated_events=[orchestrator_round, self_report, verify_criterion]`
        #   —— 与 `verify_skipped` 那次是同一类缺口，处理方式也照旧：
        #   **先认下来，别让它退化成裸文本行**。
        #
        #   上游为此还特意**避开了 `orchestrator_decision` 这个名字**
        #   （`core/contract.py:178-180` 的原话：那个 kind 由前端 bridge 发，
        #   两个生产者发同一个 kind 会让审计无法判断哪条权威）。
        #   两边数据同源（同一个 `_decide` 返回值），所以标定文案也对齐。
        "orchestrator_round": {"label": "编排器第 {round} 轮决策（{status}）", "tone": "model",
                               "panel": "tasks", "detail": "{reasoning}"},
        #   判据演化：`action ∈ {adopted, rejected, executed}`，每条自带
        #   `previous_command` / `previous_passed` —— 所以"上一条失败了、这一条换成了什么"
        #   不用按 seq 拼（这正是 B1 要的东西）。
        #   tone 取 `warn`：这条事件出现在时间线上时，**最需要被看见的就是"判据动过"**；
        #   通过与否由 `passed` 字段表达，由透明化面板负责完整呈现。
        "verify_criterion": {"label": "验收判据 {action}", "tone": "warn", "panel": "gate",
                             "detail": "{reason}{detail}"},
        #   收尾自述 + 与机械事实的对照。`ok=false` 是**自述没生成出来**，
        #   不是"模型说没事"（`core/contract.py:194-195`）。
        #   **刻意不给 `detail` 模板**：`confidence` 是对象 `{level,basis}`，
        #   `render()` 对对象做 `String(v)` 会得到 `[object Object]` —— 那正是
        #   "显示了一个事实不支持的东西"。没模板时前端会从 payload 里挑可读字段。
        "self_report": {"label": "收尾自述（与机械事实交叉核对）", "tone": "model",
                        "panel": "gate"},

        # ================= TRANSPARENCY2-BACKEND（上游 `since="1.3"`）=================
        # 同样是**先认下来**：不标定，真上游下 `/api/spec` 就报
        # `uncalibrated_events=['decompose_review','reuse']`（实测）。
        # 契约主本还没同步这两个（见 `partition.CONTRACT_LAG_KINDS`），已作为
        # 接口级缺口报给统筹方。
        #
        #   `reuse`（`core/contract.py:200`，**已在 `core/coding_cycle.py:507` 发出**）：
        #   机械层**复用性**检查 —— 同一个概念模型发明了三个名字那种事，是**阻塞**项。
        #   标 `warn`：它是"有否决权的机械关卡"，通过与否由 `passed` 说。
        "reuse": {"label": "复用性检查（机械 · 有否决权）", "tone": "warn",
                  "panel": "gate", "detail": "{blocking}"},
        #
        #   `decompose_review`（`core/contract.py:207`，**已声明、尚未发出**）：
        #   ③ 拆解合规关卡。`principles` 每条形如
        #   `{principle, verdict: violated|ok|undecidable, evidence, checked_by, independent}`。
        #   ⚠ `undecidable` 非空说明**审查范围不完整**，**不得**呈现为"审查通过"。
        #   tone 取 `warn` 而不是 `ok`，就是这个原因（"判不了"不是"通过"）。
        "decompose_review": {"label": "拆解合规审查", "tone": "warn",
                             "panel": "gate"},

        # 人工决策
        "decision_opened": {"label": "打开人工决策点", "tone": "warn", "panel": "decisions",
                            "detail": "{question}"},
        "decision_notified": {"label": "决策已推送（通道 {channel}）", "tone": "warn",
                              "panel": "decisions", "detail": "{detail}"},
        "decision_action": {"label": "人工决策生效：{action}", "tone": "warn",
                            "panel": "decisions"},
    },

    # 运行状态 → {label, tone, terminal}
    "statuses": {
        "queued": {"label": "排队", "tone": "neutral", "terminal": False},
        "running": {"label": "执行中", "tone": "live", "terminal": False},
        "passed": {"label": "通过", "tone": "ok", "terminal": True},
        "failed": {"label": "失败", "tone": "err", "terminal": True},
        "relaxed": {"label": "放宽", "tone": "warn", "terminal": True},
        "cancelled": {"label": "取消", "tone": "warn", "terminal": True},
        "error": {"label": "异常", "tone": "err", "terminal": True},
    },

    "tool_labels": {
        "write_file": "写文件", "read_file": "读文件", "run_python": "跑 Python",
        "check_syntax": "语法检查", "run_lint": "lint", "check_and_run": "执行校验",
        "get_architecture": "查架构", "get_module": "看模块", "find_symbol": "找符号",
        "review_code": "静态审查", "list_workspace": "列工作区",
    },

    # 失败终态在阶段图上的落点（前端把红灯打在哪）
    "failure_phase": "failed",
}


def _auto_event(kind: str) -> dict:
    """没标定过的事件：给一个像样的默认值，并标记出来。

    label 由 kind 推导（`task_result` → `Task Result`），tone 取 info。
    **不猜语义**——猜错比不猜更糟；只是让它可读、不出现裸 kind。
    """
    return {
        "label": kind.replace("_", " ").title(),
        "tone": "info",
        "panel": "timeline",
        "calibrated": False,
    }


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_calibration() -> tuple[dict, list[str]]:
    """标定 = 内置默认 + 用户覆盖文件。返回 (标定, 报错列表)。"""
    errors: list[str] = []
    cal = CALIBRATION
    if os.path.isfile(OVERRIDE_FILE):
        try:
            raw = json.loads(io.open(OVERRIDE_FILE, encoding="utf-8").read())
            if not isinstance(raw, dict):
                errors.append("spec.override.json 顶层必须是对象")
            else:
                cal = _deep_merge(CALIBRATION, raw)
        except (OSError, json.JSONDecodeError) as e:
            errors.append(f"spec.override.json 解析失败: {e}")
    return cal, errors


# ============================================================
# 端点：这些是 bridge 自己的，所以这里就是权威
# ============================================================
ENDPOINTS: dict[str, str] = {
    "spec": "/api/spec",
    "audit": "/api/audit",
    "health": "/api/health",
    "profile": "/api/profile",
    "runs": "/api/runs",
    "run": "/api/runs/{run_id}",
    "run_events": "/api/runs/{run_id}/events",
    "run_stream": "/api/runs/{run_id}/stream",
    "workspace_file": "/api/workspace/file",
    "workspace_tree": "/api/workspace/tree",
    "decisions": "/api/decisions",
    "answer_decision": "/api/decisions/{decision_id}/answer",
    "insights": "/api/insights",
    "reflect": "/api/reflect",
}


#: 前端可调参数。**默认值在这里，前端不再各自写死。**
UI_DEFAULTS: dict[str, Any] = {
    "poll": {
        "health_ms": 12000,
        "runs_ms": 6000,
        "decisions_ms": 2500,
    },
    "stream": {
        "reconnect_ms": 700,
        "max_reconnects": 40,
    },
    "limits": {
        "timeline": 600,
        "tool_calls": 400,
        "reasoning": 40,
        "detail_chars": 300,
    },
    "features": {
        "demo_run": True,
        "cancel": True,
        "artifact_viewer": True,
        "decision_inline": True,
    },
    "examples": [
        {
            "label": "L1 · 纯函数",
            "goal": "在 workspace 下创建 add.py，实现 add(a, b) 返回两数之和",
            "verify": "import add\nassert add.add(2, 3) == 5\nprint('PASS')",
        },
        {
            "label": "递归 + 校验",
            "goal": "在 workspace 下创建 fib.py，实现 fib(n) 返回第 n 项斐波那契数（fib(0)=0, fib(1)=1），负数抛 ValueError",
            "verify": ("import fib\nassert fib.fib(10) == 55\ntry:\n    fib.fib(-1)\n"
                       "    raise AssertionError('负数未抛 ValueError')\nexcept ValueError:\n    pass\nprint('PASS')"),
        },
    ],
}


def build_spec() -> dict:
    """组装完整标定。前端只需要这一个请求。"""
    cal, cal_errors = load_calibration()

    kinds = event_kinds()
    events: dict[str, dict] = {}
    uncalibrated: list[str] = []
    for kind in sorted(kinds):
        declared = cal.get("events", {}).get(kind)
        if declared:
            entry = dict(declared)
            entry.setdefault("calibrated", True)
        else:
            entry = _auto_event(kind)
            uncalibrated.append(kind)
        entry["sources"] = kinds[kind]
        events[kind] = entry

    # 标定了但代码里根本不发的事件：死标定，报出来（多半是上游删了事件）
    dead = sorted(k for k in cal.get("events", {}) if k not in kinds)

    ui = _deep_merge(UI_DEFAULTS, cal.get("ui", {}) or {})

    # 契约相关：版本轴与三条分区。**全部从事实源推导**，不硬编码——
    # 硬编码一份名单一定会漂，漂了以后归因就会指错人（契约里的 G2/G3 就是这么来的）。
    from . import partition as partition_mod

    stages = pipeline_stages(cal)
    cv, cv_source = partition_mod.contract_version()
    sv, sv_source = partition_mod.schema_version()
    ph = partition_mod.phases_partition(stages)

    return {
        "spec_version": SPEC_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),

        # ---- 契约版本（gap_G1）----
        # 前端据此声明它实现的 CONTRACT_VERSION；没有它，上游的
        # P-version-behind / -ahead / -unparsable 三条规则**永远不会触发**
        # ——不是"没问题"，是"判不出来"。
        #
        # `_source` 是刻意的：契约的 CONTRACT_VERSION 由 **backend 拥有**，
        # bridge 只有在读不到上游时才回退。不标来源等于 bridge 冒充 backend 说话。
        "implements_contract_version": cv,
        "implements_contract_version_source": cv_source,   # upstream | fallback
        "schema_version": sv,
        "schema_version_source": sv_source,               # upstream | absent

        "runtime": {
            "runtime_root": paths.RUNTIME_ROOT,
            "frontend_built": os.path.isdir(paths.FRONTEND_DIST),
            "stray_dirs": paths.stray_dirs(),
        },
        "endpoints": ENDPOINTS,
        # 端点分区：bridge 自己的（仅信息）vs 它重新暴露的上游端点。
        # ★ 不能把 bridge 自己的 /api/* 当成 upstream_endpoints 上报——
        #   那会让上游对 14 个它从未拥有的端点报 P-endpoint-missing(owner=backend)，
        #   与 G3 的 manifest 是同型错误。
        "endpoint_partition": partition_mod.endpoint_partition(ENDPOINTS),
        "pipeline": {
            "stages": stages,
            "failure_phase": cal.get("failure_phase", "failed"),
            # 上游阶段 vs bridge 自补的门禁节点（gap_G3）。
            # 上报给上游的 `phases` 只填 upstream，自补的走 bridge_gate_steps。
            "upstream_phases": ph["upstream"],
            "bridge_gate_steps": ph["bridge_gate_steps"],
        },
        # 事件分区（gap_G2）：上游 12 + bridge 21。
        # 平铺上报会让上游对 bridge 自产的 21 个事件报 P-event-gone-upstream。
        "event_partition": partition_mod.event_partition(),
        "statuses": cal.get("statuses", {}),
        "events": events,
        "tools": tool_catalog(),
        "ui": ui,
        # 自检信息：前端可以把它显示在"标定"面板里，人一眼看出哪里需要补
        "diagnostics": {
            "event_count": len(events),
            "uncalibrated_events": uncalibrated,
            "dead_calibrations": dead,
            # ★ 上游已实装、契约主本尚未声明的事件（事实源：`partition.CONTRACT_LAG_KINDS`）。
            #   它是**真信号**（主本落后），不是实现错 —— 但必须**显示出来**，
            #   否则"实测与契约不一致"就没人看得见。
            "contract_lag": partition_mod.CONTRACT_LAG_KINDS and sorted(
                set(event_kinds()) & set(partition_mod.CONTRACT_LAG_KINDS)
            ),
            "contract_lag_note": (
                "上游已实装、契约主本（v1.0.24）尚未声明：" 
                + "、".join(sorted(set(event_kinds()) & set(partition_mod.CONTRACT_LAG_KINDS)))
                + "。方向是「主本落后」；契约同步后本项应清空。"
                if (set(event_kinds()) & set(partition_mod.CONTRACT_LAG_KINDS)) else ""
            ),
            "override_file": OVERRIDE_FILE if os.path.isfile(OVERRIDE_FILE) else None,
            "errors": cal_errors,
        },
    }

# ============================================================
# 跨语言核对：前端认得的事件 == 后端会发的事件
#
# 前端 `store/run.ts` 的 `case` 是**手工镜像**。两边漂移不会报错，
# 只会"某类事件显示成裸文本行"——所以这里把核对做成函数，
# 测试（test_event_contract.py）与体检（scripts/doctor.py）共用同一份判据。
# ============================================================
FRONTEND_REDUCER = os.path.join(paths.ROOT, "frontend", "src", "store", "run.ts")


#: 采集器声明的词表所在的文件（`RECOGNIZED_KINDS`）
FRONTEND_COLLECTOR = os.path.join(paths.ROOT, "frontend", "src", "store", "transparency.ts")

#: 采集器声明的事件名（与 `frontend/scripts/gen-expectations.mjs` 扫的是同一处）。
#: ★ 为什么它也算"前端认得的词"：`TRANSPARENCY-UI` 的三个新事件由采集器的
#:   `RECOGNIZED_KINDS` 声明并处理（写 `case` 会与"死代码"门禁冲突，见
#:   `frontend/src/store/transparency.ts` 开头的说明）。只扫 `case` 会**少报 3 个**,
#:   于是 `/api/audit` 会给出错误的责任判定（把"前端早就认得"报成"前端没跟上"）。
def collector_event_kinds() -> set[str]:
    if not os.path.isfile(FRONTEND_COLLECTOR):
        return set()
    text = io.open(FRONTEND_COLLECTOR, encoding="utf-8").read()
    m = re.search(r"export const RECOGNIZED_KINDS = \[(.*?)\]", text, re.S)
    return set(re.findall(r"'([a-z_]+)'", m.group(1))) if m else set()


def frontend_event_kinds() -> set[str]:
    """从 TS 归约器（`case`）与采集器（`RECOGNIZED_KINDS`）抽出它认得的事件 kind。

    文件不在就返回空集合。
    """
    if not os.path.isfile(FRONTEND_REDUCER):
        return set()
    text = io.open(FRONTEND_REDUCER, encoding="utf-8").read()
    return set(re.findall(r"case '([a-z_]+)':", text)) | collector_event_kinds()


def event_contract() -> dict:
    """返回前后端事件词表的差集。两边都在时这个必须为空。"""
    backend = set(event_kinds())
    frontend = frontend_event_kinds()
    return {
        "backend_count": len(backend),
        "frontend_count": len(frontend),
        "frontend_available": bool(frontend),
        "missing_in_frontend": sorted(backend - frontend),
        "orphan_in_frontend": sorted(frontend - backend),
    }
