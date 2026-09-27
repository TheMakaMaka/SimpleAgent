"""技能（固定调用链路）自检。

重点验证三件事：
  1. 技能定义校验能拦住坏技能（未声明参数、缺 verify、无产出文件）。
  2. 模板渲染正确（参数替换到路径/符号/验证命令）。
  3. **与 CodingCycle 的集成**：SkillRunner 作为 Orchestrator 的替代实现，
     真的能跑通 manifest + syntax + verify 全部门禁，且不过门禁时不判成功。
"""

import asyncio
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import WORKSPACE as WS  # noqa: E402

from core import CheckPipeline, CodingCycle, VerifyCommand  # noqa: E402
from core.skill_runner import SkillRunner, render_task_description  # noqa: E402
from core.skills import (  # noqa: E402
    Skill, SkillError, SkillFile, SkillParameter, SkillStore,
    find_placeholders, record_skill, render_template,
)
from core.task import Artifact, TaskResult  # noqa: E402

TMP = os.path.join(WS, "_skilltest")


def clean() -> None:
    """清空 workspace 里本测试涉及的产物。

    必须彻底清 —— 之前只删特定前缀，结果上一个 section 留下的文件
    污染了后面 section 的 manifest 判定（unexpected-file），
    造成难以定位的偶发失败。
    """
    KEEP = {"_debug", "_tmp", "__pycache__"}
    shutil.rmtree(TMP, ignore_errors=True)
    os.makedirs(TMP, exist_ok=True)
    for name in os.listdir(WS):
        if name in KEEP:
            continue
        p = os.path.join(WS, name)
        shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)


def make_skill() -> Skill:
    return Skill(
        id="simple_func",
        name="单函数生成",
        goal_template="在 workspace 下创建 {filename}.py，实现 {func}({args}) 返回结果",
        files=[SkillFile(path="{filename}.py", symbols=["{func}"], role="实现")],
        verify_command=(
            "import {filename}\n"
            "assert {filename}.{func}([3, 1, 2]) == [1, 2, 3]\n"
            "print('PASS {func}')\n"
        ),
        parameters=[
            SkillParameter("filename", "文件名（不含 .py）", "add"),
            SkillParameter("func", "函数名", "add"),
            SkillParameter("args", "参数列表", "a, b"),
        ],
        # 示例的键必须与**模板路径**一致（这里是 {filename}.py），
        # 否则参数一换就查不到参考实现
        example_code={"{filename}.py": "def add(a, b):\n    return a + b\n"},
        source_cycle="cy_demo",
    )


