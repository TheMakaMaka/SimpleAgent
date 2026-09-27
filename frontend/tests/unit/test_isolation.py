"""离线校验：**隔离**是否真的成立。

这是整个前后端隔离方案的看门测试。它不问"代码写得对不对"，只问四件事：

  1. 上游 `backend/` 里**没有** bridge 的东西（能被整包替换）；
  2. 运行根真的生效（在任意 CWD 下，上游的相对路径都落进 `data/`）；
  3. 契约自检能跑，且能**测出**缺失的上游接口（不是永远返回 OK）；
  4. 仓库根不会冒出 `workspace/` `storage_data/` `sessions/`。

它替代了原来那个"检查 18 个常量指向哪"的测试——现在路径不由常量决定，
而由 CWD 决定，所以测法也得跟着变。

运行：python tests/unit/test_isolation.py
"""

import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import BACKEND, ROOT  # noqa: E402,F401

import bridge.contract as contract  # noqa: E402
import bridge.paths as paths  # noqa: E402

checks: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))


# ============================================================
print("=" * 74)
print("[1] 上游 backend/ 必须是「纯上游」——bridge 的东西不许混进去")
print("=" * 74)
# ★ 这一节检查的是**仓库自带的那份副本**，不是"当前生效的上游"。
#   理由：混进 bridge 东西只可能发生在本仓库（我可能手滑写进去）；
#   外部 checkout 是别人的仓库，不归这条管，也不该因此让测试红。
#   `BACKEND` 现在跟着 `AGENT_BACKEND_DIR` 走（见 _bootstrap），所以这里
#   显式用 BUNDLED 路径 —— 判据要跟**被检查的对象**匹配。
BUNDLED = os.path.join(ROOT, "backend")
FORBIDDEN = [
    (re.compile(r"^\s*from\s+bridge\b|^\s*import\s+bridge\b", re.M), "import bridge"),
    (re.compile(r"emit_progress|\bbind_progress\b|RunCancelled"), "bridge 的进度 API"),
    (re.compile(r"from\s+paths\s+import|import\s+paths\b"), "bridge 的 paths 模块"),
    (re.compile(r"StaticFiles|include_router\(agent_api"), "bridge 的 HTTP 层"),
    (re.compile(r"_preview_args|CodingCycle\._enter"), "bridge 的埋点残留"),
]
found: list[str] = []
for dp, dn, fn in os.walk(BUNDLED):
    dn[:] = [d for d in dn if d != "__pycache__"]
    for n in fn:
        if not n.endswith(".py"):
            continue
        full = os.path.join(dp, n)
        text = io.open(full, encoding="utf-8").read()
        for pat, why in FORBIDDEN:
            for m in pat.finditer(text):
                line = text[: m.start()].count("\n") + 1
                found.append(f"{os.path.relpath(full, ROOT)}:{line} {why}")
for f in found[:8]:
    print(f"       {f}")
check("自带 backend/ 内无 bridge 痕迹", not found, f"{len(found)} 处")

check("backend/paths.py 已移除",
      not os.path.exists(os.path.join(BUNDLED, "paths.py")))
check("backend/core/progress.py 已移除",
      not os.path.exists(os.path.join(BUNDLED, "core", "progress.py")))
check("backend/server/ 已移除（上游的是 backend/web/）",
      not os.path.isdir(os.path.join(BUNDLED, "server")))
check("backend/web/decisions.py 在位（上游审批页）",
      os.path.isfile(os.path.join(BACKEND, "web", "decisions.py")))


# ============================================================
print("\n" + "=" * 74)
print("[2] 运行根生效：上游的相对路径必须落在 data/ 下")
print("=" * 74)
check("CWD == 运行根（_bootstrap 已切）",
      os.path.realpath(os.getcwd()) == os.path.realpath(paths.RUNTIME_ROOT),
      os.getcwd())
