"""一轮编码流程的契约定义。

术语约定（重要，避免和 Orchestrator 的 round 混淆）：
  - Cycle（一轮编码流程）：从「规划」到「记录」的完整一遍，是本模块的单位。
  - Orchestrator round：主循环内部的一次拆解决策，属于 Cycle 内部细节。
  - Worker step：子循环内部的一次工具调用，属于 Cycle 内部细节。

设计原则：进入 verify 阶段之前，必须通过 check 阶段的程序化校验；
verify 的成败由 verify_command 的退出码决定，不由模型自述决定。
"""

from dataclasses import dataclass, field
from enum import Enum


class CyclePhase(str, Enum):
    PLAN = "plan"          # 编排器拆解任务
    WRITE = "write"        # 子模型落盘实现
    CHECK = "check"        # 【程序驱动】语法 + lint
    VERIFY = "verify"      # 【程序驱动】跑用户给的验证命令
    RECORD = "record"      # 结构化摘要 + git 检查点
    FAILED = "failed"      # 本 Cycle 未通过校验


# 阶段推进顺序；CHECK 未通过时不允许进入 VERIFY
PHASE_ORDER: tuple[CyclePhase, ...] = (
    CyclePhase.PLAN,
    CyclePhase.WRITE,
    CyclePhase.CHECK,
    CyclePhase.VERIFY,
    CyclePhase.RECORD,
)


@dataclass(frozen=True)
class VerifyCommand:
    """机器可判定的验证方式。

    必须是「退出码 == 0 即通过」的命令。不要接受自然语言描述的验证方式，
    否则整个流程又会退化成依赖模型自述。
    """

    command: str                      # 例如 "python check.py"
    reason: str = ""                  # 这条命令为什么能证明目标达成
    expect_exit: int = 0

    def label(self) -> str:
        return self.command.strip() or "(未指定)"


@dataclass
class CycleReport:
    """一轮编码流程的可观测记录，用于落盘和回退关联。"""

    cycle_id: str
    goal: str
    phase: CyclePhase = CyclePhase.PLAN
    transitions: list[str] = field(default_factory=list)
    attempts: int = 0
    check_steps: list[dict] = field(default_factory=list)
    manifest: dict | None = None
    #: 程序驱动 check 阶段的**汇总事实**（`VERIFY-VACUOUS` 建议 4）。
    #:
    #: 为什么不能只看 `check_steps`：空列表是**两义**的 ——
    #: 既可能是"查了、没发现问题"，也可能是"压根没东西可查"。
    #: 实测事故里 `steps=0` 被读成绿灯，而真相是这一轮什么都没查。
    #: 现在照 `manifest` 的样子给出 `checked` + 三态 `status`
    #: （`passed` / `failed` / `skipped`），"未验证"明写、不假装通过。
    check: dict | None = None
    verify: dict | None = None
    touched_files: list[str] = field(default_factory=list)
    commit: str | None = None
    rolled_back: bool = False
    error: str | None = None

    # ---------- 状态推进 ----------
    def enter(self, phase: CyclePhase) -> None:
        """进入下一阶段，并校验推进顺序合法。

        PHASE_ORDER 此前只是声明、无人消费，注释里写的
        「CHECK 未通过时不允许进入 VERIFY」并不由它保证。现在由这里强制：
        除 FAILED 外，阶段必须沿 PHASE_ORDER 前进，不得跳跃或倒退。
        """
        if not self.is_valid_transition(phase):
            raise ValueError(
                f"非法阶段推进: {self.phase.value} -> {phase.value}；"
                f"合法顺序为 {' -> '.join(p.value for p in PHASE_ORDER)}"
            )
        self.phase = phase
        self.transitions.append(phase.value)

    def is_valid_transition(self, phase: CyclePhase) -> bool:
        # FAILED 是任意阶段的终点，允许从任何阶段进入
        if phase is CyclePhase.FAILED:
            return self.phase is not CyclePhase.FAILED
        # 重试：FAILED 之后重新从 PLAN 开始
        if self.phase is CyclePhase.FAILED:
            return phase is CyclePhase.PLAN
        # 已在 PLAN 时重复进入 PLAN，视为重启本轮（多轮尝试会走到这里）
        if self.phase is CyclePhase.PLAN and phase is CyclePhase.PLAN:
            return True
        # 其余情况必须沿 PHASE_ORDER 恰好前进一步
        try:
            cur = PHASE_ORDER.index(self.phase)
            nxt = PHASE_ORDER.index(phase)
        except ValueError:
            return False
        return nxt == cur + 1

    def to_dict(self) -> dict:
        return {
            "cycle_id": self.cycle_id,
            "goal": self.goal,
            "phase": self.phase.value,
            "transitions": self.transitions,
            "attempts": self.attempts,
            "check_steps": self.check_steps,
            "check": self.check,
            "manifest": self.manifest,
            "verify": self.verify,
            "touched_files": self.touched_files,
            "commit": self.commit,
            "rolled_back": self.rolled_back,
            "error": self.error,
        }
