"""离线校验：进度事件通路与运行管理器。

不启服务、不调模型。覆盖三件事：
  1. `core.progress` 在没有订阅者时是纯 no-op（不得影响 cycle 行为）；
  2. `RunCancelled` 能穿过工作流层到处都有的 `except Exception` 兜底；
  3. `RunManager` 的事件日志按 seq 追加、可增量 tail、终态判定正确。

运行：python tests/unit/test_webui_runtime.py
"""

import os
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401

from bridge.progress import (  # noqa: E402
    RunCancelled,
    bind_progress,
    current_sink,
    emit_progress,
    reset_progress,
)
from bridge.runner import EventLog, RunInfo, RunManager  # noqa: E402

checks: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    checks.append((name, ok))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")


# ============================================================
print("=" * 74)
print("[1] 无订阅者时必须是纯 no-op")
print("=" * 74)
check("默认没有 sink", current_sink() is None)
emit_progress("anything", x=1)  # 不应抛异常
check("emit_progress 无订阅者不抛异常", True)


# ============================================================
print("\n" + "=" * 74)
print("[2] 绑定 / 还原 / 串台")
print("=" * 74)
seen: list[tuple[str, dict]] = []
token = bind_progress(lambda kind, payload: seen.append((kind, payload)))
emit_progress("phase", phase="plan")
check("收到事件", seen and seen[0][0] == "phase")
check("payload 原样传递", seen[0][1].get("phase") == "plan")
reset_progress(token)
emit_progress("phase", phase="write")
check("还原后不再接收（不串台）", len(seen) == 1)


# ============================================================
print("\n" + "=" * 74)
print("[3] 坏订阅者不能拖垮流程")
print("=" * 74)


def boom(kind, payload):
    raise ValueError("订阅者自己炸了")


token = bind_progress(boom)
try:
    emit_progress("phase", phase="check")
    survived = True
except Exception:
    survived = False
check("普通异常被吞掉", survived)
reset_progress(token)


# ============================================================
print("\n" + "=" * 74)
print("[4] RunCancelled 必须能穿出去（这是唯一能中断模型调用的位置）")
print("=" * 74)


def cancel(kind, payload):
    raise RunCancelled("stop")


token = bind_progress(cancel)
try:
    emit_progress("tool_call", tool="write_file")
    escaped = False
except RunCancelled:
    escaped = True
except Exception:
    escaped = False
check("RunCancelled 穿透 emit_progress", escaped)
check("RunCancelled 是 BaseException（不被 except Exception 吞）", issubclass(RunCancelled, BaseException))
reset_progress(token)


# ============================================================
print("\n" + "=" * 74)
print("[5] EventLog：追加、增量 tail、坏行容错")
print("=" * 74)
tmp = tempfile.mkdtemp(prefix="agent_evt_")
try:
    path = os.path.join(tmp, "events.jsonl")
    log = EventLog(path)
    for i in range(5):
        log.append("phase", phase=f"p{i}")

    all_events = log.read_all()
    check("追加 5 条", len(all_events) == 5)
    check("seq 从 1 递增", [e["seq"] for e in all_events] == [1, 2, 3, 4, 5])
    check("带时间戳", bool(all_events[0].get("ts")))
    check("按 after_seq 过滤", [e["seq"] for e in log.read_all(3)] == [4, 5])

    # 增量 tail：先读到 3，再追加 2 条，只应拿到新增的
    with open(path, "rb") as f:
        chunk = f.read()
    offset = chunk.rindex(b"\n", 0, chunk.rindex(b"\n", 0, chunk.rindex(b"\n")) + 1) + 1
    head, new_offset = log.tail(0)
    check("从头 tail 拿到全部", len(head) == 5)
    log.append("verify", passed=True)
    tail, _ = log.tail(new_offset)
    check("增量 tail 只拿到新增", [e["kind"] for e in tail] == ["verify"])

    # 坏行：不应让整条流挂掉
    with open(path, "a", encoding="utf-8") as f:
        f.write("{ this is not json }\n")
    log.append("cycle_end", status="passed")
    check("坏行被跳过、后续仍可读", len(log.read_all()) == 7)

    # 半行：模拟正在写入
    with open(path, "a", encoding="utf-8") as f:
        f.write('{"seq": 999, "kind": "partial"')  # 没有换行
    tail_events, off2 = log.tail(0)
    check("未写完的尾行不返回", all(e.get("seq") != 999 for e in tail_events))
finally:
    shutil.rmtree(tmp, ignore_errors=True)


# ============================================================
print("\n" + "=" * 74)
print("[6] RunInfo 终态判定")
print("=" * 74)
for status, want in [
    ("queued", False), ("running", False),
    ("passed", True), ("failed", True), ("relaxed", True),
    ("cancelled", True), ("error", True),
]:
    info = RunInfo(run_id="r", goal="g", status=status)
    check(f"{status} -> terminal={want}", info.terminal is want)

# 未知字段必须被忽略（否则改 meta 结构会让历史记录读不进来）
info = RunInfo.from_dict({"run_id": "r", "goal": "g", "brand_new_field": 1})
check("from_dict 容忍未知字段", info.run_id == "r")


# ============================================================
print("\n" + "=" * 74)
print("[7] RunManager：演示运行跑通全链路")
print("=" * 74)
tmp = tempfile.mkdtemp(prefix="agent_runs_")
try:
    mgr = RunManager(root=tmp)
    info = mgr.start(goal="离线自检：演示运行", demo=True, max_attempts=2)
    check("start 立刻返回且不阻塞", info.status in ("queued", "running"))

    import time

    for _ in range(200):  # 演示运行约 18 秒
        time.sleep(0.25)
        if mgr.get(info.run_id).terminal:
            break

    final = mgr.get(info.run_id)
    check("演示运行到达终态", final.terminal)
    check("演示运行判为 passed", final.status == "passed")
    check("记录了尝试次数", final.attempts == 2)

    events = mgr.events(info.run_id)
    kinds = [e["kind"] for e in events]
    check("事件 ≥ 20 条", len(events) >= 20)
    check("包含相位事件", "phase" in kinds)
    check("包含工具调用", "tool_call" in kinds)
    check("包含回退与重试", "rollback" in kinds and "retry" in kinds)
    check("包含 manifest / check / verify 门禁",
          {"manifest", "syntax", "verify"} <= set(kinds))
    check("run_end 只出现一次（收尾由 RunManager 负责）", kinds.count("run_end") == 1)
    check("seq 严格递增",
          [e["seq"] for e in events] == sorted({e["seq"] for e in events}))

    # 重入：同一个 root 能重新加载历史
    again = RunManager(root=tmp)
    check("重启后能加载历史", again.get(info.run_id) is not None)
    check("重启后历史保持终态", again.get(info.run_id).status == "passed")

    # 取消一个不存在的运行
    ok, msg = mgr.cancel("run_does_not_exist")
    check("取消不存在的运行返回失败", ok is False and "不存在" in msg)
finally:
    shutil.rmtree(tmp, ignore_errors=True)


# ============================================================
print("\n" + "=" * 74)
print("断言检查")
print("=" * 74)
failed = [n for n, ok in checks if not ok]
print(f"通过 {len(checks) - len(failed)}/{len(checks)}")
if failed:
    print("失败: " + "; ".join(failed))
raise SystemExit(1 if failed else 0)
