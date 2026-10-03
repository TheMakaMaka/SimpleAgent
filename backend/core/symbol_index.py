"""符号索引：用 AST 扫描 workspace，产出「结构事实」。

这是架构视图的**可信部分**：文件、导出符号、签名、import 关系全部由程序从
真实代码里解析出来，不经过模型，因此可以作为判据使用。

与设计注记的分工：
  - 本模块（结构事实）：程序生成，可信，每轮可重新生成 → 可判定 violation
  - 设计注记（职责/扩展点/取舍）：模型编写，可能过时 → 只作参考，不算判据

不使用 grep 或正则匹配代码，避免把字符串里的内容误判为真实符号。
"""

import ast
import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

WORKSPACE_DIR = os.path.abspath("workspace")

# 扫描时跳过的目录
_SKIP_DIRS = {"_tmp", "_debug", "__pycache__", ".git", ".venv", "node_modules"}


@dataclass
class Symbol:
    name: str
    kind: str                 # function | async_function | class
    signature: str            # 例如 "add(a, b)" 或 "Stack" 或 "run(args)"
    lineno: int
    methods: list[str] = field(default_factory=list)   # 仅 class

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "kind": self.kind,
            "signature": self.signature,
            "lineno": self.lineno,
        }
        if self.methods:
            d["methods"] = self.methods
        return d


@dataclass
class ModuleEntry:
    path: str                 # 相对 workspace，正斜杠
    module: str               # 可 import 的模块名，例如 "pkg.mod"
    package: str              # 所属包，例如 "pkg"，顶层为空串
    symbols: list[Symbol] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)         # 原始 import 目标
    local_deps: list[str] = field(default_factory=list)      # 解析后指向本地模块的依赖
    sha1: str = ""
    lines: int = 0
    syntax_ok: bool = True
    error: str | None = None

    def symbol_names(self) -> set[str]:
        return {s.name for s in self.symbols}

    def to_dict(self, include_code: bool = False) -> dict:
        d = {
            "path": self.path,
            "module": self.module,
            "symbols": [s.to_dict() for s in self.symbols],
            "local_deps": sorted(self.local_deps),
            "sha1": self.sha1,
            "lines": self.lines,
        }
        if self.error:
            d["error"] = self.error
        return d


def _format_signature(node) -> str:
    """把函数签名格式化成可读文本，用于对照。"""
    args = node.args
    parts: list[str] = []

    posonly = getattr(args, "posonlyargs", []) or []
    for a in list(posonly) + list(args.args):
        parts.append(a.arg)
    if args.vararg:
        parts.append("*" + args.vararg.arg)
    elif args.kwonlyargs:
        parts.append("*")
    for a in args.kwonlyargs:
        parts.append(a.arg)
    if args.kwarg:
        parts.append("**" + args.kwarg.arg)

    return f"{node.name}({', '.join(parts)})"


class _ModuleVisitor(ast.NodeVisitor):
    """只收模块级符号与类方法，忽略函数内部定义。"""

    def __init__(self) -> None:
        self.symbols: list[Symbol] = []
        self.imports: list[str] = []

    # ---------- 导入 ----------
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """记录「实际被导入的模块」。

        注意 `from . import a, b` 的语义是导入当前包下的 a 和 b，
        而不是导入一个叫 "." 的模块。若只记 base，就无法判断 a/b 是否存在，
        会漏掉整类悬空依赖。
        """
        base = ("." * (node.level or 0)) + (node.module or "")
        if node.module:
            # from x.y import a  → 依赖 x.y（a 是其中的符号，不是模块）
            self.imports.append(base)
            return
        # from . import a, b → 依赖 .a 和 .b
        for alias in node.names:
            if alias.name == "*":
                self.imports.append(base)
            else:
                self.imports.append(f"{base}{alias.name}")

    # ---------- 顶层符号 ----------
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.symbols.append(
            Symbol(
                name=node.name,
                kind="function",
                signature=_format_signature(node),
                lineno=node.lineno,
            )
        )
        # 不深入函数体，避免把内部嵌套函数当成模块符号

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.symbols.append(
            Symbol(
                name=node.name,
                kind="async_function",
                signature=_format_signature(node),
                lineno=node.lineno,
            )
        )

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        methods: list[str] = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(_format_signature(item))
        self.symbols.append(
            Symbol(
                name=node.name,
                kind="class",
                signature=node.name,
                lineno=node.lineno,
                methods=methods,
            )
        )

    # ---------- ★ 模块级赋值（`TRANSPARENCY3-BACKEND` P7）----------
    # 实测假失败：交付物是标准的 Flask 写法
    #     from flask import Flask
    #     app = Flask(__name__)
    # 却被判「`app.py` 缺少符号: app」—— 因为这里原来只收
    # `FunctionDef`/`AsyncFunctionDef`/`ClassDef`，**模块级变量不算符号**。
    #
    # 后果不只是"少一类符号"：它让**任何"交付物是模块级对象"的任务**（Flask/FastAPI
    # 的 `app`、Django 的配置对象、常量与单例）**必然假失败**，
    # 于是那些能力轴的读数**无效** —— 与 P6 同族：**判词不描述产物**。
    def visit_Assign(self, node: ast.Assign) -> None:
        self._add_assignments(node.targets, node.lineno)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """`x: T = ...`（含仅注解 `x: T`）也算模块级绑定。

        注解形式没有值，但它**确实在运行时把名字绑进模块名字空间**，
        所以对"这个符号存在吗"的判定必须收它。
        """
        self._add_assignments([node.target], node.lineno)

    def _add_assignments(self, targets: list, lineno: int) -> None:
        for t in targets:
            names = []
            if isinstance(t, ast.Name):
                names = [t.id]
            elif isinstance(t, (ast.Tuple, ast.List)):
                names = [e.id for e in t.elts if isinstance(e, ast.Name)]
            for name in names:
                if name and name not in {s.name for s in self.symbols}:
                    self.symbols.append(
                        Symbol(name=name, kind="variable", signature=name,
                               lineno=lineno)
                    )


