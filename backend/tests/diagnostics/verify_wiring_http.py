"""经 **HTTP** 断言：不带 `verify_command` 的真实目标也必须真的执行了验证。

为什么必须是 HTTP（`FIX-VERIFY-WIRING` 附 3）
--------------------------------------------
本次缺陷的成因是「**生产路径忘了注入 pipeline**」，而它藏了很久，是因为
**验证方式与生产路径不一致**（统筹方原话）：

  · `tests/diagnostics/repro_user_goal.py` 原先**手工传了**
    `Orchestrator(..., pipeline=CheckPipeline())` → 永远复现不出该缺陷；
  · 而生产走的是 `main._build_orchestrator()` → 那里没传 → 验证从不执行。

所以这条自检**必须**经 `POST /encode`（FastAPI 处理器，与生产同一条构造路径），
断言 `verify` 非空 —— **进程内直调挡不住这一类**（D7 已经踩过一次）。

用法（**需要真实模型**，Ollama）：

    python tests/diagnostics/verify_wiring_http.py
    python tests/diagnostics/verify_wiring_http.py --goal "在 workspace 下创建 f.py 实现 f()"

它不启动服务器：用 FastAPI 的 TestClient 直接打处理器 ——
请求模型、路由、`_build_orchestrator()` 全都经过，只是少一层网络。
"""

import argparse
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))          # tests/

from _bootstrap import ROOT  # noqa: E402,F401

DEFAULT_GOAL = "在 workspace 下创建 note.txt，写入一行文本 hello"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--goal", default=DEFAULT_GOAL)
    args = ap.parse_args()

    # 用临时运行根，避免污染仓库 workspace（上游所有路径都是 CWD 相对的）
    tmp = tempfile.mkdtemp(prefix="verify_wiring_")
    os.makedirs(os.path.join(tmp, "workspace"), exist_ok=True)
    old = os.getcwd()
    os.chdir(tmp)
    try:
        from fastapi.testclient import TestClient

        import main as app_module

        # 先核对构造路径本身就注入了 pipeline（最直接的那条断言）
        orch = app_module._build_orchestrator()
        print("=" * 78)
        print("构造路径检查（main._build_orchestrator 与 /encode 同源）")
        print("=" * 78)
        print(f"  orchestrator.pipeline          = {type(orch.pipeline).__name__}")
        print(f"  orchestrator.context_provider  = "
              f"{'已注入' if orch.context_provider else '未注入（应已注入）'}")
        print(f"  orchestrator.verify_command    = {orch.verify_command}")
        built_ok = orch.pipeline is not None

        client = TestClient(app_module.app)
        payload = {"goal": args.goal, "max_attempts": 2}
        print("\n" + "=" * 78)
        print("POST /encode（**不带** verify_command —— 用户目标的真实形态）")
        print("=" * 78)
        print(f"  请求: {payload}")
        r = client.post("/encode", json=payload)
        print(f"  HTTP {r.status_code}")
        if r.status_code != 200:
            print(f"  响应体: {r.text[:400]}")
            return 1
        d = r.json()
        for k in ("ok", "phase", "attempts", "verify_passed", "manifest_passed",
                  "error", "touched_files"):
            print(f"  {k:16s} = {d.get(k)}")

        # ★ `VERIFY-VACUOUS` 之后，"验证没执行"多了一种**正确**的原因：
        #   模型自拟的判据不合格被拒（没引用任何交付物）。
        #   必须与"接线断了"分开 —— 否则会把一次正确的拒绝读成接线又断了。
        from storage.store import default_storage

        cyc = d.get("cycle_id")
        skips = [e for e in default_storage().get_events()
                 if e.cycle_id == cyc and e.kind == "verify_skipped"]
        rejections = [e for e in skips
                      if "不合格，已拒绝采纳" in str((e.payload or {}).get("reason", ""))]
        if rejections:
            print("\n  [注意] 本轮验证**没有执行**，但原因是**自拟判据不合格被拒**"
                  "（`VERIFY-VACUOUS` 的预期行为，不是接线缺陷）：")
            for e in rejections:
                print(f"    reason={str((e.payload or {}).get('reason'))[:200]}")

        verify_ran = d.get("verify_passed") is not None
        print()
        print("=" * 78)
        print("断言")
        print("=" * 78)
        checks = [
            ("构造路径注入了 pipeline", built_ok),
            # 两种"没执行"要分开：被拒（正确）vs 接线断（缺陷）
            ("verify_passed 非空 **或** 本轮判据被明确拒绝",
             verify_ran or bool(rejections)),
            ("phase 到达 record 或 failed（不是从未验证就判失败）",
             d.get("phase") in ("record", "failed")),
        ]
        for name, ok in checks:
            print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        bad = [n for n, ok in checks if not ok]
        print(f"\n通过 {len(checks) - len(bad)}/{len(checks)}")
        if not verify_ran and not rejections:
            print("\n✗ 验证没执行，且**没有任何**被拒判据的留痕 ——")
            print("  正是 FIX-VERIFY-WIRING 的症状（命令不缺，是没跑）。")
            print("  先查 `main._build_orchestrator()` 有没有传 pipeline，")
            print("  以及 `CodingCycle._setup_orchestrator` 是否被无条件调用。")
        return 1 if bad else 0
    finally:
        os.chdir(old)


raise SystemExit(main())
