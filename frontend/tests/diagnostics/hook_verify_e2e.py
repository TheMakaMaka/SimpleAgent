"""P5/P5b/P6 验收：**真的跑一次流程，并走到 verify**（离线，只把最底层模型换成假的）。

为什么要有它
------------
统筹方的验收条件之一是「**真的跑一次任务能走到 verify**」（他那侧是
`capability-run.py --only T1` 应当 `pass`）。而三次问题都出在**生产路径**上：

| 缺陷 | 形态 | 单测为什么没抓到 |
|---|---|---|
| **P5** | 包装器镜像了 `run_verify` 的旧签名 → `TypeError` | 那个包装器不在测试范围内 |
| **P5b** | `_around_invoke` 引用模块全局 `Worker`（实际只在函数内 import）→ `NameError` | **我的 harness 把 worker 换成桩，恰好绕过了 `_invoke`** |
| **`_safe`** | `except BaseException: raise` 把**所有**异常重抛 → 一个都没兜住 | 只验了"正常路径能跑"，**没验"坏了以后会怎样"** |

★ 所以这一版做两件事：

1. **不绕过任何挂钩点**：只伪造最底层的 `LLMClient._client`（模型返回什么），
   `LLMClient.chat` / `Worker.run` / `Worker._invoke` / `Orchestrator` /
   `CheckPipeline` **全是真的**；
2. **故意往挂钩里注入异常**，断言**整轮运行照样跑完** ——
   这才是"每个包装都兜住自己的异常"那句承诺的**行为证据**
   （挂钩坏掉只该让**那一条事件**消失，不该让用户看到 `status=error`）。

用法：
    python tests/diagnostics/hook_verify_e2e.py
    $env:AGENT_BACKEND_DIR="…\\SimpleAgent2_Cycle"; python tests/diagnostics/hook_verify_e2e.py
"""

import asyncio
import inspect
import json
import os
import sys
from types import SimpleNamespace

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import WORKSPACE, clean_workspace  # noqa: E402

import bridge.bootstrap as bootstrap  # noqa: E402

bootstrap.install()

from bridge import hooks, progress  # noqa: E402

hooks.install()

from core import CheckPipeline, CodingCycle, LLMClient, Orchestrator, VerifyCommand, Worker  # noqa: E402

checks: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))


class Capture:
    def __init__(self):
        self.kinds: list[str] = []
        self.events: list[tuple[str, dict]] = []

    def __call__(self, kind, payload):
        self.kinds.append(kind)
        self.events.append((kind, payload))


SOURCE = (
    "def fib(n):\n"
    "    a, b = 0, 1\n"
    "    for _ in range(n):\n"
    "        a, b = b, a + b\n"
    "    return a\n"
)

#: 编排器的决策（照上游读的字段名：`tasks` / `files` / `verify` / `final_answer`）。
#: ★ `files` **必须有**：`_files_to_verify()` 的优先来源就是这份"计划声明的交付物"，
#:   它空 → 验证回流拿到空文件集 → **`run_verify` 根本不会被调用**（实测踩过）。
DECISION = {
    "status": "continue",
    "reasoning": "写出 math_utils.py 的 fib，然后用调用方判据验证它",
    "tasks": [{
        "id": "t1",
        "description": "实现 math_utils.fib 并保存为 math_utils.py",
        "expected_output": "math_utils.py",
    }],
    "files": [{"path": "math_utils.py", "role": "斐波那契实现", "symbols": ["fib"]}],
    "final_answer": "",
}

VERIFY = VerifyCommand(
    command=(
        "import math_utils\n"
        "assert math_utils.fib(1) == 1, math_utils.fib(1)\n"
        "assert math_utils.fib(10) == 55, math_utils.fib(10)\n"
        "print('PASS')\n"
    ),
    reason="调用 fib 并断言数列值（调用方判据）",
)


def _tool_call(call_id: str, name: str, args: dict):
    return SimpleNamespace(id=call_id,
                           function=SimpleNamespace(name=name, arguments=json.dumps(args)))


