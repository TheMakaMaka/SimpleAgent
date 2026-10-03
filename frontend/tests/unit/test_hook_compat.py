"""★ 全部挂钩点：包装器必须**接得住上游签名**（P5 —— D9 的推广）。

背景：一次真实的"系统跑不起来"
------------------------------
上游 v1.23 给 `CheckPipeline.run_verify` 加了一个**可选参数**：

    core/pipeline.py:361   async def run_verify(self, command, files=None) -> dict
    core/orchestrator.py:246   vr = await self.pipeline.run_verify(vc, files)

而 `bridge/hooks.py` 的包装器**镜像了旧签名**：

    async def _run_verify(self, command):     # ← 收不下第二个位置参数

于是每一次运行都在 ~6 秒内炸：

    TypeError: install.<locals>._run_verify() takes 2 positional arguments but 3 were given

**验证整条链停摆**，而我们的单测全绿 —— 因为它不在测试范围内。这与 D9
（`_emit` 包装器撞名）**是同一类**：在一处学到了"要透传"，没推广到另外九个挂钩点。

这个测试把"推广"钉住
--------------------
不逐个手写断言，而是按 `bridge/hooks.py` 的**唯一名单** `HOOK_POINTS` 遍历：

  [1] 名单与安装结果一致（11 个点，一个不少、一个不多）
  [2] 每个包装器都**不是镜像**：签名就是 `(*args, **kwargs)`
  [3] 每个包装器都**接得住**上游的真实参数 —— 而且**再加一个可选参数**也接得住
      （那正是 P5 的形态：上游加性新增，我们不该跟着改）
  [4] 同步/异步**问上游**，不手写
  [5] 真回归复现：用上游的调用形态（2 个位置参数）真的跑一次 `run_verify`
  [6] **负向**：一个镜像签名的假包装器必须被上面这套判据判红
      （否则这条门禁只是"永远绿"）

运行：python tests/unit/test_hook_compat.py
"""

import asyncio
import inspect
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401

checks: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))


# ============================================================
print("=" * 74)
print("[1] 名单：挂钩点一个不少、一个不多")
print("=" * 74)
import bridge.bootstrap as bootstrap  # noqa: E402

bootstrap.install()

from bridge import hooks  # noqa: E402

report = hooks.install()
points = list(hooks.HOOK_POINTS)
installed = list(report["installed"])
print(f"  HOOK_POINTS {len(points)} 个 · 实际安装 {len(installed)} 个")
for spec, attr, why, is_static in points:
    print(f"    {spec.split(':')[-1]}.{attr:22} {'static' if is_static else '      '} {why}")

check("★ 挂钩点是 11 个（与设计清单一致）", len(points) == 11, str(len(points)))
expect = [f"{spec.split(':')[-1]}.{attr}" for spec, attr, _w, _s in points]
check("★ 名单里的每一个都装上了（一个都不漏）",
      set(expect) <= set(installed), str(sorted(set(expect) - set(installed))))
check("★ 实际安装的每一个都在名单里（没有偷偷多挂）",
      set(installed) <= set(expect), str(sorted(set(installed) - set(expect))))
check("★ 围绕逻辑与名单一一对应（没有「有点没逻辑」的空壳）",
      all((spec, attr) in hooks._AROUND or attr == "_emit" for spec, attr, _w, _s in points))


# ============================================================
print()
print("=" * 74)
print("[2]/[3] 逐个挂钩点：不镜像签名，且接得住上游参数（+ 多加一个）")
print("=" * 74)


class Dummy:
    """哑 self：包装器内部只做 `getattr(x, '...', 默认)`，碰不出错。"""

    def __init__(self, name: str = "self"):
        self._name = name

    def __repr__(self):
        return f"<Dummy {self._name}>"


def dummies_for(func):
    """按**上游真实签名**造一次调用：必填参数给哑值，可选参数**不传**（走默认）。

    这就是"上游可以加可选参数而我们不用改"的那条边界。
    """
    sig = inspect.signature(func)
    args: list = []
    for pname, p in sig.parameters.items():
        if p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        if p.default is not inspect.Parameter.empty:
            continue                     # 可选：不传
        args.append(Dummy(pname))
    return args


async def call_maybe(func, *args, **kwargs):
    out = func(*args, **kwargs)
    return await out if inspect.isawaitable(out) else out


mirrored: list[str] = []
unaccepting: list[str] = []
async_mismatch: list[str] = []
not_factory: list[str] = []

