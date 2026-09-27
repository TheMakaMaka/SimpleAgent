"""入口：把上游的 app 与 bridge 的接口层合成一个应用。

启动顺序很讲究，一步都不能少：

    bootstrap.install()   ① sys.path ② .env ③ 建运行根 ④ **切 CWD**
    hooks.install()       ⑤ 包装上游的汇聚点，产出进度事件
    contract.check()      ⑥ 核对上游接口，缺什么当场说清楚
    import main           ⑦ 这时才 import 上游，路径已经落位
    include_router        ⑧ 把 /api/* 与 /app 接上去

启动方式（二选一）：

    cd backend && uvicorn bridge.app:app        # 不推荐：CWD 会被 bootstrap 纠正
    uvicorn bridge.app:app                      # 在仓库根；推荐用 scripts/run.ps1

注意 ⑦ 必须在 ① 之后：`import main` 会连带 import 上游一堆模块，
其中不少在**模块级**就算好了 `os.path.abspath("workspace")`。
CWD 没切就直接 import，那些常量会永久指向错误的位置（而且不报错）。
"""

import os
import sys

from . import bootstrap, contract, hooks, paths, staleness

#: 日志一律走 stderr —— 这个模块会被别的程序 import（见 ⑥ 的说明）
def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)

# ① ~ ④
_boot = bootstrap.install()

# ④b 上游副本：**bundled 即拒绝启动**（架构清单 A2b）。
#
# 为什么从"硬警告"升级成"拒绝"（实测）：A2 的目标是"让它无法被静默使用"，
# 而事实是它**被静默使用了约 10 轮** —— 启动警告没人看见、探针字段没人去看、
# 上游所有修复一条都没生效。**「可见」被当成了「足够」，而它不够。**
#
# ★ 判据是 `backend_is_bundled`（**形态**），不是 `backend_stale`（状态）：
#   "副本此刻恰好同步"是一个会过期的属性，而这条规则要防的正是
#   "你以为在跑上游、其实在跑副本"这种**误解**。
#
# ⚠️ 放在 import 期是**必须的**：uvicorn 先 import 应用再绑定端口，
#   所以在这里退出 → **端口不会被监听**（验收标准要的就是这个，
#   而不是"端口起来了再关掉"）。
#   代价：**import 本模块 ≠ 启动服务**（测试要 in-process 拿 app 对象），
#   所以给了显式逃生舱；测试用它，并另有一个子进程负向测试专测"拒绝真的发生"。
_STALE = staleness.probe()
_ALLOW_BUNDLED = staleness.allow_bundled_requested()
if staleness.should_refuse(_STALE, allow=_ALLOW_BUNDLED):
    _log(staleness.refusal_message(_STALE))
    raise SystemExit(staleness.REFUSAL_EXIT_CODE)

# ⑤
_hooks = hooks.install()

# ⑥ 契约自检。缺接口**不阻止启动**——上游少一个挂钩点，
#    前端少一块信息而已，不该让整个服务起不来。但要在日志里说清楚。
#
# ⚠ 全部走 **stderr**：这个模块会被别的程序 import（例如 scripts/doctor.py），
#    import 时往 stdout 打横幅会污染它们的输出——
#    实测 `doctor.py --json | json.load` 直接解析失败。
#    日志归 stderr，数据归 stdout，这条分界不能含糊。
_contract = contract.check()
_log("[bridge] " + _contract.summary())
_log(f"[bridge] 运行根: {paths.RUNTIME_ROOT}")
_log(f"[bridge] 挂钩: {len(_hooks['installed'])} 个")

# 版本追溯（A2b / 用户要求）：一次运行到底用的是**哪份代码、哪一版前端**。
# 与 `/api/health` 共用 `staleness.provenance()` —— 两处各拼一遍迟早会分叉。
_PROV = staleness.provenance(_STALE)
for _line in staleness.provenance_lines(_PROV):
    _log(_line)

# A2 的醒目警告：**在逃生舱路径上仍然打**。
# 默认路径现在是"直接拒绝"，所以警告若只挂在启动上就成了死代码；
# 而"用了逃生舱"恰恰是最需要看到"你在用副本、上游修复不生效、后果是什么"的时刻。
if _PROV["backend_bundled_override"]:
    _warn = staleness.startup_warning(_STALE)
    if _warn:
        _log(_warn)
    _log(f"[bridge] ⚠ 逃生舱已启用（{staleness.ALLOW_BUNDLED_ENV} / "
         f"{staleness.ALLOW_BUNDLED_FLAG}）—— 上游的修复**不会**生效。"
         "该事实已写入 /api/health 的 backend_bundled_override。")

# ⑦ 现在才 import 上游
from fastapi.staticfiles import StaticFiles  # noqa: E402

from main import app as upstream_app  # noqa: E402

from .agent_api import router as agent_api_router  # noqa: E402

# ⑧
upstream_app.include_router(agent_api_router)

FRONTEND_MOUNTED = os.path.isdir(paths.FRONTEND_DIST)
if FRONTEND_MOUNTED:
    upstream_app.mount(
        "/app", StaticFiles(directory=paths.FRONTEND_DIST, html=True), name="frontend"
    )
    _log(f"[bridge] 前端已挂载: /app → {paths.FRONTEND_DIST}")
else:
    _log(
        "[bridge] 未找到 frontend/dist，`/app` 不注册"
        "（在 frontend/ 下执行 npm run build 后重启）"
    )

app = upstream_app

__all__ = ["app"]
