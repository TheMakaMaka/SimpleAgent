"""机械层的**复用性**检查（`TRANSPARENCY2-BACKEND` P2）。

用户原话：「代码基本模块能满足要求，但**不具备全局复用属性**，对项目的危害会很大。」

实测证据（工作单 §P2）：同一个概念模型发明了**三个名字** ——
真名 `obstacle_generator.generate_obstacles`；Run A 判据写 `ant_colony.generate_obstacles`
→ `AttributeError`；Run B 判据写 `obstacle_generator.generate_obstacle_grid()`
→ **函数不存在**。**两次都因此失败**。

## 五类缺陷与**我实际做成阻塞的还是警告的**（这条必须说清）

| # | 缺陷 | 手段 | 级别 | 为什么 |
|---|---|---|---|---|
| 1 | **调用了不存在的符号** | 符号表反查（AST） | **阻塞** | 必然运行时崩；两条实测判据都被它抓住 |
| 2 | 同一符号名在多个模块被定义 | 符号表去重 | **警告** | `main()`/`run()`/`test_*` 同名是常见且合法的 |
| 3 | 模块自造了一个已在别处导出的符号 | 同 2 | **警告** | 同上；要判"是不是同一概念"需要模型（属 ② 的模型层） |
| 4a | **用了没导入**（未定义名） | ruff `F821` / AST 兜底 | **阻塞** | 必然 `NameError`；实测 `np` 未定义就是它 |
| 4b | 导入了没用 | ruff `F401` | **警告** | 只是噪音。**把噪音做成阻塞 = 慢门禁 = 会被绕过**（本项目已结论） |
| 5 | 命名不一致（同一概念多种命名） | 词干聚类（机械近似） | **警告** | 只能近似；判定"是不是同一概念"要模型 |

> **为什么 2/3/5 没做成阻塞**（如实声明，不默默处理）：
> 它们要么会误伤合法代码（`main()` 同名），要么依赖语义判断（是不是同一概念）。
> 把它们硬做成阻塞，会让**几乎每次运行都失败** —— 那不是"严格"，
> 是把门禁变成噪音。**阻塞项只留"必然崩"的两类**；其余进 `warnings` 且**照样进事件**，
> 看得见、不拦路。若统筹方要求提升，改 `BLOCKING_KINDS` 一行即可。
"""

from __future__ import annotations

import ast
import os

#: 阻塞级缺陷（会让 check 阶段直接红）。
BLOCKING_KINDS = frozenset({"undefined-symbol", "undefined-name", "symbol-arity-mismatch"})

#: 允许在多个模块同名而不报的**约定名**（避免把合法结构当缺陷）。
_DUP_ALLOWLIST = {
    "main", "run", "setup", "cli", "test", "app", "__init__", "__main__",
    "config", "settings", "handler", "handler_main",
}


def _dotted(node) -> str:
    """把 `a.b.c` 形式的调用目标取成字符串；取不到返回空串。"""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _module_aliases(tree: ast.AST) -> dict[str, str]:
    """`别名 → 真实模块名`：`import a.b as c` → `c → a.b`；`from a.b import f as g` → `g → a.b`。"""
    alias: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                alias[a.asname or a.name.split(".")[0]] = a.name
        elif isinstance(node, ast.ImportFrom):
            if node.module and not node.level:
                for a in node.names:
                    alias[a.asname or a.name] = node.module
    return alias


def _bound_names(tree: ast.AST) -> set[str]:
    """粗粒度收集"这个文件里被定义/导入/赋值的名字"（用于未定义名兜底检查）。

    刻意**保守**：宁可漏报也不误报 —— 兜底检查只在 ruff 不可用时启用。
    """
    names: set[str] = set(dir(__builtins__) if isinstance(__builtins__, dict) is False
                          else __builtins__)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
            for a in node.args.args + node.args.kwonlyargs if hasattr(node, "args") else []:
                names.add(a.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                names.add(a.asname or a.name.split(".")[0])
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, (ast.comprehension,)):
            for t in ast.walk(node.target):
                if isinstance(t, ast.Name):
                    names.add(t.id)
    return names


def _arity_of(signature: str) -> tuple[int, int, bool] | None:
    """从签名串解析 `(最少位置参数, 最多位置参数, 是否 *args)`。

    `Symbol.signature` 是**字符串**（如 `generate_obstacles(map_size, num_obstacles, seed)`），
    所以这里重新 parse 一次。解析不了（类名、带注解的怪签名）→ 返回 `None`（**不判**）。
    """
    try:
        tree = ast.parse(f"def {signature}: pass")
    except SyntaxError:
        return None
    fn = tree.body[0]
    a = fn.args
    pos = list(a.posonlyargs) + list(a.args)
    if not pos:
        return None
    has_varargs = a.vararg is not None
    required = len(pos) - len(a.defaults)
    return required, len(pos), has_varargs


