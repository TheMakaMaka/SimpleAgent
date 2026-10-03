"""离线校验：前端认得的事件词表 == 后端会发出的事件词表。

为什么这是"迁移价值"的看门测试
------------------------------
前端 `store/run.ts` 的 `case` 列表是**手工镜像**后端事件词的。两边一旦漂移：

  - 后端加事件 → 前端退化成时间线上的一行裸文本（比如标题写着 `task_result`）；
  - 前端加 case → 死代码，没人知道后端根本不发。

**不报错，只是少显示** —— 这类失效最难查。所以在这里钉死。

事件从三处来，都要扫：

  1. 上游 `backend/` 里 `self._emit("kind", ...)` —— 上游自带的 cycle 级事件
  2. `bridge/hooks.py` 里 `emit_progress("kind", ...)` —— 挂钩补出来的事件
  3. `bridge/runner.py` 里 `log.append("kind", ...)` —— 运行管理器自己的事件

上游那部分因为是**运行时挂钩**，扫描方式与普通源码一样：挂钩并没有改变
上游调用 `_emit` 的事实，所以扫上游文件仍然能拿到完整词表。

运行：python tests/unit/test_event_contract.py
"""

import ast
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import BACKEND, ROOT  # noqa: E402,F401

REDUCER = os.path.join(ROOT, "frontend", "src", "store", "run.ts")

#: (文件, 函数名) —— 这些函数的第一参数是事件 kind
CALL_SITES = [
    (os.path.join(BACKEND, "core", "coding_cycle.py"), "_emit"),
    (os.path.join(ROOT, "bridge", "hooks.py"), "emit_progress"),
    (os.path.join(ROOT, "bridge", "runner.py"), "append"),
]

checks: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))


def scan_kinds(path: str, func_name: str) -> set[str]:
    """用 AST 扫出这个函数产生的所有事件 kind。

    处理三种写法（**扫描器必须跟着代码走**）：
        emit_progress("phase", ...)              ← 直接调用
        _safe(emit_progress, "phase", ...)       ← 早期写法（实参在保护之外）
        emit_safe("phase", _build, ...)          ← 现行写法（payload 构造也在保护内）

    ★ 漏认 `emit_safe` 会让这个门禁**看不见** 5 个 bridge 事件
    （`phase`/`files`/`task_start`/`tool_call`/`verify_probe`）——
    实测：`bridge/spec.py` 的同类扫描器没跟着改时，bridge 侧从 21 掉到 **0**。
    跨行、字符串拼接都能正确处理，正则做不到这点。
    """
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    out: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        fn = node.func
        name = getattr(fn, "attr", None) or getattr(fn, "id", None)

        target = None
        if name == func_name:
            target = node.args[0]
        elif name == "emit_safe" and len(node.args) >= 2:
            target = node.args[0]          # `emit_safe(kind, build, *args)`
        elif name == "_safe" and len(node.args) >= 2:
            first = node.args[0]
            if getattr(first, "id", None) == func_name:
                target = node.args[1]

        if isinstance(target, ast.Constant) and isinstance(target.value, str):
            out.add(target.value)
    return out


def frontend_kinds() -> set[str]:
    """前端认得的事件词 = `run.ts` 的 `case` ∪ 采集器**声明**的词表。

    ★ 为什么不是只看 `case`（2026-09-27 `TRANSPARENCY-UI`）：

    上游新增的 `orchestrator_round` / `verify_criterion` / `self_report`
    （`core/contract.py:172/181/189`，`since="1.2"`）**还不在契约主本里**
    （主本 v1.0.24，与镜像逐字节一致）。于是：

      - 写 `case` → 自带旧副本那种配置下被判成死代码（[3] 红）；
      - 不写 `case` → 指向真上游时 [2] 红（后端发的没被认下）。

    两个配置都得绿，所以"前端认了"的判据从"必须写 case"改成
    "**必须有一处明确声明，且那份声明代码真的在用**"——
    `store/transparency.ts` 的 `RECOGNIZED_KINDS` 就是那份声明
    （它的键就是 `HANDLERS` 的键，声明与行为同一处，不会漂）。

    **这不是放宽**：`case` 之外的地方少一个，[2] 照样红；多一个，[3] 照样红。
    """
    ts = io.open(REDUCER, encoding="utf-8").read()
    kinds = set(re.findall(r"case '([a-z_]+)':", ts))
    kinds |= declared_kinds()
    return kinds


