"""bridge —— 上游后端与 Vue 前端之间的**唯一**适配层。

为什么要有这一层
----------------
用户的工作流是「把最新版后端复制过来覆盖 `backend/`」。
只要集成代码写在上游文件里，这次复制就会把它**静默抹掉**：进度埋点没了、
`/api/*` 路由没了、前端直接死。

所以规矩很简单：

    backend/   只放上游代码，**不改**。可以整包替换。
    frontend/  Vue 前端。只跟 bridge 说话，不跟 backend 说话。
    bridge/    我的全部集成代码。上游换新时，这里原则上不用动。
    data/      运行态（bridge 通过切 CWD 让上游的相对路径落在这里）

`backend/` 里跑起来需要知道的四件事，全部由 bridge 提供：

| 需要什么 | 谁提供 | 怎么提供 |
|---|---|---|
| 进度事件 | `hooks.py` | 运行时包装上游的汇聚点，不写进上游 |
| `/api/*` 与 `/app` | `agent_api.py` + `app.py` | 新建 app，把上游 app 的路由接进来 |
| 路径落位 | `bootstrap.py` | 把进程 CWD 切到 `data/`，上游的 `abspath("workspace")` 自动落对 |
| 契约自检 | `contract.py` | 上游接口变了就精确报错，不静默 |

入口是 `bridge.app:app`（见 `scripts/run.ps1`）。上游原来的
`backend/main.py` 仍然能单独跑——只是没有前端和事件流。
"""

from . import bootstrap, contract, hooks, paths, progress  # noqa: F401

__all__ = ["bootstrap", "contract", "hooks", "paths", "progress"]