def _arity_violation(entry, sym, node: ast.Call, label: str) -> dict | None:
    """调用的**位置参数个数**与签名不符 → 必然 `TypeError`（实测踩过：U2 签名重构）。

    刻意保守：带 `*args` 展开、带关键字参数、或签名解析不了的**一律不判** ——
    宁可漏报，也不要把合法调用判成错。
    """
    if any(isinstance(a, ast.Starred) for a in node.args) or node.keywords:
        return None
    arity = _arity_of(getattr(sym, "signature", "") or "")
    if arity is None:
        return None
    required, maximum, has_varargs = arity
    n = len(node.args)
    if has_varargs:
        return None
    if required <= n <= maximum:
        return None
    return {
        "kind": "symbol-arity-mismatch",
        "severity": "blocking",
        "message": (f"{label} 用 {n} 个位置参数调用 `{entry.module}.{sym.name}`，"
                    f"但它的签名是 `{sym.signature}` —— 必然 TypeError"
                    "（『签名重构』这类改动最容易漏改调用点）"),
        "where": label,
        "module": entry.module,
        "symbol": sym.name,
    }


def check_code(code: str, *, label: str = "<code>") -> tuple[list[dict], set[str]]:
    """检查一段代码里**对本地模块符号的引用是否真实存在**。

    返回 `(violations, referenced_modules)`。`referenced_modules` 供调用方
    （判据检查）判断"这段代码动了哪些交付物"。

    这是本模块的核心：它同时服务
      · 交付物自检（P2 第 1 类：代码里调了不存在的符号）；
      · **判据**自检（P1：判据引用了不存在的符号 → 结局是 `invalid` 而不是 `fail`）。
    """
    from .symbol_index import build_index

    violations: list[dict] = []
    try:
        tree = ast.parse(code or "")
    except SyntaxError as e:
        return ([{
            "kind": "undefined-symbol",
            "severity": "blocking",
            "message": f"代码无法解析（{e.msg}，第 {e.lineno} 行）—— 无法做符号反查",
            "where": label,
        }], set())
    except Exception:  # noqa: BLE001
        return [], set()

    index = build_index()
    by_module = {e.module: e for e in index.values()}
    by_stem = {e.module.rsplit(".", 1)[-1]: e for e in index.values()}

    alias = _module_aliases(tree)
    referenced: set[str] = set()
    #: `from mod import f` 之后，`f(...)` 的归属模块
    from_alias = {k: v for k, v in alias.items()}
    #: 被调用的那个表达式节点 → 它所属的 Call（用于签名/参数个数核对）
    call_of: dict[int, ast.Call] = {
        id(n.func): n for n in ast.walk(tree) if isinstance(n, ast.Call)
    }

    def _lookup(owner: str):
        real = from_alias.get(owner, owner)
        return by_module.get(real) or by_stem.get(real)

    # ---------- ★ P7b（`REUSE-SYMBOL-SCOPE`）：作用域，先于模块反查 ----------
    # 实测假失败（能力基线 T9）：模型写的 Flask 代码**完全正确**
    #     from flask import Flask
    #     app = Flask(__name__)
    #     @app.route('/ping', methods=['GET'])
    # 而本层对 `app.route` 取 `owner = "app"` → `_lookup("app")` 命中**同名模块**
    # `app.py`（模型自己刚写的那个文件）→ 在它里面找 `route` → 找不到 → **blocking**。
    # 因为本层有硬否决权，它**否决了正确的代码**；更糟的是模型在 `self_report` 里
    # 写下"静态检查未通过"，**它以为自己对代码是错的**。
    #
    # 判据（可机械判定）：`owner` 的根名若由**非 import** 的绑定引入
    # （赋值 / 参数 / `with ... as` / `for` 目标 / `except ... as` / 推导式目标 /
    #  def|class 名），那它就是**某个对象的属性** —— 本地 AST 索引**不可能**知道
    # 那个对象上有什么，**不得判 blocking**（这类引用一律不报，见评估文档 §7）。
    # ⚠️ **import 别名必须继续反查**，否则会退化成"关掉检查"：
    # `import numpy as np` 却写 `np.array(...)`（缺 import 时另有 F821 兜底）、
    # `import t1` 却写 `t1.bar` 这些**必须仍然被抓住**。
    local_bindings = _bound_names(tree)
    import_bindings = set(alias) | {k.split(".")[0] for k in alias.values()}
    # `from x import *` 会引入**看不见的名字** ⇒ 这类文件不做"未定义名"判定
    # （宁可漏报，也不要对合法代码报错 —— 实测这条纪律的代价是假失败）。
    has_star_import = any(
        isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names)
        for n in ast.walk(tree)
    )

    def _is_local_object(owner: str) -> bool:
        root = (owner or "").split(".")[0]
        if not root:
            return False
        return root in local_bindings and root not in import_bindings

    def _is_undefined_root(owner: str) -> bool:
        """`owner` 的根名**既没绑定也不是内置** ⇒ 必然 `NameError`（P7b 要求 2）。"""
        if has_star_import:
            return False
        root = (owner or "").split(".")[0]
        if not root or root.startswith("__") and root.endswith("__"):
            return False
        return root not in local_bindings

    for node in ast.walk(tree):
        # ---- 形式 1：`mod.name(...)` / `mod.name` ----
        if isinstance(node, ast.Attribute):
            owner = _dotted(node.value)
            if owner:
                if _is_local_object(owner):
                    # 本地对象的属性：索引不可知 ⇒ 不判（顶多 info，本层选择不报）
                    continue
                if _is_undefined_root(owner):
                    # ★ 反空洞：`np.array(...)` 而**没有** `import numpy` ——
                    # 这类"根名压根不存在"必须仍然红（否则就是把检查关掉了）。
                    root = owner.split(".")[0]
                    violations.append({
                        "kind": "undefined-name",
                        "severity": "blocking",
                        "message": (f"{label} 第 {node.lineno} 行用了未定义的 `{root}`"
                                    "（没有 import，也没有任何绑定）—— 必然 NameError"),
                        "where": label,
                        "symbol": root,
                    })
                    continue
                entry = _lookup(owner)
                if entry is not None:
                    referenced.add(entry.path)
                    sym = next((s for s in entry.symbols if s.name == node.attr), None)
                    if sym is None:
                        violations.append({
                            "kind": "undefined-symbol",
                            "severity": "blocking",
                            "message": (f"{label} 引用了不存在的符号 "
                                        f"`{entry.module}.{node.attr}` —— "
                                        f"`{entry.module}` 里只有 "
                                        f"{sorted(entry.symbol_names())[:6]}"),
                            "where": label,
                            "module": entry.module,
                            "symbol": node.attr,
                        })
                    elif call_of.get(id(node)) is not None:
                        bad = _arity_violation(entry, sym, call_of[id(node)], label)
                        if bad:
                            violations.append(bad)
        # ---- 形式 2：`from mod import name` 导了不存在的东西 ----
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            entry = _lookup(node.module)
            if entry is not None:
                referenced.add(entry.path)
                for a in node.names:
                    if a.name != "*" and a.name not in entry.symbol_names():
                        violations.append({
                            "kind": "undefined-symbol",
                            "severity": "blocking",
                            "message": (f"{label} 从 `{entry.module}` 导入了不存在的符号 "
                                        f"`{a.name}` —— 它只有 "
                                        f"{sorted(entry.symbol_names())[:6]}"),
                            "where": label,
                            "module": entry.module,
                            "symbol": a.name,
                        })
        # ---- 形式 3：`f(...)`（`from mod import f` 之后直接调用）----
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            entry = _lookup(node.id) if node.id in from_alias else None
            if entry is not None:
                sym = next((s for s in entry.symbols if s.name == node.id), None)
                if sym is not None and call_of.get(id(node)) is not None:
                    bad = _arity_violation(entry, sym, call_of[id(node)], label)
                    if bad:
                        violations.append(bad)
    return violations, referenced