def _module_name_for(rel_path: str) -> tuple[str, str]:
    """由相对路径推出 (module, package)。"""
    norm = rel_path.replace("\\", "/")
    if norm.endswith(".py"):
        norm = norm[:-3]
    parts = [p for p in norm.split("/") if p]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    module = ".".join(parts)
    package = ".".join(parts[:-1]) if len(parts) > 1 else ""
    return module, package


def _resolve_local(imp: str, module: str, package: str, known: set[str]) -> str | None:
    """把一条 import 解析成本地模块名；不是本地依赖则返回 None。

    支持绝对导入（`import mod_b`）与相对导入（`from . import x` → `.x`）。
    """
    if not imp.startswith("."):
        return imp if imp in known else None

    level = len(imp) - len(imp.lstrip("."))
    rest = imp[level:]

    parts = module.split(".")
    # 回到 level-1 层，再拼上 rest
    base_parts = parts[: len(parts) - level] if level <= len(parts) else []
    base = ".".join(base_parts)

    if rest:
        candidate = f"{base}.{rest}" if base else rest
        if candidate in known:
            return candidate
        # 相对导入指向一个具体模块却没找到 → 交给上层报悬空
        return None

    return base if base in known else None


def raw_module_bindings(rel_path: str, base_dir: str | None = None) -> dict[str, int]:
    """**独立于索引**地扫一遍模块级名字绑定，返回 `{名字: 行号}`。

    ★ 为什么需要它（`TRANSPARENCY3-BACKEND` P7 要求 2）：P7 的假失败之所以致命，
    是因为"**有但我没索引到**"被当成了"**真没有**"。这两者必须能区分 ——
    而这个函数就是那个**独立的第二意见**：它不复用 `_ModuleVisitor`，
    自己扫 `Assign`/`AnnAssign`/`FunctionDef`/`AsyncFunctionDef`/`ClassDef`/`import`，
    所以索引漏收什么，它就能把差异暴露出来。

    宁可多收（列表宽）也不要漏收：它的用途是**给"缺符号"的判定兜底**，
    多收的后果只是"少报一次假失败"。
    """
    import ast as _ast
    import os as _os

    base = base_dir or WORKSPACE_DIR
    path = _os.path.join(base, rel_path.replace("\\", "/"))
    try:
        with open(path, "r", encoding="utf-8") as f:
            tree = _ast.parse(f.read())
    except (OSError, SyntaxError):
        return {}

    out: dict[str, int] = {}

    def add(name: str, lineno: int) -> None:
        if name and name not in out:
            out[name] = lineno

    for node in tree.body:          # 只看模块级
        if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
            add(node.name, node.lineno)
        elif isinstance(node, _ast.Assign):
            for t in node.targets:
                if isinstance(t, _ast.Name):
                    add(t.id, node.lineno)
                elif isinstance(t, (_ast.Tuple, _ast.List)):
                    for e in t.elts:
                        if isinstance(e, _ast.Name):
                            add(e.id, node.lineno)
        elif isinstance(node, _ast.AnnAssign) and isinstance(node.target, _ast.Name):
            add(node.target.id, node.lineno)
        elif isinstance(node, (_ast.Import, _ast.ImportFrom)):
            for a in node.names:
                if a.name != "*":
                    add(a.asname or a.name.split(".")[0], node.lineno)
        elif isinstance(node, _ast.Try):        # 顶层 try 里的绑定（少见但真实）
            for sub in _ast.walk(node):
                if isinstance(sub, _ast.Assign):
                    for t in sub.targets:
                        if isinstance(t, _ast.Name):
                            add(t.id, sub.lineno)
    return out