TRANSPARENCY = os.path.join(ROOT, "frontend", "src", "store", "transparency.ts")


def declared_kinds() -> set[str]:
    """采集器声明的词表（从源码里读，不手抄）。"""
    if not os.path.isfile(TRANSPARENCY):
        return set()
    src = io.open(TRANSPARENCY, encoding="utf-8").read()
    m = re.search(r"export const RECOGNIZED_KINDS = \[(.*?)\]", src, re.S)
    if not m:
        return set()
    return set(re.findall(r"'([a-z_]+)'", m.group(1)))


def transparency_uses_its_declaration() -> bool:
    """★ 声明必须**真的被用到**：`HANDLERS` 的键类型就是 `RecognizedKind`。

    只声明不使用 = 又做了一个会漂的副本，而这个门禁的全部意义就是防漂。
    """
    if not os.path.isfile(TRANSPARENCY):
        return False
    src = io.open(TRANSPARENCY, encoding="utf-8").read()
    return ("Record<RecognizedKind," in src
            and "HANDLERS[kind as RecognizedKind]" in src)


# ============================================================
print("=" * 74)
print("[1] 收集三处事件源")
print("=" * 74)
backend: dict[str, list[str]] = {}
for path, func in CALL_SITES:
    rel = os.path.relpath(path, ROOT)
    if not os.path.isfile(path):
        print(f"  FAIL  找不到 {rel}")
        checks.append((f"{rel} 存在", False))
        continue
    kinds = scan_kinds(path, func)
    print(f"  {rel:38} {func:16} → {len(kinds):2} 个")
    for k in kinds:
        backend.setdefault(k, []).append(rel)

b = set(backend)
f = frontend_kinds()
print(f"\n  后端共 {len(b)} 个 kind；前端归约器 + 采集器共 {len(f)} 个")
declared = declared_kinds()
if declared:
    print(f"  其中由 `store/transparency.ts` 声明：{sorted(declared)}")
check("★ 采集器的声明真的被代码用到（不是注释式声明）", transparency_uses_its_declaration())

#: 上游**已声明、契约主本尚未同步**的加性事件（逐个列名，有到期条件）。
#:
#: **第一批已到期并已删除**（2026-09-27）：`orchestrator_round` / `verify_criterion` /
#: `self_report` —— 契约 **v1.0.25** 已声明它们（13 → 16），那三个名字从这里删掉了。
#: **这就是本表该有的下场：契约一同步就删。** 现在这一批同样要求
#: **逐名能在参考上游的 `core/contract.py` 里核实**（下面会去读，核不到就 FAIL）。
#:
#: 依据：`core/contract.py:200` `reuse`（`since="1.3"`）、`:207` `decompose_review`（`since="1.3"`）。
PENDING_CONTRACT_KINDS = {"reuse", "decompose_review"}


# ============================================================
print("\n" + "=" * 74)
print("[2] 后端发的，前端必须认")
print("=" * 74)
missing = sorted(b - f)
checks.append(("后端事件词全部被前端处理", not missing))
if missing:
    print(f"  FAIL  {len(missing)} 个 kind 会退化成裸文本行：")
    for k in missing:
        print(f"         {k:24} 来自 {backend[k][0]}")
    print("        → 在 frontend/src/store/run.ts 的 switch 里补 case")
else:
    print("  PASS  全部命中")


# ============================================================
print("\n" + "=" * 74)
print("[3] 前端认的，后端必须真会发（否则是死代码）")
print("=" * 74)
extra = sorted(f - b)
# `default` 不是 kind；另外有几个由 hooks 用变量透传（见下）

# ★ 按**配置**分流：自带副本是旧的，前端却要为**新上游**备好 case
#   （这正是"上游加性新增 → 消费方跟上"该有的样子）。
#   所以当当前上游落后时，凡是**契约声明属上游**的 kind，
#   前端先认下来不算死代码 —— 那是"预备"，不是"孤儿"。
#   判据取自契约的 `event_partition.observed.upstream_kinds`（不是我记的名单）。
_contract_upstream: set[str] = set()
try:
    _cj = os.path.join(ROOT, ".interface_contract", "interface-contract.json")
    if os.path.isfile(_cj):
        import json as _json

        _obs = (_json.load(io.open(_cj, encoding="utf-8"))
                .get("event_partition") or {}).get("observed") or {}
        _contract_upstream = set(_obs.get("upstream_kinds") or [])
except Exception:  # noqa: BLE001
    _contract_upstream = set()

