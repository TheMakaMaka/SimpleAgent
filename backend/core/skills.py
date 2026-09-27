"""技能：把「已被验证稳定的流程」固化成可重放链路。

定位
----
一个 `Skill` 就是**预先烘焙好的计划**（pre-baked plan）：
  - 固定：产出哪些文件、每个文件要有哪些符号、用什么方式验证
  - 变化：少量参数（函数名、目标名等）

重放时**不再让编排器重新规划**，因此：
  - 少一轮模型调用（原来 PLAN 走一次 LLM，现在直接读技能）
  - 流程一致（同样的文件、同样的验证方式，不受模型随机性影响）
  - 仍然经过 CHECK / VERIFY / manifest 全部门禁 —— 稳定不等于免检

技能是**资产，不是遥测**
------------------------
默认落在 `storage_data/skills/`，但请注意它与 `storage_data/` 里其它内容的性质不同：
其它是运行遥测（可随时删），技能是**需要备份与版本管理**的资产。
因此本目录**不应被 .gitignore 忽略**（.gitignore 里对它做了例外），
也可以用 `SKILLS_DIR` 环境变量指到仓库内的目录，以便纳入版本控制。

关键纪律
--------
1. **只有验证通过的 cycle 才能被提升为技能。** 未验证的流程不是"稳定流程"。
2. **重放不过门禁就不算成功。** 技能记录的是"曾经成功过"，不是"永远正确"。
   代码由模型按参数重新生成，仍需实测。
3. 技能里的 `example` 只作为**参考实现**给模型看，不作为直接复制的产物——
   参数不同则代码必须不同。

数据结构分三层：
  SkillFile      产出契约（路径模板 + 必须有符号）
  Skill          整条链路（文件 + 验证模板 + 参数 + 示例）
  SkillStore     落盘与检索
"""

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

# 可用 SKILLS_DIR 覆盖（例如指到仓库内做版本管理）
SKILL_ROOT = os.path.abspath(
    os.getenv("SKILLS_DIR") or os.path.join("storage_data", "skills")
)

# 模板占位符形如 {func_name}；替换时用这个正则校验
_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


class SkillError(ValueError):
    """技能定义或重放时的可预期错误。"""


