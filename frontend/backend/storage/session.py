import json
import os
import re
from dataclasses import asdict
from datetime import datetime

from core.task import Artifact, Task, TaskResult

STORAGE_DIR = "sessions"
_SAFE_ID = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


def _safe_id(session_id: str) -> str:
    if _SAFE_ID.match(session_id):
        return session_id
    import hashlib
    return hashlib.sha256(session_id.encode()).hexdigest()[:16]


class RunStore:
    """保存一次 Orchestrator run 的完整记录。"""

    def __init__(self, session_id: str):
        self.session_id = _safe_id(session_id)
        os.makedirs(STORAGE_DIR, exist_ok=True)
        self.file_path = os.path.join(STORAGE_DIR, f"{self.session_id}.json")

    def load(self) -> dict:
        if not os.path.exists(self.file_path):
            return {"runs": [], "created_at": str(datetime.now())}
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"runs": [], "created_at": str(datetime.now())}

    def append_run(self, goal: str, ok: bool, answer: str, records: list) -> None:
        data = self.load()
        data["runs"].append({
            "goal": goal,
            "ok": ok,
            "answer": answer,
            "records": [self._record_to_dict(r) for r in records],
            "finished_at": str(datetime.now()),
        })
        self._atomic_save(data)

    def _atomic_save(self, data: dict) -> None:
        tmp = self.file_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.file_path)

    @staticmethod
    def _record_to_dict(record) -> dict:
        task: Task = record.task
        result: TaskResult = record.result
        return {
            "task": asdict(task),
            "result": {
                "task_id": result.task_id,
                "ok": result.ok,
                "output": result.output,
                "error": result.error,
                "steps_used": result.steps_used,
                "artifacts": [asdict(a) for a in result.artifacts],
            },
        }