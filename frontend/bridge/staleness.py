"""上游副本陈旧检测：让"你正在用一个过期的 backend/"**无法被静默使用**。

为什么要有它（实测事实，不是推测）
----------------------------------
本仓库自带一份 `backend/` 是为了"开箱可跑"。但它**落后于上游**，实测：

    bundled  core 模块 27 个
    upstream core 模块 29 个
    上游有、bundled 缺：core/contract.py, core/vision.py
    两边都有但内容不同：9 个

其中 `core/contract.py` 的缺失最要命：**新契约机制（`CONTRACT_VERSION` /
`ISSUE_RULES` / `/contract/check`）整体静默不可用**。于是：

    服务照常启动 · 界面照常显示 · 契约版本退回 `fallback`
    → **没有任何一处报错**

**不报错的失效最难查** —— 这个模块就是治它：
把"我在用哪份上游、它是不是落后了、落后在哪"变成**显式且被检查**的事实。

为什么判据必须是 `paths.BACKEND_DIR`
-----------------------------------
仓库里同时存在两个同名 `core` 包（`<仓库>/backend/core` 与上游的 `core`）。
**"import 到了 core 就算对"是错的判据** —— 它两个都能 import 成功，
只取决于 `sys.path` 里谁在前面。唯一正确的判据是 `paths.BACKEND_DIR`
（它由 `AGENT_BACKEND_DIR` 决定，默认才是仓库自带的副本）。

设计约束
--------
- **纯函数、按目录取参**：不 import、不改全局状态。这样"指向一个缺
  `core/contract.py` 的目录 → 必须报落后"这条**负向测试**才写得了。
- 拿不到参照物时**不猜**：只根据标记（marker）判断，不假装知道上游最新版长什么样。
"""

import os
import re
import sys

from . import paths

#: 版本标记：这些文件/符号在，才说明上游的那套机制是**可用**的。
#:
#: 每条都写清"缺了会怎样"——否则运维看到"缺 core/vision.py"不知道要不要管。
MARKERS: tuple[tuple[str, str, str], ...] = (
    (
        "core/contract.py",
        "契约机制",
        "CONTRACT_VERSION / ISSUE_RULES / /contract/check 整体不可用，"
        "契约版本会静默退回 fallback",
    ),
    (
        "core/vision.py",
        "视觉能力",
        "依赖它的上游功能会 import 失败（或静默降级）",
    ),
)

#: 契约版本常量所在文件（与 MARKERS 里的那条对应，用于读值）
CONTRACT_FILE = "core/contract.py"


def _read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def read_contract_version(backend_dir: str) -> str:
    """从 `core/contract.py` 的源码里读出 `CONTRACT_VERSION` 的字面量。

    刻意用**读文件**而不是 `import`：import 会污染本进程的 `sys.modules`，
    那样就没法对任意目录做探针了（测"另一个目录"时会被缓存骗到）。
    读源码是弱一点但**不会说谎**的判据——读不到就返回空。
    """
    text = _read_text(os.path.join(backend_dir, CONTRACT_FILE))
    if not text:
        return ""
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("CONTRACT_VERSION") and "=" in s:
            value = s.split("=", 1)[1].strip()
            # 去掉行尾注释与引号
            for sep in ("#",):
                if sep in value:
                    value = value.split(sep, 1)[0].strip()
            return value.strip().strip("'\"").strip()
    return ""


def core_modules(backend_dir: str) -> list[str]:
    """`core/` 下的模块文件名。目录不存在时返回空。"""
    p = os.path.join(backend_dir, "core")
    if not os.path.isdir(p):
        return []
    return sorted(f for f in os.listdir(p) if f.endswith(".py"))


def probe(backend_dir: str | None = None,
          reference_dir: str | None = None) -> dict:
    """探一次：用的是哪份上游、它是否落后、落后在哪。

    `reference_dir` 可选：给了就顺带比一下模块清单（列缺的/不一致的）。
    不给也能判——**标记缺失本身就是落后**，不需要知道上游最新版的样子。
    """
    d = os.path.abspath(backend_dir or paths.BACKEND_DIR)
    is_bundled = os.path.realpath(d) == os.path.realpath(
        os.path.join(paths.ROOT, "backend")
    )

    markers = []
    for rel, what, consequence in MARKERS:
        present = os.path.isfile(os.path.join(d, rel))
        markers.append({
            "file": rel, "what": what, "present": present,
            "consequence": "" if present else consequence,
        })
    missing = [m["file"] for m in markers if not m["present"]]

    modules = core_modules(d)
    cv = read_contract_version(d)

    # ---- 与参照物对比（可选）----
    ref_modules: list[str] = []
    missing_vs_ref: list[str] = []
    if reference_dir:
        ref_modules = core_modules(reference_dir)
        if ref_modules:
            missing_vs_ref = sorted(set(ref_modules) - set(modules))

    # ---- 结论 ----
    reasons: list[str] = []
    if not os.path.isdir(d):
        reasons.append(f"目录不存在：{d}")
    if not modules:
        reasons.append("没有 core/ 目录（这不像是上游代码）")
    for m in markers:
        if not m["present"]:
            reasons.append(f"缺 {m['file']}（{m['what']}）→ {m['consequence']}")
    if modules and not cv:
        reasons.append(
            f"{CONTRACT_FILE} 里读不到 CONTRACT_VERSION → 契约版本只能退回 fallback"
        )
    if missing_vs_ref:
        reasons.append(
            f"比参照物少 {len(missing_vs_ref)} 个 core 模块：{missing_vs_ref}"
        )

    stale = bool(reasons)
    return {
        "backend_dir": d,
        "is_bundled": is_bundled,
        "markers": markers,
        "missing_markers": missing,
        "core_module_count": len(modules),
        "contract_version": cv,
        "contract_version_readable": bool(cv),
        "reference_dir": os.path.abspath(reference_dir) if reference_dir else "",
        "reference_module_count": len(ref_modules),
        "missing_vs_reference": missing_vs_ref,
        "stale": stale,
        "reasons": reasons,
        "summary": ("落后：" + "；".join(reasons)) if stale else "标记齐备，未发现落后",
    }


