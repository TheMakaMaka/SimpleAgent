"""文件清单（manifest）：声明 vs 实际的交付契约。

解决的问题
----------
此前验证阶段的文件清单只能从 `memory.artifacts` 里散落的 `write_file` 产物拼出来，
**文件压根没写就不在清单里**，验证自然不会去查它存在不存在。L8 实测中：
编排器声称产出了 3 个文件，实际 `contacts.py` 从未写出、`cli.py` 的 `run()`
缺了 `args` 参数，而系统直到 `ModuleNotFoundError` 才发现——那已经是很晚的间接症状。

设计约束（重要）
----------------
**只报结构性事实，不报语义判断。**

声明来自模型的计划，是自由文本或自由表单。如果拿模型写的角色描述去和代码做语义
比对，必然产生大量误报，会像 L2/L3 那样白白耗尽重试次数。因此 violation 只包含
程序能确证的事实：

  error   : declared-missing     声明的文件不存在
  error   : symbol-missing       声明的文件存在，但缺了声明的符号
  warning : dangling-import      本地模块之间 import 了不存在的模块
  warning : unexpected-file      出现了声明之外的 .py 文件

签名只作为**信息**列出，不参与判定——因为计划里通常只写符号名，不写签名，
硬比对会误报。
"""

from dataclasses import dataclass, field

from .symbol_index import ModuleEntry, build_index, dangling_imports

BLOCKING_SEVERITIES = {"error"}


def normalize_declared_path(path: str) -> str:
    """把模型写的路径归一化到「相对 workspace」的形式。

    模型经常写 `workspace/foo.py`（因为工具说明里提到 workspace），
    而索引里的键是 `foo.py`。不做归一化会把通过验证的产出误判为「文件不存在」，
    这类误报的代价是白烧整个重试预算（实测踩过）。
    """
    p = (path or "").strip().replace("\\", "/")
    p = p.lstrip("/")
    while p.startswith("./"):
        p = p[2:]
    if p.startswith("workspace/"):
        p = p[len("workspace/"):]
    return p


@dataclass
class DeclaredFile:
    """计划中声明的交付物。"""

    path: str
    role: str = ""
    symbols: list[str] = field(default_factory=list)

    @classmethod
    def from_raw(cls, raw) -> "DeclaredFile | None":
        if isinstance(raw, str):
            raw = {"path": raw}
        if not isinstance(raw, dict):
            return None
        path = (raw.get("path") or raw.get("filename") or raw.get("file") or "").strip()
        if not path:
            return None
        symbols = raw.get("symbols") or raw.get("exports") or []
        if isinstance(symbols, str):
            symbols = [s.strip() for s in symbols.replace(",", " ").split() if s.strip()]
        return cls(
            path=normalize_declared_path(path),
            role=(raw.get("role") or raw.get("purpose") or "").strip(),
            symbols=[str(s).strip() for s in symbols if str(s).strip()],
        )


@dataclass
class Manifest:
    declared: list[DeclaredFile] = field(default_factory=list)
    actual: list[dict] = field(default_factory=list)
    violations: list[dict] = field(default_factory=list)
    checked: bool = False
    note: str = ""

    @property
    def blocking(self) -> list[dict]:
        return [v for v in self.violations if v.get("severity") in BLOCKING_SEVERITIES]

    @property
    def passed(self) -> bool:
        return not self.blocking

    def to_dict(self) -> dict:
        return {
            "checked": self.checked,
            "passed": self.passed,
            "declared": [
                {"path": d.path, "role": d.role, "symbols": d.symbols} for d in self.declared
            ],
            "actual": self.actual,
            "violations": self.violations,
            "note": self.note,
        }

    def to_prompt(self, limit: int = 12) -> str:
        """给模型看的紧凑陈述，用于把 violation 定向喂回。"""
        if not self.checked:
            return self.note or "（未做文件清单校验）"
        lines = ["【文件清单校验】"]
        if self.passed:
            lines.append(f"  通过：{len(self.actual)} 个文件，未发现交付缺口")
            return "\n".join(lines)
        for v in self.violations[:limit]:
            sev = v.get("severity", "?").upper()
            loc = v.get("path") or v.get("from") or ""
            lines.append(f"  [{sev}] {v.get('kind')} {loc}: {v.get('message', '')}")
            if v.get("fix"):
                lines.append(f"        建议: {v['fix']}")
        if len(self.violations) > limit:
            lines.append(f"  ...还有 {len(self.violations) - limit} 条")
        return "\n".join(lines)


def parse_declared(raw_files) -> list[DeclaredFile]:
    """把主循环输出的 files 字段解析成声明列表（容忍多种写法）。"""
    if not raw_files:
        return []
    if isinstance(raw_files, dict):
        raw_files = [{"path": k, "role": v if isinstance(v, str) else ""} for k, v in raw_files.items()]
    if not isinstance(raw_files, list):
        return []

    out: list[DeclaredFile] = []
    seen: set[str] = set()
    for raw in raw_files:
        d = DeclaredFile.from_raw(raw)
        if d and d.path not in seen:
            seen.add(d.path)
            out.append(d)
    return out


