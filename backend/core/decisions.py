"""决策点：可持久化的人工介入机制。

设计目标
--------
让「决策流不必一直盯着」成为可能：cycle 在关键节点挂起、把待决策项**落盘**、
通过任意通道推送出去；你从手机作答后流程继续。

分层（关键）
-----------
  决策层（本模块）   与通道无关：待决策项的数据模型、状态机、持久化、超时策略
  投递层（notify）   可插拔：钉钉/企业微信/Slack/Telegram/邮件……都只是「发一条带链接的消息」
  审批页（web）      真正的交互在这里，因此不受各 IM bot 能力差异影响

为什么这样切：投递通道是易变的（今年用钉钉，明年可能换），而「哪里需要人决策」
是稳定的。混在一起写，换通道就要动工作流——那正是这个项目一直在避免的耦合。

超时策略（fail-safe）
--------------------
没人作答时**不能默认放行**。`on_timeout` 默认取保守动作：
  - 回退确认类（risky_rollback）→ 默认 "abort"（不覆盖已有文件）
  - 连续失败类（repeated_failure）→ 默认 "stop"（停止 cycle，不空转烧预算）
"""

import json
import os
import secrets
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Literal, Protocol

DECISION_ROOT = os.path.abspath("storage_data/decisions")

DecisionKind = Literal["repeated_failure", "risky_rollback"]
DecisionStatus = Literal["pending", "answered", "expired", "cancelled"]


@dataclass
class Option:
    """一个可选项。value 是回传给流程的动作标识。"""

    value: str
    label: str
    hint: str = ""
    danger: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


# ---------- 预设选项集 ----------
FAILURE_OPTIONS = [
    Option("retry", "再试一次", "让模型换一种思路重试", danger=False),
    Option("relax", "放宽验收", "跳过当前验证，标记为未验证通过", danger=True),
    Option("stop", "停止本轮", "回退到基线并结束该 cycle", danger=False),
]

ROLLBACK_OPTIONS = [
    Option("allow", "允许回退", "丢弃本次改动，恢复到上一个检查点", danger=True),
    Option("keep", "保留改动", "不回退，继续在现有工作区上修改", danger=False),
    Option("stop", "停止本轮", "结束 cycle，交由人工处理", danger=False),
]


@dataclass
class PendingDecision:
    """一条待人工决策。这是**跨进程存活**的实体，必须可完整序列化。"""

    id: str
    kind: DecisionKind
    cycle_id: str
    question: str
    options: list[Option] = field(default_factory=list)
    context: dict = field(default_factory=dict)      # 结构化快照（供审批页渲染）
    default: str = ""                                # 超时后的保守动作
    created_at: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    expires_at: str = ""
    status: DecisionStatus = "pending"
    answer: str = ""
    answered_by: str = ""
    answered_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["options"] = [o.to_dict() for o in self.options]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "PendingDecision":
        opts = [Option(**o) for o in (d.get("options") or [])]
        return cls(
            id=d["id"], kind=d["kind"], cycle_id=d.get("cycle_id", ""),
            question=d.get("question", ""), options=opts,
            context=d.get("context") or {}, default=d.get("default", ""),
            created_at=d.get("created_at", ""), expires_at=d.get("expires_at", ""),
            status=d.get("status", "pending"), answer=d.get("answer", ""),
            answered_by=d.get("answered_by", ""), answered_at=d.get("answered_at", ""),
        )

    # ---------- 状态 ----------
    def is_expired(self, now: datetime | None = None) -> bool:
        if not self.expires_at:
            return False
        try:
            deadline = datetime.fromisoformat(self.expires_at)
        except ValueError:
            return False
        return (now or datetime.now()) > deadline

    def valid_values(self) -> set[str]:
        return {o.value for o in self.options}

    def resolve_effective(self) -> str:
        """最终生效的动作：有作答用作答，否则用保守默认。"""
        if self.status == "answered" and self.answer:
            return self.answer
        return self.default

    def to_markdown(self) -> str:
        """渲染给 IM 消息的短文本（链接由投递层附加）。"""
        lines = [f"⚠ 需要你决策：{self.question}"]
        ctx = self.context or {}
        if ctx.get("goal"):
            lines.append(f"目标：{str(ctx['goal'])[:80]}")
        if ctx.get("error"):
            lines.append(f"原因：{str(ctx['error'])[:120]}")
        if ctx.get("touched"):
            lines.append(f"涉及文件：{', '.join(ctx['touched'][:5])}")
        lines.append("可选：" + " / ".join(o.label for o in self.options))
        return "\n".join(lines)


# ============================================================
# 持久化
# ============================================================
class DecisionStore(Protocol):
    def save(self, d: PendingDecision) -> None: ...
    def get(self, decision_id: str) -> PendingDecision | None: ...
    def list(self, status: str | None = None) -> list[PendingDecision]: ...
    def delete(self, decision_id: str) -> None: ...


