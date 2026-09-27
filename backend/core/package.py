"""封装候选分析：从历史成功运行里找出「可封装、可复用」的形态。

这是「封装优化角色」的离线分析部分。

为什么是离线分析而不是运行时角色
--------------------------------
运行时角色（编排器/执行器/未来的审查员）作用于**活着的 cycle**；
本模块作用于**已完成的历史**，产出可复用资产。因此它天然安全：
只读 `storage_data`，只写候选区，**不参与任何执行决策**。

关键前提：单次运行无法识别参数
------------------------------
"哪些部分是变量"只有对比**多次同类运行**才知道。
单次运行看起来一切固定——那正是过拟合的来源。

所以流程是：
  1. 用形态指纹分组（core/shape.py），找出"同一类任务"
  2. 组内 diff，找出**变化点** → 那就是参数
  3. 变化点**自动命名不出语义**，只能给 p1/p2…，由人重命名
  4. 打分 → 达到阈值的进入候选区（**不是直接安装**）

步骤 3 的诚实说明：自动命名变量在一般情形下不可解（需要语义理解）。
本模块不假装能猜对，只给出位置与示例值，命名交给人或后续的角色。
"""

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Iterable

from .compress import Snapshot
from .shape import Shape, _TOKEN, group_by_shape, shape_of
from .skills import Skill, SkillFile, SkillParameter

# 候选区（与已安装技能分开，落实"先建副本、不影响主库"）
CANDIDATE_ROOT = "storage_data/skill_candidates"

# 打分阈值：低于此值不建议封装。
# 取 0.7 而非 0.6 是有意的——只有 2 次成功时证据太弱，
# 区分不出"固定形态"与"碰巧相似"，那个分数段不应自动过关。
PACKAGE_SCORE_THRESHOLD = 0.7


@dataclass
class ParameterGuess:
    """一个自动识别出的变量位置。"""

    placeholder: str          # 自动名 p1 / p2 …（无语义，待人工重命名）
    kind: str                 # path | symbol | verify
    examples: list[str] = field(default_factory=list)
    suggested_name: str = ""  # 基于 kind 的弱建议（filename / func …），可能不准

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PackageCandidate:
    """一个「看起来可以封装」的形态。**只是候选，未安装。**"""

    candidate_id: str
    shape_desc: str
    cycles: list[str] = field(default_factory=list)
    goal_template: str = ""
    verify_template: str = ""
    files: list[dict] = field(default_factory=list)      # {path, symbols}
    parameters: list[ParameterGuess] = field(default_factory=list)
    score: float = 0.0
    score_reasons: list[str] = field(default_factory=list)
    example_code: dict[str, str] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    status: str = "candidate"     # candidate | installed | rejected

    def to_dict(self) -> dict:
        d = asdict(self)
        d["parameters"] = [p.to_dict() for p in self.parameters]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "PackageCandidate":
        return cls(
            candidate_id=d["candidate_id"],
            shape_desc=d.get("shape_desc", ""),
            cycles=d.get("cycles") or [],
            goal_template=d.get("goal_template", ""),
            verify_template=d.get("verify_template", ""),
            files=d.get("files") or [],
            parameters=[ParameterGuess(**p) for p in (d.get("parameters") or [])],
            score=float(d.get("score", 0.0)),
            score_reasons=d.get("score_reasons") or [],
            example_code=d.get("example_code") or {},
            created_at=d.get("created_at", ""),
            status=d.get("status", "candidate"),
        )

    def to_skill(self, *, skill_id: str, name: str = "",
                 renamed: dict[str, str] | None = None) -> Skill:
        """转成可安装的技能。

        `renamed` 把自动名（p1）映射成有语义的名字（filename）——
        这是审核环节的核心动作，也是"人/审核角色"必须介入的地方。
        """
        mapping = dict(renamed or {})

        def apply(text: str) -> str:
            out = text
            for auto, real in mapping.items():
                out = out.replace("{" + auto + "}", "{" + real + "}")
            return out

        params = []
        for p in self.parameters:
            real = mapping.get(p.placeholder, p.placeholder)
            params.append(SkillParameter(
                name=real,
                description=f"自动识别自 {p.kind}（原占位符 {p.placeholder}）",
                example=p.examples[0] if p.examples else "",
            ))

        files = [
            SkillFile(path=apply(f["path"]),
                      symbols=[apply(s) for s in (f.get("symbols") or [])])
            for f in self.files
        ]

        # 示例代码的键也按同样规则改写
        examples = {}
        for path, code in (self.example_code or {}).items():
            examples[apply(path)] = code

        return Skill(
            id=skill_id,
            name=name or skill_id,
            goal_template=apply(self.goal_template),
            files=files,
            verify_command=apply(self.verify_template),
            parameters=params,
            example_code=examples,
            verify_reason=f"从 {len(self.cycles)} 次成功运行归纳",
            source_cycle=self.cycles[-1] if self.cycles else "",
        )

    def describe(self) -> str:
        params = ", ".join(f"{p.placeholder}({p.kind})" for p in self.parameters) or "(无变量)"
        return (f"{self.candidate_id} | 分数 {self.score:.2f} | "
                f"{len(self.cycles)} 次成功 | 变量: {params}")