def startup_warning(result: dict | None = None) -> str | None:
    """启动期的醒目警告文本；不需要警告时返回 `None`。

    **返回字符串而不是直接 print** —— 这样测试能断言内容，
    调用方也能决定往哪儿写（stdout / stderr / 日志）。
    """
    r = result or probe()
    if not r["is_bundled"] and not r["stale"]:
        return None

    bar = "!" * 72
    lines = [bar]
    if r["is_bundled"]:
        lines += [
            "[警告] 你正在使用**仓库自带的** backend/ 副本（bundled），"
            "它可能落后于上游。",
            f"       位置：{r['backend_dir']}",
            "       想指向真正的最新上游：设 AGENT_BACKEND_DIR=<上游仓库目录>",
            "       （本仓库的隔离设计就是「指过去」而不是「搬过来」，见 docs/LAYOUT.md）",
        ]
    if r["stale"]:
        lines.append(f"[警告] 陈旧检测：{r['summary']}")
        lines.append("       后果：新契约机制可能静默不可用 —— 服务照常起、界面照常显示。")
    lines.append(f"       当前 core 模块 {r['core_module_count']} 个；"
                 f"CONTRACT_VERSION = {r['contract_version'] or '（读不到）'}")
    lines.append("       体检：python scripts/doctor.py ；探针：GET /api/health")
    lines.append(bar)
    return "\n".join(lines)


def reference_dir_from_env() -> str:
    """可选的参照物目录（`AGENT_UPSTREAM_DIR`）。没设就返回空。"""
    return (os.getenv("AGENT_UPSTREAM_DIR") or "").strip()


# ============================================================
# A2b：bundled 即拒绝启动
# ============================================================
#: 拒绝启动时的退出码。**非 0** 是验收标准的一部分（"不是只打警告"）。
REFUSAL_EXIT_CODE = 2

#: 逃生舱：显式允许用自带副本启动
ALLOW_BUNDLED_ENV = "AGENT_ALLOW_BUNDLED"
ALLOW_BUNDLED_FLAG = "--allow-bundled"

_TRUE = {"1", "true", "yes", "on", "y"}


def allow_bundled_requested(argv: list[str] | None = None) -> bool:
    """是否显式要求"就用自带副本启动"。

    两个入口都认（验收标准里写的是"`--allow-bundled`（或 `AGENT_ALLOW_BUNDLED=1`）"）：
    - 环境变量 `AGENT_ALLOW_BUNDLED=1`
    - 命令行 `--allow-bundled`

    环境变量是**主入口**：`uvicorn bridge.app:app` 不认识自定义 flag，
    会先报参数错误；而环境变量对任何启动方式都有效。
    `python -m bridge --allow-bundled` 那条路由 `bridge/__main__.py` 负责解析。
    """
    if (os.getenv(ALLOW_BUNDLED_ENV) or "").strip().lower() in _TRUE:
        return True
    args = sys.argv[1:] if argv is None else argv
    return ALLOW_BUNDLED_FLAG in args


def should_refuse(result: dict | None = None, *, allow: bool | None = None) -> bool:
    """该不该拒绝启动。

    ★ 判据是 **`is_bundled`（形态）**，不是 `stale`（状态）。

    这是刻意的，也是本轮最容易搞错的地方：**"副本此刻恰好同步"是一个会过期的
    属性**，而这条规则要防的正是"你以为在跑上游、其实在跑副本"这种**误解**。
    判形态，不判状态。

    （`stale` 仍然有用 —— 它用来在拒绝时说明"落后在哪、有什么后果"。）
    """
    r = result or probe()
    if allow is None:
        allow = allow_bundled_requested()
    return bool(r["is_bundled"]) and not allow


