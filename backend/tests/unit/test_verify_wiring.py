"""`FIX-VERIFY-WIRING` 的门禁：**不带 verify_command 的真实目标也必须执行验证**。

缺陷原样（统筹方报告 + 本侧复核逐条为真）
----------------------------------------
`main.py:119` 构造 `Orchestrator` 时没注入 `pipeline`，而唯一会注入它的
`CodingCycle._setup_orchestrator` 原先只在 `if verify_command is not None:` 成立时
才被调用 —— 也就是**只有调用方自带验收命令**时。于是：

  · 循环内验证回流**从不执行** → `memory.verify_state` 恒为 None；
  · 最后却报「**缺少**可机器判定的验证命令」—— 而模型**已经把命令拟好了**；
  · 同一个 `if` 还连带杀掉了 `context_provider`（结构化上下文回流）。

**为什么当时的自检抓不到**：`tests/diagnostics/repro_user_goal.py` 手工传了
`pipeline=CheckPipeline()`，于是永远复现不出"生产忘了注入"。
与 D7 同型：**验证方式与生产路径不一致**。

本文件用**离线**断言把这个缺陷钉死：
  ① `main._build_orchestrator()` 必须注入 pipeline（直接抓原缺陷）；
  ② 两处 `_setup_orchestrator` 调用**不得**再被 `if verify_command …` 包住（结构）；
  ③ `_setup_orchestrator(None)` 必须安全（否则无条件调用会崩）；
  ④ 有命令却没 pipeline 时，`verify_skipped` 必须**可见**（不许静默跳过）；
  ⑤ 「验什么」必须随**本轮交付物**变化（附 4 的语义修正）。

> 真正"经 HTTP"的那条在生产路径上，见 `tests/diagnostics/verify_wiring_http.py`
> （它需要真实模型，故不放在离线单测里）。
"""

import ast
import asyncio
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT, WORKSPACE  # noqa: E402

from core import (  # noqa: E402
    CheckPipeline, CodingCycle, OrchestratorResult, SharedMemory,
)
from storage.store import Event  # noqa: E402

checks: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    checks.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")


class RecStorage:
    def __init__(self):
        self.events: list[Event] = []

    def append_event(self, event: Event) -> None:
        self.events.append(event)

    def get_events(self, cycle_id=None):
        return list(self.events)

    def kinds(self) -> list[str]:
        return [e.kind for e in self.events]


class StubOrchestrator:
    """只回答两个问题：被调用时 pipeline 设了没、要不要报 verify_skipped。"""

    def __init__(self, skipped: str = "", command: str = ""):
        self.pipeline = None
        self.verify_command = None
        self.context_provider = None
        self._skipped = skipped
        self._command = command
        self.seen_pipeline = "unset"
        self.seen_context_provider = "unset"

    async def run(self, goal: str):
        # 关键观测点：主循环被调用的**那一刻**，pipeline 到底在不在
        self.seen_pipeline = type(self.pipeline).__name__ if self.pipeline else None
        self.seen_context_provider = bool(self.context_provider)
        return OrchestratorResult(
            ok=True, answer="stub", memory=SharedMemory(goal=goal),
            verify_command=({"command": self._command} if self._command else None),
            declared_files=None, verify_skipped=self._skipped,
        )


def build(stub: StubOrchestrator, storage: RecStorage) -> CodingCycle:
    return CodingCycle(
        orchestrator=stub, worker=None,          # type: ignore[arg-type]
        pipeline=CheckPipeline(), storage=storage, persist=True,
        verbose=False, max_attempts=1,
    )


def check_main_builds_with_pipeline() -> None:
    print("=" * 74)
    print("[1] main._build_orchestrator() 必须注入 pipeline（抓原缺陷）")
    print("=" * 74)
    import main as app_module

    orch = app_module._build_orchestrator()
    print(f"  pipeline = {type(orch.pipeline).__name__ if orch.pipeline else None}")
    check("main 的构造路径注入了 pipeline", orch.pipeline is not None)


def check_setup_is_unconditional() -> None:
    print("\n" + "=" * 74)
    print("[2] 两处 _setup_orchestrator 不得再被 `if verify_command …` 包住")
    print("=" * 74)
    src = open(os.path.join(ROOT, "core", "coding_cycle.py"),
               encoding="utf-8").read()
    tree = ast.parse(src)
    guilty: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test_src = ast.unparse(node.test)
        if "verify_command" not in test_src:
            continue
        for sub in ast.walk(node):
            if (isinstance(sub, ast.Call)
                    and getattr(sub.func, "attr", "") == "_setup_orchestrator"):
                guilty.append(node.lineno)
    print(f"  受 `if verify_command …` 保护的调用点: {guilty or '无'}")
    check("没有任何 _setup_orchestrator 调用被该条件包住", not guilty)

    calls = sum(1 for n in ast.walk(tree)
                if isinstance(n, ast.Call)
                and getattr(n.func, "attr", "") == "_setup_orchestrator")
    print(f"  _setup_orchestrator 调用点总数: {calls}（应为 2：循环前 + 每次尝试前）")
    check("调用点数量符合预期（≥2）", calls >= 2)


