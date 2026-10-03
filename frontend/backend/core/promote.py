"""封装审核与副本安装：候选 → 审核 → 副本 → 验证 → 入库。

分层（落实「先建副本，不影响主库」）
------------------------------------
  storage_data/skill_candidates/   候选（分析产出，未经验证）
  storage_data/skill_staging/      副本（审核通过后的隔离安装，待实测）
  storage_data/skills/             正式库（只有实测通过的才进来）

为什么必须经过副本
------------------
分析出来的候选是**归纳产物**：模板可能归纳错、参数可能漏识别。
直接装进正式库，等于把未经验证的推断当成资产——正是本项目一直在避免的
「把不确定性固化」。

所以流程是：
  候选 --审核闸门--> 副本 --重放实测--> 正式库
                         └─ 失败则丢弃副本，不污染正式库

审核闸门是**程序判据**，不是模型判断
------------------------------------
可核查的几条：分数达阈值、参数名有语义、模板无残留占位符、
副本 ID 不与正式库冲突。这些都能被验证，所以可以作为闸门。
"""
import json
import os
from dataclasses import dataclass, field
from datetime import datetime

from .package import PACKAGE_SCORE_THRESHOLD, PackageCandidate
from .skills import Skill, SkillStore

CANDIDATE_ROOT = os.path.abspath("storage_data/skill_candidates")
STAGING_ROOT = os.path.abspath("storage_data/skill_staging")

# 自动占位符形如 p1 / p2 —— 有语义的参数名不应匹配它
import re
_AUTO_NAME = re.compile(r"^p\d+$")


@dataclass
class AuditResult:
    """审核结论。每条都是可核查的事实，不是印象。"""

    approved: bool = False
    score: float = 0.0
    checks: list[dict] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append({"check": name, "ok": bool(ok), "detail": detail})

    @property
    def failed(self) -> list[str]:
        return [c["check"] for c in self.checks if not c["ok"]]

    def to_dict(self) -> dict:
        return {
            "approved": self.approved,
            "score": self.score,
            "checks": self.checks,
            "failed": self.failed,
        }

    def explain(self) -> str:
        lines = [f"审核{'通过' if self.approved else '未通过'}（分数 {self.score:.2f}）"]
        for c in self.checks:
            lines.append(f"  [{'OK' if c['ok'] else 'NG'}] {c['check']}"
                         + (f" — {c['detail']}" if c["detail"] else ""))
        return "\n".join(lines)


