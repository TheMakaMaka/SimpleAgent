"""P14 门禁：**输出契约** —— 声明的交付物必须存在且哈希一致。

契约 `runtime_paths_and_output_contract`（v1.0.32）验收 ①④：
  ① `/profile.runtime` 三个绝对路径都存在（在 `test_project_root.py` 里也覆盖）；
  ④ 交付物声明**必须存在且哈希一致**；故意声明一个不存在的交付物 ⇒ **必须判不合格**。

反空洞（"不是把检查关掉"）：
  · 声明**存在且哈希正确**的交付物必须**通过**（证明不是一律报红）；
  · 声明**不存在**的必须失败，且失败原因是结构化的 `deliverable-missing`；
  · 产物**被删掉之后**再对账必须由 pass 翻成 fail（判据真的看磁盘，不是恒真）。
"""

import asyncio
import hashlib
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import Checker  # noqa: E402

from core import CheckPipeline, CodingCycle, OrchestratorResult, SharedMemory, Task, TaskResult  # noqa: E402
from core import runtime  # noqa: E402
from core.task import Artifact  # noqa: E402
from storage.store import Event  # noqa: E402

c = Checker()


class RecStorage:
    def __init__(self):
        self.events: list[Event] = []

    def append_event(self, event: Event) -> None:
        self.events.append(event)

    def get_events(self, cycle_id=None):
        return list(self.events)


class GateOrch:
    """脚本化的编排器：把给定文件写出来并登记成产物，然后给一个验证结论。"""

    def __init__(self, files: dict[str, str], verify_state: dict | None = None):
        self.pipeline = None
        self.verify_command = None
        self.context_provider = None
        self._files = dict(files or {})
        self._vs = verify_state

    async def run(self, goal: str):
        mem = SharedMemory(goal=goal)
        items = list(self._files.items()) or [("(noop)", None)]
        for i, (rel, content) in enumerate(items):
            if content is not None:
                target = runtime.resolve_write(rel)
                os.makedirs(os.path.dirname(target) or runtime.effective_root(), exist_ok=True)
                with open(target, "w", encoding="utf-8") as f:
                    f.write(content)
            task_id = f"t{i + 1}"
            mem.record(
                Task(id=task_id, description=f"写出 {rel}",
                     expected_output=f"{rel}"),
                TaskResult(task_id=task_id, ok=True, output=f"已写入 {rel}",
                           artifacts=([Artifact(key=f"{task_id}_file_{rel}",
                                                kind="file", path=rel)]
                                      if content is not None else []),
                           steps_used=1),
            )
        if self._vs is not None:
            mem.verify_state = dict(self._vs)
        return OrchestratorResult(ok=True, answer="stub", memory=mem,
                                  verify_command=None, declared_files=None)


def build(orch, storage):
    return CodingCycle(orchestrator=orch, worker=None,          # type: ignore[arg-type]
                       pipeline=CheckPipeline(), storage=storage, persist=True,
                       verbose=False, max_attempts=1, checkpoint_prefer="none")


VS_PASS = {"passed": True, "detail": "ok", "command": "assert True",
           "source": "caller", "artifact_hashes": {}, "cwd": "",
           # ★ P17：pass 的 executed 证据要求**执行记录**（真实退出码）。
           # 假编排器也必须如实带上，否则这条"通过"没有机械证据支撑。
           "exit_code": 0, "expect_exit": 0}