class FakeWorker:
    """按脚本写文件并产出 artifact，不调用模型。"""

    def __init__(self, writes: dict[str, str] | None = None, ok: bool = True):
        self.writes = writes or {}
        self.ok = ok
        self.last_task = None
        self.last_context = None

    async def run(self, task, context):
        self.last_task = task
        self.last_context = context
        artifacts = []
        for i, (path, content) in enumerate(self.writes.items(), 1):
            full = os.path.join(WS, path)
            os.makedirs(os.path.dirname(full) or WS, exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(content)
            artifacts.append(Artifact(
                key=f"skill_{i}_file_{path}", kind="file", path=path,
            ))
        return TaskResult(
            task_id=task.id, ok=self.ok,
            output="已生成" if self.ok else "失败",
            artifacts=artifacts, steps_used=1,
        )


async def run_cycle(skill: Skill, params: dict, writes: dict, ok: bool = True):
    runner = SkillRunner(skill=skill, params=params, llm=None, worker=FakeWorker(writes, ok))
    # 真实流程里 CodingCycle 会注入 pipeline；这里显式装配以复现同样条件
    runner.pipeline = CheckPipeline()
    cycle = CodingCycle(
        orchestrator=runner, worker=runner.worker,
        pipeline=CheckPipeline(), max_attempts=1, verbose=False, persist=False,
    )
    return await cycle.run(skill.render_goal(params))


async def main() -> int:
    checks: list[tuple[str, bool]] = []
    clean()
    skill = make_skill()

    # ============================================================
    print("=" * 74)
    print("[1] 技能定义校验")
    print("=" * 74)
    checks.append(("合法技能无问题", skill.validate() == []))
    print(f"  合法技能 problems={skill.validate()}")

    bad_param = Skill(
        id="bad1", name="未声明参数", goal_template="创建 {nope}.py",
        files=[SkillFile(path="{nope}.py")], verify_command="print(1)",
    )
    p1 = bad_param.validate()
    checks.append(("未声明参数被拦", any("未声明" in x for x in p1)))
    print(f"  未声明参数: {p1}")

    no_verify = Skill(id="bad2", name="缺验证", goal_template="做题",
                      files=[SkillFile(path="a.py")], verify_command="")
    checks.append(("缺 verify_command 被拦", any("verify_command" in x for x in no_verify.validate())))
    print(f"  缺验证: {no_verify.validate()}")

    no_files = Skill(id="bad3", name="无产出", goal_template="做题", verify_command="print(1)")
    checks.append(("无产出文件被拦", any("产出文件" in x for x in no_files.validate())))
    print(f"  无产出: {no_files.validate()}")

    # ============================================================
    print("\n" + "=" * 74)
    print("[2] 模板渲染")
    print("=" * 74)
    params = {"filename": "bubble", "func": "bubble_sort", "args": "lst"}
    rendered_files = skill.render_files(params)
    rendered_verify = skill.render_verify(params)
    rendered_goal = skill.render_goal(params)
    print(f"  goal   : {rendered_goal}")
    print(f"  file   : {rendered_files[0].path} symbols={rendered_files[0].symbols}")
    print(f"  verify : {rendered_verify.splitlines()[1]}")

    checks.append(("路径已替换", rendered_files[0].path == "bubble.py"))
    checks.append(("符号已替换", rendered_files[0].symbols == ["bubble_sort"]))
    checks.append(("验证命令已替换", "bubble.bubble_sort" in rendered_verify))
    checks.append(("remaining 无未替换占位符",
                   not find_placeholders(rendered_verify, rendered_goal,
                                         rendered_files[0].path)))
    checks.append(("render_template 保留未知占位符",
                   render_template("{a}-{b}", {"a": "1"}) == "1-{b}"))

    # 缺失必填参数
    checks.append(("缺失参数可检测",
                   skill.missing_params({"filename": "x"}) == ["func", "args"]))
    print(f"  缺失参数: {skill.missing_params({'filename': 'x'})}")

    # ============================================================
    print("\n" + "=" * 74)
    print("[3] 任务说明：三样门禁相关信息都要写清")
    print("=" * 74)
    desc = render_task_description(skill, params)
    checks.append(("含目标", "bubble_sort" in desc))
    checks.append(("含必须产出的文件", "bubble.py" in desc and "必须产出" in desc))
    checks.append(("含必须有符号", "bubble_sort" in desc))
    checks.append(("含验收断言", "assert" in desc))
    checks.append(("含参考实现并警告不可照抄", "参考实现" in desc and "不要照抄" in desc))
    print(f"  任务说明长度: {len(desc)} 字符")

    # 无示例时不应出现空的参考段
    noskill = Skill(id="nos", name="无示例", goal_template="做 {x}",
                    files=[SkillFile(path="{x}.py", symbols=["f"])],
                    verify_command="import {x}",
                    parameters=[SkillParameter("x", example="a")])
    desc2 = render_task_description(noskill, {"x": "a"})
    checks.append(("无示例时不写参考段", "参考实现" not in desc2))

    # ============================================================
    print("\n" + "=" * 74)
    print("[4] 与 CodingCycle 集成：正向（应通过全部门禁）")
    print("=" * 74)
    report, memory = await run_cycle(
        skill, params,
        writes={"bubble.py": "def bubble_sort(lst):\n    return sorted(lst)\n"},
    )
    print(f"  phase={report.phase.value} manifest={(report.manifest or {}).get('passed')} "
          f"verify={(report.verify or {}).get('passed')}")
    checks.append(("技能重放通过", report.phase.value == "record"))
    checks.append(("manifest 通过", (report.manifest or {}).get("passed") is True))
    checks.append(("verify 通过", (report.verify or {}).get("passed") is True))
    checks.append(("声明来自技能而非模型",
                   (report.manifest or {}).get("declared", [{}])[0].get("path") == "bubble.py"))

    # ============================================================
    print("\n" + "=" * 74)
    print("[5] 与 CodingCycle 集成：反向（少写文件必须被拦）")
    print("=" * 74)
    clean()
    report2, _ = await run_cycle(
        skill, params,
        writes={},   # 什么都没写
    )
    print(f"  phase={report2.phase.value} error={report2.error}")
    checks.append(("少写文件被判失败", report2.phase.value == "failed"))
    checks.append(("失败原因是交付缺口", "交付清单不完整" in (report2.error or "")))
    checks.append(("未产生检查点", report2.commit is None))

    print("\n" + "=" * 74)
    print("[6] 与 CodingCycle 集成：反向（验证不过也必须被拦）")
    print("=" * 74)
    clean()
    report3, _ = await run_cycle(
        skill, params,
        writes={"bubble.py": "def bubble_sort(lst):\n    return 'wrong'\n"},
    )
    print(f"  phase={report3.phase.value} verify={(report3.verify or {}).get('passed')}")
    checks.append(("验证不过被判失败", report3.phase.value == "failed"))
    checks.append(("verify 记录为未通过", (report3.verify or {}).get("passed") is False))

    # ============================================================
    print("\n" + "=" * 74)
    print("[7] 技能落盘与统计")
    print("=" * 74)
    store = SkillStore(root=TMP)
    store.save(skill)
    loaded = store.get("simple_func")
    checks.append(("技能可往返", loaded is not None and loaded.id == skill.id))
    checks.append(("往返后参数完整", loaded.parameter_names() == skill.parameter_names()))
    checks.append(("往返后示例保留（模板键）",
                   loaded.example_for("{filename}.py") == skill.example_code["{filename}.py"]))
    checks.append(("示例可按参数解析（模板键→具体路径）",
                   "def add" in loaded.example_for("bubble.py", params)))
    checks.append(("列表可读", len(store.list()) == 1))

    store.record_use("simple_func", ok=True)
    store.record_use("simple_func", ok=True)
    store.record_use("simple_func", ok=False)
    s2 = store.get("simple_func")
    print(f"  使用统计: {s2.successes}/{s2.uses}")
    checks.append(("使用统计被记录", s2.uses == 3 and s2.successes == 2))
    checks.append(("describe 可读", "2/3" in s2.describe()))

    # ============================================================
    print("\n" + "=" * 74)
    print("[8] 从成功 cycle 记录技能（example 必须来自磁盘）")
    print("=" * 74)
    clean()
    os.makedirs(WS, exist_ok=True)
    with open(os.path.join(WS, "gen_add.py"), "w", encoding="utf-8") as f:
        f.write("def add(a, b):\n    return a + b\n")
    recorded = record_skill(
        cycle_id="cy_x", goal="创建 {filename}.py 实现 {func}",
        declared_files=[{"path": "gen_add.py", "symbols": ["add"], "role": "实现"}],
        verify_command="import gen_add\nassert gen_add.add(1,2)==3",
        workspace_dir=WS, skill_id="rec1",
        parameters=[SkillParameter("filename", example="gen_add")],
    )
    print(f"  记录到示例: {list(recorded.example_code.keys())}")
    checks.append(("example 从磁盘读到内容",
                   "def add" in recorded.example_code.get("gen_add.py", "")))
    checks.append(("记录的文件契约正确",
                   recorded.files[0].path == "gen_add.py"
                   and recorded.files[0].symbols == ["add"]))

    # 文件不存在时不该崩
    missing = record_skill(
        cycle_id="cy_y", goal="g", declared_files=[{"path": "nope.py"}],
        verify_command="print(1)", workspace_dir=WS, skill_id="rec2",
    )
    checks.append(("文件缺失时不崩", missing.example_code == {}))

    # ============================================================
    print("\n" + "=" * 74)
    print("[9] 坏技能不能重放")
    print("=" * 74)
    for bad, why in ((bad_param, "未声明参数"), (no_verify, "缺验证"), (no_files, "无产出")):
        try:
            SkillRunner(skill=bad, params={}, llm=None, worker=FakeWorker())
            checks.append((f"{why} 被拒绝", False))
        except ValueError as e:
            checks.append((f"{why} 被拒绝", True))
            print(f"  {why}: {str(e)[:60]}")

    try:
        SkillRunner(skill=skill, params={"filename": "x"}, llm=None, worker=FakeWorker())
        checks.append(("缺必填参数被拒绝", False))
    except ValueError as e:
        checks.append(("缺必填参数被拒绝", "缺少必填参数" in str(e)))
        print(f"  缺参数: {e}")

    # ============================================================
    print("\n" + "=" * 74)
    print("[10] 提升闸门：只有通过验证的 cycle 才能成为技能")
    print("=" * 74)
    from core.skills import PromotionRefused, promote_from_report

    class FakeReport:
        def __init__(self, phase, passed, declared):
            self.phase = type("P", (), {"value": phase})()
            self.verify = {"passed": passed, "command": "import {x}"}
            self.manifest = {"declared": declared}
            self.cycle_id = "cy_f"
            self.goal = "做 {x}"

    store2 = SkillStore(root=os.path.join(TMP, "promote"))
    os.makedirs(store2.root, exist_ok=True)
    with open(os.path.join(WS, "promo.py"), "w", encoding="utf-8") as f:
        f.write("def f():\n    return 1\n")

    # 未通过 → 拒绝
    try:
        promote_from_report(FakeReport("failed", False, [{"path": "promo.py", "symbols": []}]),
                            skill_id="p1", store=store2)
        checks.append(("未通过的 cycle 被拒绝提升", False))
    except PromotionRefused as e:
        checks.append(("未通过的 cycle 被拒绝提升", True))
        print(f"  拒绝(failed): {str(e)[:60]}")

    # phase=record 但 verify 未通过 → 拒绝
    try:
        promote_from_report(FakeReport("record", False, [{"path": "promo.py"}]),
                            skill_id="p2", store=store2)
        checks.append(("verify 未通过被拒绝", False))
    except PromotionRefused as e:
        checks.append(("verify 未通过被拒绝", True))
        print(f"  拒绝(verify=False): {str(e)[:60]}")

    # 无声明清单 → 拒绝
    try:
        promote_from_report(FakeReport("record", True, []), skill_id="p3", store=store2)
        checks.append(("无声明清单被拒绝", False))
    except PromotionRefused as e:
        checks.append(("无声明清单被拒绝", True))
        print(f"  拒绝(无清单): {str(e)[:60]}")

    # 合法提升（参数与模板一致）
    promoted = promote_from_report(
        FakeReport("record", True, [{"path": "promo.py", "symbols": ["f"]}]),
        skill_id="ok_skill", name="可提升", store=store2,
        parameters=[SkillParameter("x", example="promo")],
    )
    checks.append(("合法 cycle 可提升", promoted.id == "ok_skill"))
    checks.append(("提升后已落盘", store2.get("ok_skill") is not None))
    checks.append(("提升的技能带示例代码",
                   "def f" in promoted.example_code.get("promo.py", "")))
    print(f"  合法提升: {promoted.describe()}")

    # 参数不匹配模板 → 也要拒绝（否则技能定义不完整）
    try:
        promote_from_report(
            FakeReport("record", True, [{"path": "promo.py", "symbols": ["f"]}]),
            skill_id="bad_params", store=store2,
        )
        checks.append(("缺参数声明的提升被拒绝", False))
    except PromotionRefused as e:
        checks.append(("缺参数声明的提升被拒绝", True))
        print(f"  拒绝(缺参数): {str(e)[:70]}")

    clean()
    print("\n" + "=" * 74)
    print("断言检查")
    print("=" * 74)
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    failed = [n for n, ok in checks if not ok]
    print(f"\n通过 {len(checks) - len(failed)}/{len(checks)}")
    if failed:
        print("失败: " + "; ".join(failed))
    return 1 if failed else 0


raise SystemExit(asyncio.run(main()))