for spec, attr, _why, is_static in points:
    cls = hooks.resolve(spec)
    # `current` = 现在生效的那个函数（staticmethod 要脱一层）
    current = getattr(cls, attr)
    raw = cls.__dict__.get(attr)
    if isinstance(raw, staticmethod):
        current = raw.__func__
    # `orig` = **包装之前**的原方法（工厂留了 `__wrapped_orig__`）
    orig = getattr(current, "__wrapped_orig__", None) or current

    # 每个包装器都必须是工厂造的（`__bridge_hook__` 是工厂的印记）
    if not hasattr(current, "__bridge_hook__"):
        not_factory.append(f"{spec.split(':')[-1]}.{attr}")
        continue

    # [2] 签名只许是「可选的 `self` + `*args` + `**kwargs`」—— 这是**真相**，
    #     也是"没镜像上游参数"的证据。`self` 是实例绑定，不算镜像。
    params = inspect.signature(current).parameters
    kinds = [(n, p.kind) for n, p in params.items()]
    only_var = all(
        k is inspect.Parameter.VAR_POSITIONAL
        or k is inspect.Parameter.VAR_KEYWORD
        or (n == "self" and k is inspect.Parameter.POSITIONAL_OR_KEYWORD)
        for n, k in kinds
    ) and any(k is inspect.Parameter.VAR_KEYWORD for _n, k in kinds)
    if not only_var:
        mirrored.append(f"{spec.split(':')[-1]}.{attr}={list(params)}")

    # [4] 同步/异步与上游一致（问上游，不手写）
    if inspect.iscoroutinefunction(current) != inspect.iscoroutinefunction(orig):
        async_mismatch.append(f"{spec.split(':')[-1]}.{attr}")

    # [3] 接得住上游参数 —— 用**同一个工厂**造一个只透传的包装器来验
    #     （不跑各挂钩点自己的副作用；那些由各自的测试覆盖）
    seen: list[tuple] = []

    def probe(*args, **kwargs):
        seen.append((args, kwargs))
        return None

    probe.__name__ = attr
    wrapped = hooks.make_hook(probe, lambda named, call: call(), label="probe")
    base = dummies_for(orig)
    extra = Dummy("新增的可选参数")
    try:
        if inspect.iscoroutinefunction(wrapped):
            asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
                call_maybe(wrapped, *base))
            asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
                call_maybe(wrapped, *base, extra))
        else:
            wrapped(*base)
            wrapped(*base, extra)          # ★ 上游加性新增：必须照样接住
    except TypeError as e:
        unaccepting.append(f"{spec.split(':')[1]}.{attr}: {e}")
    else:
        # 原方法收到的参数**原样**（不多不少）
        if not seen or seen[0][0] != tuple(base):
            unaccepting.append(f"{spec.split(':')[1]}.{attr}: 参数没原样透传")

check("★ 所有包装器都不是镜像签名（签名 = `*args, **kwargs`）", not mirrored, str(mirrored))
check("★ 所有包装器都接得住上游参数，**并且多加一个可选参数也接得住**",
      not unaccepting, "; ".join(unaccepting[:3]))
check("★ 同步/异步与上游一致（从上游读，不手写）", not async_mismatch, str(async_mismatch))
check("★ 所有挂钩点都是工厂造的（没有手写的镜像包装器）", not not_factory, str(not_factory))


# ============================================================
print()
print("=" * 74)
print("[4] 真回归复现：上游的调用形态（2 个位置参数）真的跑一次 run_verify")
print("=" * 74)
from core.cycle import VerifyCommand  # noqa: E402
from core.pipeline import CheckPipeline  # noqa: E402

from bridge import progress  # noqa: E402


class Capture:
    def __init__(self):
        self.received: list[tuple[str, dict]] = []

    def __call__(self, kind, payload):
        self.received.append((kind, payload))


sig_up = inspect.signature(getattr(CheckPipeline.run_verify, "__wrapped_orig__",
                                 CheckPipeline.run_verify))
up_params = [n for n, p in sig_up.parameters.items()
             if p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD and n != "self"]
has_files = "files" in up_params
print(f"  当前生效上游 run_verify 的位置参数：{up_params}"
      f"（{'v1.23 形态，含 files' if has_files else '旧副本，无 files'}）")
check("★ 能读到当前生效上游的 run_verify 签名（判据来自真实上游，不是假设）",
      len(up_params) >= 1, str(up_params))


