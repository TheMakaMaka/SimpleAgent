"""文档审查的机械检查层。

为何单独成模块（而不是写在测试里）
----------------------------------
`tests/unit/test_doc_review.py` 与模型可调用的审查工具**必须共用同一套判据**。
若各写一份，两处逻辑必然分叉——那正是本项目一直在治理的漂移。

所以：检查逻辑住在这里，测试与工具都调它。

分层定位
--------
  机械检查（本模块）  程序可判定 → **可作门禁**
    · 代码块是否合法 Python
    · `from X import Y` 的 Y 是否真实存在
    · `模块.符号` 引用是否存在
    · `/profile` 字段名是否真实返回
    · 文档间 § 交叉引用是否有效

  语义审查（模型）    "这段解释是否误导" → **只能建议，不能裁决**
    与 `CYCLE.md` §8 的「门禁 vs 建议」同一条纪律。

返回结构：`{"passed": bool, "checks": [...], "failures": [...]}`，
每条 check 带 `evidence`（行号或具体符号），便于人工复核。
"""

import ast
import os
import re
from dataclasses import dataclass, field

# 伪代码块标记：含这些字样的块不参与"必须能 ast.parse"的判定
FRAGMENT_MARKERS = ("...", "# 省略", "def foo", "-> ")

_SECTION_RE = re.compile(r"^#{2,4}\s+(\d+(?:\.\d+)*(?:[.\d]*\d)?)\s*[.、\s]",
                         re.MULTILINE)


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "check": self.name,
            "ok": self.ok,
            "detail": self.detail,
            "evidence": self.evidence[:10],
        }


