"""契约自检：上游换了新版本之后，告诉我还差什么。

为什么必须有它
--------------
`bridge` 依赖上游的若干**具体接口**（类名、方法名、构造参数）。上游一迭代，
这些可能悄悄变掉，表现为"事件少了几个""前端某个面板一直是空的"——
**不报错的失效最难查**。

所以把依赖列成表，启动时逐条核对，缺什么就指名道姓地说出来：

    bridge 依赖 upstream 的 12 个接口，缺 2 个：
      ✗ core.CodingCycle._new_file_artifacts   → 前端「产物文件」会一直为空
      ✗ tools.is_error_result                  → 工具成败无法判定

比"前端不显示"好查得多。
"""

import importlib
import inspect
import os
from dataclasses import dataclass, field

from . import paths


@dataclass
class Requirement:
    """bridge 对上游的一条依赖。写明**缺了会怎样**，否则报错等于没说。"""

    module: str
    attr: str
    impact: str
    optional: bool = False


#: bridge 依赖的上游接口清单。**改动 hooks.py 时必须同步这张表。**
REQUIREMENTS: tuple[Requirement, ...] = (
    Requirement("core.coding_cycle", "CodingCycle", "整个流程跑不起来"),
    Requirement("core.coding_cycle", "CodingCycle._emit",
                "cycle 级事件（plan/manifest/verify/cycle_end…）全部丢失"),
    Requirement("core.coding_cycle", "CodingCycle.run", "无法起一次运行"),
    Requirement("core.coding_cycle", "CodingCycle._new_file_artifacts",
                "前端「产物文件」面板会一直为空"),
    Requirement("core.cycle", "CycleReport.enter",
                "阶段流水线动画不会推进（phase 事件丢失）"),
    Requirement("core.checkpoint", "CheckpointManager.commit",
                "看不到检查点（baseline / 成功提交）"),
    Requirement("core.checkpoint", "CheckpointManager.rollback",
                "看不到回退（回退标记与次数）"),
    Requirement("core.orchestrator", "Orchestrator._decide",
                "看不到主循环轮次与模型决策原文"),
    Requirement("core.worker", "Worker.run", "任务列表为空"),
    Requirement("core.worker", "Worker._invoke", "工具调用面板为空"),
    Requirement("core.worker", "Worker._parse_args", "工具参数无法预览"),
    Requirement("core.llm", "LLMClient.chat", "子循环步数与模型响应看不到"),
    Requirement("core.pipeline", "CheckPipeline.run_verify",
                "「循环内验证回流」看不到"),
    Requirement("tools", "is_error_result", "工具成败无法判定"),
)


@dataclass
class Report:
    ok: bool = True
    missing: list[str] = field(default_factory=list)
    present: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        n = len(self.present) + len(self.missing)
        if self.ok:
            base = f"bridge 依赖上游的 {n} 个接口，全部就位。"
            return base + ("\n  " + "\n  ".join(self.notes) if self.notes else "")
        lines = [f"bridge 依赖上游的 {n} 个接口，缺 {len(self.missing)} 个："]
        lines += [f"  ✗ {m}" for m in self.missing]
        lines += [f"  （{len(self.present)} 个就位）"]
        if self.notes:
            lines += ["  " + x for x in self.notes]
        return "\n".join(lines)


def _resolve(module: str, dotted_attr: str):
    mod = importlib.import_module(module)
    obj = mod
    for part in dotted_attr.split("."):
        obj = getattr(obj, part, None)
        if obj is None:
            return None, mod
    return obj, mod


def check(verbose: bool = False) -> Report:
    """核对全部依赖。不抛异常——调用方决定是警告还是拒绝启动。"""
    rep = Report()

    for req in REQUIREMENTS:
        try:
            obj, _ = _resolve(req.module, req.attr)
        except Exception as e:  # 模块本身 import 不了
            obj = None
            rep.notes.append(f"{req.module} 导入失败: {type(e).__name__}: {e}")

        if obj is None:
            rep.missing.append(f"{req.module}.{req.attr}  → {req.impact}")
            if not req.optional:
                rep.ok = False
        else:
            rep.present.append(f"{req.module}.{req.attr}")

    # ---- 运行根是否真的生效 ----
    # 这是最容易悄悄坏掉的一条：CWD 没切过去，上游会在仓库根新建目录。
    cwd = os.getcwd()
    if os.path.realpath(cwd) != os.path.realpath(paths.RUNTIME_ROOT):
        rep.ok = False
        rep.missing.append(
            f"CWD 不在运行根（当前 {cwd}，应为 {paths.RUNTIME_ROOT}）"
            "  → 上游会在仓库根乱建 workspace/ storage_data/ sessions/"
        )
    else:
        rep.present.append("CWD == 运行根")

    stray = paths.stray_dirs()
    if stray:
        rep.notes.append(
            f"⚠ 仓库根出现了运行态目录 {stray} —— 说明有路径没被运行根覆盖住。"
            f" 删掉它们，并检查上游是不是新增了写死相对路径的地方。"
        )

    # ---- 挂钩是否装上 ----
    try:
        from . import hooks

        hr = hooks.report()
        if hr.get("installed"):
            rep.present.append(f"hooks ×{len(hr['installed'])}")
        for note in hr.get("skipped", []):
            rep.notes.append(f"提示：{note}")
    except Exception as e:
        rep.ok = False
        rep.missing.append(f"hooks 未安装: {type(e).__name__}: {e}")

    # ---- 前端产物 ----
    if os.path.isdir(paths.FRONTEND_DIST):
        rep.present.append("frontend/dist")
    else:
        rep.notes.append(
            "frontend/dist 不存在 → `/app` 不会注册（先在 frontend/ 下 npm run build）"
        )

    if verbose:
        rep.notes.append(f"运行根: {paths.RUNTIME_ROOT}")
        rep.notes.append(f"上游代码: {paths.BACKEND_DIR}")
    return rep


def smoke() -> dict:
    """更轻的诊断：只报关键事实，供 `/api/health` 用。"""
    return {
        "runtime_root": paths.RUNTIME_ROOT,
        "stray_dirs": paths.stray_dirs(),
        "frontend_built": os.path.isdir(paths.FRONTEND_DIST),
        "upstream_modules": sorted(
            {".".join(r.attr.split(".")[:0]) or r.module for r in REQUIREMENTS}
        ),
    }


def describe_calls() -> dict:
    """诊断：列出每个挂钩点的签名，便于人工比对上游改了什么。"""
    out: dict[str, str] = {}
    for req in REQUIREMENTS:
        try:
            obj, _ = _resolve(req.module, req.attr)
            out[f"{req.module}.{req.attr}"] = str(inspect.signature(obj)) if obj else "(缺失)"
        except Exception as e:
            out[f"{req.module}.{req.attr}"] = f"(错误: {e})"
    return out
