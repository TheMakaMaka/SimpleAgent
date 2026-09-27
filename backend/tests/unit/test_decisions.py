"""人工决策机制自检。

覆盖：决策生命周期、非法作答拦截、超时 fail-safe、审批页、以及最关键的
**挂起→（另一进程/线程）作答→恢复**这条链路。
"""

import asyncio
import os
import shutil
import sys
import threading
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401

from core.decisions import (  # noqa: E402
    FAILURE_OPTIONS, ROLLBACK_OPTIONS, DecisionManager, FileDecisionStore,
)
from core.notify import (  # noqa: E402
    ConsoleNotifier, DingTalkNotifier, WebhookNotifier, build_notifier, channel_status,
)

TMP = os.path.join(ROOT, ".tmp_decision_test")


def main() -> int:
    shutil.rmtree(TMP, ignore_errors=True)
    checks: list[tuple[str, bool]] = []
    store = FileDecisionStore(TMP)
    mgr = DecisionManager(store=store, default_timeout_minutes=30)

    # ============================================================
    print("=" * 74)
    print("[1] 决策生命周期")
    print("=" * 74)
    d = mgr.open("repeated_failure", "cy_1", "验证连续失败 2 次，如何继续？",
                 context={"goal": "实现 fib", "error": "AssertionError: got 34",
                          "touched": ["fib.py"]})
    print(f"  id={d.id[:12]}… kind={d.kind} status={d.status} default={d.default}")
    checks.append(("新建为 pending", d.status == "pending"))
    checks.append(("默认是保守动作 stop", d.default == "stop"))
    checks.append(("选项集非空", len(d.options) == 3))
    checks.append(("可从磁盘读回", mgr.get(d.id) is not None))

    # ---- 非法作答必须被拦 ----
    ok, msg = mgr.answer(d.id, "delete_everything")
    print(f"  非法选项 -> ok={ok} msg={msg}")
    checks.append(("非法选项被拒", ok is False and "非法" in msg))

    # ---- 合法作答 ----
    ok, msg = mgr.answer(d.id, "retry", by="mobile")
    got = mgr.get(d.id)
    print(f"  合法选项 -> ok={ok} status={got.status} answer={got.answer} by={got.answered_by}")
    checks.append(("合法作答成功", ok and got.status == "answered"))
    checks.append(("记录了作答来源", got.answered_by == "mobile"))
    checks.append(("生效动作取作答值", got.resolve_effective() == "retry"))

    # ---- 重复作答必须被拒 ----
    ok2, msg2 = mgr.answer(d.id, "stop")
    print(f"  重复作答 -> ok={ok2} msg={msg2}")
    checks.append(("重复作答被拒", ok2 is False))

    # ============================================================
    print("\n" + "=" * 74)
    print("[2] 超时 fail-safe：没人管时不能自己往前冲")
    print("=" * 74)
    d2 = mgr.open("risky_rollback", "cy_2", "即将回退，是否允许？",
                  timeout_minutes=0)   # 立刻过期
    time.sleep(1.1)
    expired = mgr.sweep_expired()
    d2b = mgr.get(d2.id)
    print(f"  过期处理: {expired}")
    print(f"  status={d2b.status} answer={d2b.answer!r}（应为保守默认 abort）")
    checks.append(("超时被标记 expired", d2b.status == "expired"))
    checks.append(("回退类超时默认 abort（不覆盖文件）", d2b.answer == "abort"))
    checks.append(("过期后不能再作答", mgr.answer(d2.id, "allow")[0] is False))

    d3 = mgr.open("repeated_failure", "cy_3", "连续失败，如何继续？", timeout_minutes=0)
    time.sleep(1.1)
    mgr.sweep_expired()
    print(f"  失败类超时默认 = {mgr.get(d3.id).answer!r}（应为 stop）")
    checks.append(("失败类超时默认 stop（不空转）", mgr.get(d3.id).answer == "stop"))

    # 两类决策的保守默认必须不同
    checks.append(("两类默认动作不同",
                   DecisionManager._conservative_default("risky_rollback")
                   != DecisionManager._conservative_default("repeated_failure")))

    # ============================================================
    print("\n" + "=" * 74)
    print("[3] pending 列表与取消")
    print("=" * 74)
    d4 = mgr.open("repeated_failure", "cy_4", "另一个待决策")
    print(f"  pending 数: {len(mgr.pending())}")
    checks.append(("pending 能列出", any(x.id == d4.id for x in mgr.pending())))
    mgr.cancel(d4.id, reason="人工撤回")
    print(f"  取消后 status={mgr.get(d4.id).status}")
    checks.append(("取消后不再是 pending",
                   not any(x.id == d4.id for x in mgr.pending())))

    # ============================================================
    print("\n" + "=" * 74)
    print("[4] 投递层：未配置时必须退化，且不能阻塞")
    print("=" * 74)
    for ch, expect_type in (("console", ConsoleNotifier), ("none", ConsoleNotifier),
                            ("dingtalk", ConsoleNotifier),   # 没配 webhook → 退化
                            ("webhook", ConsoleNotifier)):
        n = build_notifier(ch)
        print(f"  AGENT_NOTIFY_CHANNEL={ch:<10} -> {type(n).__name__} ({n.name})")
        checks.append((f"{ch} 通道可用", n is not None))

    os.environ["AGENT_NOTIFY_CHANNEL"] = "dingtalk"
    os.environ["AGENT_DINGTALK_WEBHOOK"] = "https://oapi.dingtalk.com/robot/send?access_token=FAKE"
    n = build_notifier()
    print(f"  配置 webhook 后 -> {type(n).__name__}")
    checks.append(("配了 webhook 用钉钉", isinstance(n, DingTalkNotifier)))

    st = channel_status()
    print(f"  channel_status: {st}")
    checks.append(("channel_status 可用", st["channel"] == "dingtalk" and st["ready"]))

    # 钉钉加签 URL 生成（不实际发请求）
    dn = DingTalkNotifier("https://oapi.dingtalk.com/robot/send?access_token=x", secret="s3cr3t")
    url = dn._signed_url()
    print(f"  加签 URL 含 timestamp/sign: {'timestamp=' in url and 'sign=' in url}")
    checks.append(("加签 URL 生成正确", "timestamp=" in url and "sign=" in url))

    # 控制台通知不抛异常
    r = ConsoleNotifier().send(d, "http://x/decisions/1")
    checks.append(("控制台投递成功", r.ok and r.channel == "console"))

    # 清理环境变量，避免影响后续
    for k in ("AGENT_NOTIFY_CHANNEL", "AGENT_DINGTALK_WEBHOOK"):
        os.environ.pop(k, None)

    # ============================================================
    print("\n" + "=" * 74)
    print("[5] 关键链路：挂起 → 另一线程作答 → 恢复")
    print("=" * 74)
    # 用真实 CodingCycle 的 _ask/_wait_for_answer，但不需要模型：
    # 直接构造一个最小对象来复用等待逻辑。
    from core.coding_cycle import CodingCycle
    from core.cycle import CycleReport

    wait_mgr = DecisionManager(store=FileDecisionStore(TMP), default_timeout_minutes=1)

    class FakeCycle:
        """只借用真实的 _ask / _wait_for_answer，不碰模型。"""
        _ask = CodingCycle._ask
        _wait_for_answer = CodingCycle._wait_for_answer
        _build_context = CodingCycle._build_context
        _emit = lambda self, *a, **k: None          # noqa: E731
        _log = lambda self, *a, **k: None           # noqa: E731
        on_decision = "wait"
        notifier = ConsoleNotifier()
        approval_base_url = "http://192.168.1.10:8000"

        def __init__(self, mgr):
            self.decisions = mgr

    fc = FakeCycle(wait_mgr)
    report = CycleReport(cycle_id="cy_resume", goal="实现 fib")
    report.attempts = 2
    report.error = "验证未通过: AssertionError: got 34"
    report.touched_files = ["fib.py"]

    holder: dict = {}

    def answer_later():
        """模拟你从手机上作答——注意用的是**另一个** DecisionManager 实例。"""
        time.sleep(1.5)
        other = DecisionManager(store=FileDecisionStore(TMP))
        pend = [x for x in other.pending() if x.kind == "repeated_failure"]
        if pend:
            holder["id"] = pend[0].id
            holder["result"] = other.answer(pend[0].id, "retry", by="phone")

    t = threading.Thread(target=answer_later, daemon=True)
    t0 = time.time()
    t.start()
    action = fc._ask(
        kind="repeated_failure", report=report, goal="实现 fib",
        question="验证连续失败 2 次，如何继续？",
        options=FAILURE_OPTIONS, default="stop",
    )
    t.join(timeout=5)
    elapsed = time.time() - t0
    print(f"  作答来自另一实例: {holder.get('result')}")
    print(f"  最终动作 = {action!r}  等待耗时 {elapsed:.1f}s")
    checks.append(("跨实例作答被感知", holder.get("result", (False,))[0] is True))
    checks.append(("恢复后采用人的选择", action == "retry"))
    checks.append(("等待期间确实阻塞过（>1s）", elapsed > 1.0))

    # ---- notify 失败时不得挂死 ----
    class FailingNotifier:
        name = "always-fail"
        def send(self, decision, link):
            from core.notify import NotifyResult
            return NotifyResult(ok=False, channel="always-fail", detail="网络不可达")

    fc2 = FakeCycle(DecisionManager(store=FileDecisionStore(TMP), default_timeout_minutes=1))
    fc2.notifier = FailingNotifier()
    t0 = time.time()
    action2 = fc2._ask(
        kind="risky_rollback", report=report, goal="实现 fib",
        question="即将回退，是否允许？",
        options=ROLLBACK_OPTIONS, default="abort",
    )
    elapsed2 = time.time() - t0
    print(f"  推送失败时 action={action2!r} 耗时 {elapsed2:.2f}s（应立刻返回，不等待）")
    checks.append(("推送失败不阻塞", elapsed2 < 1.0))
    checks.append(("推送失败取保守默认", action2 == "abort"))

    # ---- auto 模式不推送不等待 ----
    fc3 = FakeCycle(DecisionManager(store=FileDecisionStore(TMP)))
    fc3.on_decision = "auto"
    t0 = time.time()
    action3 = fc3._ask(
        kind="repeated_failure", report=report, goal="g",
        question="q", options=FAILURE_OPTIONS, default="stop",
    )
    checks.append(("auto 模式立刻返回默认值", action3 == "stop" and time.time() - t0 < 0.5))
    print(f"  auto 模式 action={action3!r}")

    shutil.rmtree(TMP, ignore_errors=True)

    print("\n" + "=" * 74)
    print("断言检查")
    print("=" * 74)
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    failed = [n for n, ok in checks if not ok]
    print(f"\n通过 {len(checks) - len(failed)}/{len(checks)}")
    if failed:
        print("失败: " + "; ".join(failed))
    return 1 if failed else 0


raise SystemExit(main())