# ============================================================
# 候选存取
# ============================================================
class CandidateStore:
    def __init__(self, root: str = CANDIDATE_ROOT):
        self.root = os.path.abspath(root)
        os.makedirs(self.root, exist_ok=True)

    def _path(self, cid: str) -> str:
        safe = "".join(c for c in cid if c.isalnum() or c in "-_.") or "cand"
        return os.path.join(self.root, f"{safe}.json")

    def save(self, c: PackageCandidate) -> None:
        path = self._path(c.candidate_id)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(c.to_dict(), f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    def get(self, cid: str) -> PackageCandidate | None:
        try:
            with open(self._path(cid), "r", encoding="utf-8") as f:
                return PackageCandidate.from_dict(json.load(f))
        except (OSError, json.JSONDecodeError, KeyError):
            return None

    def list(self, status: str | None = None) -> list[PackageCandidate]:
        out = []
        for name in sorted(os.listdir(self.root)):
            if name.endswith(".json"):
                c = self.get(name[:-5])
                if c and (status is None or c.status == status):
                    out.append(c)
        out.sort(key=lambda c: -c.score)
        return out


# ============================================================
# 审核闸门
# ============================================================
def audit(candidate: PackageCandidate, *,
          renamed: dict[str, str] | None = None,
          live_store: SkillStore | None = None,
          proposed_id: str = "") -> AuditResult:
    """审核一个候选是否「可封装复用」。**程序判据。**"""
    result = AuditResult(score=candidate.score)

    # 1) 证据量：至少 2 次成功运行，否则无法区分固定与可变
    n = len(candidate.cycles)
    result.add("证据量 ≥ 2 次成功运行", n >= 2, f"实际 {n} 次")

    # 2) 分数达阈值
    result.add("分数达阈值", candidate.score >= PACKAGE_SCORE_THRESHOLD,
               f"{candidate.score:.2f} / {PACKAGE_SCORE_THRESHOLD}")

    # 3) 验证模板必须完整——缺了就无法判定重放成败
    result.add("验证模板完整（可机器判定）",
               bool((candidate.verify_template or "").strip()))

    # 4) 至少识别出一个变量，否则谈不上"复用"
    result.add("识别出至少一个变量", len(candidate.parameters) >= 1)

    # 5) 参数名必须有语义（自动名 p1 需重命名后才能入库）
    mapping = dict(renamed or {})
    auto_left = [p.placeholder for p in candidate.parameters
                 if p.placeholder not in mapping and _AUTO_NAME.match(p.placeholder)]
    result.add("参数已重命名为有语义的名字",
               not auto_left,
               f"待重命名: {', '.join(auto_left)}" if auto_left else "")

    # 6) 重命名后不能有重复名
    final_names = [mapping.get(p.placeholder, p.placeholder) for p in candidate.parameters]
    result.add("参数名不重复", len(final_names) == len(set(final_names)),
               f"{final_names}")

    # 7) 模板不能残留未替换占位符（转技能后再校验一次）
    try:
        skill = candidate.to_skill(skill_id=proposed_id or candidate.candidate_id,
                                   renamed=mapping)
        problems = skill.validate()
    except Exception as e:                       # noqa: BLE001
        problems = [f"转技能失败: {e}"]
    result.add("转成的技能定义自洽", not problems, "; ".join(problems)[:160])

    # 8) 与正式库不冲突（副本机制的前提）
    sid = proposed_id or candidate.candidate_id
    if live_store is not None and live_store.get(sid) is not None:
        result.add("技能 ID 不与正式库冲突", False, f"{sid} 已存在")
    else:
        result.add("技能 ID 不与正式库冲突", True)

    result.approved = not result.failed
    return result


# ============================================================
# 副本安装
# ============================================================
class StagingStore(SkillStore):
    """副本区。与正式库同构，但完全隔离。"""

    def __init__(self, root: str = STAGING_ROOT):
        super().__init__(root=root)


def install_to_staging(
    candidate: PackageCandidate,
    *,
    skill_id: str,
    name: str = "",
    renamed: dict[str, str] | None = None,
    staging: StagingStore | None = None,
    live_store: SkillStore | None = None,
    force: bool = False,
) -> tuple[Skill | None, AuditResult]:
    """审核通过后装进**副本区**，不动正式库。

    返回 (副本技能 或 None, 审核结果)。未通过则返回 None —— 调用方据此
    决定是否提示人工介入（而不是静默丢弃）。
    """
    staging = staging or StagingStore()
    live = live_store or SkillStore()
    result = audit(candidate, renamed=renamed, live_store=live,
                   proposed_id=skill_id)

    if not result.approved and not force:
        return None, result

    skill = candidate.to_skill(skill_id=skill_id, name=name, renamed=renamed)
    staging.save(skill)
    return skill, result


def promote_staging_to_live(
    skill_id: str,
    *,
    proven: bool,
    staging: StagingStore | None = None,
    live_store: SkillStore | None = None,
) -> tuple[bool, str]:
    """把副本提升到正式库。**只有实测通过（proven=True）才允许。**

    `proven` 必须由调用方根据**真实重放结果**给出（见 /skills 重放接口），
    不能凭审核分数推断——审核只能筛掉明显不合格的，不能证明它能跑通。
    """
    staging = staging or StagingStore()
    live = live_store or SkillStore()

    skill = staging.get(skill_id)
    if skill is None:
        return False, f"副本不存在: {skill_id}"
    if not proven:
        return False, "未经实测通过，不允许进入正式库（副本保留，可继续验证）"
    if live.get(skill_id) is not None:
        return False, f"正式库已存在同名技能: {skill_id}（如需覆盖请先删除）"

    live.save(skill)
    staging.delete(skill_id)
    return True, f"已提升到正式库: {skill_id}"


def discard_staging(skill_id: str, staging: StagingStore | None = None) -> bool:
    """丢弃副本（审核未过、或实测失败）。正式库不受影响。"""
    staging = staging or StagingStore()
    return staging.delete(skill_id)
