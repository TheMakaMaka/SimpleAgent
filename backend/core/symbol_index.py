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
