"""演示运行：不发一次模型请求，也能跑出一整套真实事件序列。

为什么需要它
------------
进度可视化最怕两件事：一是没有模型就什么都看不到，二是调 UI 时每次都要等
两分钟。演示运行复用**与真实运行完全相同的事件词汇**（kind 与字段名一致），
所以它验证的是真链路，而不是一条只在演示里成立的旁路。

脚本刻意包含一次「manifest 失败 → 回退 → 重试 → 通过」，
这样重试动画、回退标记、阶段重置都能被看到。
"""

import time
from typing import Any, Callable

Sink = Callable[[str, dict], None]

# 节奏（秒）。太快看不出动画，太慢拖沓；这一段是刻意可调的。
BEAT = 0.32


def _step(sink: Sink, kind: str, delay: float = BEAT, **payload: Any) -> None:
    sink(kind, payload)
    if delay:
        time.sleep(delay)


def run_demo_cycle(sink: Sink, run_id: str, goal: str) -> dict:
    goal = goal or "在 workspace 下创建 math_utils.py，实现 fib(n) 返回斐波那契数列第 n 项"

    _step(sink, "run_start", backend="git", max_attempts=2, on_decision="auto", goal=goal, delay=0.5)
    _step(sink, "baseline", ref="demo0000")
    _step(sink, "cycle_start", backend="git", prior_files=[], goal=goal, delay=0.4)

    # ---------- 第 1 次尝试：交付清单不过关 ----------
    _attempt_1(sink, run_id, goal)

    _step(sink, "rollback", ref="demo0000", ok=True, attempt=1, delay=0.6)

    # ---------- 第 2 次尝试：通过 ----------
    _attempt_2(sink, run_id, goal)

    _step(sink, "cycle_end", status="passed", commit="demo0001", attempt=2, delay=0.3)
    # 注意：这里**不发 `run_end`**。收尾事件由 `RunManager._finish` 统一发出，
    # 演示脚本再发一次会在事件流里出现两条「运行结束」。

    return {
        "status": "passed",
        "phase": "record",
        "attempts": 2,
        "touched_files": ["math_utils.py"],
        "commit": "demo0001",
        "rolled_back": False,
        "error": None,
        "answer": "cycle 通过校验，检查点 demo0001（演示数据）",
        "report": {
            "cycle_id": run_id, "goal": goal, "phase": "record",
            "transitions": ["plan", "write", "check", "verify", "record"],
            "attempts": 2, "touched_files": ["math_utils.py"],
            "commit": "demo0001", "rolled_back": False, "error": None,
            "demo": True,
        },
        "summary": {"tasks_total": 4, "tasks_ok": 4, "tasks_failed": 0,
                    "check_steps": 2, "demo": True},
    }


def _phase(sink: Sink, phase: str, attempt: int, transitions: list[str], delay: float = BEAT) -> None:
    _step(sink, "phase", phase=phase, attempt=attempt,
          transitions=list(transitions), delay=delay)