@dataclass
class SkillParameter:
    name: str
    description: str = ""
    example: str = ""
    required: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SkillFile:
    """一个产出文件的契约。`path` 可含占位符。"""

    path: str
    symbols: list[str] = field(default_factory=list)
    role: str = ""

    def render_path(self, params: dict[str, str]) -> str:
        return render_template(self.path, params)

    def render_symbols(self, params: dict[str, str]) -> list[str]:
        return [render_template(s, params) for s in self.symbols]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Skill:
    """一条可重放的固定链路。"""

    id: str
    name: str
    goal_template: str
    files: list[SkillFile] = field(default_factory=list)
    verify_command: str = ""          # 可含占位符
    parameters: list[SkillParameter] = field(default_factory=list)
    example_code: dict[str, str] = field(default_factory=dict)   # 路径 → 参考实现
    verify_reason: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    source_cycle: str = ""            # 从哪个成功 cycle 提升而来
    uses: int = 0
    successes: int = 0

    # ---------- 校验 ----------
    def validate(self) -> list[str]:
        """返回问题列表；空表示可用。"""
        problems: list[str] = []
        if not self.id:
            problems.append("技能缺少 id")
        if not self.files:
            problems.append("技能没有任何产出文件，无法验证交付")
        if not self.verify_command.strip():
            problems.append("技能缺少 verify_command，重放后无法机器判定")
        declared = set(self.parameter_names())
        for src, label in [(self.goal_template, "goal_template"),
                           (self.verify_command, "verify_command")]:
            for ph in _PLACEHOLDER.findall(src or ""):
                if ph not in declared:
                    problems.append(f"{label} 使用了未声明的参数 {{{ph}}}")
        for f in self.files:
            for ph in _PLACEHOLDER.findall(f.path):
                if ph not in declared:
                    problems.append(f"文件路径 {f.path} 使用了未声明的参数 {{{ph}}}")
            for s in f.symbols:
                for ph in _PLACEHOLDER.findall(s):
                    if ph not in declared:
                        problems.append(f"符号 {s} 使用了未声明的参数 {{{ph}}}")
        return problems

    def parameter_names(self) -> list[str]:
        return [p.name for p in self.parameters]

    def missing_params(self, given: dict[str, str]) -> list[str]:
        return [p.name for p in self.parameters
                if p.required and not str(given.get(p.name, "")).strip()]

    # ---------- 渲染 ----------
    def render_goal(self, params: dict[str, str]) -> str:
        return render_template(self.goal_template, params)

    def render_verify(self, params: dict[str, str]) -> str:
        return render_template(self.verify_command, params)

    def render_files(self, params: dict[str, str]) -> list[SkillFile]:
        return [
            SkillFile(
                path=f.render_path(params),
                symbols=f.render_symbols(params),
                role=render_template(f.role, params),
            )
            for f in self.files
        ]

    def example_for(self, path: str, params: dict[str, str] | None = None) -> str:
        """取某个产出文件的参考实现。

        `example_code` 的键可能是**模板路径**（`{filename}.py`），也可能是具体路径。
        两种都支持：
          - 先按原样精确匹配（记录时用的是具体路径的情况）
          - 再按参数渲染后匹配（记录时用的是模板路径的情况）
        这样参数一换仍能查到参考实现。
        """
        if path in self.example_code:
            return self.example_code[path]
        if params:
            for key, code in self.example_code.items():
                if render_template(key, params) == path:
                    return code
        return ""

    # ---------- 序列化 ----------
    def to_dict(self) -> dict:
        d = asdict(self)
        d["files"] = [f.to_dict() for f in self.files]
        d["parameters"] = [p.to_dict() for p in self.parameters]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Skill":
        return cls(
            id=d["id"],
            name=d.get("name", d["id"]),
            goal_template=d.get("goal_template", ""),
            files=[SkillFile(**f) for f in (d.get("files") or [])],
            verify_command=d.get("verify_command", ""),
            parameters=[SkillParameter(**p) for p in (d.get("parameters") or [])],
            example_code=d.get("example_code") or {},
            verify_reason=d.get("verify_reason", ""),
            created_at=d.get("created_at", ""),
            source_cycle=d.get("source_cycle", ""),
            uses=int(d.get("uses", 0)),
            successes=int(d.get("successes", 0)),
        )

    def describe(self) -> str:
        params = ", ".join(self.parameter_names()) or "(无)"
        files = ", ".join(f.path for f in self.files)
        rate = f"{self.successes}/{self.uses}" if self.uses else "未重放过"
        return (
            f"{self.id} | 参数: {params} | 产出: {files} | "
            f"成功率: {rate}"
        )


def render_template(text: str, params: dict[str, str]) -> str:
    """替换 {name} 占位符。缺失的参数保留原样（由 validate 提前拦截）。"""
    if not text:
        return ""
    return _PLACEHOLDER.sub(
        lambda m: str(params.get(m.group(1), m.group(0))), text
    )


def find_placeholders(*texts: str) -> set[str]:
    out: set[str] = set()
    for t in texts:
        out |= set(_PLACEHOLDER.findall(t or ""))
    return out


# ============================================================
# 记录：从「已验证通过」的 cycle 提升为技能
# ============================================================
def record_skill(
    *,
    cycle_id: str,
    goal: str,
    declared_files: list[dict],
    verify_command: str,
    workspace_dir: str,
    skill_id: str,
    name: str = "",
    parameters: list[SkillParameter] | None = None,
    verify_reason: str = "",
) -> Skill:
    """把一个成功 cycle 的形态记录下来。

    只接受**已通过验证**的 cycle —— 调用方负责确认这一点（见 `promote_from_report`）。

    注意：`example_code` 从**磁盘读取**，因为 worker 产生的 file artifact
    只存路径不存内容（`kind="file", path=...`）。这是本模块需要显式读盘的原因。
    """
    files = []
    examples: dict[str, str] = {}
    for d in declared_files or []:
        path = (d.get("path") or "").strip()
        if not path:
            continue
        files.append(SkillFile(
            path=path,
            symbols=list(d.get("symbols") or []),
            role=(d.get("role") or "").strip(),
        ))
        # 捕获真实实现作为参考
        abs_path = os.path.join(workspace_dir, path)
        try:
            if os.path.isfile(abs_path):
                with open(abs_path, "r", encoding="utf-8") as fh:
                    examples[path] = fh.read()
        except OSError:
            pass

    return Skill(
        id=skill_id,
        name=name or skill_id,
        goal_template=goal,
        files=files,
        verify_command=verify_command,
        parameters=list(parameters or []),
        example_code=examples,
        verify_reason=verify_reason,
        source_cycle=cycle_id,
    )