async def real_run_verify(*extra):
    cap = Capture()
    token = progress.bind_progress(cap)
    err = None
    res = None
    try:
        vc = VerifyCommand(command="print('PASS')\n", reason="挂钩点兼容性自检")
        # ★ 按**上游自己的**参数个数调用（自带副本比真上游旧，这点如实分流）
        res = await CheckPipeline().run_verify(vc, *extra)
    except Exception as e:  # noqa: BLE001
        err = e
    finally:
        progress.reset_progress(token)
    return res, err, cap.received


loop = asyncio.new_event_loop()
res, err, got = loop.run_until_complete(real_run_verify())
kinds = [k for k, _ in got]
print(f"  run_verify(vc) → err={type(err).__name__ if err else '无'} · 发出 {kinds}")
check("★ 真的走到了验证：`verify_probe` 事件发出来了", "verify_probe" in kinds, str(kinds))
check("★ 验证结果取到了（passed 字段存在）", isinstance(res, dict) and "passed" in res,
      str(sorted(res) if isinstance(res, dict) else res)[:120])
check("★ 载荷带上了命令原文（`verify_probe.command`）",
      bool(got) and bool(got[-1][1].get("command")), str(got[-1][1].get("command"))[:60] if got else "")

if has_files:
    # ★★ 这一条就是 P5 的复现：上游用**两个位置参数**调用
    res_f, err_f, got_f = loop.run_until_complete(real_run_verify(["obstacle_generator.py"]))
    kinds_f = [k for k, _ in got_f]
    print(f"  run_verify(vc, files) → err={type(err_f).__name__ if err_f else '无'} · 发出 {kinds_f}")
    check("★★ P5 复现：上游的**两个位置参数**形态不再抛 TypeError", err_f is None, repr(err_f))
    check("★★ 且真的走到了验证（`verify_probe` 发出来了）", "verify_probe" in kinds_f, str(kinds_f))
    # 关键字形态也必须收得下（上游将来改传参风格时不用再动我们）
    kw_err = None
    try:
        loop.run_until_complete(
            CheckPipeline().run_verify(
                command=VerifyCommand(command="print('PASS')\n", reason="kw"),
                files=[]))
    except Exception as e:  # noqa: BLE001
        kw_err = e
    check("★ 关键字形态也收得下（上游将来改传参风格不用再动我们）", kw_err is None, repr(kw_err))
else:
    print("  SKIP  两位置参数形态（当前生效的这份上游还没有 `files` 参数）")
    print("       → 设 AGENT_BACKEND_DIR 指向 v1.23+ 的真上游即可验这一条")

check("★ 重复调用仍然成立（幂等：挂钩只装一次）",
      hooks.report()["installed"] == installed, str(hooks.report()["installed"]))


# ============================================================
print()
print("=" * 74)
print("[5] 负向：镜像签名的包装器**必须**被这套判据判红")
print("=" * 74)


def mirroring_wrapper(self, command):        # ← 旧写法（就是 P5 那个）
    return None


sig = inspect.signature(mirroring_wrapper)
only_var = sorted(p.kind.name for p in sig.parameters.values()) == ["VAR_KEYWORD",
                                                                   "VAR_POSITIONAL"]
check("★ 负向：镜像签名不会被误判成透传", not only_var, str(list(sig.parameters)))
try:
    mirroring_wrapper(Dummy("self"), Dummy("command"), Dummy("files"))
    accepted = True
except TypeError:
    accepted = False
check("★ 负向：镜像签名**接不住**多加的那个参数（正是上游 v1.23 的形态）", not accepted)

src = io.open(os.path.join(ROOT, "bridge", "hooks.py"), encoding="utf-8").read()
# 旧形态**只许作为说明**出现（带反引号的散文引用），不许出现在代码行上 ——
# 与 `test_hooks_passthrough.py` 对 `_emit` 旧形态用的是同一条判据。
_mirror_lines = [ln for ln in src.splitlines() if "async def _run_verify(self, command)" in ln]
check("★ 镜像写法只作为「说明」出现（带反引号的散文引用），不是代码",
      len(_mirror_lines) <= 1 and all("`" in ln for ln in _mirror_lines),
      str(_mirror_lines)[:120])
check("★ 同步/异步的判断来自 `iscoroutinefunction`（不手写）",
      "inspect.iscoroutinefunction(orig)" in src)
check("★ 只有一个名单（`HOOK_POINTS`），install 按它遍历",
      "HOOK_POINTS" in src and "for spec, attr, why, is_static in HOOK_POINTS" in src)


