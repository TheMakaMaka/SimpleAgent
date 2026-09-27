"""测试公共引导。

两件事必须在这里做对，否则测试会写错地方：

1. **sys.path**：`bridge/` 在仓库根下（`import bridge.*`），上游包在
   `backend/` 下（`import core` / `import tools` / `import web`）。两个都要进。
2. **CWD 切到运行根（`data/`）**：上游的路径全是 CWD 相对的
   （`os.path.abspath("workspace")`）。不切的话，跑一次测试就会在**仓库根**
   新建 `workspace/`、`storage_data/`、`sessions/`——正是结构梳理要消掉的东西。

测试脚本可以位于 tests/ 的任意子目录，导入 `core` / `bridge` 前先 import 本模块：

    from _bootstrap import ROOT, WORKSPACE   # noqa: F401
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))   # tests/
ROOT = os.path.dirname(HERE)                        # 仓库根

# ★ 上游包目录：**必须与 `bridge/paths.py` 同一条判据** ——
#   `AGENT_BACKEND_DIR` 优先，没设才用仓库自带的 `backend/`。
#
#   这里本来写死成 `os.path.join(ROOT, "backend")`，后果是**静默的**：
#   用户明明指了最新上游，而所有"扫源码"的测试（`test_event_contract.py`
#   扫 `_emit` 调用点、`test_doc_consistency.py` 扫文档…）**扫的还是仓库里
#   那份旧副本** —— 测试全绿，但验的不是你在用的那棵树。
#   这正是架构项 A3 说的"两个同名 `core` 包的歧义"，只不过发生在**测试层**。
#
#   刻意**不 import bridge**（原注释的理由成立：bridge 坏了测试也该能跑），
#   所以这里直接读环境变量，语义与 `bridge/paths._abs_env` 一致。
BACKEND = os.path.abspath(
    (os.environ.get("AGENT_BACKEND_DIR") or "").strip()
    or os.path.join(ROOT, "backend")
)
BACKEND_IS_BUNDLED = os.path.realpath(BACKEND) == os.path.realpath(
    os.path.join(ROOT, "backend")
)

for _entry in (ROOT, BACKEND):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

# ★ A2b 的闸门在 `bridge/app.py` 的 **import 期**（必须如此：uvicorn 先 import
#   应用再绑定端口，在那儿退出才能保证**端口不被监听**）。
#   而"import 本模块"与"启动服务"在进程内是**看不出区别**的 —— 测试要
#   in-process 拿到 `app` 对象，所以在这里显式开逃生舱。
#
#   **这不削弱 A2b**：真正的门禁由 `tests/unit/test_bundled_gate.py` 用
#   **子进程**验证 —— 它会把本变量从子进程环境里**删掉**，断言拒绝真的发生
#   （进程不监听端口、退出码非 0）。换句话说：这里开的是"测试导入用"的
#   逃生舱，而不是"服务可以随便用副本"。
os.environ.setdefault("AGENT_ALLOW_BUNDLED", "1")

# 运行根：与 bridge/paths.py 保持一致。这里不 import bridge（避免测试
# 因为 bridge 出问题而跑不起来），只重复一个常量——由 test_isolation.py 保证一致。
RUNTIME_ROOT = os.environ.get("AGENT_RUNTIME_ROOT") or os.path.join(ROOT, "data")
RUNTIME_ROOT = os.path.abspath(RUNTIME_ROOT)

WORKSPACE = os.path.join(RUNTIME_ROOT, "workspace")
OUTPUT_DIR = os.path.join(HERE, "output")

# 关键一步：切 CWD，让上游的相对路径落进 data/
os.makedirs(WORKSPACE, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
if os.path.realpath(os.getcwd()) != os.path.realpath(RUNTIME_ROOT):
    os.chdir(RUNTIME_ROOT)

# 扫描/清理 workspace 时保留的内部目录
KEEP_DIRS = {"_debug", "_tmp", "__pycache__"}


def clean_workspace(keep_existing: bool = False) -> None:
    """清空 workspace 里由模型产出的文件，保留内部调试目录。

    keep_existing=True 时把原有文件备份到 tests/output/_ws_backup 并返回还原函数。
    """
    os.makedirs(WORKSPACE, exist_ok=True)
    if not keep_existing:
        for name in os.listdir(WORKSPACE):
            if name in KEEP_DIRS:
                continue
            p = os.path.join(WORKSPACE, name)
            shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)
        return

    backup = os.path.join(OUTPUT_DIR, "_ws_backup")
    shutil.rmtree(backup, ignore_errors=True)
    os.makedirs(backup, exist_ok=True)
    for name in os.listdir(WORKSPACE):
        if name in KEEP_DIRS:
            continue
        shutil.move(os.path.join(WORKSPACE, name), os.path.join(backup, name))

    def restore() -> None:
        for name in os.listdir(backup):
            src = os.path.join(backup, name)
            dst = os.path.join(WORKSPACE, name)
            if os.path.exists(dst):
                shutil.rmtree(dst, ignore_errors=True) if os.path.isdir(dst) else os.remove(dst)
            shutil.move(src, dst)
        shutil.rmtree(backup, ignore_errors=True)

    return restore


def restore_workspace() -> None:
    """把 clean_workspace(keep_existing=True) 备份的文件还原回 workspace。"""
    backup = os.path.join(OUTPUT_DIR, "_ws_backup")
    if not os.path.isdir(backup):
        return
    for name in os.listdir(backup):
        src = os.path.join(backup, name)
        dst = os.path.join(WORKSPACE, name)
        if os.path.exists(dst):
            shutil.rmtree(dst, ignore_errors=True) if os.path.isdir(dst) else os.remove(dst)
        shutil.move(src, dst)
    shutil.rmtree(backup, ignore_errors=True)


class Checker:
    """极简断言收集器，让脚本结束时统一打印 PASS/FAIL。"""

    def __init__(self) -> None:
        self.results: list[tuple[str, bool]] = []

    def check(self, name: str, ok: bool) -> None:
        self.results.append((name, bool(ok)))

    def report(self) -> int:
        print("\n" + "=" * 70)
        print("断言检查")
        print("=" * 70)
        for name, ok in self.results:
            print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        failed = [n for n, ok in self.results if not ok]
        print("-" * 70)
        print(f"通过 {len(self.results) - len(failed)}/{len(self.results)}")
        if failed:
            print("失败项: " + ", ".join(failed))
        return 1 if failed else 0