class FakeCompletions:
    """假的 `client.chat.completions` —— 只决定"模型返回什么"。"""

    def __init__(self, state: dict):
        self.state = state

    async def create(self, **kwargs):        # noqa: ANN003
        self.state["calls"] += 1
        if kwargs.get("tools"):
            self.state["steps"] += 1
            if self.state["steps"] == 1:
                msg = SimpleNamespace(
                    content="",
                    tool_calls=[_tool_call("call-1", "write_file",
                                           {"filename": "math_utils.py", "content": SOURCE})],
                )
            else:
                msg = SimpleNamespace(content="已完成 math_utils.py", tool_calls=None)
        else:
            msg = SimpleNamespace(content=json.dumps(DECISION), tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")])


class FakeClient:
    def __init__(self, state: dict):
        self.chat = SimpleNamespace(completions=FakeCompletions(state))


async def run_once(fault: str = "") -> tuple:
    """跑一轮真实 cycle。`fault` 用来**故意**在挂钩里制造异常。"""
    clean_workspace()
    state = {"calls": 0, "steps": 0}
    llm = LLMClient()
    llm._client = FakeClient(state)
    worker = Worker(llm)
    orch_llm = LLMClient()
    orch_llm._client = FakeClient(state)
    orchestrator = Orchestrator(orch_llm, worker, max_rounds=4)
    cycle = CodingCycle(orchestrator=orchestrator, worker=worker,
                        pipeline=CheckPipeline(), max_attempts=1)

    saved = hooks.preview_args
    if fault == "preview_args":
        def _boom(name, args):                   # noqa: ANN001, ANN202
            raise TypeError("注入的故障：preview_args 遇到没料到的类型")
        hooks.preview_args = _boom

    cap = Capture()
    token = progress.bind_progress(cap)
    err = None
    report = None
    try:
        report, _memory = await cycle.run("实现 math_utils.fib", verify_command=VERIFY)
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        err = e
    finally:
        progress.reset_progress(token)
        hooks.preview_args = saved
    return report, err, cap, state


async def main() -> int:
    # ============================================================
    print("=" * 74)
    print("[A] 正常路径：真的跑一次，并走到 verify")
    print("=" * 74)
    report, err, cap, state = await run_once()
    print(f"  模型调用 {state['calls']} 次（子循环步 {state['steps']}） · "
          f"phase={getattr(getattr(report, 'phase', None), 'value', None)} · "
          f"异常={type(err).__name__ if err else '无'}")
    print(f"  事件：{cap.kinds}")

    check("★ 跑完没有异常（P5 是 TypeError / P5b 是 NameError）", err is None, repr(err))
    EXPECT = [
        ("CodingCycle._emit", "cycle_start"),
        ("CycleReport.enter", "phase"),
        ("CodingCycle.run", "run_start"),
        ("CodingCycle._new_file_artifacts", "files"),
        ("CheckpointManager.commit", "baseline"),
        ("Orchestrator._decide", "orchestrator_decision"),
        ("Worker.run", "task_start"),
        ("LLMClient.chat", "model_reply"),
        ("Worker._invoke", "tool_call"),
    ]
    missing = [(p, ev) for p, ev in EXPECT if ev not in cap.kinds]
    check("★★ 9 个挂钩点**在生产路径上真的被走到**（各自的事件都出现了）",
          not missing, str(missing))
    check("★ 事件链完整：run_start → task_start → tool_call → verify_probe → verify → cycle_end",
          all(k in cap.kinds for k in ("run_start", "task_start", "tool_call",
                                       "verify_probe", "verify", "cycle_end")),
          str([k for k in ("run_start", "task_start", "tool_call", "verify_probe",
                           "verify", "cycle_end") if k not in cap.kinds]))
    check("★ 工具调用真的执行了（`tool_result` ok=true）",
          any(k == "tool_result" and p.get("ok") for k, p in cap.events))
    check("★ 产出真的落盘了（math_utils.py 存在）",
          os.path.isfile(os.path.join(WORKSPACE, "math_utils.py")))

    _sig = inspect.signature(getattr(CheckPipeline.run_verify, "__wrapped_orig__",
                                     CheckPipeline.run_verify))
    if "files" not in _sig.parameters:
        print("  SKIP  「走到 verify」那几条（当前生效的上游是自带旧副本："
              "它的验证接线在 `FIX-VERIFY-WIRING` 之前，本来就走不到）")
    else:
        check("★ 走到了验证：发出 `verify_probe`", "verify_probe" in cap.kinds, str(cap.kinds))
        check("★ 验证真的执行了（`passed=true`）",
              any(k == "verify_probe" and p.get("passed") for k, p in cap.events))
        check("★ 最终 phase 是 `record`（走完了 VERIFY 才可能到 RECORD）",
              getattr(getattr(report, "phase", None), "value", None) == "record",
              str(getattr(getattr(report, "phase", None), "value", None)))

    # ============================================================
    print()
    print("=" * 74)
    print("[B] 故意在挂钩里注入异常：**整轮运行必须照样跑完**")
    print("=" * 74)
    # 这一条验的是模块抬头那句承诺：
    #   「每个包装都兜住自己的异常，进度坏掉不能让 cycle 失败」
    # 改前 `_safe` 是 `except BaseException: raise` —— 一个都没兜住，
    # 所以注入的 TypeError 会**杀掉整轮运行**，用户看到 `status=error`
    # （而那与"模型做不出来"长得一模一样 ⇒ 污染能力画像）。
    report_b, err_b, cap_b, _state_b = await run_once(fault="preview_args")
    print(f"  phase={getattr(getattr(report_b, 'phase', None), 'value', None)} · "
          f"异常={type(err_b).__name__ + ': ' + str(err_b) if err_b else '无'}")
    print(f"  事件：{cap_b.kinds}")
    check("★★ 挂钩里的异常**没有**杀掉这一轮（cycle 跑完了）", err_b is None, repr(err_b))
    check("★★ 而且它照样走到了 verify（坏掉的只是那一条事件）",
          "verify_probe" in cap_b.kinds or "cycle_end" in cap_b.kinds, str(cap_b.kinds))
    check("★ 代价可见：`tool_call` 那一条事件确实**缺了**（不是静默假装成功）",
          "tool_call" not in cap_b.kinds, str(cap_b.kinds))
    check("★ 但流程本身照旧：run_start / task_start / cycle_end 都在",
          all(k in cap_b.kinds for k in ("run_start", "task_start", "cycle_end")),
          str([k for k in ("run_start", "task_start", "cycle_end") if k not in cap_b.kinds]))

    print()
    failed = [n for n, ok in checks if not ok]
    print(f"通过 {len(checks) - len(failed)}/{len(checks)}")
    if failed:
        print("失败: " + "; ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
