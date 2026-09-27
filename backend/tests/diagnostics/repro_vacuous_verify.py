"""`VERIFY-VACUOUS` 的真实模型复现（在**临时目录**里跑，不碰仓库 workspace）。

复刻统筹方那次真实运行 `cy_20260926_154707_882595`：

    目标「读取根目录下的项目结构输出一份分析报告」
    调用方**不给** verify_command（网页端对这种目标给不出来）
    工作区里躺着上一次留下的 calc.py / notes.txt

修复前的结果（他们的证据）：

    verify = {'passed': True, 'command': "print('PASS')"}
    manifest declared=0 checked=False · check steps=0 · touched=[]
    → phase=record（成功）  而**根本没有产出报告**

用法：

    python tests/diagnostics/repro_vacuous_verify.py
    python tests/diagnostics/repro_vacuous_verify.py --goal "..."

退出码：0 = 按 `VERIFY-VACUOUS` 的判据通过；1 = 不通过（并打印是哪一条）。
"""

import argparse
import asyncio
import os
import shutil
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

DEFAULT_GOAL = "读取根目录下的项目结构输出一份分析报告"

#: 第二个 cycle 用的**简单**目标：判据来源（caller）是这里唯一要验的东西，
#: 目标必须容易一轮做完，否则模型自己漏交付会把这条断言搅成假失败
#: （实测踩过：用同一个"写分析报告"的目标时，模型声明了 analysis_report.txt
#: 却没写，cycle 卡在 manifest 交付缺口，验证根本没走到）。
DEFAULT_CALLER_GOAL = "在 workspace 下创建 note.txt，写入一行文本 hello"

#: 上一次测试留下的历史文件 —— **必须有**，否则复现不出那个组合：
#: 正是它们让 `_files_to_verify` 的兜底有"文件"可挂，`print('PASS')` 才跑得起来。
LEFTOVERS = {
    "calc.py": "def add(a, b):\n    return a + b\n",
    "notes.txt": "上一条需求留下的笔记\n",
}


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--goal", default=DEFAULT_GOAL)
    ap.add_argument("--caller-goal", default=DEFAULT_CALLER_GOAL)
    ap.add_argument("--max-attempts", type=int, default=2)
    ap.add_argument("--skip-caller-check", action="store_true",
                    help="跳过第二个 cycle（调用方给判据的那次）")
    return ap.parse_args()