@dataclass
class ReviewResult:
    subject: str
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def failures(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.ok]

    @property
    def passed(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict:
        return {
            "subject": self.subject,
            "passed": self.passed,
            "summary": {
                "checks": len(self.checks),
                "failed": len(self.failures),
            },
            "checks": [c.to_dict() for c in self.checks],
            "failures": [
                {"check": c.name, "detail": c.detail, "evidence": c.evidence[:10]}
                for c in self.failures
            ],
        }


# ============================================================
# 项目符号表（供引用校验）
# ============================================================
def project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def importable_modules(root: str | None = None) -> dict[str, set[str]]:
    """扫描项目，得到 {模块全名: 顶层符号集合}。"""
    root = root or project_root()
    out: dict[str, set[str]] = {}
    for pkg in ("core", "tools", "storage", "web"):
        base = os.path.join(root, pkg)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            if not name.endswith(".py"):
                continue
            mod = pkg if name == "__init__.py" else f"{pkg}.{name[:-3]}"
            try:
                with open(os.path.join(base, name), "r", encoding="utf-8") as f:
                    tree = ast.parse(f.read())
            except (OSError, SyntaxError):
                continue
            syms: set[str] = set()
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    syms.add(node.name)
                elif isinstance(node, ast.Assign):
                    for t in node.targets:
                        if isinstance(t, ast.Name):
                            syms.add(t.id)
                elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                    syms.add(node.target.id)
                elif isinstance(node, ast.ImportFrom):
                    for a in node.names:
                        syms.add(a.asname or a.name)
            out[mod] = syms
    return out


# ============================================================
# 单项检查
# ============================================================
def python_blocks(text: str) -> list[tuple[int, str]]:
    out = []
    for m in re.finditer(r"```python\n(.*?)```", text, re.DOTALL):
        start = text[: m.start()].count("\n") + 1
        out.append((start, m.group(1)))
    return out


def check_code_blocks(text: str) -> CheckResult:
    """文档里的 python 代码块必须是合法 Python。"""
    blocks = python_blocks(text)
    bad: list[str] = []
    for start, body in blocks:
        try:
            ast.parse(body)
        except SyntaxError as e:
            if any(mk in body for mk in FRAGMENT_MARKERS):
                continue          # 明显示伪代码，跳过
            bad.append(f"L{start}: {e.msg}")
    return CheckResult(
        name="python 代码块语法合法",
        ok=not bad,
        detail=f"{len(blocks)} 个块",
        evidence=bad,
    )


def check_imports(text: str, mods: dict[str, set[str]]) -> CheckResult:
    """`from 本项目模块 import Y` 里的 Y 必须存在。"""
    bad: list[str] = []
    for m in re.finditer(r"^from\s+([\w.]+)\s+import\s+(.+)$", text, re.MULTILINE):
        mod, names = m.group(1), m.group(2)
        if mod not in mods:
            continue
        for raw in names.split(","):
            sym = raw.strip().split(" as ")[0].strip()
            if not sym or sym == "*":
                continue
            if sym not in mods[mod]:
                bad.append(f"{mod}.{sym}")
    return CheckResult(
        name="import 指向真实符号",
        ok=not bad,
        evidence=sorted(set(bad)),
    )


def check_module_refs(text: str, mods: dict[str, set[str]]) -> CheckResult:
    """`模块.符号` 引用必须存在。

    三类误报（都已在判据里排除）：
      `storage/session.py`  文件路径
      `core.task`           模块引用
      `tools.registry`      同上
    """
    bad: list[str] = []
    pat = re.compile(r"`((?:core|tools|storage|web)(?:\.[\w]+)+)`")
    for m in pat.finditer(text):
        ref = m.group(1)
        if ref.endswith(".py") or ref in mods:
            continue
        parts = ref.split(".")
        sym, mod_name = parts[-1], ".".join(parts[:-1])
        if sym in mods:
            continue
        if mod_name not in mods:
            continue
        if sym not in mods[mod_name]:
            bad.append(f"{mod_name}.{sym}")
    return CheckResult(
        name="「模块.符号」引用存在",
        ok=not bad,
        evidence=sorted(set(bad)),
    )


#: 版本戳不是"引用"，是**同步标记**：它的数字必须等于 CHANGELOG 最新章节，
#: 那一件事由 `test_doc_consistency.py` 负责。把它当引用会误判 ——
#: 实测踩过：MODULES 恰好有 `## 23.` 时 `同步至 CHANGELOG §23` 一路通过，
#: 等版本戳升到 §24 而 MODULES 仍只到 §23 时，就报了个假失败。
_STAMP_RE = re.compile(r"同步至\s*CHANGELOG\s*§\d+")


def check_section_refs(texts: dict[str, str],
                       extra_refs: dict[str, str] | None = None) -> CheckResult:
    """`§X.Y` 交叉引用必须在**全部文档的标题**里有对应（引用可跨文档）。

    `extra_refs`：只参与"章节号池"、不参与自身内容检查的文档。
    为什么需要它：文档里合法地写着"见 `docs/CHANGELOG.md` §7"这类引用，
    而 CHANGELOG 不适合进 `texts`（它有自己的结构约定）。
    不把它的章节号放进池子，就等于**这类引用从来没被校验过** ——
    以前它们只是"恰好"撞上了别的文档的同号章节。
    """
    heads: set[str] = set()
    for t in list(texts.values()) + list((extra_refs or {}).values()):
        heads |= set(_SECTION_RE.findall(t))

    bad: list[str] = []
    for name, t in texts.items():
        for line in t.splitlines():
            if "§" not in line:
                continue
            # 版本戳不参与（见 _STAMP_RE 的说明）
            line = _STAMP_RE.sub("", line)
            for ref in re.findall(r"§(\d+(?:\.\d+)*(?:[.\d]*\d)?)", line):
                if ref not in heads:
                    bad.append(f"{name}: §{ref}")
    return CheckResult(
        name="§ 交叉引用有效",
        ok=not bad,
        evidence=sorted(set(bad)),
    )


def check_profile_fields(texts: dict[str, str], top_keys: set[str]) -> CheckResult:
    """文档里明确标注为 `/profile` 字段的名字必须真实返回。"""
    bad: list[str] = []
    for name, t in texts.items():
        for m in re.finditer(r"`/profile`[^\n]*?`(\w+)`\s*字段", t):
            if m.group(1) not in top_keys:
                bad.append(f"{name}: {m.group(1)}")
    return CheckResult(
        name="/profile 字段名真实存在",
        ok=not bad,
        detail=f"实际顶层键 {sorted(top_keys)}",
        evidence=sorted(set(bad)),
    )


# ============================================================
# 组合入口
# ============================================================
def review_text(subject: str, text: str, mods: dict[str, set[str]]) -> ReviewResult:
    """审查单份文档的**可独立判定**的部分。"""
    return ReviewResult(subject=subject, checks=[
        check_code_blocks(text),
        check_imports(text, mods),
        check_module_refs(text, mods),
    ])


def review_collection(texts: dict[str, str],
                      top_keys: set[str] | None = None) -> ReviewResult:
    """审查一组文档（含跨文档检查：§ 引用、/profile 字段）。"""
    mods = importable_modules()
    checks: list[CheckResult] = []
    for name, t in sorted(texts.items()):
        checks.append(CheckResult(
            name=f"{name}: 代码块语法", ok=check_code_blocks(t).ok,
            evidence=check_code_blocks(t).evidence))
        imp = check_imports(t, mods)
        checks.append(CheckResult(name=f"{name}: import 引用", ok=imp.ok,
                                  evidence=imp.evidence))
        ref = check_module_refs(t, mods)
        checks.append(CheckResult(name=f"{name}: 模块.符号", ok=ref.ok,
                                  evidence=ref.evidence))
    checks.append(check_section_refs(texts))
    if top_keys is not None:
        checks.append(check_profile_fields(texts, top_keys))
    return ReviewResult(subject=", ".join(sorted(texts)), checks=checks)
