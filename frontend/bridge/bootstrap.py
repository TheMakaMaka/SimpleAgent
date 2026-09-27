"""引导：让 bridge 能在**任意 CWD** 下把上游拉起来。

做四件事，顺序不能变：

1. 把 `backend/` 放进 `sys.path`（这样 `import core` / `import tools` 才成立），
   并把 `bridge/` 自己所在的仓库根也放进去（`import bridge.*`）。
2. 加载 `.env`：先仓库根，再 `backend/.env`（后者不覆盖已有值）。
   `.env` 放仓库根是刻意的——它在 backend/ 之外，后端整包替换不会带走它。
3. 建好运行根目录。
4. **把进程 CWD 切到运行根**。上游的路径全是 CWD 相对的（`abspath("workspace")`），
   切了 CWD 它们就全部落进 `data/`，**一行上游代码都不用改**。

第 4 步是整个隔离方案的关键，也是最容易被忽略的一步：
不切 CWD，上游会在仓库根新建 `workspace/`、`storage_data/`、`sessions/`，
而且是**静默**的。`bridge.contract` 会把这件事查出来。
"""

import os
import sys

from . import paths

_installed = False


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        # 没装 python-dotenv 就只用环境变量——与上游的降级行为一致
        return
    # 先加载仓库根，且不覆盖已导出的环境变量（override=False 是默认值）
    for candidate in (paths.ENV_FILE, paths.BACKEND_ENV_FILE):
        if os.path.isfile(candidate):
            load_dotenv(candidate, override=False)


def install(*, chdir: bool = True) -> dict:
    """幂等。返回本次实际做了什么，便于自检与日志。"""
    global _installed
    actions: list[str] = []

    # 指向上游代码（可以是仓库外的 checkout，见 paths.BACKEND_DIR）。
    # 这里显式报错而不是让后面的 import 抛 ModuleNotFoundError——
    # "AGENT_BACKEND_DIR 指错了" 和 "上游少了个模块" 是两种完全不同的故障。
    if not os.path.isdir(paths.BACKEND_DIR):
        raise RuntimeError(
            f"上游代码目录不存在: {paths.BACKEND_DIR}\n"
            f"  （来自 AGENT_BACKEND_DIR；未设置时默认用 <仓库>/backend）\n"
            f"  检查这个路径，或把最新版后端放到 <仓库>/backend"
        )

    for entry in (paths.BACKEND_DIR, paths.ROOT):
        if entry not in sys.path:
            sys.path.insert(0, entry)
            actions.append(f"sys.path += {entry}")

    if not _installed:
        _load_env()
        actions.append("已加载 .env")

    created = paths.ensure_dirs()
    if created:
        actions.append(f"新建目录 {len(created)} 个")

    if chdir and os.path.realpath(os.getcwd()) != os.path.realpath(paths.RUNTIME_ROOT):
        os.chdir(paths.RUNTIME_ROOT)
        actions.append(f"cwd → {paths.RUNTIME_ROOT}")

    _installed = True
    return {"actions": actions, "paths": paths.describe()}