def check_setup_accepts_none() -> None:
    print("\n" + "=" * 74)
    print("[3] `_setup_orchestrator(None)` 必须安全，且**不得清空已有命令**")
    print("=" * 74)
    stub = StubOrchestrator()
    cyc = build(stub, RecStorage())
    try:
        cyc._setup_orchestrator(None)
        ok = True
    except Exception as e:  # noqa: BLE001
        ok = False
        print(f"  抛错: {type(e).__name__}: {e}")
    print(f"  pipeline={type(stub.pipeline).__name__ if stub.pipeline else None} "
          f"verify_command={stub.verify_command} context_provider="
          f"{'已注入' if stub.context_provider else '未注入'}")
    check("verify_command=None 时不抛异常", ok)
    check("仍然注入了 pipeline", stub.pipeline is not None)
    check("仍然注入了 context_provider（同一处注入，别再漏）",
          bool(stub.context_provider))

    # ★ 关键契约：调用方**没给**命令时，**保留**编排器自带的命令。
    # 实测踩过：无条件调用后这里会把 `SkillRunner` 烘焙的命令抹成 None，
    # `test_skills.py` 当场报 'NoneType' object has no attribute 'get'。
    baked = {"command": "print('skill')", "reason": "技能自带"}
    stub2 = StubOrchestrator()
    stub2.verify_command = dict(baked)
    build(stub2, RecStorage())._setup_orchestrator(None)
    print(f"  自带命令在 `_setup_orchestrator(None)` 之后 = {stub2.verify_command}")
    check("调用方没给时不覆盖编排器自带的命令（SkillRunner 依赖这条）",
          stub2.verify_command == baked)

    # 反向：调用方给了就必须覆盖（调用方权威）
    from core import VerifyCommand

    stub3 = StubOrchestrator()
    stub3.verify_command = dict(baked)
    build(stub3, RecStorage())._setup_orchestrator(
        VerifyCommand(command="print('caller')", reason="调用方"))
    print(f"  调用方给了之后 = {stub3.verify_command}")
    check("调用方给了命令时覆盖为调用方的（权威性不变）",
          stub3.verify_command.get("command") == "print('caller')")


def check_run_injects_without_verify() -> None:
    print("\n" + "=" * 74)
    print("[4] 端到端（离线段）：verify_command 为空时主循环仍拿到 pipeline")
    print("=" * 74)
    stub = StubOrchestrator()
    storage = RecStorage()
    cyc = build(stub, storage)
    asyncio.run(cyc.run("随便一个目标", verify_command=None))
    print(f"  主循环被调用时 pipeline = {stub.seen_pipeline}")
    print(f"  主循环被调用时 context_provider = {stub.seen_context_provider}")
    check("主循环看到了 pipeline（不再依赖调用方给不给命令）",
          stub.seen_pipeline is not None)
    check("主循环看到了 context_provider（结构化上下文回流同样复活）",
          stub.seen_context_provider is True)


def check_verify_skipped_visible() -> None:
    print("\n" + "=" * 74)
    print("[5] 有命令却跑不了验证时，必须记 `verify_skipped` 事件（不许静默）")
    print("=" * 74)
    stub = StubOrchestrator(skipped="主循环没有 pipeline（未注入）",
                            command="assert True")
    storage = RecStorage()
    cyc = build(stub, storage)
    asyncio.run(cyc.run("随便一个目标", verify_command=None))
    kinds = storage.kinds()
    print(f"  事件种类: {kinds}")
    check("发出了 verify_skipped", "verify_skipped" in kinds)
    ev = next((e for e in storage.events if e.kind == "verify_skipped"), None)
    if ev:
        print(f"  事件 payload: {ev.payload}")
        check("payload 带 reason", bool(ev.payload.get("reason")))
        check("payload 带 command（证明'命令不缺，是没跑'）",
              bool(ev.payload.get("command")))


def check_files_to_verify_semantics() -> None:
    print("\n" + "=" * 74)
    print("[6] 「验什么」必须随本轮交付物变化（附 4 的语义修正）")
    print("=" * 74)
    from core.orchestrator import Orchestrator
    from core.task import Artifact

    mem = SharedMemory(goal="g")
    mem.artifacts["f1"] = Artifact(key="f1", kind="file", path="built.py")

    prior = {"old1.py", "old2.py"}
    declared = [{"path": "workspace/report.txt"}]

    only_prior = Orchestrator._files_to_verify(mem, prior, None)
    with_declared = Orchestrator._files_to_verify(mem, prior, declared)
    print(f"  仅 prior（无声明、无产物）: {only_prior}")
    print(f"  有声明时                 : {with_declared}")

    mem2 = SharedMemory(goal="g")
    mem2.artifacts["f1"] = Artifact(key="f1", kind="file", path="built.py")
    artifacts_only = Orchestrator._files_to_verify(mem2, prior, None)
    print(f"  有产物时（无声明）        : {artifacts_only}")

    check("有声明时以**声明**为准（不再返回旧的 prior 集）",
          with_declared == ["report.txt"])
    check("无声明时以**产物**为准（不再是 prior）",
          artifacts_only == ["built.py"])
    check("两者都空时才退回 prior（兜底保留）",
          Orchestrator._files_to_verify(SharedMemory(goal="g"), prior, None)
          == sorted(prior))

    # 指纹随交付物变化 —— 这正是"修复后重验"能成立的前提
    cmd = {"command": "print('x')"}
    fp_a = Orchestrator._verify_fingerprint(cmd, ["a.py"])
    fp_b = Orchestrator._verify_fingerprint(cmd, ["a.py", "b.py"])
    print(f"  指纹: {fp_a} vs {fp_b}")
    check("交付物变化 → 验证指纹变化（同命令也会重验）", fp_a != fp_b)


def main() -> int:
    check_main_builds_with_pipeline()
    check_setup_is_unconditional()
    check_setup_accepts_none()
    check_run_injects_without_verify()
    check_verify_skipped_visible()
    check_files_to_verify_semantics()
    failed = [n for n, ok in checks if not ok]
    print(f"\n通过 {len(checks) - len(failed)}/{len(checks)}")
    return 1 if failed else 0


raise SystemExit(main())
