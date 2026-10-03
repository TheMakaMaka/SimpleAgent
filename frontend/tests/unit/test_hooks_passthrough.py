"""挂钩包装器必须**按上游签名绑定**，不许镜像它（D9）。

背景：一次真实的 `status=error`
-------------------------------
`bridge/hooks.py` 的 `CodingCycle._emit` 包装器原来这么写：

    def _emit(self, kind, cycle_id, goal="", **payload):

—— 把上游签名**原样抄了一份**，位置参数就叫 `kind`。于是任何调用点只要写

    self._emit("decision_opened", cid, kind="repeated_failure", ...)

Python 会把那个值同时绑给位置参数与关键字参数：

    TypeError: _emit() got multiple values for argument 'kind'

**整轮 run 直接 status=error**。上游踩过一次并把自己的首参改名 `event_kind`
做二次防御 —— 但 bridge 这份镜像**不会跟着变**。镜像的本质就是"第二份判据"。

现在的实现用 `inspect.signature(orig_emit).bind(...)`：**问上游要签名**。
这个测试直接调 `hooks.make_emit_wrapper`，用不同签名的假 orig_emit，
把两件事分别钉住：

  1. **上游已是新签名**（首参 `event_kind`）→ 绑定冲突消失、载荷完整；
  2. **上游还是旧签名**（首参 `kind`）→ 冲突仍在**上游那一层**，
     但 bridge 不许再自己造一个冲突，且事件**不许静默消失**。

运行：python tests/unit/test_hooks_passthrough.py
"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401

checks: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))


class Capture:
    """`bridge.progress` 的接收器；不绑定时 emit 是纯 no-op。"""

    def __init__(self):
        self.received: list[tuple[str, dict]] = []

    def __call__(self, kind, payload):
        self.received.append((kind, payload))


# ============================================================
print("=" * 74)
print("[1] 源码形态：实现只有一份，且不镜像签名")
print("=" * 74)
src = open(os.path.join(ROOT, "bridge", "hooks.py"), encoding="utf-8").read()
check("★ 包装器用 `*args, **kwargs`（不再写死位置参数）",
      "def _emit(self, *args, **kwargs):" in src)
# 旧形态只许出现在**说明它为什么不行**的文档里，不许出现在代码行上。
# 判据：那一行的出现必须带反引号（说明是散文引用），且全文件只出现一次。
old_form_lines = [ln for ln in src.splitlines()
                  if "def _emit(self, kind, cycle_id" in ln]
check("★ 旧形态只作为「说明」出现（带反引号的散文引用），不是代码",
      len(old_form_lines) == 1 and "`" in old_form_lines[0],
      str(old_form_lines)[:120])
check("★ 用 inspect 向上游要签名（而不是自己记一份）",
      "inspect.signature(orig_emit)" in src)
# P5 之后 `_emit` 由 `install()` 的**名单遍历**安装（`wrapped = make_emit_wrapper(orig)`），
# 所以这里不再断言某一行赋值语句，而是断言两件事：
#   ① 实现只有一份（`def _emit(self, *args, **kwargs):` 出现一次）；
#   ② install 真的走了工厂（不是内联一份副本）。
check("★ 实现只有一份：install() 调用工厂，不再内联副本",
      "make_emit_wrapper(orig)" in src
      and src.count("def _emit(self, *args, **kwargs):") == 1,
      str(src.count("def _emit(self, *args, **kwargs):")))
check("★ 展开 VAR_KEYWORD（否则 **payload 会被收成嵌套字典）",
      "VAR_KEYWORD" in src and "params.update(extra)" in src)


import bridge.bootstrap as bootstrap  # noqa: E402

bootstrap.install()

from bridge import hooks, progress  # noqa: E402


def run_case(orig_emit, *args, **kwargs):
    """把工厂造出的包装器绑到一个只带 orig_emit 的假实例上跑一次。"""
    wrapper = hooks.make_emit_wrapper(orig_emit)
    holder = type("H", (), {"_emit": staticmethod(orig_emit)})()
    cap = Capture()
    token = progress.bind_progress(cap)
    err = None
    try:
        wrapper(holder, *args, **kwargs)
    except Exception as e:  # noqa: BLE001
        err = e
    finally:
        progress.reset_progress(token)
    return cap.received, err


# ============================================================
print("\n" + "=" * 74)
print("[2] ★ 上游已是新签名（首参 event_kind）—— 这是外部 checkout 的现状")
print("=" * 74)


def new_upstream(self, event_kind, cycle_id, goal="", **payload):
    """当前上游的签名（首参已改名 event_kind）。"""
    new_upstream.calls.append((event_kind, cycle_id, goal, payload))


new_upstream.calls = []

got, err = run_case(new_upstream, "decision_opened", "cycle-1",
                    kind="repeated_failure", decision_id="d1", question="q")
check("★ `kind=` 作为关键字**不再抛 TypeError**", err is None, repr(err))
check("★ 事件名取对了（decision_opened，不是 payload 里的 kind）",
      bool(got) and got[-1][0] == "decision_opened", str([k for k, _ in got]))
p = got[-1][1] if got else {}
check("★ 载荷完整：cycle_id 没被丢掉（纯 **kwargs 透传会丢）",
      p.get("cycle_id") == "cycle-1", str(p))
check("★ 载荷完整：decision_id / question 都在",
      p.get("decision_id") == "d1" and p.get("question") == "q", str(p))
check("★ payload 里的 kind 原样带出（不吞）",
      p.get("kind") == "repeated_failure", str(p))
check("★ goal 的缺省值也补上了（与旧行为一致）", "goal" in p, str(sorted(p)))
check("★ 原方法仍被调用（透传不是短路）",
      len(new_upstream.calls) == 1
      and new_upstream.calls[0][0] == "decision_opened",
      str(new_upstream.calls))
check("★ 原方法原样收到 kwargs（不吞不改）",
      new_upstream.calls and new_upstream.calls[0][3].get("kind") == "repeated_failure",
      str(new_upstream.calls))


# ============================================================
print("\n" + "=" * 74)
print("[3] 上游仍是旧签名（首参 kind）—— 仓库自带副本的现状")
print("=" * 74)


def old_upstream(self, kind, cycle_id, goal="", **payload):
    old_upstream.calls.append((kind, cycle_id, goal, payload))


old_upstream.calls = []

got2, err2 = run_case(old_upstream, "decision_opened", "cycle-1",
                      kind="repeated_failure", decision_id="d1")
# 这一层：上游自己的签名仍会撞名 —— bridge 无法替它修。
# 但要求是：**bridge 不许再自己造一个冲突**，且事件不许静默消失。
check("★ 事件仍被播报出来（不许静默消失）",
      bool(got2) and got2[-1][0] == "decision_opened", str([k for k, _ in got2]))
check("★ 载荷里其它键还在",
      got2 and got2[-1][1].get("decision_id") == "d1", str(got2[-1][1] if got2 else {}))
# `emit_progress` 的首参已改名 `event_kind`，所以载荷里叫 `kind` **不再撞名**，
# 该字段被如实保留（改名前它会让 emit_progress 抛 TypeError，
# 而那一次 TypeError 被 `_safe` 吞掉 → 事件静默消失）。
check("★ 载荷里的 `kind` 被保留（emit_progress 改首参名后不再撞名）",
      got2 and got2[-1][1].get("kind") == "repeated_failure",
      str(got2[-1][1] if got2 else {}))
print(f"       （上游那一层的冲突：{type(err2).__name__ if err2 else '无'} —— "
      f"只能由上游改名解决，外部 checkout 已改）")

# 正面确认：仓库**自带**副本是否还是旧签名（记录事实，不作为失败）
import inspect  # noqa: E402

from core.coding_cycle import CodingCycle  # noqa: E402

params = list(inspect.signature(CodingCycle._emit).parameters)
print(f"       当前生效上游 _emit 的前几个参数：{params[:3]}")
check("能读到上游 _emit 的签名（判据来自真实上游，不是假设）",
      len(params) >= 2, str(params))


# ============================================================
print("\n" + "=" * 74)
print("[4] 边界：签名不可内省 / 只有位置参数")
print("=" * 74)


def only_positional(self, *args):
    only_positional.calls.append(args)


only_positional.calls = []
# 这个假上游只收位置参数，所以**不能**给它传关键字载荷（那是它自己的限制）
got3, err3 = run_case(only_positional, "cycle_end", "c2")
check("★ 不可内省时仍能取到事件名（退回第一个位置参数）",
      bool(got3) and got3[-1][0] == "cycle_end", str([k for k, _ in got3]))
check("★ 且原方法被如实调用", len(only_positional.calls) == 1,
      str(only_positional.calls))


# ============================================================
print("\n" + "=" * 74)
print("断言检查")
print("=" * 74)
failed = [n for n, ok in checks if not ok]
print(f"通过 {len(checks) - len(failed)}/{len(checks)}")
if failed:
    print("失败: " + "; ".join(failed))
raise SystemExit(1 if failed else 0)
