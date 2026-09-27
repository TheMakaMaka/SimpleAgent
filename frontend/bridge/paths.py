"""bridge 的路径定义。

与 `backend/` 的关系
--------------------
`bridge/` 是**适配层**，`backend/` 是**上游代码**。两者必须能独立替换：
上游整包换新时，这里的东西不该跟着变。

所以路径不再由上游代码持有（上游用的是 `os.path.abspath("workspace")`，
CWD 相对），而是由 bridge 在启动时把**运行根**定下来：

    <repo>/data/          ← 运行根（= 上游眼里的"项目根"）
      workspace/            模型产出
      storage_data/         事件流 / 快照 / 决策 / 技能
      sessions/             每次 run 的记录

上游那些相对路径**不需要改一行**：只要进程的 CWD 是运行根，
`abspath("workspace")` 就落在 `data/workspace`。

为什么用 CWD 而不是逐个改常量
-----------------------------
常量能改，但上游还有**函数内部**算路径的地方（例如
`tools/code_checks.list_workspace()` 里的 `abspath("workspace")`）。
逐个打补丁一定会漏，而且上游新增一处我们也看不见。
把 CWD 定成运行根是一刀切的，上游新增的路径也自动落对位置。
"""

import os

#: bridge/paths.py → bridge/ → 仓库根
BRIDGE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BRIDGE_DIR)


def _abs_env(name: str, default: str) -> str:
    raw = (os.getenv(name) or "").strip()
    return os.path.abspath(raw) if raw else os.path.abspath(default)


#: ★ 上游 Python 代码所在目录（进 sys.path 的那个）。
#:
#: **不一定是仓库里的 `backend/`。** 用 `AGENT_BACKEND_DIR` 指向上游 checkout：
#:
#:     $env:AGENT_BACKEND_DIR = "D:\upstream\SimpleAgent2_Cycle\backend"
#:
#: 这样就不用把上游代码复制进本仓库——「指过去」而不是「搬过来」。
#: 仓库自带的 `backend/` 只是**开箱可跑的兜底**。
#:
#: 为什么必须同进程而不是纯远端服务：进度事件靠运行时挂钩（见 hooks.py），
#: 那要求上游代码在**本进程内**可 import。纯 HTTP 的黑盒只能看到
#: `/encode` 的最终返回，拿不到 round/task/tool 级过程。
BACKEND_DIR = _abs_env("AGENT_BACKEND_DIR", os.path.join(ROOT, "backend"))

#: 用的是不是仓库自带的兜底后端（决定要不要提示"你其实可以指过去"）
BACKEND_IS_BUNDLED = os.path.realpath(BACKEND_DIR) == os.path.realpath(
    os.path.join(ROOT, "backend")
)

#: Vue 前端构建产物；不存在时 `/app` 不注册
FRONTEND_DIR = os.path.join(ROOT, "frontend")
FRONTEND_DIST = os.path.join(FRONTEND_DIR, "dist")

#: 部署配置留在仓库根——它在后端目录之外，所以换后端不会把它带走
ENV_FILE = os.path.join(ROOT, ".env")
BACKEND_ENV_FILE = os.path.join(BACKEND_DIR, ".env")


#: ★ 运行根：进程 CWD 会被切到这里，上游所有相对路径随之落位
RUNTIME_ROOT = _abs_env("AGENT_RUNTIME_ROOT", os.path.join(ROOT, "data"))

# 下面是运行根下的三项，仅用于**自检与展示**——
# 上游自己会用相对路径找到它们，bridge 不替上游拼路径。
WORKSPACE_DIR = os.path.join(RUNTIME_ROOT, "workspace")
STORAGE_DIR = os.path.join(RUNTIME_ROOT, "storage_data")
SESSIONS_DIR = os.path.join(RUNTIME_ROOT, "sessions")
RUNS_DIR = os.path.join(STORAGE_DIR, "runs")

#: 运行根下必须存在的目录（也是仓库根不该出现的目录名）
RUNTIME_SUBDIRS = ("workspace", "storage_data", "sessions")


def ensure_dirs() -> list[str]:
    """建好运行根与三个子目录，返回实际创建的路径。"""
    created: list[str] = []
    if not os.path.isdir(RUNTIME_ROOT):
        os.makedirs(RUNTIME_ROOT, exist_ok=True)
        created.append(RUNTIME_ROOT)
    for name in RUNTIME_SUBDIRS:
        path = os.path.join(RUNTIME_ROOT, name)
        if not os.path.isdir(path):
            os.makedirs(path, exist_ok=True)
            created.append(path)
    return created


def stray_dirs() -> list[str]:
    """仓库根下不该出现的运行态目录。

    上游的路径都是 CWD 相对的：**只要有一处没被运行根覆盖住，
    它就会在仓库根新建一个目录**。这个函数就是那件事的探测器——
    契约自检会调它，所以"悄悄冒出一个 workspace/"不会没人发现。
    """
    return [
        name for name in RUNTIME_SUBDIRS
        if os.path.isdir(os.path.join(ROOT, name))
    ]


def describe() -> dict:
    cwd = os.getcwd()
    return {
        "root": ROOT,
        "bridge": BRIDGE_DIR,
        "backend": BACKEND_DIR,
        "backend_is_bundled": BACKEND_IS_BUNDLED,
        "backend_exists": os.path.isdir(BACKEND_DIR),
        "runtime_root": RUNTIME_ROOT,
        "cwd": cwd,
        "cwd_is_runtime_root": os.path.realpath(cwd) == os.path.realpath(RUNTIME_ROOT),
        "frontend_dist": FRONTEND_DIST,
        "frontend_built": os.path.isdir(FRONTEND_DIST),
        "stray_dirs": stray_dirs(),
    }