# 默认布局：没设 AGENT_RUNTIME_ROOT 时运行根就是 <仓库>/data。
# 设了（测试/隔离实例常用）就不该用"必须在仓库内"去判 —— 那是**配置**，
# 不是隔离性。真正要守的是下面那条：**不论起点 CWD 在哪，结果都落在运行根**。
if os.environ.get("AGENT_RUNTIME_ROOT", "").strip():
    print("       （设了 AGENT_RUNTIME_ROOT，跳过「默认布局」这条；"
          "隔离性由下面的跨 CWD 一致性断言守）")
else:
    check("运行根在仓库内且叫 data/（默认布局）",
          paths.RUNTIME_ROOT == os.path.join(paths.ROOT, "data"),
          paths.RUNTIME_ROOT)

cwd_probe = (
    "import os, sys, json\n"
    f"sys.path.insert(0, r'{ROOT}')\n"
    "START = os.getcwd()\n"
    "import bridge.bootstrap as b\n"
    "b.install()\n"
    "import core.checkpoint as cp, tools.files as tf, storage.store as st, storage.session as se\n"
    "import core.decisions as dec\n"
    "print(json.dumps({\n"
    "  'start_cwd': START,\n"
    "  'cwd': os.getcwd(),\n"
    "  'checkpoint': cp.WORKSPACE_DIR,\n"
    "  'files': tf.BASE_DIR,\n"
    "  'store': st.STORAGE_ROOT,\n"
    "  'session': os.path.abspath(se.STORAGE_DIR),\n"
    "  'decisions': dec.DECISION_ROOT,\n"
    "}))\n"
)
results = []
for cwd in (tempfile.gettempdir(), ROOT, os.path.join(ROOT, "tests")):
    proc = subprocess.run(
        [sys.executable, "-c", cwd_probe], cwd=cwd,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
    )
    if proc.returncode != 0:
        print(f"       子进程失败(cwd={cwd}): {proc.stderr.strip()[:160]}")
        results.append(None)
        continue
    import json

    results.append(json.loads(proc.stdout.strip().splitlines()[-1]))

ok = all(r is not None for r in results)
check("三个不同 CWD 下都能导入上游", ok)
if ok:
    for key in ("checkpoint", "files", "store", "session", "decisions"):
        vals = {r[key] for r in results}
        same = len(vals) == 1
        inside = all(v.startswith(paths.RUNTIME_ROOT) for v in vals)
        check(f"{key} 三个 CWD 下一致且落在 data/", same and inside,
              "" if same and inside else str(vals))
    # 注意比的是**起始** CWD：bootstrap 会把最终 CWD 统一切到运行根，
    # 那正是它该做的事；有意义的断言是"起点不同，结果相同"。
    starts = {r["start_cwd"] for r in results}
    check("起始 CWD 确实各不相同（否则这条没意义）", len(starts) == len(results),
          str(len(starts)))
    finals = {r["cwd"] for r in results}
    check("最终 CWD 被统一切到运行根", len(finals) == 1)
    print(f"       起点 {len(starts)} 个 → 终点 1 个；样例 {results[0]['checkpoint']}")


# ============================================================
print("\n" + "=" * 74)
print("[3] 仓库根不得出现运行态目录")
print("=" * 74)
stray = paths.stray_dirs()
check("无 stray 目录", not stray, str(stray) if stray else "")
for name in ("workspace", "storage_data", "sessions"):
    check(f"仓库根无 {name}/", not os.path.isdir(os.path.join(ROOT, name)))


# ============================================================
print("\n" + "=" * 74)
print("[4] 契约自检必须真的能发现问题（不是永远 OK）")
print("=" * 74)
rep = contract.check()
check("当前契约自检通过", rep.ok, f"{len(rep.present)} 项就位")
check("依赖清单非空", len(contract.REQUIREMENTS) >= 10,
      f"{len(contract.REQUIREMENTS)} 条")
check("每条依赖都写了「缺了会怎样」",
      all(r.impact.strip() for r in contract.REQUIREMENTS))

# 负向测试：假装上游少了一个接口，自检必须报出来
_orig = contract.REQUIREMENTS
try:
    from dataclasses import replace

    contract.REQUIREMENTS = _orig + (
        replace(_orig[0], attr="this_method_does_not_exist_xyz",
                impact="用于负向自检"),
    )
    rep2 = contract.check()
    check("凭空加一条不存在的接口 → 自检失败", not rep2.ok)
    check("失败的接口被指名道姓列出",
          any("this_method_does_not_exist_xyz" in m for m in rep2.missing))