def sha256_of(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


async def main() -> int:
    tmp = os.path.join(runtime.workspace_root(), "_p14_probe")
    os.makedirs(tmp, exist_ok=True)
    name = "_p14_probe/deliv.txt"
    abs_deliv = os.path.join(runtime.workspace_root(), name)
    body = "hello deliverable\n"

    try:
        print("=" * 74)
        print("[1] 声明存在的交付物 + 哈希正确 ⇒ **通过**（不是一律报红）")
        print("=" * 74)
        # 先算出内容哈希，作为声明值
        with open(abs_deliv, "w", encoding="utf-8") as f:
            f.write(body)
        want = sha256_of(abs_deliv)
        # 注意：Windows 上文本模式会把 \n 翻成 \r\n，所以 size 必须**从磁盘取**，
        # 不能用 len(body.encode()) —— 否则测的是测试自己的假设，不是文件事实。
        size_on_disk = os.path.getsize(abs_deliv)
        report, _mem = await build(
            GateOrch({}, verify_state=VS_PASS), RecStorage()
        ).run("写交付物", deliverables=[{"path": name, "sha256": want,
                                          "size": size_on_disk}])
        dv = report.deliverables or {}
        print(f"  phase={report.phase.value} deliverables.passed={dv.get('passed')}")
        print(f"  actual={dv.get('actual')}")
        print(f"  violations={dv.get('violations')}")
        c.check("声明正确 ⇒ 交付物对账通过", dv.get("passed") is True)
        c.check("回报了 {path, sha256, size}", bool(dv.get("actual"))
                and dv["actual"][0]["sha256"] == want
                and dv["actual"][0]["size"] == size_on_disk)
        c.check("整轮仍然通过（对账没有误伤）", report.phase.value == "record")

        print("\n" + "=" * 74)
        print("[2] 故意声明一个**不存在**的交付物 ⇒ 必须判不合格")
        print("=" * 74)
        report2, _m2 = await build(
            GateOrch({}, verify_state=VS_PASS), RecStorage()
        ).run("写交付物", deliverables=[{"path": "_p14_probe/never_written.txt"}])
        dv2 = report2.deliverables or {}
        kinds2 = [v.get("kind") for v in (dv2.get("violations") or [])]
        print(f"  phase={report2.phase.value} outcome={report2.outcome} "
              f"kind={report2.outcome_kind}")
        print(f"  violations={kinds2}")
        print(f"  error={report2.error}")
        c.check("不存在的交付物被判不合格", dv2.get("passed") is False)
        c.check("失败原因是结构化 deliverable-missing",
                "deliverable-missing" in kinds2)
        c.check("结局是 fail（delivery-gap），不是静默放过",
                report2.outcome == "fail" and report2.outcome_kind == "delivery-gap")
        c.check("整轮 phase=failed", report2.phase.value == "failed")

        print("\n" + "=" * 74)
        print("[3] 哈希不一致 ⇒ 不合格（哈希判据真的有牙齿）")
        print("=" * 74)
        report3, _m3 = await build(
            GateOrch({}, verify_state=VS_PASS), RecStorage()
        ).run("写交付物", deliverables=[{"path": name, "sha256": "deadbeef" * 8}])
        dv3 = report3.deliverables or {}
        kinds3 = [v.get("kind") for v in (dv3.get("violations") or [])]
        print(f"  violations={kinds3}  passed={dv3.get('passed')}")
        c.check("哈希不一致被判不合格", dv3.get("passed") is False)
        c.check("原因是 deliverable-hash-mismatch",
                "deliverable-hash-mismatch" in kinds3)

        print("\n" + "=" * 74)
        print("[4] 反空洞：产物**被删掉之后**再对账 ⇒ pass 翻成 fail")
        print("=" * 74)
        dv_before = runtime.check_deliverables([name])
        os.remove(abs_deliv)
        dv_after = runtime.check_deliverables([name])
        print(f"  删除前 passed={dv_before['passed']} / 删除后 passed={dv_after['passed']}")
        c.check("删除前通过", dv_before["passed"] is True)
        c.check("删除后失败（判据看磁盘，不是恒真）", dv_after["passed"] is False)

        print("\n" + "=" * 74)
        print("[5] 没有声明时：不判定，但仍回报**实际产物** {path, sha256, size}")
        print("=" * 74)
        report4, _m4 = await build(
            GateOrch({name: body}, verify_state=VS_PASS), RecStorage()
        ).run("随手写点东西")
        dv4 = report4.deliverables or {}
        print(f"  checked={dv4.get('checked')} passed={dv4.get('passed')} "
              f"actual={[(a.get('path'), bool(a.get('sha256')), a.get('size')) for a in dv4.get('actual') or []]}")
        c.check("没声明时不判定（checked=False）但也不拦路", dv4.get("checked") is False
                and dv4.get("passed") is True)
        c.check("仍回报实际产物（含 sha256/size）",
                any(a.get("path") == name and a.get("sha256") and a.get("size")
                    for a in (dv4.get("actual") or [])))
        c.check("整轮仍然通过", report4.phase.value == "record")

        print("\n" + "=" * 74)
        print("[6] /profile.runtime 的三个绝对路径存在（验收 ① 的机械判据）")
        print("=" * 74)
        info = runtime.describe()
        ok = all(os.path.isabs(info[k]) and os.path.isdir(info[k])
                 for k in ("runtime_root", "workspace_root", "output_root"))
        print(f"  {[info[k] for k in ('runtime_root', 'workspace_root', 'output_root')]}")
        c.check("三个绝对路径都存在", ok)
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)

    return c.report()


raise SystemExit(asyncio.run(main()))
