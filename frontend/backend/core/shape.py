"""任务形态指纹：判断两个 cycle 是不是「同一类任务」。

为什么需要它
------------
`Skill` 的参数化前提是「多次运行只有少数地方变化」。
但要知道**哪些地方变化**，先得知道**哪几次运行属于同一类**——
否则把冒泡排序和阶乘放在一起 diff，只会得到一堆无意义的差异。

指纹刻意取**保守的特征**（宁可漏配，不可错配）：
  - 产出文件的扩展名集合
  - 产出文件的数量
  - 验证命令的结构（去掉标识符后的骨架）
  - 声明符号的数量

**不含**目标文本本身（措辞每次都不同）、**不含**具体标识符
（那正是我们要识别的变量）。

这与 fingerprint/manifest 的既有纪律一致：只认结构事实。
"""

import re
from dataclasses import dataclass
from typing import Iterable

from .compress import Snapshot

# 词法单元：字符串 / 数字 / 标识符。顺序很重要——先匹配更长的。
_TOKEN = re.compile(r"'[^']*'|\"[^\"]*\"|\d+|[A-Za-z_][A-Za-z0-9_]*")


@dataclass
class Shape:
    """一次运行的结构形态。

    `verify_skeleton` 是**结构签名**：标识符与字面量都归一化。
    它用于判断"两次运行是否同一类任务"，因此必须对具体值不敏感——
    `fib(10)==55` 与 `factorial(5)==120` 都属"单文件单函数、断言返回值"，
    是同一个可封装的工作流。
    """

    cycle_id: str
    exts: tuple[str, ...]          # 产出文件扩展名（排序后）
    file_count: int
    symbol_count: int
    verify_skeleton: str           # 结构签名（字面量已归一）
    ok: bool                       # 该次是否通过验证

    def key(self) -> tuple:
        return (self.exts, self.file_count, self.symbol_count, self.verify_skeleton)

    def describe(self) -> str:
        return (f"{self.file_count} 个文件 {list(self.exts)} | "
                f"{self.symbol_count} 个符号 | verify≈{self.verify_skeleton[:60]}")


def _exts_of(paths: Iterable[str]) -> tuple[str, ...]:
    exts = []
    for p in paths:
        p = (p or "").replace("\\", "/")
        _, dot, ext = p.rpartition(".")
        if dot and "/" not in ext:
            exts.append("." + ext.lower())
    return tuple(sorted(set(exts)))


def verify_skeleton(command: str, normalize_literals: bool = True) -> str:
    """把验证命令归一成**结构签名**，用于判断两次运行是否同一类任务。

    三条规则：
      - 标识符（文件名、函数名）→ `ID`：它们是我们要识别的**变量**
      - 数字 / 字符串字面量 → `<int>` / `<str>`（`normalize_literals=True`）：
        断言里的具体值也是变量，归一后才能把同类任务分到一组
      - `a.b.c` 连续属性访问压缩成 `ID.ID`，避免点数影响分组

    为什么字面量也要归一（踩过两次坑）：
      1. 早期版本连数字一起抹成 `N`，但**没处理带括号的 `[3,1,2]`**，
         结果同类任务因"有没有方括号"被拆到不同组；
      2. 改成保留字面量后，`fib(10)==55` 与 `factorial(5)==120` 又分到不同组，
         同类工作流无法聚类，`analyze` 产出 0 个候选。

    正确的边界是：**结构签名对具体值不敏感，参数提取才去用具体值**。
    两级分工，各司其职。
    """
    if not command:
        return ""

    def repl(m: re.Match) -> str:
        tok = m.group(0)
        if tok[0].isdigit():
            return "<int>" if normalize_literals else tok
        if tok[0] in "'\"":
            return "<str>" if normalize_literals else tok
        return "ID"

    lines = [ln.strip() for ln in command.splitlines() if ln.strip()]
    normalized = []
    for ln in lines:
        ln = _TOKEN.sub(repl, ln)
        ln = re.sub(r"(\s*(?:ID|<int>|<str>)\s*)(\.\s*(?:ID|<int>|<str>))+", r"\1.ID", ln)
        ln = re.sub(r"\s+", " ", ln)
        normalized.append(ln)
    return " | ".join(normalized)


def shape_of(snapshot: Snapshot) -> Shape:
    """从 Snapshot 提取形态。只读 verified / declared 事实。"""
    paths = [f.path for f in snapshot.files]
    symbols = [s for f in snapshot.files for s in (f.symbols or [])]
    return Shape(
        cycle_id=snapshot.cycle_id,
        exts=_exts_of(paths),
        file_count=len(paths),
        symbol_count=len(symbols),
        verify_skeleton=verify_skeleton(snapshot.verify_command),
        ok=snapshot.status == "passed",
    )


def group_by_shape(snapshots: dict[str, Snapshot]) -> dict[tuple, list[Shape]]:
    """按形态分组。只有 **通过验证** 的 cycle 参与分组——

    未通过的流程不是"稳定流程"，没有封装价值（与 promotes 的闸门一致）。
    """
    groups: dict[tuple, list[Shape]] = {}
    for snap in snapshots.values():
        shape = shape_of(snap)
        if not shape.ok:
            continue
        if shape.file_count == 0 or not shape.verify_skeleton:
            continue      # 没有产出或没有验证方式，形态不完整
        groups.setdefault(shape.key(), []).append(shape)
    return groups
