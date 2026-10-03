"""代码质量审查（确定性、模型无关）。

分层定位（避免和门禁混淆）：
  - `core/pipeline.py` 的 CheckPipeline 是**门禁**：程序调度，模型绕不过，
    决定 cycle 能否通过。
  - `tools/quality.py` 是**建议**：模型可主动调用，检查结果作为上下文回灌，
    帮助它在写的过程中自查。它不参与成败判定。

所有分析都是确定性的：AST 静态检查 + 已有的 check_syntax / run_lint。
不引入任何需要模型参与判断的步骤，否则就又多了一个幻觉源。
"""

import ast
import json

from .registry import register

# 单函数行数阈值；超过即提示拆分
_LONG_FUNCTION_LINES = 50
_MAX_NESTING = 4
_MAX_LINE_LEN = 120


class _QualityVisitor(ast.NodeVisitor):
    """用有限状态遍历 AST，收集常见质量问题。"""

    def __init__(self) -> None:
        self.issues: list[dict] = []
        self.imported: dict[str, int] = {}      # 顶层 import 名 -> 行号
        self.used: set[str] = set()
        self.functions: list[tuple[str, int, int]] = []   # (name, lineno, end_lineno)

    # ---------- 工具 ----------
    def _add(self, severity: str, code: str, line: int, message: str, fix: str = "") -> None:
        item = {"severity": severity, "code": code, "line": line, "message": message}
        if fix:
            item["fix"] = fix
        self.issues.append(item)

    # ---------- 导入 ----------
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.asname or alias.name.split(".")[0]
            self.imported[name] = node.lineno
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name == "*":
                self._add(
                    "low", "star-import", node.lineno,
                    "使用了 from ... import *，会污染命名空间并让依赖不明确",
                    "改为显式导入需要的名字",
                )
                continue
            self.imported[alias.asname or alias.name] = node.lineno
        self.generic_visit(node)

    # ---------- 名字使用 ----------
    def visit_Name(self, node: ast.Name) -> None:
        self.used.add(node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # 记录根名字，便于判断 import 是否被使用
        cur = node
        while isinstance(cur, ast.Attribute):
            cur = cur.value
        if isinstance(cur, ast.Name):
            self.used.add(cur.id)
        self.generic_visit(node)

    # ---------- 函数 ----------
    def visit_FunctionDef(self, node) -> None:
        self._check_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node) -> None:
        self._check_function(node)
        self.generic_visit(node)

    def _check_function(self, node) -> None:
        name = getattr(node, "name", "?")
        start = getattr(node, "lineno", 0)
        end = getattr(node, "end_lineno", start) or start
        self.functions.append((name, start, end))

        length = end - start + 1
        if length > _LONG_FUNCTION_LINES:
            self._add(
                "medium", "long-function", start,
                f"函数 {name} 长约 {length} 行，超过 {_LONG_FUNCTION_LINES} 行的建议上限",
                "拆分为职责单一的多个小函数",
            )

        # 可变默认参数：运行时会被共享，是经典陷阱
        for default in list(node.args.defaults) + list(node.args.kw_defaults):
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                self._add(
                    "high", "mutable-default", start,
                    f"函数 {name} 使用了可变默认参数（会在多次调用间共享）",
                    "默认值改为 None，在函数体内再创建容器",
                )

        # 缺少 return 注解（仅提示，不算错）
        if name != "__init__" and node.returns is None:
            self._add(
                "low", "missing-return-annotation", start,
                f"函数 {name} 没有返回类型注解",
                "补充 -> 返回类型，便于静态检查",
            )

    # ---------- 异常 ----------
    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is None:
            self._add(
                "high", "bare-except", node.lineno,
                "使用了裸 except，会吞掉所有异常（包括 KeyboardInterrupt）",
                "捕获具体异常类型，例如 except ValueError",
            )
        elif isinstance(node.type, ast.Name) and node.type.id == "Exception":
            self._add(
                "medium", "broad-except", node.lineno,
                "捕获 Exception 范围过宽，可能掩盖真实缺陷",
                "收窄到具体的异常类型",
            )
        self.generic_visit(node)

    # ---------- 嵌套深度 ----------
    # 由 _compute_nesting 独立递归计算，这里不需要 visit 钩子


def _compute_nesting(node: ast.AST, depth: int = 0) -> int:
    """独立递归计算最大嵌套深度（只统计控制流容器）。"""
    containers = (ast.If, ast.For, ast.While, ast.With, ast.Try)
    best = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, containers):
            best = max(best, _compute_nesting(child, depth + 1))
        else:
            best = max(best, _compute_nesting(child, depth))
    return best