def main() -> int:
    args = parse_args()

    tmp = tempfile.mkdtemp(prefix="repro_vacuous_verify_")
    ws = os.path.join(tmp, "workspace")
    os.makedirs(ws)
    for name, content in LEFTOVERS.items():
        with open(os.path.join(ws, name), "w", encoding="utf-8") as f:
            f.write(content)

    os.chdir(tmp)
    print(f"临时运行根: {tmp}")
    print(f"目标: {args.goal}")
    print(f"工作区历史文件: {sorted(LEFTOVERS)}（复刻那次运行）")
    print("=" * 78)

    # ★ 按**生产的方式**构造（同 `/encode`）：不手工注入 pipeline、不给 verify_command。
    #   （`FIX-VERIFY-WIRING` 的教训：验证方式必须等于生产路径。）
    import main as app_module
    from core import CheckPipeline, CodingCycle
    from core.identity import code_fingerprint
    from storage.store import default_storage

    orchestrator = app_module._build_orchestrator()
    cycle = CodingCycle(
        orchestrator=orchestrator, worker=orchestrator.worker,
        pipeline=CheckPipeline(), max_attempts=max(1, args.max_attempts),
        verbose=True,
    )
    print(f"[构造] 经 main._build_orchestrator() | pipeline="
          f"{type(orchestrator.pipeline).__name__} | "
          f"verify_command={orchestrator.verify_command!r}（调用方不给）")

    t0 = time.time()
    report, memory = asyncio.run(_run(cycle, args.goal))
    dt = time.time() - t0

    man = report.manifest or {}
    chk = report.check or {}
    declared = man.get("declared") or []
    rv = report.verify

    print("\n" + "=" * 78)
    print(f"phase={report.phase.value}  attempts={report.attempts}  用时={dt:.1f}s")
    print(f"  manifest: declared={len(declared)} checked={man.get('checked')} "
          f"passed={man.get('passed')} actual={len(man.get('actual') or [])}")
    print(f"  check:    checked={chk.get('checked')} status={chk.get('status')} "
          f"steps={len(report.check_steps)}")
    print(f"  touched_files={report.touched_files}")
    print(f"  verify={rv}")
    print(f"  error={(report.error or '')[:300]}")
    print(f"  自拟判据被拒的理由（memory.verify_untrusted）: "
          f"{(memory.verify_untrusted or '(无)')[:300]}")

    kinds = [e for e in default_storage().get_events() if e.cycle_id == report.cycle_id]
    skips = [e for e in kinds if e.kind == "verify_skipped"]
    verifies = [e for e in kinds if e.kind == "verify"]
    print(f"\n事件流（本 cycle，共 {len(kinds)} 条）：verify={len(verifies)} "
          f"verify_skipped={len(skips)}")
    for e in skips:
        print(f"  [verify_skipped] reason={str((e.payload or {}).get('reason'))[:220]!r}")
    for e in verifies:
        p = e.payload or {}
        print(f"  [verify] passed={p.get('passed')} source={p.get('source')!r} "
              f"command={str(p.get('command'))[:80]!r}")

    starts = [e for e in kinds if e.kind == "cycle_start"]
    ident = (starts[-1].payload if starts else {}) or {}
    fp_ok = ident.get("code_fingerprint") == code_fingerprint()
    print(f"\n代码身份: code_fingerprint={ident.get('code_fingerprint')} "
          f"与当前一致={fp_ok}")

    # ================= 断言（统筹方 §5 的复验方式）=================
    checks: list[tuple[str, bool]] = []
    no_work = (not declared) and not report.touched_files

    checks.append((
        "★ 不出现「declared=0 且 touched=[] 却 phase=record」这个组合",
        not (no_work and report.phase.value == "record"),
    ))
    if rv:
        checks.append((
            "有验证结论时，判据必须真的引用了本轮交付物（不是恒真）",
            report.phase.value != "record" or bool(declared or report.touched_files),
        ))
        checks.append((
            "本脚本没给调用方判据 → source 必须是 model",
            rv.get("source") == "model",
        ))
    else:
        checks.append((
            "没有验证结论时，理由必须是**说清楚**的（不是无声的 None）",
            bool(memory.verify_untrusted) or bool(report.error),
        ))
        if no_work:
            checks.append((
                "★ 什么都没产出 → 必须在事件流里留下 verify_skipped（可事后追查）",
                bool(skips),
            ))
    checks.append(("运行记录自报代码身份且与当前代码一致", bool(fp_ok)))

    if not args.skip_caller_check:
        print("\n" + "=" * 78)
        print("[第二个 cycle] 调用方给 verify_command=print('PASS')（简单目标）")
        print(f"  目标: {args.caller_goal}")
        print("  要验的是：判据**来源**能否区分 caller / model（调用方的判据是权威的，")
        print("           本门禁不插手 —— 哪怕它是恒真的）")
        print("=" * 78)
        orch2 = app_module._build_orchestrator()
        cycle2 = CodingCycle(orchestrator=orch2, worker=orch2.worker,
                             pipeline=CheckPipeline(), max_attempts=1, verbose=False)
        from core import VerifyCommand

        r2, _m2 = asyncio.run(_run(cycle2, args.caller_goal,
                                   VerifyCommand(command="print('PASS')",
                                                reason="调用方给的（本检查用）")))
        man2 = r2.manifest or {}
        print(f"  phase={r2.phase.value}  declared="
              f"{len(man2.get('declared') or [])} checked={man2.get('checked')}")
        print(f"  verify={r2.verify}")
        if r2.error:
            print(f"  error={r2.error[:200]}")
        checks.append((
            "调用方给的判据执行后 → source=caller（能区分来源）",
            bool(r2.verify) and (r2.verify or {}).get("source") == "caller",
        ))
        checks.append((
            "调用方给判据的那次确实跑通（简单目标，phase=record）",
            r2.phase.value == "record",
        ))

    print("\n" + "=" * 78)
    print("断言")
    print("=" * 78)
    ok_all = True
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        ok_all = ok_all and ok
    print(f"\n通过 {sum(1 for _, o in checks if o)}/{len(checks)}")
    print(f"（临时目录保留供你查看：{tmp}）")
    return 0 if ok_all else 1


async def _run(cycle, goal, verify_command=None):
    """给整个 cycle 一个上限，避免模型卡住时脚本永不返回。"""
    return await asyncio.wait_for(
        cycle.run(goal, verify_command=verify_command), timeout=900
    )


if __name__ == "__main__":
    sys.exit(main())
