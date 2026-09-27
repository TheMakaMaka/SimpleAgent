"""`python -m bridge` —— 带逃生舱的服务启动器。

为什么需要它
------------
A2b 决定：解析到仓库自带的 bundled 副本就**拒绝启动**。
逃生舱有两条路：

    AGENT_ALLOW_BUNDLED=1   # 环境变量，对任何启动方式都有效
    --allow-bundled         # 命令行，由本模块解析

**为什么环境变量是主入口**：`uvicorn bridge.app:app --allow-bundled` 会在
uvicorn 自己的参数解析阶段就报错（它不认识这个 flag），根本轮不到我们看。
所以想用 flag 就必须经过一个**我们自己的**入口 —— 就是这个模块。

用法
----
    python -m bridge                          # 正常启动（bundled 会被拒绝）
    python -m bridge --allow-bundled          # 显式放行自带副本
    python -m bridge --port 8080 --host 0.0.0.0
    python -m bridge --allow-bundled --port 8080
    python -m bridge --rebuild                # 先构建前端再起
"""

import argparse
import os
import subprocess
import sys

from . import paths


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m bridge",
        description="启动 bridge（上游 + 适配层 + 前端）。",
    )
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--allow-bundled", action="store_true",
                    help="显式允许用仓库自带的 backend/ 副本启动"
                         "（会在 /api/health 留痕 backend_bundled_override=true）")
    ap.add_argument("--rebuild", action="store_true", help="启动前先构建前端")
    args, passthrough = ap.parse_known_args(argv)

    if args.allow_bundled:
        # 必须在**导入 bridge.app 之前**设好：闸门在 import 期。
        os.environ["AGENT_ALLOW_BUNDLED"] = "1"

    if args.rebuild:
        frontend = paths.FRONTEND_DIR
        npm = "npm.cmd" if os.name == "nt" else "npm"
        print(f"[bridge] 构建前端：{frontend}", file=sys.stderr)
        rc = subprocess.call([npm, "run", "build"], cwd=frontend)
        if rc != 0:
            print(f"[bridge] 前端构建失败（exit {rc}）", file=sys.stderr)
            return rc

    import uvicorn

    # `--app-dir` 让 uvicorn 找到 bridge 包，而进程 CWD 留在仓库根 ——
    # 真正的 CWD 切换由 bridge/bootstrap.py 完成（它要切到运行根）。
    # **不要 cd 到 backend/**：上游的路径是 CWD 相对的，会因此落错地方。
    uvicorn.run(
        "bridge.app:app",
        host=args.host,
        port=args.port,
        app_dir=paths.ROOT,
        **({} if not passthrough else {}),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