# ============================================================
print()
print("=" * 74)
print("[6] ★ P5b：挂钩体内**不许引用不存在的模块全局**")
print("=" * 74)
# 起因（一次真实阻塞）：`_around_invoke` 里写的是 `Worker._parse_args(...)`，
# 而 `Worker` 只在 `install()` 里**函数内** import 过 —— 模块全局里从来没有它：
#
#     NameError: name 'Worker' is not defined
#
# 后果与 P5 一样重：**每一次运行在"模型第一次调用工具"的那一刻死掉**。
# ★ 而 ruff **早就报了** `F821 Undefined name 'Worker'` ——
#   被我自己那句 `# noqa: F821（install 时已 import）` 压掉了，**理由是错的**。
#   **一句 noqa 能让门禁闭嘴，但改不了运行期的事实。**
#
# 所以这里放**两条**判据：一条用 ruff（真门禁），一条自己扫 `LOAD_GLOBAL`
# （不依赖外部工具，且能证明它不是永远绿）。
import builtins  # noqa: E402
import dis  # noqa: E402
import subprocess  # noqa: E402


def undefined_globals(fn) -> list[str]:
    """扫出函数体里引用的、**模块里并不存在**的全局名。

    用 `dis` 而不是正则：只看真正编译成 `LOAD_GLOBAL`/`LOAD_NAME` 的名字 ——
    函数内 import 是 `LOAD_FAST`（局部），不会被误判。
    """
    mod = sys.modules[fn.__module__]
    have = set(vars(mod)) | set(dir(builtins))
    bad: list[str] = []
    for ins in dis.get_instructions(fn):
        if ins.opname in ("LOAD_GLOBAL", "LOAD_NAME") and ins.argval not in have:
            bad.append(f"{fn.__name__}: {ins.argval}")
    return bad


_hook_fns = list(hooks._AROUND.values()) + [hooks.install, hooks.make_hook,
                                            hooks.make_sync_hook, hooks.make_async_hook,
                                            hooks.bind_arguments, hooks.worker_cls]
_bad = [b for fn in _hook_fns for b in undefined_globals(fn)]
check("★ 全部挂钩体没有引用不存在的模块全局（P5b 的形态）", not _bad, str(_bad))

# ★ 判据不是永远绿：一个引用不存在全局的假函数**必须**被扫出来。
def _fake_with_missing_global():
    return DefinitelyNotDefinedAnywhere()._parse_args("{}")   # noqa: F821


check("★ 负向：引用不存在全局的假函数会被扫出来",
      bool(undefined_globals(_fake_with_missing_global)),
      str(undefined_globals(_fake_with_missing_global)))
check("★ `Worker` 不再以模块全局形式出现（走 worker_cls() 延迟取）",
      "worker_cls()" in src and "Worker._parse_args(arguments_json)" not in src)

_ruff = os.path.join(ROOT, ".venv", "Scripts", "ruff.exe")
if not os.path.isfile(_ruff):
    print("  SKIP  ruff F821 门禁（.venv\\Scripts\\ruff.exe 不在）")