# ============================================================
# 提升：只允许「已验证通过」的 cycle
# ============================================================
class PromotionRefused(SkillError):
    """拒绝提升。原因见消息——这是纪律，不是 bug。"""


def promote_from_report(
    report,
    *,
    skill_id: str,
    name: str = "",
    parameters: list[SkillParameter] | None = None,
    store: "SkillStore | None" = None,
    workspace_dir: str | None = None,
) -> Skill:
    """把一个**已通过验证**的 CycleReport 提升为技能。

    闸门（这是本模块最重要的纪律）：
      - `report.phase` 必须是 `record`（= 通过校验并打了检查点）
      - 必须有 verify 结论且为通过
      - 必须有清单声明（否则不知道该固定哪些产出文件）

    拒绝提升不是失败，而是保护：**未验证的流程不是"稳定流程"**，
    把它封装成可复用链路，等于把不确定性批量复制。

    参数通常需要人工确定（或由调用方从多次成功运行中diff得出）——
    单次运行无法自动知道"哪些部分是可变的"。这里只固化形态，参数由你命名。
    """
    phase = getattr(getattr(report, "phase", None), "value", None)
    if phase != "record":
        raise PromotionRefused(
            f"只有通过验证的 cycle 才能提升为技能；当前 phase={phase!r}"
        )

    verify = getattr(report, "verify", None) or {}
    if not verify.get("passed"):
        raise PromotionRefused("该 cycle 没有通过的验证结论，无法提升")

    manifest = getattr(report, "manifest", None) or {}
    declared = manifest.get("declared") or []
    if not declared:
        raise PromotionRefused(
            "该 cycle 没有声明产出清单（manifest.declared 为空），"
            "无法确定要固定哪些文件"
        )

    skill = record_skill(
        cycle_id=getattr(report, "cycle_id", "") or "",
        goal=getattr(report, "goal", "") or "",
        declared_files=declared,
        verify_command=str(verify.get("command") or ""),
        workspace_dir=workspace_dir or os.path.abspath("workspace"),
        skill_id=skill_id,
        name=name,
        parameters=parameters,
        verify_reason=str(verify.get("detail") or ""),
    )

    problems = skill.validate()
    if problems:
        raise PromotionRefused(
            "提升后的技能定义不完整（通常是因为缺少参数声明）：\n  - "
            + "\n  - ".join(problems)
        )

    if store is not None:
        store.save(skill)
    return skill


# ============================================================
# 落盘
# ============================================================
class SkillStore:
    """技能持久化。一技能一 JSON，便于人工查看与版本管理。"""

    def __init__(self, root: str = SKILL_ROOT):
        self.root = os.path.abspath(root)
        os.makedirs(self.root, exist_ok=True)

    @staticmethod
    def _safe(skill_id: str) -> str:
        return "".join(c for c in skill_id if c.isalnum() or c in "-_.") or "unnamed"

    def _path(self, skill_id: str) -> str:
        return os.path.join(self.root, f"{self._safe(skill_id)}.json")

    def save(self, skill: Skill) -> None:
        path = self._path(skill.id)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(skill.to_dict(), f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    def get(self, skill_id: str) -> Skill | None:
        try:
            with open(self._path(skill_id), "r", encoding="utf-8") as f:
                return Skill.from_dict(json.load(f))
        except (OSError, json.JSONDecodeError, KeyError):
            return None

    def list(self) -> list[Skill]:
        out: list[Skill] = []
        for name in sorted(os.listdir(self.root)):
            if name.endswith(".json"):
                s = self.get(name[:-5])
                if s:
                    out.append(s)
        return out

    def delete(self, skill_id: str) -> bool:
        try:
            os.remove(self._path(skill_id))
            return True
        except OSError:
            return False

    def record_use(self, skill_id: str, ok: bool) -> None:
        """重放后回写统计，让"稳定"变成可度量的。"""
        s = self.get(skill_id)
        if not s:
            return
        s.uses += 1
        if ok:
            s.successes += 1
        self.save(s)