def analyze_file(abs_path: str, rel_path: str) -> ModuleEntry:
    """解析单个 .py 文件。语法错误不抛异常，降级为 syntax_ok=False。"""
    module, package = _module_name_for(rel_path)

    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            source = f.read()
    except OSError as e:
        return ModuleEntry(
            path=rel_path, module=module, package=package,
            syntax_ok=False, error=f"读取失败: {e}",
        )

    sha1 = hashlib.sha1(source.encode("utf-8")).hexdigest()[:12]
    lines = len(source.splitlines())

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return ModuleEntry(
            path=rel_path, module=module, package=package,
            sha1=sha1, lines=lines, syntax_ok=False,
            error=f"SyntaxError: {e.msg} (line {e.lineno})",
        )

    v = _ModuleVisitor()
    v.visit(tree)
    return ModuleEntry(
        path=rel_path, module=module, package=package,
        symbols=v.symbols, imports=v.imports,
        sha1=sha1, lines=lines, syntax_ok=True,
    )


def build_index(base_dir: str | None = None) -> dict[str, ModuleEntry]:
    """扫描整个 workspace，返回 {相对路径: ModuleEntry}。

    分两趟：先收集所有模块名，再解析 import 是否为本地依赖。
    """
    base = os.path.abspath(base_dir or WORKSPACE_DIR)
    if not os.path.isdir(base):
        return {}

    entries: dict[str, ModuleEntry] = {}
    for root, dirs, names in os.walk(base):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")]
        for name in names:
            if not name.endswith(".py") or name.endswith(".pyc"):
                continue
            abs_path = os.path.join(root, name)
            rel = os.path.relpath(abs_path, base).replace("\\", "/")
            entries[rel] = analyze_file(abs_path, rel)

    known = {e.module for e in entries.values()}
    for entry in entries.values():
        resolved: set[str] = set()
        for imp in entry.imports:
            target = _resolve_local(imp, entry.module, entry.package, known)
            if target and target != entry.module:
                resolved.add(target)
        entry.local_deps = sorted(resolved)

    return entries


# ---------------------------------------------------------------------------
# ★ P11：覆盖率账目 + 新鲜度（`tools/arch.py` 的可信地图）
# ---------------------------------------------------------------------------
#: 跳过原因词表（**机器可判**；每条 skipped 必须落在其中之一）。
SKIP_REASONS: tuple[str, ...] = (
    "non-python",       # 不是 .py（P11 要求逐条列出：不许静默跳过）
    "parse-failed",     # 是 .py 但解析失败（真值：语法错）
    "permission-denied",  # 读不了
    "skip-dir",         # 命中 _SKIP_DIRS / 隐藏目录（整棵目录未走）
    "over-limit",       # 解析成功但超出本次返回上限（**禁止静默截断**）
)


def _sha256_file(path: str) -> str | None:
    """文件内容 sha256（新鲜度判据：内容一变，哈希就变）。"""
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def reverse_index(index: dict[str, ModuleEntry]) -> dict[str, list[str]]:
    """★ P11 要求 4（可选但已做）：反向索引 —— 「谁 import 了 X」。

    没有它就算不出改动的**爆炸半径**（改了 util.py，谁会被连带影响）。
    键是**被依赖的模块名**，值是按路径排序的依赖者。
    """
    out: dict[str, list[str]] = {}
    for entry in index.values():
        for dep in entry.local_deps:
            out.setdefault(dep, [])
            if entry.path not in out[dep]:
                out[dep].append(entry.path)
    for dep in out:
        out[dep].sort()
    return out


def dependents_of(index: dict[str, ModuleEntry], module: str) -> list[str]:
    rev = reverse_index(index)
    return rev.get(module, [])