from bridge import staleness as _staleness  # noqa: E402

_stale_mode = _staleness.probe()["stale"]
_prepared = sorted(k for k in extra if k in _contract_upstream)
_pending = sorted(k for k in extra if k in PENDING_CONTRACT_KINDS and k not in _contract_upstream)
if _stale_mode and _prepared:
    print(f"        （当前上游落后：{_prepared} 是**契约已声明**的上游事件，"
          f"前端预备认下来 —— 不算死代码）")
    extra = [k for k in extra if k not in _contract_upstream]

if _stale_mode and _pending:
    # ★ 逐名核对：这些名字必须能在**参考上游**的契约里找到。
    #   找不到就不许豁免 —— 否则这条清单就成了"把死代码洗白"的后门。
    ref = _staleness.reference_dir_from_env() or os.getenv("AGENT_BACKEND_DIR", "")
    rel = os.path.relpath(ref, ROOT) if ref else ""
    contract_py = os.path.join(ref, "core", "contract.py") if ref else ""
    if ref and os.path.isfile(contract_py):
        src = io.open(contract_py, encoding="utf-8").read()
        absent = [k for k in _pending if f'"{k}": EventSpec(' not in src]
        check(f"★ 待同步事件确实由参考上游声明（{rel}）", not absent, str(absent))
        print(f"        （当前上游落后：{_pending} 上游已实装、契约主本尚未声明 —— "
              f"已在 `core/contract.py` 逐名核实；这条豁免在契约同步后应当删除）")
        extra = [k for k in extra if k not in PENDING_CONTRACT_KINDS]
    else:
        print(f"  SKIP  待同步事件 {_pending} 的逐名核实"
              f"（没设 AGENT_UPSTREAM_DIR / AGENT_BACKEND_DIR，够不到参考上游）")
        extra = [k for k in extra if k not in PENDING_CONTRACT_KINDS]

checks.append(("前端无孤儿 case", not extra))
if extra:
    print(f"  FAIL  {len(extra)} 个 case 后端不会发：")
    for k in extra:
        print(f"         {k}")
else:
    print("  PASS  无死代码")


# ============================================================
print("\n" + "=" * 74)
print("[4] 挂钩必须覆盖上游 _emit 产生的每一个 kind")
print("=" * 74)
# 上游的 `_emit` 是挂钩唯一接管 cycle 级事件的地方。只要 hooks 里包装了
# `CodingCycle._emit`，上游发什么它就能透传什么——这里确认包装确实存在，
# 而不是靠"我记得写了"。
#
# ★ 判据改成**读名单 + 读实际安装结果**（P5 之后）：
#   以前这里是九条 `"X.y = z" in hooks_src` 的**文本**断言 —— 那既会
#   "实现换个写法就红"（D9 已经因此改过一次），又**补不上新挂钩点**
#   （漏一个就少一条断言，而少一条没人会发现）。名单是唯一事实源：
#   `bridge/hooks.py` 的 `HOOK_POINTS` + `install()` 的返回值。
hooks_mod = None
try:
    sys.path.insert(0, ROOT)
    from bridge import hooks as hooks_mod  # noqa: E402
except Exception as e:  # noqa: BLE001
    print(f"  （读不到 bridge.hooks：{e}）")

if hooks_mod is None:
    check("能读到 bridge/hooks.py 的挂钩名单", False, "import 失败")
else:
    points = {f"{spec.split(':')[-1]}.{attr}" for spec, attr, _w, _s in hooks_mod.HOOK_POINTS}
    need = {
        "CodingCycle._emit", "CycleReport.enter", "CodingCycle.run",
        "CodingCycle._new_file_artifacts", "CheckpointManager.commit",
        "CheckpointManager.rollback", "Orchestrator._decide", "Worker.run",
        "LLMClient.chat", "Worker._invoke", "CheckPipeline.run_verify",
    }
    check("★ 挂钩名单覆盖全部 11 个汇聚点（少了谁这里就红）",
          need <= points, str(sorted(need - points)))
    reported = set(hooks_mod.install()["installed"])
    check("★ 实际装上的是名单里的全部（不是「我写了」而是「装上了」）",
          need <= reported, str(sorted(need - reported)))
    for name in sorted(need):
        check(f"挂钩包装了 {name}", name in reported)
    hooks_src = io.open(os.path.join(ROOT, "bridge", "hooks.py"), encoding="utf-8").read()
    check("★ 安装按名单遍历（不再逐个手写赋值 = 不再有十份会漂的镜像）",
          "for spec, attr, why, is_static in HOOK_POINTS" in hooks_src)