def refusal_message(result: dict | None = None) -> str:
    """拒绝启动时打印的内容。三件事，缺一不可：

    1. **实际的 `backend_dir`** —— 你到底用的是哪份；
    2. **为什么判为不可用** —— 带**后果**的理由（沿用 `probe()` 的 `summary`）；
    3. **怎么修** —— 可复制的命令。
    """
    r = result or probe()
    bar = "!" * 72
    lines = [
        "",
        bar,
        "[拒绝启动] 解析到的后端是**仓库自带的 bundled 副本**。",
        "",
        f"  实际 backend_dir : {r['backend_dir']}",
        f"  判定依据         : backend_is_bundled = True（判形态，不判状态）",
        "",
        "  为什么这不可用：",
        f"    {r['summary']}",
    ]
    if not r["stale"]:
        lines += [
            "    （注意：此刻的标记看起来是齐的 —— 但本条**不判状态**。",
            "      '此刻恰好同步'会过期，而它要防的是'以为在跑上游、其实在跑副本'。）",
        ]
    lines += [
        "",
        "  怎么修（复制一条执行，然后重启）：",
        f'    PowerShell : $env:AGENT_BACKEND_DIR = "{_suggest_upstream()}"',
        f"    cmd        : set AGENT_BACKEND_DIR={_suggest_upstream()}",
        f"    bash       : export AGENT_BACKEND_DIR={_suggest_upstream()}",
        "",
        "  确实要用自带副本（例如只想看界面）：显式开逃生舱",
        f"    PowerShell : $env:{ALLOW_BUNDLED_ENV} = '1'",
        f"    bash       : {ALLOW_BUNDLED_ENV}=1 uvicorn bridge.app:app",
        f"    或         : python -m bridge {ALLOW_BUNDLED_FLAG}",
        "    留痕字段：backend_bundled_override=true —— 降级必须留痕。",
        bar,
        "",
    ]
    return "\n".join(lines)


def _suggest_upstream() -> str:
    """给一条**可复制**的上游路径建议。

    先看参照物环境变量，再看仓库的常见同级目录；都没有就给一个明确的占位符
    —— **不编一个看起来像真的路径**（那会让人复制了却指向不存在的地方）。
    """
    explicit = reference_dir_from_env()
    if explicit:
        return explicit
    sibling = os.path.join(os.path.dirname(paths.ROOT), "SimpleAgent2_Cycle")
    if os.path.isdir(os.path.join(sibling, "core")):
        return sibling
    return r"<你的 SimpleAgent2_Cycle 上游 checkout 目录>"


# ============================================================
# 版本追溯：这个实例到底在跑"哪一份代码、哪一版前端"
# ============================================================
def frontend_asset(dist_dir: str | None = None) -> str:
    """本实例正在服务的**前端 bundle 名**（例如 `index-CsUZBNxG.js`）。

    用户的要求是"版本追溯性：我希望下次打开网页应用看到的是最新的"——
    所以这个字段回答的是「**你打开看到的是哪一版**」。

    从 `dist/index.html` 里读它引用的那个 JS —— 那才是**真正在服务的**那个文件，
    而不是"目录里最新的那个"（两者在构建中断时会不一致）。
    读不到就返回空串（不猜）。
    """
    d = dist_dir or paths.FRONTEND_DIST
    index = os.path.join(d, "index.html")
    try:
        with open(index, encoding="utf-8", errors="replace") as f:
            html = f.read()
    except OSError:
        return ""
    for m in re.finditer(r'src="([^"]+\.js)"', html):
        return os.path.basename(m.group(1))
    return ""


def provenance(result: dict | None = None, *, override: bool | None = None,
               asset: str | None = None) -> dict:
    """一次运行用的是什么 —— 供启动日志与 `/api/health` **共用同一份**。

    两处各拼一遍迟早会分叉，而这两处恰好是"我打开看到的到底是哪一版"的
    唯一答案来源。
    """
    r = result or probe()
    if override is None:
        override = allow_bundled_requested()
    if asset is None:
        asset = frontend_asset()
    return {
        "backend_dir": r["backend_dir"],
        "backend_is_bundled": r["is_bundled"],
        "backend_bundled_override": bool(override),
        "backend_stale": r["stale"],
        "backend_stale_reason": r["summary"],
        "backend_core_modules": r["core_module_count"],
        "backend_contract_version": r["contract_version"],
        "frontend_asset": asset,
    }


def provenance_lines(prov: dict) -> list[str]:
    """把 `provenance()` 渲染成可直接粘进版本记录的几行。"""
    return [
        "[bridge] ── 本次运行（版本追溯）────────────────────────────",
        f"[bridge]   后端目录      : {prov['backend_dir']}",
        f"[bridge]   自带副本      : {prov['backend_is_bundled']}"
        + ("（★ 用了逃生舱，见 backend_bundled_override）"
           if prov["backend_bundled_override"] else ""),
        f"[bridge]   逃生舱        : {prov['backend_bundled_override']}",
        f"[bridge]   陈旧          : {prov['backend_stale']} — "
        f"{prov['backend_stale_reason'][:80]}",
        f"[bridge]   core 模块     : {prov['backend_core_modules']} 个",
        f"[bridge]   契约版本      : {prov['backend_contract_version'] or '（读不到）'}",
        f"[bridge]   前端 bundle   : {prov['frontend_asset'] or '（未构建）'}",
        "[bridge] ────────────────────────────────────────────────",
    ]
