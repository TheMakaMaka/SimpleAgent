"""结构化上下文回流（压缩快照 → 编排器 prompt）。

这组用例守的是一条纪律：**压缩快照是旁路增强，不是判据，也绝不能挤掉判据。**

  1. 验证结论永远是 prompt 里第一段，快照再大也不能把它挤掉；
  2. 快照被截断时必须写明，不静默丢；
  3. 快照缺失（空串）时不输出空标题——否则模型会读成"上一轮什么都没发生"；
  4. 取快照的任何环节抛异常都不能影响主循环。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core import coding_cycle as cc  # noqa: E402
from core.memory import SharedMemory  # noqa: E402
from core.orchestrator import Orchestrator  # noqa: E402
from storage.store import Event  # noqa: E402

checks: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    checks.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")


class FakeStorage:
    """最小 Storage：只实现本组用例用到的两个方法。"""

    def __init__(self, events=None, boom: bool = False):
        self._events = list(events or [])
        self._boom = boom

    def get_events(self, cycle_id=None):
        if self._boom:
            raise RuntimeError("storage 挂了")
        if cycle_id:
            return [e for e in self._events if e.cycle_id == cycle_id]
        return list(self._events)

    def append_event(self, event):  # pragma: no cover - 用例不需要
        self._events.append(event)

    def save_snapshot(self, cycle_id, snapshot):  # pragma: no cover
        pass

    def load_snapshot(self, cycle_id):  # pragma: no cover
        return None

    def list_cycles(self):  # pragma: no cover
        return []

    def search(self, keyword, limit=20):  # pragma: no cover
        return []


def _events() -> list[Event]:
    """两个 cycle：cy_old 验证失败，cy_new 里同因失败再来一次。"""
    evs = [
        Event(kind="cycle_start", cycle_id="cy_old", goal="旧目标",
              payload={"backend": "git", "prior_files": []}),
        Event(kind="plan", cycle_id="cy_old", goal="旧目标",
              payload={"attempt": 1, "verify_command": "python -m app",
                       "declared": [{"path": "app.py", "role": "入口",
                                     "symbols": ["main"]}]}),
        Event(kind="verify", cycle_id="cy_old", goal="旧目标",
              payload={"passed": False, "detail": "ModuleNotFoundError: no module named 'b'"}),
        Event(kind="syntax", cycle_id="cy_old", goal="旧目标",
              payload={"ok": False, "path": "app.py", "message": "invalid syntax line 3"}),
        Event(kind="cycle_end", cycle_id="cy_old", goal="旧目标",
              payload={"status": "failed", "commit": ""}),
        # ---- 当前 cycle：第 1 次 attempt 已经失败过 ----
        Event(kind="plan", cycle_id="cy_new", goal="新目标",
              payload={"attempt": 1, "verify_command": "python -m app",
                       "declared": [{"path": "app.py", "role": "入口",
                                     "symbols": ["main"]}],
                       "intent": [{"id": "t1", "description": "写入口",
                                   "expected_output": "可运行的 app.py"}]}),
        Event(kind="verify", cycle_id="cy_new", goal="新目标",
              payload={"passed": False, "detail": "ModuleNotFoundError: no module named 'b'"}),
        Event(kind="syntax", cycle_id="cy_new", goal="新目标",
              payload={"ok": False, "path": "app.py", "message": "invalid syntax line 3"}),
    ]
    return evs


def _cycle(storage) -> cc.CodingCycle:
    """只要 _structured_context 能跑，依赖用哑对象即可。

    注意 `persist=True`：`persist=False` 时构造器会把 storage 丢掉
    （那是"不落盘"的语义），测试里必须显式保留。
    """
    cyc = cc.CodingCycle(
        orchestrator=object.__new__(Orchestrator),
        worker=None,  # type: ignore[arg-type]
        storage=storage,
        verbose=False,
        persist=True,
    )
    return cyc


# ---------- [1] memory 渲染 ----------
def test_memory_ordering() -> None:
    print("[1] 结构化上下文在 prompt 中的位置与截断")
    m = SharedMemory(goal="写一个计算器")
    m.set_verify(True, "退出码 0", "python -m calc", "fp1")
    m.set_structured_context("已实测确认（可信）:\n  - 语法检查 通过 app.py", "compress:cy_x")

    txt = m.summary_for_orchestrator(char_budget=4000)
    check("结构化上下文已渲染", "【结构化上下文】" in txt)
    check("渲染了快照内容", "语法检查 通过 app.py" in txt)
    check("验证结论排在结构化上下文之前",
          txt.index("【验证结论】") < txt.index("【结构化上下文】"))
    check("验证结论仍要求 done", "status=done" in txt)

    # 极端预算：判据优先。验证结论必须完整，快照若有残留必须自带截断标记，
    # 且整体不得明显超出预算（否则"预算"就是假的）。
    m2 = SharedMemory(goal="g")
    m2.set_verify(True, "退出码 0", "python -m calc", "fp1")
    m2.set_structured_context("填充" * 3000, "compress:cy_x")
    tiny = m2.summary_for_orchestrator(char_budget=300)
    check("预算极小仍有完整验证结论",
          "【验证结论】" in tiny and "结果: 通过" in tiny
          and "验证命令: python -m calc" in tiny and "status=done" in tiny)
    check("预算极小快照若出现必带截断标记",
          "【结构化上下文】" not in tiny or "已截断" in tiny)
    check("预算极小不超支", len(tiny) <= 300 + 80)

    # 截断要写明
    m3 = SharedMemory(goal="g")
    m3.set_structured_context(
        "第一行\n" + "\n".join(f"  第{i}行内容填充填充填充" for i in range(200)), "src")
    big = m3.summary_for_orchestrator(char_budget=5000)
    check("超出预算时写明已截断", "已截断" in big)

    # 空串不输出空标题
    m4 = SharedMemory(goal="g")
    check("无快照时不输出标题",
          "【结构化上下文】" not in m4.summary_for_orchestrator(char_budget=4000))
    m4.set_structured_context("   ")
    check("空白快照视同无快照",
          "【结构化上下文】" not in m4.summary_for_orchestrator(char_budget=4000))


# ---------- [2] orchestrator 刷新逻辑 ----------
def test_orchestrator_refresh() -> None:
    print("[2] 编排器的结构化上下文刷新（旁路，不许崩）")
    orch = Orchestrator.__new__(Orchestrator)
    orch.context_provider = None
    mem = SharedMemory(goal="g")

    orch._refresh_structured_context(mem)
    check("无 provider 时不写入", mem.structured_context == "")

    orch.context_provider = lambda: ("事实块", "src")
    orch._refresh_structured_context(mem)
    check("接受 (text, source) 形式",
          mem.structured_context == "事实块" and mem.structured_source == "src")

    orch.context_provider = lambda: "纯字符串"
    orch._refresh_structured_context(mem)
    check("接受纯字符串形式", mem.structured_context == "纯字符串")

    orch.context_provider = lambda: ("只有文本",)
    orch._refresh_structured_context(mem)
    check("单元组不报错", mem.structured_context == "只有文本")

    def boom():
        raise RuntimeError("provider 挂了")

    orch.context_provider = boom
    orch._refresh_structured_context(mem)          # 不得抛出
    check("provider 抛异常被吞掉且清空旧块", mem.structured_context == "")

    orch.context_provider = lambda: ""
    orch._refresh_structured_context(mem)
    check("空返回清空（不留陈旧块）", mem.structured_context == "")


# ---------- [3] CodingCycle 从事件流构建 ----------
def test_cycle_builds_block() -> None:
    print("[3] CodingCycle 从事件流构建结构化上下文")
    cyc = _cycle(FakeStorage(_events()))
    cyc._current_cycle_id = "cy_new"
    text, source = cyc._structured_context()

    check("返回非空", bool(text.strip()))
    check("回源标注存在", source.startswith("compress:cy_new"))
    check("含本轮实测事实", "app.py" in text)
    check("含跨轮反复失败",
          "跨轮反复失败" in text and "ModuleNotFoundError" in text)

    # expected_output 是自由文本 → 只能是 declared，永远不能变成 verified
    from core.compress import reduce_cycle

    snap = reduce_cycle(_events(), "cy_new")
    eo = [f for f in snap.facts if "期望产出" in f.text]
    check("expected_output 进了压缩事实", bool(eo))
    check("expected_output 只标 declared（不作判据）",
          bool(eo) and all(f.confidence == "declared" for f in eo))
    check("expected_output 未混入 verified",
          all("期望产出" not in f.text for f in snap.verified_facts()))
    check("渲染在『计划声明』段而非『已实测确认』段",
          "期望产出" in text and "计划声明" in text
          and text.index("计划声明") < text.index("期望产出") < text.index("文件:"))

    # 无 storage：静默留空
    # 注意：传 storage=None 会被构造器替换成 default_storage()（真实落盘目录），
    # 所以这里必须直接改属性，否则测的是真实事件流。
    cyc2 = _cycle(FakeStorage(_events()))
    cyc2.storage = None
    cyc2._current_cycle_id = "cy_new"
    check("无 storage 返回空", cyc2._structured_context() == ("", ""))

    # storage 抛异常：不得冒泡
    cyc3 = _cycle(FakeStorage(_events(), boom=True))
    cyc3._current_cycle_id = "cy_new"
    check("storage 异常返回空且不抛", cyc3._structured_context() == ("", ""))

    # 空事件流
    cyc4 = _cycle(FakeStorage([]))
    cyc4._current_cycle_id = "cy_new"
    check("空事件流返回空", cyc4._structured_context() == ("", ""))

    # 首轮刚开始（只有 cycle_start）：块应为空，不输出空壳
    only_start = [Event(kind="cycle_start", cycle_id="cy_fresh", goal="g",
                        payload={"backend": "git"})]
    cyc5 = _cycle(FakeStorage(only_start))
    cyc5._current_cycle_id = "cy_fresh"
    check("首轮无事实时不产出空壳", cyc5._structured_context()[0] == "")


# ---------- [4] 端到端：prompt 里真的能看到 ----------
def test_prompt_end_to_end() -> None:
    print("[4] 拼到 prompt 里（编排器视角）")
    cyc = _cycle(FakeStorage(_events()))
    cyc._current_cycle_id = "cy_new"
    orch = Orchestrator.__new__(Orchestrator)
    orch.context_provider = cyc._structured_context
    mem = SharedMemory(goal="新目标")
    mem.set_verify(False, "ModuleNotFoundError", "python -m app", "fp")
    orch._refresh_structured_context(mem)

    prompt = mem.summary_for_orchestrator(char_budget=6000)
    check("prompt 含结构化段", "【结构化上下文】" in prompt)
    check("验证结论仍在最前",
          prompt.index("【验证结论】") < prompt.index("【结构化上下文】"))
    check("跨轮失败提示进了 prompt", "跨轮反复失败" in prompt)


def main() -> int:
    test_memory_ordering()
    test_orchestrator_refresh()
    test_cycle_builds_block()
    test_prompt_end_to_end()

    bad = [n for n, ok in checks if not ok]
    print("-" * 72)
    print(f"通过 {len(checks) - len(bad)}/{len(checks)}")
    if bad:
        print("失败项:")
        for n in bad:
            print(f"  - {n}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
