import hashlib
from dataclasses import dataclass, field
from typing import Literal, Optional


ArtifactKind = Literal["code", "file", "data", "text"]


@dataclass
class Artifact:
    key: str                           # 引用名，如 "ant_colony_v1"
    kind: ArtifactKind
    content: Optional[str] = None      # 小内容
    path: Optional[str] = None         # 大内容落盘路径
    meta: dict = field(default_factory=dict)

    def preview(self, n: int = 120) -> str:
        if self.content:
            head = self.content[:n].replace("\n", " ")
            suffix = "..." if len(self.content) > n else ""
            return f"[{self.kind}] key='{self.key}': {head}{suffix}"
        if self.path:
            return f"[{self.kind}] key='{self.key}': path='{self.path}'"
        return f"[{self.kind}] key='{self.key}'"


@dataclass
class Task:
    id: str
    description: str
    expected_output: str = ""
    tool_hint: list[str] = field(default_factory=list)
    context_refs: list[str] = field(default_factory=list)
    # 0 表示「用模型档位的默认预算」（ModelLimits.max_steps），避免两处各写一个默认值
    max_steps: int = 0

    def fingerprint(self) -> str:
        norm = self.description.strip().lower()
        return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:12]


@dataclass
class TaskResult:
    task_id: str
    ok: bool
    output: str                        # 给主循环看的摘要（一句话/一段话）
    artifacts: list[Artifact] = field(default_factory=list)
    error: Optional[str] = None
    steps_used: int = 0

    def summary(self) -> str:
        flag = "OK" if self.ok else "FAIL"
        head = f"[{flag}] {self.task_id}: {self.output[:200]}"
        if self.error:
            head += f" | err: {self.error[:120]}"
        return head