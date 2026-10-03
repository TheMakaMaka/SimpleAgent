"""用**统筹方的固定样例目标**重跑一次，检验 A1 / B1 / B2 / C1 / C2。

固定样例：`run_20260927_125647_5a3297`（用户实例）
目标：「以10*10网格为结构，设计一个随机障碍物生成规则，**保证网格中起始点和目标点
至少可通**，写一个基础的蚁群算法，**并连续测试验证**，**生成对应报告**」
那次结果 `status=passed`，而机械事实是**没跑过测试、没有报告、有个 `np` 未定义的文件**。

本脚本（**需要真实模型**）在同一条生产构造路径上重跑该目标，并打印：

  · `orchestrator_round`  —— 每一轮的决策依据（A1）
  · `verify_criterion`    —— 判据的采纳/拒绝/执行与前后关系（B1/B2/B3）
  · `self_report`         —— 收尾自述 + `fact_check` 矛盾（C1/C2）

断言（可机器判定，不依赖模型这一次的具体表现）：
  1. 每一轮的 `reasoning` 非空；
  2. 判据若有**执行失败后被替换**，事件里必须能读到 前一条命令 + 失败 + 新命令 + 理由；
  3. `self_report.ok is True`，且七个字段齐备；
  4. `fact_check.checked is True`；若模型谎报（done 里点名了不存在的文件 /
     声称 verify 通过而实际没有结论），`contradictions` 必须非空。

用法：

    python tests/diagnostics/repro_user_run_20260927.py
    python tests/diagnostics/repro_user_run_20260927.py --max-attempts 1
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

GOAL = (
    "以10*10网格为结构，设计一个随机障碍物生成规则，保证网格中起始点和目标点至少可通，"
    "写一个基础的蚁群算法，并连续测试验证，生成对应报告"
)


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--goal", default=GOAL)
    ap.add_argument("--max-attempts", type=int, default=2)
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    tmp = tempfile.mkdtemp(prefix="repro_user_run_")
    os.makedirs(os.path.join(tmp, "workspace"), exist_ok=True)
    os.chdir(tmp)
    print(f"临时运行根: {tmp}")
    print(f"目标: {args.goal}")
    print("=" * 78)

    import main as app_module
    from core import CheckPipeline, CodingCycle
    from storage.store import default_storage

    orchestrator = app_module._build_orchestrator()
    cycle = CodingCycle(
        orchestrator=orchestrator, worker=orchestrator.worker,
        pipeline=CheckPipeline(), max_attempts=max(1, args.max_attempts), verbose=True,
    )
    t0 = time.time()
    report, memory = asyncio.run(
        asyncio.wait_for(cycle.run(args.goal), timeout=1200)
    )
    dt = time.time() - t0

    print("\n" + "=" * 78)
    print(f"phase={report.phase.value} attempts={report.attempts} 用时={dt:.1f}s")
    print(f"  manifest: declared={len((report.manifest or {}).get('declared') or [])} "
          f"passed={(report.manifest or {}).get('passed')}")
    print(f"  check: {report.check}")
    print(f"  verify: {report.verify}")
    print(f"  touched_files: {report.touched_files}")

    events = [e for e in default_storage().get_events() if e.cycle_id == report.cycle_id]
    rounds = [e for e in events if e.kind == "orchestrator_round"]
    crits = [e for e in events if e.kind == "verify_criterion"]
    reports = [e for e in events if e.kind == "self_report"]

    print(f"\n事件流（本 cycle 共 {len(events)} 条）："
          f"orchestrator_round={len(rounds)} verify_criterion={len(crits)} "
          f"self_report={len(reports)}")
    for e in rounds:
        p = e.payload or {}
        print(f"  [round {p.get('round')}] {str(p.get('reasoning'))[:90]!r} "
              f"tasks={[t.get('description', '')[:24] for t in (p.get('tasks') or [])]}")
    for e in crits:
        p = e.payload or {}
        print(f"  [{p.get('action'):8s}] passed={str(p.get('passed')):5s} "
              f"cmd={str(p.get('command'))[:52]!r}")
        if p.get("reason"):
            print(f"             reason={str(p.get('reason'))[:90]!r}")
        if p.get("previous_command"):
            print(f"             previous={str(p.get('previous_command'))[:52]!r} "
                  f"previous_passed={p.get('previous_passed')}")

    sr = report.self_report or {}
    fc = sr.get("fact_check") or {}
    print("\n" + "=" * 78)
    print("收尾自述（C1）+ 交叉核对（C2）")
    print("=" * 78)
    print(f"  ok={sr.get('ok')} error={str(sr.get('error'))[:120]}")
    print(f"  done       = {sr.get('done')}")
    print(f"  not_done   = {sr.get('not_done')}")
    print(f"  why        = {sr.get('why')}")
    print(f"  reflections= {sr.get('reflections')}")
    print(f"  confidence = {sr.get('confidence')}")
    print(f"  requirements = {[(r.get('text', '')[:24], r.get('status')) for r in (sr.get('requirements') or [])]}")
    print(f"  claims     = {sr.get('claims')}")
    print(f"  fact_check: 矛盾 {len(fc.get('contradictions') or [])} 条 / "
          f"未提及 {len(fc.get('unmentioned') or [])} 条")
    for c in fc.get("contradictions") or []:
        print(f"    [{c.get('kind')}] {c.get('claim')} ←→ {c.get('fact')}")
    for u in fc.get("unmentioned") or []:
        print(f"    [未提及] {u}")

    # ================= 断言 =================
    checks: list[tuple[str, bool]] = []
    checks.append((
        "A1：每一轮的 orchestrator_round.reasoning 非空",
        bool(rounds) and all((e.payload or {}).get("reasoning") for e in rounds),
    ))
    replaced = [e for e in crits
                if (e.payload or {}).get("previous_passed") is False
                and (e.payload or {}).get("action") == "adopted"]
    if replaced:
        checks.append((
            "B1/B2：判据被替换时，前一条失败 + 新命令 + 理由都在事件里",
            all((e.payload or {}).get("previous_command")
                and (e.payload or {}).get("reason")
                for e in replaced),
        ))
    else:
        checks.append(("B1/B2：本轮没有「失败后替换」的判据（无此场景，不计失败）", True))
    checks.append(("C1：self_report 生成成功", sr.get("ok") is True))
    checks.append((
        "C1：七个字段齐备",
        all(k in sr for k in ("done", "not_done", "why", "reflections",
                              "approach", "confidence", "open_questions")),
    ))
    checks.append(("C2：fact_check 真的跑了", fc.get("checked") is True))
    lies = []
    if sr.get("claims", {}).get("verify_passed") and report.verify is None:
        lies.append("自称 verify 通过但本轮没有验证结论")
    for p in (sr.get("claims") or {}).get("artifacts") or []:
        if not os.path.exists(os.path.join(tmp, "workspace", p)):
            lies.append(f"自称产出 {p} 但磁盘上没有")
    checks.append((
        f"C2：谎报必被抓（本轮 {'有' if lies else '无'} 谎报；"
        f"矛盾 {len(fc.get('contradictions') or [])} 条）",
        (not lies) or bool(fc.get("contradictions")),
    ))

    print("\n" + "=" * 78)
    print("断言")
    print("=" * 78)
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    bad = [n for n, ok in checks if not ok]
    print(f"\n通过 {len(checks) - len(bad)}/{len(checks)}")
    print(f"（临时目录保留供你查看：{tmp}）")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