def build_index_report(base_dir: str | None = None, limit: int | None = None) -> dict:
    """扫描一个根，返回**结构事实 + 覆盖率账目 + 新鲜度**。

    ★ P11 的核心修复：`build_index()` 只回一个 `{相对路径: ModuleEntry}`，
    **看不见被跳过的东西** —— 而非 `.py`、解析失败、超 `limit` 全都不出声，
    于是模型很容易把「我没查」读成「不存在」。
    本函数把这三类**逐条**列进 `coverage.skipped` / `coverage.truncated`。

    返回：
      `root`        扫描的**绝对**根（范围显式，不许读的人猜）
      `generated_at`生成时刻（新鲜度）
      `hashes`      `{相对路径: sha256}`（**每个被解析的文件**的内容哈希）
      `index`       `{相对路径: ModuleEntry}`（**只看解析成功**的 .py）
      `broken`      `{相对路径: ModuleEntry}`（解析失败，`syntax_ok=False`）
      `coverage`    `{scanned, indexed, skipped, truncated, skipped_items,
                      truncated_items, by_reason}`
      `skipped_dir_names` 被整棵跳过的目录名（与 `list_workspace` 同源）

    `limit` 只影响 `truncated_items` 的账目（`index` 始终是全部）——
    **截断必须留痕**，否则就是「静默截断」。
    """
    root = os.path.abspath(base_dir or WORKSPACE_DIR)
    report: dict[str, Any] = {
        "root": root,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "index": {},
        "broken": {},
        "hashes": {},
        "skipped_dir_names": sorted(_SKIP_DIRS),
        "coverage": {
            "scanned": 0,
            "indexed": 0,
            "skipped": 0,
            "skipped_dirs": 0,
            "truncated": 0,
            "skipped_items": [],
            "truncated_items": [],
            "by_reason": {},
        },
    }
    if not os.path.isdir(root):
        report["coverage"]["skipped_items"].append({
            "path": root, "kind": "dir", "reason": "permission-denied",
            "detail": "根目录不存在或不是目录",
        })
        report["coverage"]["skipped"] = 0
        report["coverage"]["skipped_dirs"] = 1
        report["coverage"]["by_reason"] = {"permission-denied": 1}
        report["note"] = f"扫描根不存在: {root}"
        return report

    index: dict[str, ModuleEntry] = report["index"]
    broken: dict[str, ModuleEntry] = report["broken"]
    hashes: dict[str, str] = report["hashes"]
    skipped: list[dict] = report["coverage"]["skipped_items"]
    scanned = 0
    skipped_dirs = 0

    def _skip(rel: str, reason: str, detail: str = "", kind: str = "file") -> None:
        skipped.append({"path": rel, "kind": kind, "reason": reason,
                        "detail": detail})

    def _onerror(err) -> None:  # os.walk 的权限错误也要留痕，不许静默
        _skip(getattr(err, "filename", "") or str(err), "permission-denied",
              str(err), kind="dir")

    for dirpath, dirnames, filenames in os.walk(root, onerror=_onerror):
        kept: list[str] = []
        for d in sorted(dirnames):
            full = os.path.join(dirpath, d)
            rel_dir = os.path.relpath(full, root).replace("\\", "/")
            if d in _SKIP_DIRS or d.startswith("."):
                # 整棵目录未走 —— 如实说"没走"，而不是假装里面没有文件
                skipped_dirs += 1
                _skip(rel_dir + "/", "skip-dir",
                      "内部/缓存/隐藏目录，内容未计入（不是「里面没有东西」）",
                      kind="dir")
            else:
                kept.append(d)
        dirnames[:] = kept

        for name in sorted(filenames):
            abs_path = os.path.join(dirpath, name)
            rel = os.path.relpath(abs_path, root).replace("\\", "/")
            scanned += 1
            if not name.endswith(".py") or name.endswith(".pyc"):
                _skip(rel, "non-python",
                      f"扩展名 {os.path.splitext(name)[1] or '（无）'} 不在本工具支持范围")
                continue

            sha = _sha256_file(abs_path)
            if sha is None:
                _skip(rel, "permission-denied", "文件读不了（权限或占用）")
                continue

            entry = analyze_file(abs_path, rel)
            hashes[rel] = sha
            if not entry.syntax_ok:
                broken[rel] = entry
                _skip(rel, "parse-failed", entry.error or "解析失败")
                continue
            index[rel] = entry

    report["coverage"]["scanned"] = scanned
    report["coverage"]["indexed"] = len(index)
    # 账目自洽：`indexed + skipped == scanned`（目录跳过单独计数，不算文件）
    report["coverage"]["skipped"] = scanned - len(index)
    report["coverage"]["skipped_dirs"] = skipped_dirs

    truncated_items: list[dict] = report["coverage"]["truncated_items"]
    if limit is not None and limit >= 0 and len(index) > limit:
        for rel in sorted(index)[limit:]:
            truncated_items.append({
                "path": rel,
                "kind": "file",
                "reason": "over-limit",
                "detail": f"已解析但超出本次返回上限 limit={limit}"
                          f"（共 {len(index)} 个）",
            })

    by_reason: dict[str, int] = {}
    for item in skipped:
        by_reason[item["reason"]] = by_reason.get(item["reason"], 0) + 1
    for item in truncated_items:
        by_reason[item["reason"]] = by_reason.get(item["reason"], 0) + 1
    report["coverage"]["by_reason"] = by_reason
    report["coverage"]["truncated"] = len(truncated_items)

    # 第二趟：把 import 解析成本地依赖（与 `build_index` 同一套判据）——
    # 反向索引（P11 要求 4）与 `depends_on` 都建立在这一步之上。
    known = {e.module for e in index.values()}
    for entry in index.values():
        resolved: set[str] = set()
        for imp in entry.imports:
            target = _resolve_local(imp, entry.module, entry.package, known)
            if target and target != entry.module:
                resolved.add(target)
        entry.local_deps = sorted(resolved)

    report["reverse_index"] = reverse_index(index)
    report["note"] = (
        "仅含程序解析出的结构事实；**覆盖之外的东西逐条列在 coverage 里**"
        "（不许把「没查/查不了」读成「不存在」）"
    )
    return report