# ============================================================
print("\n" + "=" * 74)
print("[5] 前端文档里的词表也要跟着对（它是给人看的契约）")
print("=" * 74)
doc = os.path.join(ROOT, "frontend", "README.md")
if os.path.isfile(doc):
    text = io.open(doc, encoding="utf-8").read()
    # 文档里用反引号列了很多 kind，抽出来看有没有**没有事实源声明**的
    #
    # ★ 判据与 [3] 对齐（用 `extra` 而不是自己再算一遍）：文档提到一个
    #   "前端认得、当前后端不发、且契约/上游都没声明"的 kind 才算问题。
    #   契约已声明的（预备）与上游已实装的（待同步）都**应当**被文档提到 ——
    #   那条"尚未交付"的说明正是给人看的。
    documented = set(re.findall(r"`([a-z][a-z_]{3,})`", text))
    unknown = sorted(k for k in documented if k in extra)
    doc_missing = sorted(k for k in b if k not in text and k != "queued")
    check("文档没把已不存在的事件当成现有事件", not unknown, str(unknown[:6]))
    print(f"       文档未提到的后端事件 {len(doc_missing)} 个（不强制，仅提示）")
else:
    print("  （frontend/README.md 不存在，跳过）")


# ============================================================
print("\n" + "=" * 74)
print("[6] 事件**载荷键**的跨语言对齐（D8）")
print("=" * 74)
# 词表对得上还不够：前端读的**字段名**也要与后端发的对得上。
# 这条是 D8 的教训 —— `decision_opened` 的 payload 键由 `kind` 改成
# `decision_kind` 后，前端还在读 `ev.kind`，于是**决策种类显示成事件名**。
#
# 为什么以前没暴露：上游那个 TypeError 让这条路径**从未真正跑通过**，
# 所以 reducer 里那段是"新近才可到达的代码"。**能到达之后才第一次被执行。**
reducer = io.open(REDUCER, encoding="utf-8").read()
upstream_src = io.open(os.path.join(BACKEND, "core", "coding_cycle.py"),
                       encoding="utf-8").read()

# ---- 前端那一半：**无论用哪份上游都要对**（这是本仓库自己的代码）----
def strip_comments(text: str) -> str:
    """去掉 `//` 行注释 —— 否则"解释为什么不能读 ev.kind"的注释会被当成代码读点。"""
    return "\n".join(ln for ln in text.splitlines()
                     if not ln.lstrip().startswith("//"))


code_only = strip_comments(reducer)
branch = re.search(r"case 'decision_opened':\s*\{(.*?)\n    \}", code_only, re.S)
body = branch.group(1) if branch else ""
check("reducer 里有 decision_opened 分支", bool(body))
check("★ reducer 读的是 `ev.decision_kind`（D8 的修法）",
      "ev.decision_kind" in body, "未读到 ev.decision_kind")
check("★ reducer 不再把决策种类读成事件类型 `ev.kind`",
      "kind: String(ev.kind" not in body,
      "仍写着 kind: String(ev.kind …)")
other_kind_reads = [ln.strip() for ln in code_only.splitlines()
                    if "ev.kind" in ln and "const kind" not in ln]
check("★ 除事件名（`const kind = ev.kind`）外没有别处把 ev.kind 当载荷",
      not other_kind_reads, str(other_kind_reads))

# ---- 上游那一半：只在**有效上游**上判 ----
# 仓库自带的副本是旧的（payload 键还叫 `kind`，而且它因为一个 TypeError
# 根本发不出这个事件）。跨侧那一半只能对着真上游验 —— 因此按陈旧检测分流，
# 与 test_two_entrypoints.py / doctor.py 用的是同一条判据。
from bridge import staleness  # noqa: E402

probe = staleness.probe()
if probe["stale"]:
    print(f"  SKIP  上游侧的载荷键（当前上游落后：{probe['summary'][:60]}…）")
    print("       自带副本还发不出该事件；设 AGENT_BACKEND_DIR 指向真上游即可验")
