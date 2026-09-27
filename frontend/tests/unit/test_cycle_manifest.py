"""manifest 接进 CHECK 阶段的自检（用假编排器，确定性验证）。"""

import asyncio
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import WORKSPACE as WS  # noqa: E402

from core import (  # noqa: E402
    CheckPipeline, CodingCycle, OrchestratorResult, SharedMemory, Task, TaskResult,
    VerifyCommand,
)
from core.task import Artifact  # noqa: E402

CLEAN = ("_tmp", "_debug", "__pycache__", ".git")


def clean():
    for name in os.listdir(WS):
        if name in CLEAN:
            continue
        p = os.path.join(WS, name)
        shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)


class FakeOrchestrator:
    """按脚本产出文件与声明，并复刻真实编排器的「验证回流」行为。

    真实 Orchestrator.run() 会在循环内调用 pipeline.run_verify 并写入
    memory.set_verify(...)，CodingCycle 依赖这个状态。假编排器必须同样做，
    否则测的就不是集成路径。
    """

    def __init__(self, writes: dict[str, str], declared: list | None):
        self.writes = writes
        self.declared = declared
        self.pipeline = None
        self.verify_command = None
        self.max_rounds = 3
        self.max_same_task = 2

    async def run(self, goal: str):
        memory = SharedMemory(goal=goal)
        for i, (path, content) in enumerate(self.writes.items(), 1):
            full = os.path.join(WS, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(content)
            task = Task(id=f"t{i}", description=f"写 {path}")
            memory.record(task, TaskResult(
                task_id=task.id, ok=True, output=f"已写 {path}",
                artifacts=[Artifact(key=f"t{i}_file_{path}", kind="file", path=path)],
                steps_used=1,
            ))

        # 复刻验证回流：有文件产物且给了验证命令就跑一次
        if self.verify_command and self.pipeline is not None:
            vc = VerifyCommand(
                command=self.verify_command.get("command", ""),
                reason=self.verify_command.get("reason", ""),
            )
            vr = await self.pipeline.run_verify(vc)
            memory.set_verify(
                passed=bool(vr.get("passed")),
                detail=str((vr.get("parsed") or {}).get("output")
                           or (vr.get("parsed") or {}).get("parsed_error")
                           or vr.get("reason") or ""),
                command=vc.label(),
                fingerprint="fake",
            )

        return OrchestratorResult(
            ok=memory.verified_passed(), answer="done", memory=memory,
            verify_command=None, declared_files=self.declared,
        )


async def scenario(name, writes, declared, verify_cmd):
    clean()
    fake = FakeOrchestrator(writes, declared)
    cycle = CodingCycle(
        orchestrator=fake, worker=None,
        pipeline=CheckPipeline(), max_attempts=1, verbose=False,
    )
    report, memory = await cycle.run(
        "测试目标", verify_command=VerifyCommand(command=verify_cmd, reason="测试")
    )
    print(f"\n--- {name} ---")
    print(f"  phase={report.phase.value} manifest_passed={(report.manifest or {}).get('passed')}")
    print(f"  error={report.error}")
    for v in (report.manifest or {}).get("violations") or []:
        print(f"    [{v['severity']}] {v['kind']}: {v.get('path') or v.get('from')} — {v.get('message','')[:50]}")
    return report


async def main():
    # 场景 A：声明 2 个文件，只写了 1 个 → manifest 应拦下，且不进 verify
    r = await scenario(
        "A 缺文件（复刻 L8）",
        writes={"storage.py": "def save(p, d):\n    pass\n\ndef load(p):\n    return {}\n"},
        declared=[
            {"path": "storage.py", "symbols": ["save", "load"]},
            {"path": "contacts.py", "symbols": ["Contacts"]},
        ],
        verify_cmd="print('SHOULD-NOT-RUN')",
    )
    print(f"  → verify 未被调用: {r.verify is None}")

    # 场景 B：文件齐备但缺符号
    await scenario(
        "B 缺符号",
        writes={"cli.py": "def run():\n    return ''\n"},
        declared=[{"path": "cli.py", "symbols": ["run", "main"]}],
        verify_cmd="print('x')",
    )

    # 场景 C：全部齐备 → 应通过 manifest 并进入 verify
    r = await scenario(
        "C 齐备",
        writes={
            "storage.py": "def save(p, d):\n    pass\n\ndef load(p):\n    return {}\n",
            "cli.py": "import storage\n\ndef run(args):\n    return 'ok'\n",
        },
        declared=[
            {"path": "storage.py", "symbols": ["save", "load"]},
            {"path": "cli.py", "symbols": ["run"]},
        ],
        verify_cmd="import cli\nassert cli.run([]) == 'ok'\nprint('C PASS')",
    )
    print(f"  → verify_passed={(r.verify or {}).get('passed')}")

    # 场景 D：未声明清单 → 跳过校验，不应因此失败
    r = await scenario(
        "D 未声明清单",
        writes={"solo.py": "def f():\n    return 1\n"},
        declared=None,
        verify_cmd="import solo\nassert solo.f() == 1\nprint('D PASS')",
    )
    print(f"  → manifest.checked={(r.manifest or {}).get('checked')} phase={r.phase.value}")

    # 场景 E：悬空 import 只报警告、不拦截。
    #         side.py 里有无法解析的相对导入，但验证只 import main_ok，
    #         因此 side.py 不参与执行；manifest 应出 warning 且仍然放行。
    r = await scenario(
        "E 悬空import仅警告（不拦截）",
        writes={
            "main_ok.py": "def f():\n    return 1\n",
            "side.py": "from . import missing_thing\n\ndef unused():\n    return 2\n",
        },
        declared=[
            {"path": "main_ok.py", "symbols": ["f"]},
            {"path": "side.py", "symbols": ["unused"]},
        ],
        verify_cmd="import main_ok\nassert main_ok.f() == 1\nprint('E PASS')",
    )
    print(f"  → phase={r.phase.value} (期望 record)")
    warns = [v for v in (r.manifest or {}).get("violations") or [] if v["severity"] == "warning"]
    print(f"  → 警告 {len(warns)} 条: {[w['kind'] for w in warns]}")

    clean()
    print("\n" + "=" * 70)
    print("断言")
    print("=" * 70)
    return r


result_e = asyncio.run(main())

checks = [
    ("E 仅警告时最终通过", result_e.phase.value == "record"),
    ("E manifest.passed 为真", (result_e.manifest or {}).get("passed") is True),
    ("E 确实产生了 warning", any(
        v["severity"] == "warning" for v in (result_e.manifest or {}).get("violations") or []
    )),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