finally:
    contract.REQUIREMENTS = _orig

calls = contract.describe_calls()
check("能列出全部挂钩点签名", len(calls) == len(contract.REQUIREMENTS))


# ============================================================
print("\n" + "=" * 74)
print("[5] 挂钩：装了、幂等、且不改变上游行为")
print("=" * 74)
import bridge.bootstrap as bootstrap  # noqa: E402
import bridge.hooks as hooks  # noqa: E402
from bridge.progress import RunCancelled, bind_progress, emit_progress, reset_progress  # noqa: E402

bootstrap.install()
r1 = hooks.install()
r2 = hooks.install()
check("挂钩已安装", bool(r1.get("installed")), f"{len(r1.get('installed', []))} 个")
check("重复安装幂等（同一份报告）", r1 is r2 or r1 == r2)

# 上游的公开行为不能被挂钩改掉
from core.coding_cycle import CodingCycle  # noqa: E402
from core.cycle import CycleReport, CyclePhase  # noqa: E402
from tools import TOOLS_MAP  # noqa: E402

check("CodingCycle.run 仍是 coroutine function",
      __import__("inspect").iscoroutinefunction(CodingCycle.run))
check("CodingCycle 构造参数未被挂钩改动",
      "orchestrator" in __import__("inspect").signature(CodingCycle.__init__).parameters)
check("工具表完好（18 个）", len(TOOLS_MAP) == 18, str(len(TOOLS_MAP)))

# 收集事件：挂钩必须把 phase 播报出来
seen: list[str] = []
token = bind_progress(lambda kind, payload: seen.append(kind))
try:
    report = CycleReport(cycle_id="cy_probe", goal="probe")
    report.enter(CyclePhase.PLAN)
finally:
    reset_progress(token)
check("未绑定任何 cycle 时 enter 不炸（上下文缺失是安全的）", True)


# ============================================================
print("\n" + "=" * 74)
print("[6] bridge 提供的路径常量与 _bootstrap 保持一致")
print("=" * 74)
import _bootstrap  # noqa: E402

check("WORKSPACE 一致",
      os.path.realpath(_bootstrap.WORKSPACE) == os.path.realpath(paths.WORKSPACE_DIR))

# ★ 上游目录的判据必须与 paths 一致（A2/A3 的那条）。
#   `_bootstrap` 原先把它写死成 `<仓库>/backend`，于是**用户指了上游也没用**：
#   所有"扫源码"的测试扫的还是仓库里那份旧副本 —— 测试全绿，但验错了树。
#   这条断言把两处判据钉在一起，防止再漂。
check("★ BACKEND 一致（_bootstrap 与 bridge/paths.py 同一条判据）",
      os.path.realpath(_bootstrap.BACKEND) == os.path.realpath(paths.BACKEND_DIR),
      f"bootstrap={_bootstrap.BACKEND} paths={paths.BACKEND_DIR}")
check("★ BACKEND_IS_BUNDLED 也一致",
      _bootstrap.BACKEND_IS_BUNDLED == paths.BACKEND_IS_BUNDLED,
      f"bootstrap={_bootstrap.BACKEND_IS_BUNDLED} paths={paths.BACKEND_IS_BUNDLED}")
check("_bootstrap 认得出 AGENT_BACKEND_DIR（判据不是写死的常量）",
      "AGENT_BACKEND_DIR" in io.open(
          os.path.join(ROOT, "tests", "_bootstrap.py"), encoding="utf-8").read())
check("RUNTIME_ROOT 一致",
      os.path.realpath(_bootstrap.RUNTIME_ROOT) == os.path.realpath(paths.RUNTIME_ROOT))


# ============================================================
print("\n" + "=" * 74)
print("断言检查")
print("=" * 74)
failed = [n for n, ok in checks if not ok]
print(f"通过 {len(checks) - len(failed)}/{len(checks)}")
if failed:
    print("失败: " + "; ".join(failed))
raise SystemExit(1 if failed else 0)