def _attempt_1(sink: Sink, run_id: str, goal: str) -> None:
    trans: list[str] = []
    _step(sink, "attempt_start", attempt=1, max_attempts=2, goal=goal, delay=0.3)
    trans.append("plan"); _phase(sink, "plan", 1, trans)
    _step(sink, "round_start", round=1, max_rounds=20, goal=goal)
    _step(sink, "orchestrator_decision", round=1, status="continue",
          reasoning="目标需要新建一个模块文件，先产出实现再验证。",
          task_count=2, final_answer="")
    _step(sink, "task_start", task_id="t1", description="创建 math_utils.py 并实现 fib(n)",
          tool_hint=["write_file"], total=2, delay=0.2)
    _step(sink, "worker_step", task_id="t1", step=1, max_steps=20, message_count=2, delay=0.5)
    _step(sink, "model_reply", task_id="t1", step=1, tool_calls=1, content_len=48,
          content="先写文件再自测。")
    _step(sink, "tool_call", task_id="t1", step=1, tool="write_file",
          args={"filename": "math_utils.py", "content": "def fib(n):\n    a, b = 0, 1\n..."},
          delay=0.6)
    _step(sink, "tool_result", task_id="t1", step=1, tool="write_file", ok=True,
          preview="OK:FILE|math_utils.py|612|已写入 math_utils.py（612 字符）", delay=0.5)
    _step(sink, "task_done", task_id="t1", ok=True, steps_used=2,
          output="已创建 math_utils.py", error="")
    _step(sink, "task_start", task_id="t2", description="运行一段自测代码确认 fib(10)==55",
          tool_hint=["run_python"], total=2, delay=0.2)
    _step(sink, "worker_step", task_id="t2", step=1, max_steps=20, message_count=1, delay=0.4)
    _step(sink, "tool_call", task_id="t2", step=1, tool="run_python",
          args={"code": "import math_utils\nprint(math_utils.fib(10))"})
    _step(sink, "tool_result", task_id="t2", step=1, tool="run_python", ok=True,
          preview='{"ok": true, "output": "55"}', delay=0.5)
    _step(sink, "task_done", task_id="t2", ok=True, steps_used=2, output="55", error="")

    trans.append("write"); _phase(sink, "write", 1, trans)
    _step(sink, "files", attempt=1, touched=["math_utils.py"], count=1)
    _step(sink, "manifest", checked=True, passed=False,
          violations=[{"kind": "declared-missing", "path": "demo_fib_check.py",
                       "message": "计划要产出 demo_fib_check.py，但文件不存在"}],
          actual_files=["math_utils.py"], delay=0.6)
    trans.append("failed"); _phase(sink, "failed", 1, trans, delay=0.4)
    _step(sink, "cycle_end", status="failed", attempt=1,
          error="交付清单不完整: 计划要产出 demo_fib_check.py，但文件不存在")


def _attempt_2(sink: Sink, run_id: str, goal: str) -> None:
    trans: list[str] = []
    _step(sink, "retry", attempt=2,
          reason="交付清单不完整: 计划要产出 demo_fib_check.py，但文件不存在", delay=0.4)
    _step(sink, "attempt_start", attempt=2, max_attempts=2, goal=goal, delay=0.3)
    trans.append("plan"); _phase(sink, "plan", 2, trans)
    _step(sink, "round_start", round=2, max_rounds=20, goal=goal)
    _step(sink, "orchestrator_decision", round=2, status="continue",
          reasoning="上一次少了自检脚本，这次只补这一个文件，不重复实现。",
          task_count=1, final_answer="")
    _step(sink, "task_start", task_id="t1", description="补写 demo_fib_check.py 作为交付件",
          tool_hint=["write_file"], total=1, delay=0.2)
    _step(sink, "worker_step", task_id="t1", step=1, max_steps=20, message_count=3, delay=0.4)
    _step(sink, "tool_call", task_id="t1", step=1, tool="write_file",
          args={"filename": "demo_fib_check.py", "content": "import math_utils\nassert ...\n"})
    _step(sink, "tool_result", task_id="t1", step=1, tool="write_file", ok=True,
          preview="OK:FILE|demo_fib_check.py|148|已写入 demo_fib_check.py（148 字符）", delay=0.5)
    _step(sink, "task_done", task_id="t1", ok=True, steps_used=1,
          output="已补写 demo_fib_check.py", error="")

    trans.append("write"); _phase(sink, "write", 2, trans)
    _step(sink, "files", attempt=2, touched=["math_utils.py", "demo_fib_check.py"], count=2)
    _step(sink, "manifest", checked=True, passed=True, violations=[],
          actual_files=["demo_fib_check.py", "math_utils.py"], delay=0.5)

    trans.append("check"); _phase(sink, "check", 2, trans)
    _step(sink, "syntax", path="math_utils.py", ok=True, message="")
    _step(sink, "lint", path="math_utils.py", status="passed", reason="", issues=[])
    _step(sink, "syntax", path="demo_fib_check.py", ok=True, message="")
    _step(sink, "lint", path="demo_fib_check.py", status="skipped",
          reason="ruff 未安装，lint 未执行", issues=[])

    trans.append("verify"); _phase(sink, "verify", 2, trans)
    _step(sink, "verify_probe", round=1, passed=True, detail="PASS",
          command="import math_utils\nassert math_utils.fib(10) == 55\nprint('PASS')",
          files=["math_utils.py", "demo_fib_check.py"], delay=0.7)
    _step(sink, "verify", passed=True, detail="PASS",
          command="import math_utils\nassert math_utils.fib(10) == 55\nprint('PASS')", delay=0.5)

    trans.append("record"); _phase(sink, "record", 2, trans, delay=0.4)