else:
    proc = subprocess.run(
        [_ruff, "check", "--select", "F821", "--ignore-noqa", "bridge/"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()
    check("★ ruff F821（**刻意忽略 noqa 压制**）零命中", proc.returncode == 0,
          " | ".join(out[-3:])[:160])
    # 对照：不忽略压制时也应为 0（说明**没有靠 noqa 遮**）
    proc2 = subprocess.run([_ruff, "check", "--select", "F821", "bridge/"],
                           cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    check("★ 不忽略 noqa 时也是零命中（没靠压制遮住）", proc2.returncode == 0)


# ============================================================
print()
print("=" * 74)
print("[7] ★ 生产路径冒烟：装上挂钩之后，`Worker._invoke` 真的能跑")
print("=" * 74)
# P5b 的死点就在这里：挂钩装上了，但**一调用就 NameError**。
# 前面 [4] 验的是 `run_verify`；这一条补上工具调用那一个。
from core.worker import Worker as _Worker  # noqa: E402

_smoke_kinds: list[str] = []


async def _smoke_invoke():
    cap = Capture()
    token = progress.bind_progress(cap)
    try:
        w = _Worker.__new__(_Worker)        # 不跑 __init__（不碰模型/网络）
        return await _Worker._invoke(w, "read_file", '{"filename": "README.md"}'), cap.received, None
    except BaseException as e:              # noqa: BLE001 —— **真的断言它有没有抛**
        return None, cap.received, e
    finally:
        progress.reset_progress(token)


_invoke_res, _invoke_events, _invoke_err = asyncio.new_event_loop().run_until_complete(_smoke_invoke())
_kinds_smoke = [k for k, _ in _invoke_events]
print(f"  Worker._invoke(read_file) → {str(_invoke_res)[:60]!r} · 发出 {_kinds_smoke}")
# ★ 这一条原来写的是 `check(…, True)` —— **硬编码 True 的空洞断言**：
#   它永远不会红，却计入"通过 N/N"。统筹方点出了它（判据 4-①）。
check("★ 装上挂钩之后调 `Worker._invoke` 没有抛异常（P5b 的形态是 NameError）",
      _invoke_err is None, repr(_invoke_err))
check("★ 发出 `tool_call` / `tool_result`", "tool_call" in _kinds_smoke
      and "tool_result" in _kinds_smoke, str(_kinds_smoke))


# ============================================================
print()
print("=" * 74)
print("[8] ★ `_safe` 的契约：**普通异常必须被吞、`RunCancelled` 必须穿出去**")
print("=" * 74)
# 起因（又一次 U- 类：声明 vs 实现不符）：模块抬头写着
#   「每个包装都兜住自己的异常，进度坏掉不能让 cycle 失败」
# 而 `_safe` 当时是 `except BaseException: raise` + `except Exception: return None`
# —— 第一条把**所有**异常截走重抛，第二条**永远走不到**（死代码）。
# 实测：`_safe(lambda: 1/0)` 抛 ZeroDivisionError ⇒ **一个异常都没兜住**，
# 而挂钩自身的 bug 会杀掉用户整轮运行，且与"模型做不出来"长得一模一样。
from bridge.progress import RunCancelled as _RC  # noqa: E402


class _Boom(Exception):
    pass


def _raises(exc):
    def _f():
        raise exc
    return _f


check("★ 普通异常被吞掉（返回 None）", hooks._safe(lambda: 1 / 0) is None)
check("★ 自定义异常同样被吞", hooks._safe(_raises(_Boom("boom"))) is None)
check("★ 正常返回值照旧透出（不是把成功也吞了）", hooks._safe(lambda: 42) == 42)
try:
    hooks._safe(_raises(_RC("stop")))
    _rc_out = False
except _RC:
    _rc_out = True
check("★★ `RunCancelled` **仍然穿出去**（否则「取消」就失效了）", _rc_out)
try:
    hooks._safe(_raises(KeyboardInterrupt()))
    _ki_out = False
except KeyboardInterrupt:
    _ki_out = True
check("★ `KeyboardInterrupt` 也穿出去（它不是 `Exception`）", _ki_out)

# 判据 I（结构）：**全捕获重抛之后不许再有 except**。
# ★ 断言必须**只看代码**：`_safe` 的 docstring 里引用着旧形态（那是说明，不是代码）。
#   用 `ast` 把 docstring 摘掉再判 —— 文本搜索会把"解释它为什么不行"的那段也算进去
#   （这个坑本仓库踩过：`test_hooks_passthrough.py` 对 `_emit` 的旧形态用的是
#   "旧形态只许作为带反引号的散文出现"）。
import ast as _ast  # noqa: E402

_hs = io.open(os.path.join(ROOT, "bridge", "hooks.py"), encoding="utf-8").read()
_safe_fn = next(n for n in _ast.parse(_hs).body
                if isinstance(n, _ast.FunctionDef) and n.name == "_safe")
_code_nodes = [
    n for n in _safe_fn.body
    if not (isinstance(n, _ast.Expr) and isinstance(n.value, _ast.Constant))
]
_code = "\n".join(_ast.unparse(n) for n in _code_nodes)
print(f"  `_safe` 的**代码**（摘掉 docstring）：{_code!r}")
check("★ 结构：`_safe` 里没有 `except BaseException`（那会把所有异常重抛）",
      "except BaseException" not in _code)
check("★ 结构：`_safe` 里确有 `except RunCancelled` 与 `except Exception`",
      "except RunCancelled" in _code and "except Exception" in _code)

# 负向：把**旧形态**喂给同一组行为判据，必须判红（证明判据不是永远绿）。
def _safe_old(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except BaseException:
        raise
    except Exception:
        return None


try:
    _old_swallow = _safe_old(lambda: 1 / 0) is None
except ZeroDivisionError:
    _old_swallow = False
check("★ 负向：旧形态（`except BaseException: raise`）**兜不住**普通异常",
      not _old_swallow)

# 取类失败也必须在保护范围内（`worker_cls()` 若是**在 `_safe` 之外**求值的，就炸穿）。
_orig_worker_cls = hooks.worker_cls
try:
    def _no_worker():
        raise RuntimeError("上游没有 core.worker")

    hooks.worker_cls = _no_worker
    _cls_fail = hooks._safe(hooks.parse_worker_args, "{}")
    _cls_err = None
except BaseException as e:  # noqa: BLE001
    _cls_fail, _cls_err = "炸穿了", e
finally:
    hooks.worker_cls = _orig_worker_cls
check("★ 「取类失败」也在 `_safe` 保护范围内（不炸穿）",
      _cls_err is None and _cls_fail is None, repr(_cls_err))
check("★ 源码里调用点是 `_safe(parse_worker_args, …)`（取类在**内层**）",
      "_safe(parse_worker_args, arguments_json)" in _hs)


# ============================================================
print()
print("=" * 74)
print("[9] ★ 扫描器必须跟着 emit 的写法走（否则事件会**静默消失**）")
print("=" * 74)
# 本轮差点栽在这上面：`_safe(emit_progress, "phase", …)` 改成
# `emit_safe("phase", _build, …)` 之后，`bridge/spec.py` 与
# `tests/unit/test_event_contract.py` 里的 AST 扫描器**只认前两种写法** ——
# 于是 `/api/spec` 里 bridge 侧的事件从 **21 掉到 0**
# （`phase`/`files`/`task_start`/`tool_call`/`verify_probe` 全部不再被认到），
# 而**它不报错、只是少认**。
#
# 是我自己的门禁（`test_partition` / `test_spec` / `test_event_contract`）抓到的。
# 这条判据把它钉死：**hooks.py 里每一个 emit 调用点，扫描器都必须认得**。
import bridge.spec as _spec  # noqa: E402

_HOOKS_PY = os.path.join(ROOT, "bridge", "hooks.py")
_hooks_ast = _ast.parse(io.open(_HOOKS_PY, encoding="utf-8").read())

_emitted: set[str] = set()
for _node in _ast.walk(_hooks_ast):
    if isinstance(_node, _ast.Call) and _node.args:
        _fn = _node.func
        _name = getattr(_fn, "attr", None) or getattr(_fn, "id", None)
        # 现行写法：emit_safe("kind", build, …)
        if _name == "emit_safe" and isinstance(_node.args[0], _ast.Constant) \
                and isinstance(_node.args[0].value, str):
            _emitted.add(_node.args[0].value)
        # 早期写法：_safe(emit_progress, "kind", …)
        elif _name == "_safe" and len(_node.args) >= 2 \
                and getattr(_node.args[0], "id", None) == "emit_progress" \
                and isinstance(_node.args[1], _ast.Constant) \
                and isinstance(_node.args[1].value, str):
            _emitted.add(_node.args[1].value)

_scanned = {k for k, _ln in _spec._scan_calls(_HOOKS_PY, {"emit_progress"})}
print(f"  hooks.py 里直接写死的 kind：{len(_emitted)} 个；扫描器认到：{len(_scanned)} 个")
_missed = sorted(_emitted - _scanned)
check("★ 扫描器认得 hooks.py 里**每一个** emit 调用点（一个都不许漏）",
      not _missed, f"漏认 {_missed}")
check("★ 扫描器还认得早期写法 `_safe(emit_progress, 'kind', …)`",
      "verify_probe" in _scanned or "files" in _scanned, str(sorted(_scanned))[:120])
_need = {"phase", "files", "task_start", "tool_call", "verify_probe"}
check("★ 这 5 个（最容易被写法变更漏掉的）都在扫描结果里",
      _need <= _scanned, str(sorted(_need - _scanned)))
_ek = set(_spec.event_kinds())
check("★ `bridge.spec.event_kinds()` 也认全（`/api/spec` 的分区靠它）",
      _need <= _ek, str(sorted(_need - _ek)))


# ============================================================
print()
print("=" * 74)
print("断言检查")
print("=" * 74)
failed = [n for n, ok in checks if not ok]
print(f"通过 {len(checks) - len(failed)}/{len(checks)}")
if failed:
    print("失败: " + "; ".join(failed))
raise SystemExit(1 if failed else 0)