# ============================================================
# 面向模型的工具
# ============================================================
@register(
    name="review_code",
    description=(
        "对一段 Python 代码做质量审查，返回结构化问题清单。"
        "包含：语法检查、lint（ruff 可用时）、静态质量问题"
        "（裸 except、可变默认参数、未使用导入、函数过长、嵌套过深、缺返回注解）。"
        "写完代码后用这个工具自查，按 severity 从高到低修复。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "要审查的完整 Python 代码"}
        },
        "required": ["code"],
        "additionalProperties": False,
    },
    profiles=("coding",),
)
async def review_code(code: str) -> str:
    if not code or not code.strip():
        return json.dumps(
            {"ok": False, "issues": [{"severity": "high", "code": "empty", "message": "代码为空"}]},
            ensure_ascii=False,
        )

    issues: list[dict] = []
    metrics: dict = {}

    # ---------- 语法 ----------
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return json.dumps(
            {
                "ok": False,
                "syntax_ok": False,
                "issues": [{
                    "severity": "high",
                    "code": "syntax-error",
                    "line": e.lineno,
                    "message": f"{e.msg}",
                    "fix": "先修正语法错误，其余检查在语法通过后才有意义",
                }],
                "metrics": {},
            },
            ensure_ascii=False,
        )

    # ---------- lint（复用已有工具，缺失时明确标注未执行） ----------
    lint_status = "skipped"
    try:
        from .code_checks import run_lint

        lint_raw = json.loads(await run_lint(code))
        if lint_raw.get("skipped"):
            lint_status = "skipped"
        else:
            lint_status = "passed" if lint_raw.get("ok") else "failed"
            for it in lint_raw.get("issues") or []:
                issues.append({
                    "severity": "medium",
                    "code": f"lint:{it.get('code') or '?'}",
                    "line": it.get("line"),
                    "message": it.get("message") or "",
                    "fix": "按 lint 提示修正",
                })
    except Exception:
        lint_status = "skipped"

    # ---------- 静态质量问题 ----------
    visitor = _QualityVisitor()
    visitor.visit(tree)

    # 未使用的导入
    for name, lineno in visitor.imported.items():
        if name not in visitor.used:
            issues.append({
                "severity": "low",
                "code": "unused-import",
                "line": lineno,
                "message": f"导入的 {name} 未被使用",
                "fix": f"删除 `import {name}`",
            })

    # 嵌套过深
    depth = _compute_nesting(tree)
    if depth > _MAX_NESTING:
        issues.append({
            "severity": "medium",
            "code": "deep-nesting",
            "message": f"最大嵌套深度 {depth}，超过建议上限 {_MAX_NESTING}",
            "fix": "用提前 return 或抽取函数来降低嵌套",
        })

    issues.extend(visitor.issues)

    # 过长的行
    for i, line in enumerate(code.splitlines(), 1):
        if len(line) > _MAX_LINE_LEN:
            issues.append({
                "severity": "low",
                "code": "long-line",
                "line": i,
                "message": f"第 {i} 行长度 {len(line)} 超过 {_MAX_LINE_LEN}",
                "fix": "拆行以提高可读性",
            })
            break

    # ---------- 指标 ----------
    total_lines = len(code.splitlines())
    metrics = {
        "lines": total_lines,
        "code_lines": sum(
            1 for ln in code.splitlines() if ln.strip() and not ln.strip().startswith("#")
        ),
        "functions": len(visitor.functions),
        "max_nesting": depth,
        "longest_function": max(
            ((n, e - s + 1) for n, s, e in visitor.functions),
            key=lambda x: x[1], default=("", 0),
        )[0],
    }

    order = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda x: (order.get(x.get("severity"), 3), x.get("line") or 0))

    counts = {s: sum(1 for i in issues if i.get("severity") == s) for s in ("high", "medium", "low")}

    return json.dumps(
        {
            "ok": counts["high"] == 0,
            "syntax_ok": True,
            "lint": lint_status,
            "issue_counts": counts,
            "issues": issues[:40],
            "metrics": metrics,
            "note": (
                "这是建议性审查，不参与 cycle 成败判定。"
                "请优先修复 severity=high 的问题。"
                + ("（lint 未执行：ruff 未安装）" if lint_status == "skipped" else "")
            ),
        },
        ensure_ascii=False,
    )