class FileDecisionStore:
    """一决策一文件。便于人工查看、也便于手机端直接 GET。"""

    def __init__(self, root: str = DECISION_ROOT):
        self.root = os.path.abspath(root)
        os.makedirs(self.root, exist_ok=True)

    def _path(self, decision_id: str) -> str:
        # 防路径穿越：decision_id 由本模块生成（token_urlsafe），但仍做净化
        safe = "".join(c for c in decision_id if c.isalnum() or c in "-_")
        return os.path.join(self.root, f"{safe}.json")

    def save(self, d: PendingDecision) -> None:
        path = self._path(d.id)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d.to_dict(), f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    def get(self, decision_id: str) -> PendingDecision | None:
        path = self._path(decision_id)
        try:
            with open(path, "r", encoding="utf-8") as f:
                return PendingDecision.from_dict(json.load(f))
        except (OSError, json.JSONDecodeError, KeyError):
            return None

    def list(self, status: str | None = None) -> list[PendingDecision]:
        out: list[PendingDecision] = []
        for name in sorted(os.listdir(self.root)):
            if not name.endswith(".json"):
                continue
            d = self.get(name[:-5])
            if d and (status is None or d.status == status):
                out.append(d)
        out.sort(key=lambda x: x.created_at, reverse=True)
        return out

    def delete(self, decision_id: str) -> None:
        try:
            os.remove(self._path(decision_id))
        except OSError:
            pass


# ============================================================
# 决策管理器：创建、作答、超时
# ============================================================
class DecisionManager:
    """流程侧的唯一入口。"""

    def __init__(self, store: DecisionStore | None = None,
                 default_timeout_minutes: int = 30):
        self.store = store or FileDecisionStore()
        self.default_timeout_minutes = default_timeout_minutes

    # ---------- 创建 ----------
    def open(
        self,
        kind: DecisionKind,
        cycle_id: str,
        question: str,
        options: list[Option] | None = None,
        context: dict | None = None,
        default: str = "",
        timeout_minutes: int | None = None,
    ) -> PendingDecision:
        opts = options or (FAILURE_OPTIONS if kind == "repeated_failure"
                           else ROLLBACK_OPTIONS)
        timeout = self.default_timeout_minutes if timeout_minutes is None else timeout_minutes
        expires = (datetime.now() + timedelta(minutes=timeout)).isoformat(timespec="seconds")

        d = PendingDecision(
            id=secrets.token_urlsafe(12),
            kind=kind,
            cycle_id=cycle_id,
            question=question,
            options=opts,
            context=context or {},
            # 保守默认：没人管的时候不要自己往前冲
            default=default or self._conservative_default(kind),
            expires_at=expires,
        )
        self.store.save(d)
        return d

    @staticmethod
    def _conservative_default(kind: DecisionKind) -> str:
        if kind == "risky_rollback":
            return "abort"       # 不覆盖已有文件
        return "stop"            # 停止而不是空转

    # ---------- 作答 ----------
    def answer(self, decision_id: str, value: str, by: str = "") -> tuple[bool, str]:
        """写入作答。返回 (是否成功, 说明)。

        只接受**选项列表内**的值——防止前端被绕过时注入任意动作。
        """
        d = self.store.get(decision_id)
        if d is None:
            return False, "决策不存在"
        if d.status != "pending":
            return False, f"该决策已处于 {d.status} 状态，不能再作答"
        if d.is_expired():
            self.expire(d)
            return False, "该决策已超时"
        if value not in d.valid_values():
            return False, f"非法选项: {value}（可选 {sorted(d.valid_values())}）"

        d.status = "answered"
        d.answer = value
        d.answered_by = by
        d.answered_at = datetime.now().isoformat(timespec="seconds")
        self.store.save(d)
        return True, "已记录"

    def cancel(self, decision_id: str, reason: str = "") -> None:
        d = self.store.get(decision_id)
        if d and d.status == "pending":
            d.status = "cancelled"
            d.answer = ""
            d.answered_by = reason
            self.store.save(d)

    # ---------- 超时 ----------
    def expire(self, d: PendingDecision) -> None:
        d.status = "expired"
        # 超时后生效的是保守默认，写进 answer 以便调用方统一读取
        d.answer = self._conservative_default(d.kind)
        d.answered_at = datetime.now().isoformat(timespec="seconds")
        self.store.save(d)

    def sweep_expired(self) -> list[str]:
        """把所有已超时的 pending 标记为 expired。返回被处理的 id。"""
        done: list[str] = []
        for d in self.store.list(status="pending"):
            if d.is_expired():
                self.expire(d)
                done.append(d.id)
        return done

    # ---------- 查询 ----------
    def pending(self) -> list[PendingDecision]:
        self.sweep_expired()
        return self.store.list(status="pending")

    def get(self, decision_id: str) -> PendingDecision | None:
        return self.store.get(decision_id)