def check_undefined_names(code: str, *, label: str = "<code>") -> list[dict]:
    """类 `F821` 的兜底检查：**用了但没导入/定义**的名字（只报"必然崩"的形态）。

    有 ruff 时优先用 ruff（见 `run_ruff_f821`），这条兜底只在没装 ruff 时使用，
    且判据刻意写窄：只报**模块级函数体里出现了、整个文件都没绑定过的名字**。
    """
    try:
        tree = ast.parse(code or "")
    except SyntaxError:
        return []
    bound = _bound_names(tree)
    out: list[dict] = []
    seen: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id not in bound and node.id not in seen:
                seen.add(node.id)
                out.append({
                    "kind": "undefined-name",
                    "severity": "blocking",
                    "message": f"{label} 第 {node.lineno} 行用了未定义的 `{node.id}`（没有导入）",
                    "where": label,
                    "symbol": node.id,
                })
    return out


def run_ruff_f821(code: str) -> list[dict]:
    """用 ruff 做 `F821`（未定义名）。ruff 不可用 → 返回 `None`（**明确"未检查"**）。"""
    import json
    import shutil
    import subprocess
    import sys
    import tempfile

    exe = shutil.which("ruff") or shutil.which("ruff.exe")
    if not exe:
        if sys.platform == "win32":
            cand = os.path.join(os.path.expanduser("~"), "AppData", "Local",
                                "Programs", "Python", "Python310", "Scripts", "ruff.exe")
            exe = cand if os.path.exists(cand) else None
    if not exe:
        return []
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                     encoding="utf-8") as f:
        f.write(code or "")
        path = f.name
    try:
        proc = subprocess.run(
            [exe, "check", "--select", "F821", "--output-format", "json", path],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(proc.stdout or "[]")
    except Exception:  # noqa: BLE001 —— 工具问题不能变成"代码有问题"
        return []
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    out: list[dict] = []
    for item in data if isinstance(data, list) else []:
        msg = (item.get("message") or "").strip()
        row = (item.get("location") or {}).get("row")
        out.append({
            "kind": "undefined-name",
            "severity": "blocking",
            "message": f"第 {row} 行：{msg}",
            "where": "<code>",
        })
    return out


def duplicate_symbols(index: dict | None = None) -> list[dict]:
    """第 2/3 类：同一符号名在**多个模块**被定义（重复实现）。级别：警告。"""
    from .symbol_index import build_index

    idx = index if index is not None else build_index()
    where: dict[str, list[str]] = {}
    for entry in idx.values():
        for name in entry.symbol_names():
            where.setdefault(name, []).append(entry.module)
    out: list[dict] = []
    for name, mods in sorted(where.items()):
        if len(mods) < 2 or name in _DUP_ALLOWLIST or name.startswith("test_"):
            continue
        if name.startswith("__") and name.endswith("__"):
            continue
        out.append({
            "kind": "duplicate-symbol",
            "severity": "warning",
            "message": (f"符号 `{name}` 在 {len(mods)} 个模块里各定义了一份："
                        f"{sorted(mods)[:5]} —— 同一概念多处实现，改动会漏改"),
            "symbol": name,
        })
    return out


def naming_inconsistency(index: dict | None = None) -> list[dict]:
    """第 5 类（机械近似）：**同一词根**出现多种拼法 → 疑似同一概念多种命名。

    实测原型：`generate_obstacles` vs `generate_obstacle_grid`（少了复数、加了后缀）。
    机械判据刻意写窄：**词干集合完全相同但拼法不同**才算
    （`obstacles` 与 `obstacle` 归一到 `obstacle`）。
    """
    import re

    from .symbol_index import build_index

    idx = index if index is not None else build_index()

    def norm(name: str) -> str:
        parts = re.split(r"[_\W]+|(?<=[a-z])(?=[A-Z])", name or "")
        toks = []
        for p in parts:
            p = (p or "").lower().rstrip("s")
            if len(p) > 2:
                toks.append(p)
        return ".".join(sorted(toks))

    groups: dict[str, list[str]] = {}
    for entry in idx.values():
        for name in entry.symbol_names():
            key = norm(name)
            if key:
                groups.setdefault(key, []).append(name)
    out: list[dict] = []
    for key, names in sorted(groups.items()):
        uniq = sorted(set(names))
        if len(uniq) > 1:
            out.append({
                "kind": "naming-inconsistency",
                "severity": "warning",
                "message": (f"疑似同一概念多种命名：{uniq} —— "
                            "模型换一批名字，复用方就会调错"),
                "stem": key,
            })
    return out


def check_workspace(index: dict | None = None) -> dict:
    """对当前 workspace 做一次完整的机械复用性检查（含 5 类）。"""
    from .symbol_index import build_index

    idx = index if index is not None else build_index()
    violations: list[dict] = []
    for entry in idx.values():
        if not entry.path.endswith(".py") or not entry.syntax_ok:
            continue
        try:
            with open(entry.path, "r", encoding="utf-8") as f:
                code = f.read()
        except OSError:
            continue
        found, _ = check_code(code, label=entry.path)
        violations += found
    warnings = duplicate_symbols(idx) + naming_inconsistency(idx)
    blocking = [v for v in violations if v.get("severity") in BLOCKING_KINDS]
    return {
        "checked": True,
        "blocking": blocking,
        "warnings": warnings,
        "passed": not blocking,
    }