# ============================================================
# 变化点提取
# ============================================================
def _common_prefix_len(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def _common_suffix_len(a: str, b: str, floor: int = 0) -> int:
    n = 0
    for x, y in zip(reversed(a), reversed(b)):
        if x != y or n >= len(a) - floor or n >= len(b) - floor:
            break
        n += 1
    return n


def diff_token(values: list[str]) -> tuple[str, list[str]] | None:
    """给一组同类字符串，抽出「固定外壳 + 变化部分」。

    返回 (模板, 各次的变化值) 或 None（无法归纳）。

    只处理**单一连续变化段**的情形（最保守）：
      ["fib.py","fact.py"]        -> ("{p1}.py", ["fib","fact"])
      ["fib.fib","fact.factorial"]-> 多个变化段 → 交给调用方拆成多次处理

    不做多段对齐——那需要更复杂的序列对齐，且容易归纳出错误模板。
    """
    if len(values) < 2:
        return None
    if len(set(values)) == 1:
        return values[0], [values[0]]      # 完全一致，无变量

    prefix = min(_common_prefix_len(values[0], v) for v in values)
    # 后缀长度：不能与前缀重叠
    suffix = min(
        _common_suffix_len(values[0], v, floor=prefix) for v in values
    )
    # 变化段的长度
    mids = [v[prefix: len(v) - suffix if suffix else len(v)] for v in values]
    if any(not m for m in mids):
        # 某次的变化段为空 → 归纳不安全
        return None
    template = values[0][:prefix] + "{P}" + (values[0][len(values[0]) - suffix:] if suffix else "")
    return template, mids


def extract_parameters(
    snaps: list[Snapshot], shapes: list[Shape]
) -> tuple[list[ParameterGuess], str, str, list[dict]]:
    """从同形态的多次运行里抽出参数、目标模板、验证模板、文件契约。

    保守策略：**任一维度归纳失败就放弃该维度**（保留常量），
    而不是硬凑一个模板——错误的模板比没有模板危害更大。
    """
    guesses: list[ParameterGuess] = []
    counter = 0

    # ---------- 1. 文件路径 ----------
    path_lists = [[f.path for f in s.files] for s in snaps]
    if not path_lists or len({len(p) for p in path_lists}) != 1:
        return [], "", "", []

    n_files = len(path_lists[0])
    template_paths: list[str] = []
    for i in range(n_files):
        col = [pl[i] for pl in path_lists]
        result = diff_token(col)
        if result is None:
            return [], "", "", []          # 路径归纳失败，整体放弃
        tmpl, mids = result
        if "{P}" in tmpl:
            counter += 1
            ph = f"p{counter}"
            row = tmpl.replace("{P}", "{" + ph + "}")
            guesses.append(ParameterGuess(
                placeholder=ph, kind="path", examples=mids,
                suggested_name="filename" if i == 0 and n_files == 1 else f"file{i+1}",
            ))
        else:
            row = tmpl
        template_paths.append(row)

    # ---------- 2. 符号名 ----------
    symbol_lists = [[s for f in snap.files for s in (f.symbols or [])] for snap in snaps]
    if len({len(sl) for sl in symbol_lists}) != 1:
        # 符号数量不一致 → 不归纳符号，保留为空（由审核环节补）
        symbol_lists = [[""] * 0 for _ in snaps]
    template_symbols: list[str] = []
    for i in range(len(symbol_lists[0]) if symbol_lists else 0):
        col = [sl[i] for sl in symbol_lists]
        result = diff_token(col)
        if result is None:
            template_symbols = []
            break
        tmpl, mids = result
        if "{P}" in tmpl:
            counter += 1
            ph = f"p{counter}"
            template_symbols.append(tmpl.replace("{P}", "{" + ph + "}"))
            guesses.append(ParameterGuess(
                placeholder=ph, kind="symbol", examples=mids,
                suggested_name=f"func{i+1}" if i else "func",
            ))
        else:
            template_symbols.append(tmpl)

    # ---------- 3. 验证命令 ----------
    verifies = [s.verify_command for s in snaps]
    verify_lines = [v.splitlines() for v in verifies]
    if len({len(vl) for vl in verify_lines}) != 1:
        return guesses, "", "", []

    out_lines: list[str] = []
    for i in range(len(verify_lines[0])):
        col = [vl[i] for vl in verify_lines]
        if len(set(col)) == 1:
            out_lines.append(col[0])
            continue

        templated = _templatize_line(col[0], col, guesses)
        if templated is None:
            return guesses, "", "", []      # 验证无法归纳 —— 整体放弃
        out_lines.append(templated)

    verify_template = "\n".join(out_lines)

    # ---------- 4. 文件契约 ----------
    files = []
    for i, p in enumerate(template_paths):
        files.append({
            "path": p,
            "symbols": [template_symbols[i]] if i < len(template_symbols) and template_symbols[i] else [],
        })

    return guesses, "", verify_template, files


def _templatize_line(
    first: str, column: list[str], guesses: list[ParameterGuess]
) -> str | None:
    """把一行验证命令参数化。

    做法是**分词重建**，而不是子串替换。子串替换有个隐蔽 bug：
    `import fib` 与 `assert fib.fib(...)` 里，先把 `fib` 换成 `{p1}` 后，
    剩下的 `.fib` 就无人认领，于是同一行出现 `{p1}.{p1}`（其实是两个不同变量）。

    分词重建还顺带保证了空白与标点原样保留，不会误伤字符串内容。

    已知变量（来自路径/符号）优先；其余随行变化的词法单元识别为**字面量参数**
    （只接受数字/字符串，标识符不猜——猜错比不猜更糟）。
    """
    # 值 → 占位符（长的优先，避免前缀重叠时替换出半截）
    known: dict[str, str] = {}
    for g in guesses:
        for ex in g.examples:
            if ex:
                known[ex] = "{" + g.placeholder + "}"

    pattern = _TOKEN
    matches_first = list(pattern.finditer(first))
    per_line = [list(pattern.finditer(line)) for line in column]

    # 词法单元数量不一致 → 结构对不齐，无法安全归纳
    if any(len(ms) != len(matches_first) for ms in per_line):
        return None

    # 逐单元决定替换文本
    replacements: list[tuple[int, int, str]] = []   # (start, end, text)
    for idx, m in enumerate(matches_first):
        tok = m.group(0)
        col_vals = [ms[idx].group(0) for ms in per_line]
        if len(set(col_vals)) == 1:
            continue                                 # 该位置不变，保留原样
        if tok in known:
            replacements.append((m.start(), m.end(), known[tok]))
            continue
        if not (tok[0].isdigit() or tok[0] in "'\""):
            return None                              # 变化的标识符无从命名 → 放弃
        kind = "int-literal" if tok[0].isdigit() else "str-literal"
        g = next((x for x in guesses
                  if x.kind == kind and x.examples == list(col_vals)), None)
        if g is None:
            g = ParameterGuess(
                placeholder=f"p{_next_index(guesses)}", kind=kind,
                examples=list(col_vals), suggested_name="literal",
            )
            guesses.append(g)
        replacements.append((m.start(), m.end(), "{" + g.placeholder + "}"))

    # 从后往前替换，避免位移影响
    out = first
    for start, end, text in reversed(replacements):
        out = out[:start] + text + out[end:]
    return out


def _next_index(guesses: list[ParameterGuess]) -> int:
    n = 0
    for g in guesses:
        m = re.fullmatch(r"p(\d+)", g.placeholder)
        if m:
            n = max(n, int(m.group(1)))
    return n + 1


# ============================================================
# 打分（审核闸门）
# ============================================================
def score_candidate(
    n_success: int, params: list[ParameterGuess], verify_template: str,
    goal_template: str = "",
) -> tuple[float, list[str]]:
    """给候选打分。**这是"算不算可封装复用"的程序化判据。**

    分数不是"像不像能复用"的语义判断，而是可核查的几条：
      - 证据量：几次成功运行支撑（1 次不算，那是过拟合）
      - 参数是否识别出来（没参数 = 常量流程，复用价值低但也不算错）
      - 验证模板是否完整（缺了就无法机器判定，不可封装）
      - 目标模板是否存在
    """
    reasons: list[str] = []
    score = 0.0

    # 证据量（最高 0.4）
    if n_success >= 4:
        score += 0.40
        reasons.append(f"证据充分：{n_success} 次成功运行")
    elif n_success == 3:
        score += 0.28
        reasons.append(f"证据尚可：{n_success} 次成功运行")
    elif n_success == 2:
        score += 0.15
        reasons.append(f"证据薄弱：仅 {n_success} 次成功运行（需人工确认是否同源）")
    else:
        reasons.append("证据不足：仅 1 次成功运行，无法区分固定与可变部分")

    # 参数识别（最高 0.3）
    if params:
        score += 0.30
        kinds = ", ".join(f"{p.placeholder}:{p.kind}" for p in params)
        reasons.append(f"识别出 {len(params)} 个变量（{kinds}），具备复用价值")
    else:
        score += 0.10
        reasons.append("未识别出变量：可能是常量流程，复用价值有限")

    # 验证模板（最高 0.2）
    if verify_template.strip():
        score += 0.20
        reasons.append("验证模板完整，可机器判定")
    else:
        reasons.append("验证模板不完整——缺失则无法判定重放是否成功，不可封装")

    # 目标模板（最高 0.1）
    if goal_template.strip():
        score += 0.10
        reasons.append("目标模板可用")
    else:
        reasons.append("目标描述未归纳（不影响执行，但降低可读性）")

    return round(min(score, 1.0), 2), reasons


def auto_rename_map(candidate: "PackageCandidate") -> dict[str, str]:
    """按 kind 给自动占位符一个**弱语义建议**名。

    这是给审核环节的起点，不是结论：
      path         → filename / file2 / file3 …
      symbol       → func / func2 …
      int-literal  → expected_int / expected_int2 …
      str-literal  → expected_str …

    命名可能不准（自动命名在一般情形下不可解），所以审核要求人工确认。
    这个函数的存在只是让"重命名"这件事有个可用的默认，而非让人从零想名字。
    """
    counters: dict[str, int] = {}
    mapping: dict[str, str] = {}
    for p in candidate.parameters:
        base = {
            "path": "filename",
            "symbol": "func",
            "int-literal": "expected_int",
            "str-literal": "expected_str",
        }.get(p.kind, "param")
        counters[base] = counters.get(base, 0) + 1
        n = counters[base]
        mapping[p.placeholder] = base if n == 1 else f"{base}{n}"
    return mapping


# ============================================================
# 主入口
# ============================================================
def analyze(snapshots: dict[str, Snapshot], min_success: int = 2) -> list[PackageCandidate]:
    """扫描历史，返回封装候选（按分数降序）。

    只读：不改任何东西、不安装任何技能。安装需显式审核（见 promote.py）。
    """
    groups = group_by_shape(snapshots)
    out: list[PackageCandidate] = []

    for key, shapes in groups.items():
        if len(shapes) < min_success:
            continue
        ids = [s.cycle_id for s in shapes]
        snaps = [snapshots[cid] for cid in ids if cid in snapshots]
        if len(snaps) < min_success:
            continue

        params, goal_tmpl, verify_tmpl, files = extract_parameters(snaps, shapes)
        score, reasons = score_candidate(
            len(snaps), params, verify_tmpl, goal_tmpl
        )

        example = {}
        for s in snaps:
            example.update({p: code for p, code in _example_of(s).items()
                            if p not in example})

        out.append(PackageCandidate(
            # key = (exts, file_count, symbol_count, verify_skeleton)
            candidate_id=f"cand_{key[1]}f_{key[2]}s_{abs(hash(key)) % 100000:05d}",
            shape_desc=shapes[0].describe(),
            cycles=ids,
            goal_template=goal_tmpl,
            verify_template=verify_tmpl,
            files=files,
            parameters=params,
            score=score,
            score_reasons=reasons,
            example_code=example,
        ))

    out.sort(key=lambda c: (-c.score, -len(c.cycles)))
    return out


def _example_of(snap: Snapshot) -> dict[str, str]:
    """Snapshot 不存代码内容；这里给空，示例由 promote 阶段从磁盘读。"""
    return {}