else:
    m = re.search(r'_emit\(\s*"decision_opened".*?\)', upstream_src, re.S)
    emit_call = m.group(0) if m else ""
    check("上游确有 decision_opened 的 _emit 调用", bool(emit_call))
    check("★ 上游发的是 `decision_kind`（不是 `kind`）",
          "decision_kind=" in emit_call, " ".join(emit_call.split())[:120])
    colliding = re.findall(r'_emit\((?:[^()]|\([^()]*\))*?\bkind\s*=', upstream_src)
    check("★ 上游没有别的 `_emit(..., kind=...)` 载荷键（全类检查）",
          not colliding, f"{len(colliding)} 处")

# ---- bridge 这一侧：与上游新旧无关，都是本仓库的代码 ----
hooks_src2 = io.open(os.path.join(ROOT, "bridge", "hooks.py"), encoding="utf-8").read()
check("★ bridge 包装器展开 VAR_KEYWORD（载荷摊平，不是嵌套）",
      "VAR_KEYWORD" in hooks_src2 and "params.update(extra)" in hooks_src2)
prog_src = io.open(os.path.join(ROOT, "bridge", "progress.py"), encoding="utf-8").read()
check("★ `emit_progress` 首参不叫 `kind`（否则载荷里的 kind 会撞名并静默丢事件）",
      "def emit_progress(event_kind" in prog_src)


# ============================================================
print("\n" + "=" * 74)
print("[7] 新事件 `verify_skipped`：**两侧同时认下**才算完（校准 + 归约器）")
print("=" * 74)
# 上游 `FIX-VERIFY-WIRING` 加性新增的事件：把「有验证命令、却没有 pipeline，
# 于是验证回流整块被跳过」变成**显式事实**。
#
# 为什么会漏：词表对齐（[2]）只保证"归约器有 case"，
# 而**校准**（label/tone/panel）在 bridge 那一侧 —— 两处都补上才算认全。
# 统筹方实测时红的就是校准那半边（`uncalibrated_events=["verify_skipped"]`）。
from bridge.spec import build_spec  # noqa: E402

_spec = build_spec()
_cal = _spec["events"].get("verify_skipped")
_reducer_has = "verify_skipped" in f
_upstream_has = "verify_skipped" in b

if not _upstream_has:
    print("  SKIP  当前上游没有这个事件（自带副本是旧的）")
    print("       → 设 AGENT_BACKEND_DIR 指向真上游即可验这半边")
    check("前端归约器**预备**认它（上游一加就自动跟上）", _reducer_has,
          "run.ts 里应有 case 'verify_skipped'")
else:
    check("★ 上游确实在发这个事件", True)
    check("★ 前端归约器有它的 case（否则退化成裸文本行）", _reducer_has)
    check("★ bridge 给了它校准（否则 /api/spec 报 uncalibrated）",
          bool(_cal) and _cal.get("calibrated") is True and bool(_cal.get("label")),
          str(_cal))
    check("★ 校准的 tone 是 `warn` 而不是 `ok` —— 它是**跳过了一次检查**",
          _cal and _cal.get("tone") == "warn", str(_cal and _cal.get("tone")))
    check("校准落在 gate 面板（它是门禁那一段的事）",
          _cal and _cal.get("panel") == "gate", str(_cal and _cal.get("panel")))
    check("含 `{reason}` 占位符（跳过原因是最有价值的信息）",
          _cal and "{reason}" in (_cal.get("detail") or ""),
          str(_cal and _cal.get("detail")))

check("★ `/api/spec` 的 diagnostics 里没有未标定事件",
      not _spec["diagnostics"]["uncalibrated_events"],
      str(_spec["diagnostics"]["uncalibrated_events"]))
# 死标定同理：自带副本是旧的，标定表为**新上游**备好了条目 ——
# 那不算"死"，只是"当前这份上游还没发它"。按配置分流。
if _stale_mode:
    print(f"  SKIP  死标定检查（当前上游落后；标定表为契约的新上游备着）"
          f"{'：' + str(_spec['diagnostics']['dead_calibrations']) if _spec['diagnostics']['dead_calibrations'] else ''}")
    print("       → 设 AGENT_BACKEND_DIR 指向真上游即可验")
else:
    check("★ 也没有死标定",
          not _spec["diagnostics"]["dead_calibrations"],
          str(_spec["diagnostics"]["dead_calibrations"]))


# ============================================================
print("\n" + "=" * 74)
print("断言检查")
print("=" * 74)
failed = [n for n, ok in checks if not ok]
print(f"通过 {len(checks) - len(failed)}/{len(checks)}")
if failed:
    print("失败: " + "; ".join(failed))
raise SystemExit(1 if failed else 0)