def check_manifest(
    declared: list[DeclaredFile],
    index: dict[str, ModuleEntry] | None = None,
    strict_extra_files: bool = False,
) -> Manifest:
    """对照声明与实际，产出 manifest。

    declared 为空时不做判定（`checked=False`），避免把「模型没声明」误判成失败。
    """
    index = index if index is not None else build_index()

    if not declared:
        return Manifest(
            actual=[e.to_dict() for e in index.values()],
            checked=False,
            note="本轮没有声明文件清单，跳过硬校验（仅记录实际结构）",
        )

    manifest = Manifest(declared=declared, checked=True)
    manifest.actual = [e.to_dict() for e in index.values()]
    declared_paths = {d.path for d in declared}

    for d in declared:
        # 先按归一化路径查；再兜底尝试 workspace/ 前缀，兼容索引中带前缀的情况
        entry = index.get(d.path) or index.get(f"workspace/{d.path}")

        # ---- 声明的文件是否存在 ----
        if entry is None:
            manifest.violations.append({
                "severity": "error",
                "kind": "declared-missing",
                "path": d.path,
                "role": d.role,
                "message": f"计划要产出 {d.path}，但该文件不存在",
                "fix": f"创建 {d.path}"
                       + (f"，并实现: {', '.join(d.symbols)}" if d.symbols else ""),
            })
            continue

        if not entry.syntax_ok:
            manifest.violations.append({
                "severity": "error",
                "kind": "declared-broken",
                "path": d.path,
                "message": f"{d.path} 存在但无法解析: {entry.error}",
                "fix": "先修正语法错误",
            })
            continue

        # ---- 声明的符号是否存在 ----
        if d.symbols:
            present = entry.symbol_names()
            # 同时接受「模块级符号」与「类方法名」（run 可能是方法）
            method_names = {
                sig.split("(")[0]
                for sym in entry.symbols
                for sig in (sym.methods or [])
            }
            available = present | method_names
            missing = [s for s in d.symbols if s not in available]
            if missing:
                manifest.violations.append({
                    "severity": "error",
                    "kind": "symbol-missing",
                    "path": d.path,
                    "missing": missing,
                    "available": sorted(available),
                    "message": f"{d.path} 缺少声明的符号: {', '.join(missing)}",
                    "fix": f"在 {d.path} 中实现: {', '.join(missing)}",
                })

    # ---- 本地模块之间的悬空依赖 ----
    for d in dangling_imports(index):
        manifest.violations.append({
            "severity": "warning",
            "kind": "dangling-import",
            "from": d["from"],
            "import": d["import"],
            "message": f"{d['from']} 导入了本地不存在的模块 {d['import']}",
            "fix": "确认模块名拼写，或补上缺少的模块",
        })

    # ---- 导入了「声明过但确实不存在」的模块 ----
    # 这是高置信度情况：模型自己声明了要产出该模块，代码也 import 了它，
    # 但它不存在——正好是 L8 里 cli.py 的症状。裸的第三方库名不会命中这里。
    known_modules = {e.module for e in index.values()}
    declared_modules = {
        d.path[:-3].replace("/", ".") if d.path.endswith(".py") else d.path
        for d in declared
    }
    for entry in index.values():
        for imp in entry.imports:
            head = imp.split(".")[0]
            if imp in known_modules or head in known_modules:
                continue
            if imp in declared_modules or head in declared_modules:
                manifest.violations.append({
                    "severity": "warning",
                    "kind": "imports-missing-declared-module",
                    "from": entry.path,
                    "import": imp,
                    "message": (
                        f"{entry.path} 导入了 {imp}，但该模块不存在"
                        f"（它在本次计划中被声明为要产出）"
                    ),
                    "fix": f"创建 {imp} 或修正 import 目标",
                })

    # ---- 声明之外的文件（仅提示，默认不判定）----
    if strict_extra_files:
        for path in sorted(index):
            if path not in declared_paths:
                manifest.violations.append({
                    "severity": "warning",
                    "kind": "unexpected-file",
                    "path": path,
                    "message": f"{path} 不在声明清单内",
                })

    return manifest


def architecture_view(index: dict[str, ModuleEntry] | None = None) -> dict:
    """只读的全局结构视图。

    这是后续「架构视图工具」的数据来源：模型可以按需查询，而不必把所有代码
    读进上下文。当前以纯结构事实为主，设计注记（职责/扩展点）留待后续阶段。
    """
    index = index if index is not None else build_index()

    modules = []
    for e in sorted(index.values(), key=lambda x: x.path):
        modules.append({
            "path": e.path,
            "module": e.module,
            "role_hint": "",          # 设计注记留空，由后续阶段填充
            "exports": [
                {"name": s.name, "kind": s.kind, "signature": s.signature}
                for s in e.symbols
            ],
            "depends_on": e.local_deps,
            "lines": e.lines,
            "sha1": e.sha1,
        })

    return {
        "modules": modules,
        "totals": {
            "files": len(index),
            "symbols": sum(len(e.symbols) for e in index.values()),
            "lines": sum(e.lines for e in index.values()),
        },
        "note": "仅含程序解析出的结构事实；设计意图需另行注入。",
    }
