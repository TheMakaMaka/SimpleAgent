"""端到端复现用户那次需求（在**临时目录**里跑，不碰前端 workspace）。

对应用户的运行：demo=false、verify_command=''、
目标「读取一下你当前根目录下所有文件输出一个txt文本文档」。
"""
import asyncio
import os
import shutil
import sys
import tempfile
import time

REPO = r"D:\PythonProject\SimpleAgent2_Cycle"
sys.path.insert(0, REPO)

GOAL = "读取一下你当前根目录下所有文件输出一个txt文本文档"

tmp = tempfile.mkdtemp(prefix="repro_user_goal_")
ws = os.path.join(tmp, "workspace")
os.makedirs(ws)
# 造几个"根目录下的文件"，让"列出所有文件"这件事有真实内容
with open(os.path.join(ws, "notes.txt"), "w", encoding="utf-8") as f:
    f.write("一些笔记\n")
with open(os.path.join(ws, "data.csv"), "w", encoding="utf-8") as f:
    f.write("a,b\n1,2\n")
with open(os.path.join(ws, "hello.py"), "w", encoding="utf-8") as f:
    f.write("def hello():\n    return 'hi'\n")

os.chdir(tmp)
print(f"临时运行根: {tmp}")
print(f"目标: {GOAL}")
print("=" * 78)

from core import (  # noqa: E402
    CheckPipeline, CodingCycle, LLMClient, Orchestrator, Worker,
)
from core.model_profile import ModelProfile  # noqa: E402


async def main() -> int:
    n_before = len(os.listdir(ws))
    # ★★ 关键（`FIX-VERIFY-WIRING` 的教训）：**按生产的方式构造**。
    # 本脚本原先手工写了 `Orchestrator(..., pipeline=CheckPipeline())` ——
    # 于是它**永远复现不出**「生产忘了注入 pipeline」这个缺陷
    # （统筹方原话：「这正是 D7 那一类，验证方式与生产路径不一致」）。
    # 现在直接走 `main._build_orchestrator()`，与 `/encode` 完全同一条构造路径。
    import main as app_module

    orchestrator = app_module._build_orchestrator()
    worker = orchestrator.worker
    # cycle 层仍然显式给 pipeline —— 那是 CodingCycle 自己的参数（与 /encode 一致）
    from core import CheckPipeline as _CP

    cycle = CodingCycle(
        orchestrator=orchestrator, worker=worker, pipeline=_CP(),
        max_attempts=3, verbose=True,
    )
    print("[构造] 经 main._build_orchestrator()（与 /encode 同一条路径）")
    print(f"[构造] orchestrator.pipeline = {type(orchestrator.pipeline).__name__}")
    print(f"[构造] orchestrator.context_provider = "
          f"{'已注入' if orchestrator.context_provider else '未注入'}")
    t0 = time.time()
    # verify_command 故意留空 —— 这正是用户目标的真实形态
    report, memory = await asyncio.wait_for(cycle.run(GOAL), timeout=600)
    dt = time.time() - t0

    print("\n" + "=" * 78)
    print(f"phase={report.phase.value}  attempts={report.attempts}  "
          f"用时={dt:.1f}s  rolled_back={report.rolled_back}")
    if report.error:
        print(f"error: {report.error}")
    print(f"manifest passed={ (report.manifest or {}).get('passed') }")
    for v in ((report.manifest or {}).get("violations") or []):
        print(f"  [{v.get('severity')}] {v.get('kind')} {v.get('path')} "
              f"| {str(v.get('message'))[:90]}")

    # ★ 本次缺陷的**验收断言**（`FIX-VERIFY-WIRING`）：不带 verify_command 的真实目标
    #   也必须真的执行了验证 → `report.verify` 非空。
    #   这正是统筹方复验时会打的那一条。
    rv = report.verify
    print(f"\nreport.verify = {rv if rv is None else {k: rv.get(k) for k in ('passed', 'command')}}")
    verify_ran = bool(rv)
    if not verify_ran:
        print("  ✗ 验证没有执行 —— 正是 FIX-VERIFY-WIRING 的症状（命令不缺，是没跑）")

    # ★ 生产路径断言（CHANGELOG §31 的教训）：运行记录必须自报**代码身份** ——
    #   否则"这次跑的到底是哪一份上游"又只能靠 traceback 运气。
    from core.identity import code_fingerprint
    from storage.store import default_storage

    starts = [e for e in default_storage().get_events() if e.kind == "cycle_start"]
    ident = (starts[-1].payload if starts else {}) or {}
    got_dir, got_fp = ident.get("code_dir", ""), ident.get("code_fingerprint", "")
    ident_ok = bool(got_dir and got_fp)
    fp_ok = ident_ok and got_fp == code_fingerprint()
    print(f"\n运行记录里的代码身份: code_dir={got_dir} code_fingerprint={got_fp}")
    print(f"  自报完整 = {ident_ok} | 与当前加载的代码一致 = {fp_ok}")
    if not ident_ok:
        print("  ✗ 运行记录里没有代码身份 —— 这正是 §31 的定位盲区")
    elif not fp_ok:
        print("  ✗ 记录的身份与当前代码不符")

    print(f"\nworkspace 现在的内容（{len(os.listdir(ws))} 项）：")
    for n in sorted(os.listdir(ws)):
        p = os.path.join(ws, n)
        print(f"  {n}  ({os.path.getsize(p)} 字节)" if os.path.isfile(p) else f"  {n}/")
    return 0 if (report.phase.value == "record" and ident_ok and fp_ok
                 and verify_ran) else 1


try:
    rc = asyncio.run(main())
finally:
    print(f"\n（临时目录保留供你查看：{tmp}）")
sys.exit(rc)