def freshness_of(report: dict, paths: list[str] | None = None) -> dict:
    """★ P11 要求 2：`{generated_at, root, files: {path: sha256}}`。

    为什么必须有：代码一改，旧地图**看起来照样有效** ——
    哈希是唯一能让「这张地图对应哪一版代码」可逐字核对的判据。
    传 `paths` 时只回报这些路径（工具截断后的视图用）。
    """
    hashes = report.get("hashes") or {}
    if paths is not None:
        hashes = {p: hashes.get(p, "") for p in paths}
    return {
        "generated_at": report.get("generated_at", ""),
        "root": report.get("root", ""),
        "hash_algorithm": "sha256",
        "files": dict(hashes),
    }


def find_symbol(index: dict[str, ModuleEntry], name: str) -> list[dict[str, Any]]:
    """按符号名反查定义位置。"""
    hits: list[dict[str, Any]] = []
    for entry in index.values():
        for sym in entry.symbols:
            if sym.name == name:
                hits.append({
                    "path": entry.path,
                    "module": entry.module,
                    "signature": sym.signature,
                    "kind": sym.kind,
                    "lineno": sym.lineno,
                })
    return hits


def _local_packages(index: dict[str, ModuleEntry]) -> set[str]:
    """本地包名集合。

    从目录结构推导（任何包含 .py 的目录都视为可导入的包），
    不依赖 `package` 字段——顶层包的 package 是空串，靠字段会漏掉。
    同时覆盖 namespace package（无 `__init__.py` 的目录）。
    """
    pkgs: set[str] = set()
    for path in index:
        norm = path.replace("\\", "/")
        parts = [p for p in norm.split("/") if p]
        # 去掉文件名，剩下的目录链每一层都是包
        for i in range(1, len(parts)):
            pkgs.add(".".join(parts[:i]))
    return pkgs


def dangling_imports(index: dict[str, ModuleEntry]) -> list[dict[str, Any]]:
    """本地模块之间的悬空依赖。

    刻意保守，只报高置信度的情况，避免误报（误报会像 L2/L3 那样白白耗尽重试）：

      1. 相对导入（明确指向本地包）无法解析
      2. 绝对导入的顶层是本地包，但成员不存在

    裸的顶层名字（如 `import numpy`）无法区分第三方库与本地模块，一律不报。
    """
    known = {e.module for e in index.values()}
    packages = _local_packages(index)
    out: list[dict[str, Any]] = []

    for entry in index.values():
        for imp in entry.imports:
            if imp.startswith("."):
                if _resolve_local(imp, entry.module, entry.package, known) is None:
                    out.append({
                        "from": entry.path,
                        "import": imp,
                        "kind": "relative-import-unresolved",
                    })
                continue
            head = imp.split(".")[0]
            if head in packages and imp not in known:
                out.append({
                    "from": entry.path,
                    "import": imp,
                    "kind": "package-member-missing",
                })
    return out


def summarize(index: dict[str, ModuleEntry]) -> dict[str, Any]:
    """给模型/日志看的紧凑结构视图。"""
    return {
        "modules": [
            e.to_dict()
            for e in sorted(index.values(), key=lambda x: x.path)
        ],
        "totals": {
            "files": len(index),
            "symbols": sum(len(e.symbols) for e in index.values()),
            "lines": sum(e.lines for e in index.values()),
            "broken": sum(1 for e in index.values() if not e.syntax_ok),
        },
    }
