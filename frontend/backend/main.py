import asyncio
import os

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# 加载仓库根目录的 .env（见 .env.example）。
# 必须在读取任何 ORCH_*/WORKER_* 变量之前执行，否则 .env 配置不生效。
# 注意：测试与诊断脚本不走这里，它们通过环境变量或默认值配置。
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:  # python-dotenv 未安装时静默降级为「只用环境变量」
    pass

from core import (
    CheckPipeline,
    CheckpointManager,
    CodingCycle,
    DecisionManager,
    LLMClient,
    ModelProfile,
    Orchestrator,
    VerifyCommand,
    Worker,
    channel_status,
    describe_roles,
    get_git_status,
    resolve_profile,
)
from storage import RunStore
from web.decisions import router as decisions_router

app = FastAPI(title="Coding Agent")
app.include_router(decisions_router)


def _approval_base_url() -> str:
    """决策链接的前缀。手机要用，必须是手机可达的地址（不是 127.0.0.1）。

    例：AGENT_APPROVAL_BASE_URL=http://192.168.1.10:8000
    """
    return (os.getenv("AGENT_APPROVAL_BASE_URL") or "http://127.0.0.1:8000").rstrip("/")


class RunRequest(BaseModel):
    goal: str
    session_id: str = "default"


class RunResponse(BaseModel):
    ok: bool
    answer: str
    rounds_used: int
    tasks_total: int
    tasks_ok: int
    tasks_failed: int


class EncodeRequest(BaseModel):
    goal: str
    session_id: str = "default"
    # 机器可判定的验证命令（一段 Python，退出码为 0 即通过）。
    # 不传则使用主循环自己提出的 verify。
    verify_command: str | None = None
    verify_reason: str = ""
    max_attempts: int = 2
    # 人工决策模式：
    #   auto   命中决策点时直接采用保守默认动作，不推送不等待（默认，等价旧行为）
    #   notify 落盘并推送，但不等待；采用保守默认动作
    #   wait   落盘并推送，**阻塞等待**你在手机上作答
    on_decision: str = "auto"
    # 连续失败多少次后转人工
    max_consecutive_failures: int = 2


class EncodeResponse(BaseModel):
    ok: bool
    cycle_id: str
    answer: str
    phase: str
    attempts: int
    checkpoint_backend: str
    commit: str | None
    rolled_back: bool
    touched_files: list[str]
    check_passed: bool
    verify_passed: bool | None
    manifest_passed: bool | None
    error: str | None


def _build_orchestrator() -> Orchestrator:
    """构建工作流。模型预算全部来自配置入口，这里不出现任何魔法数字。"""
    profiles = resolve_profiles()

    # 启动自检：模型不满足流程要求就显式失败，而不是静默劣化
    problems: list[str] = []
    for role, prof in profiles.items():
        problems.extend(prof.validate(role=role))
    if problems:
        raise HTTPException(500, "模型接入校验失败：\n" + "\n".join(problems))

    for role, prof in profiles.items():
        print(f"[模型接入] {role}: {prof.describe()}")

    orch_llm = LLMClient(profiles["ORCH"])
    worker_llm = LLMClient(profiles["WORKER"])
    worker = Worker(worker_llm)
    return Orchestrator(orch_llm, worker)


def resolve_profiles() -> dict[str, ModelProfile]:
    """解析 ORCH / WORKER 两个角色的模型档位。

    走**显式角色表**（`core.config.ROLES`）：未配置的 worker 按角色表声明继承
    orchestrator；其它角色（reviewer / package_optimizer）**不继承**，
    未配置即"未启用"，不会静默顶替成编排器模型。
    """
    from core import resolve_role

    cache: dict[str, ModelProfile] = {}
    orch = resolve_role("orchestrator", resolved=cache)
    worker = resolve_role("worker", resolved=cache)
    return {"ORCH": orch, "WORKER": worker}


@app.post("/run", response_model=RunResponse)
async def run(req: RunRequest):
    """原有流程：只跑主循环 + 子循环，不做强制校验，也不打检查点。"""
    if not req.goal.strip():
        raise HTTPException(400, "goal 不能为空")

    orchestrator = _build_orchestrator()
    result = await orchestrator.run(req.goal)

    store = RunStore(req.session_id)
    store.append_run(
        goal=req.goal,
        ok=result.ok,
        answer=result.answer,
        records=result.memory.records,
    )

    ok_count = sum(1 for r in result.memory.records if r.result.ok)
    fail_count = len(result.memory.records) - ok_count

    return RunResponse(
        ok=result.ok,
        answer=result.answer,
        rounds_used=len(result.memory.records),
        tasks_total=len(result.memory.records),
        tasks_ok=ok_count,
        tasks_failed=fail_count,
    )


@app.post("/encode", response_model=EncodeResponse)
async def encode(req: EncodeRequest):
    """一轮编码流程：规划 → 写码 → 强制检查 → 强制验证 → 检查点。

    ok=True 只代表「验证命令退出码为 0」，不代表模型自称完成。
    """
    if not req.goal.strip():
        raise HTTPException(400, "goal 不能为空")

    orchestrator = _build_orchestrator()
    cycle = CodingCycle(
        orchestrator=orchestrator,
        worker=orchestrator.worker,
        pipeline=CheckPipeline(),
        max_attempts=max(1, min(req.max_attempts, 5)),
        on_decision=req.on_decision if req.on_decision in ("auto", "notify", "wait") else "auto",
        max_consecutive_failures=max(1, min(req.max_consecutive_failures, 10)),
        approval_base_url=_approval_base_url(),
    )

    verify = None
    if req.verify_command and req.verify_command.strip():
        verify = VerifyCommand(
            command=req.verify_command,
            reason=req.verify_reason or "调用方指定的验证命令",
        )

    report, memory = await cycle.run(req.goal, verify_command=verify)

    print(f"\n===== CycleReport =====\n{report.to_dict()}\n")

    ok_count = sum(1 for r in memory.records if r.result.ok)
    RunStore(req.session_id).append_run(
        goal=req.goal,
        ok=report.phase.value == "record",
        answer=f"cycle={report.cycle_id} commit={report.commit}",
        records=memory.records,
    )

    return EncodeResponse(
        ok=report.phase.value == "record",
        cycle_id=report.cycle_id,
        answer=(
            f"cycle 通过校验，检查点 {report.commit}"
            if report.phase.value == "record"
            else (report.error or "cycle 未通过校验")
        ),
        phase=report.phase.value,
        attempts=report.attempts,
        checkpoint_backend=cycle.checkpoint.name,
        commit=report.commit,
        rolled_back=report.rolled_back,
        touched_files=report.touched_files,
        check_passed=any(
            (s.get("tool") == "check_syntax" and s.get("passed"))
            for s in report.check_steps
        ) or not report.check_steps,
        verify_passed=(report.verify or {}).get("passed"),
        manifest_passed=(report.manifest or {}).get("passed"),
        error=report.error,
    )


class SkillReplayRequest(BaseModel):
    params: dict[str, str] = {}
    max_attempts: int = 2


@app.get("/skills")
async def list_skills():
    """列出已封装的固定调用链路。

    「稳定」是可度量的：每个技能记录 uses/successes，重放后回写。
    """
    from core import SkillStore

    skills = SkillStore().list()
    return {
        "count": len(skills),
        "skills": [
            {
                "id": s.id,
                "name": s.name,
                "goal_template": s.goal_template,
                "parameters": [
                    {"name": p.name, "description": p.description,
                     "example": p.example, "required": p.required}
                    for p in s.parameters
                ],
                "files": [{"path": f.path, "symbols": f.symbols} for f in s.files],
                "verify_command": s.verify_command,
                "source_cycle": s.source_cycle,
                "created_at": s.created_at,
                "uses": s.uses,
                "successes": s.successes,
                "problems": s.validate(),
                "describe": s.describe(),
            }
            for s in skills
        ],
        "note": "技能是预先烘焙的计划；重放仍经过 manifest/语法/验证全部门禁。",
    }


@app.post("/skills/{skill_id}/replay")
async def replay_skill(skill_id: str, req: SkillReplayRequest):
    """按固定链路重放。**仍走完整门禁**——技能记录的是「曾经成功」，不是「永远正确」。"""
    from core import SkillRunner, SkillStore

    store = SkillStore()
    skill = store.get(skill_id)
    if skill is None:
        raise HTTPException(404, f"技能不存在: {skill_id}")

    problems = skill.validate()
    if problems:
        raise HTTPException(400, "技能定义有问题：\n" + "\n".join(problems))
    missing = skill.missing_params(req.params)
    if missing:
        raise HTTPException(400, f"缺少必填参数: {', '.join(missing)}")

    profiles = resolve_profiles()
    worker_llm = LLMClient(profiles["WORKER"])
    runner = SkillRunner(skill=skill, params=req.params, llm=worker_llm)
    cycle = CodingCycle(
        orchestrator=runner,
        worker=runner.worker,
        pipeline=CheckPipeline(),
        max_attempts=max(1, min(req.max_attempts, 5)),
        approval_base_url=_approval_base_url(),
    )

    report, _ = await cycle.run(skill.render_goal(req.params))
    ok = report.phase.value == "record"
    store.record_use(skill_id, ok=ok)
    updated = store.get(skill_id)

    return {
        "ok": ok,
        "skill_id": skill_id,
        "params": req.params,
        "phase": report.phase.value,
        "attempts": report.attempts,
        "commit": report.commit,
        "manifest_passed": (report.manifest or {}).get("passed"),
        "verify_passed": (report.verify or {}).get("passed"),
        "touched_files": report.touched_files,
        "error": report.error,
        "stats": {"uses": updated.uses, "successes": updated.successes} if updated else None,
    }


class InstallCandidateRequest(BaseModel):
    skill_id: str
    name: str = ""
    renamed: dict[str, str] = {}
    force: bool = False


@app.get("/candidates")
async def list_candidates(analyze_now: int = 0):
    """列出封装候选（封装优化角色的产出）。

    `analyze_now=1` 时先重新分析历史再列出。**只读** —— 不安装任何东西。
    """
    from core import CandidateStore
    from core.package import analyze, auto_rename_map

    store = CandidateStore()
    if analyze_now:
        from core.compress import reduce_all
        from storage.store import default_storage

        events = default_storage().get_events()
        snaps = reduce_all(events)
        for c in analyze(snaps):
            store.save(c)

    cands = store.list()
    return {
        "count": len(cands),
        "candidates": [
            {
                "candidate_id": c.candidate_id,
                "score": c.score,
                "cycles": c.cycles,
                "shape": c.shape_desc,
                "parameters": [p.to_dict() for p in c.parameters],
                "suggested_names": auto_rename_map(c),
                "files": c.files,
                "verify_template": c.verify_template,
                "score_reasons": c.score_reasons,
                "status": c.status,
            }
            for c in cands
        ],
        "note": (
            "候选只是**归纳产物**，未经验证。要安装必须先过审核闸门，"
            "且只进副本区（storage_data/skill_staging/），实测通过后才能进正式库。"
        ),
    }


@app.post("/candidates/{candidate_id}/install")
async def install_candidate(candidate_id: str, req: InstallCandidateRequest):
    """审核并装进**副本区**（不动正式库）。

    审核是程序判据：证据量、分数阈值、验证模板完整性、参数是否已命名等。
    未通过则返回 400 并列出具体拦截点——不静默丢弃。
    """
    from core import CandidateStore
    from core.promote import StagingStore, install_to_staging

    cand = CandidateStore().get(candidate_id)
    if cand is None:
        raise HTTPException(404, f"候选不存在: {candidate_id}")

    skill, result = install_to_staging(
        cand, skill_id=req.skill_id, name=req.name,
        renamed=req.renamed, staging=StagingStore(), force=req.force,
    )
    payload = {
        "installed": skill is not None,
        "audit": result.to_dict(),
        "explain": result.explain(),
        "staging_id": req.skill_id if skill is not None else None,
        "note": "只进了副本区；实测通过后才允许提升到正式库。",
    }
    if skill is None:
        return JSONResponse(status_code=400, content=payload)
    return payload


@app.post("/candidates/{candidate_id}/promote")
async def promote_candidate(candidate_id: str, skill_id: str, proven: bool = False):
    """把副本提升到正式库。**proven 必须来自真实重放结果。**"""
    from core.promote import promote_staging_to_live

    ok, msg = promote_staging_to_live(skill_id, proven=proven)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg, "skill_id": skill_id}


@app.get("/reflect")
async def reflect_endpoint(limit_cycles: int = 20):
    """反思报告：从历史执行里提取可复用的模式。

    **只读、只建议，不会自动应用任何修改。** 分析全部由程序完成（不经过模型），
    因此结论可信、可复现。返回结构化 patterns + 可直接阅读的 markdown。
    """
    from core import reflect_from_storage

    try:
        report = reflect_from_storage(limit_cycles=max(1, min(limit_cycles, 100)))
    except Exception as e:
        raise HTTPException(500, f"反思分析失败: {e}")

    return {
        "cycles_analyzed": report.cycles_analyzed,
        "summary": report.summary,
        "pattern_count": len(report.patterns),
        "by_confidence": {
            level: len(report.by_confidence(level)) for level in ("high", "medium", "low")
        },
        "patterns": [p.to_dict() for p in report.patterns],
        "markdown": report.to_markdown(),
        "note": "只读分析，仅供参考；不会自动修改 prompt / 预算 / 代码。",
    }


@app.get("/")
async def root():
    return {
        "status": "Coding Agent is running",
        "endpoints": ["/run", "/encode", "/profile", "/reflect", "/decisions"],
    }


@app.get("/profile")
async def profile():
    """暴露当前生效的模型接入参数，便于换模型时确认预算是否符合预期。"""
    profiles = resolve_profiles()
    return {
        "checkpoint_backend": {
            "selected": CheckpointManager().name,
            "git": get_git_status(),
        },
        "decision_channel": {
            **channel_status(),
            "approval_base_url": _approval_base_url(),
            "approval_token_required": bool((os.getenv("AGENT_APPROVAL_TOKEN") or "").strip()),
            "pending": len(DecisionManager().pending()),
        },
        # 角色表：未配置的角色**如实显示为未启用**，不会静默顶替
        "roles": describe_roles(),
        "models": {
            role: {
                "profile": prof.name,
                "model": prof.model,
                "base_url": prof.base_url,
                "context_window": prof.capabilities.context_window,
                "supports_tool_calls": prof.capabilities.supports_tool_calls,
                "supports_json_mode": prof.capabilities.supports_json_mode,
                "coupling": prof.coupling.notes or "none",
                "limits": {
                    "max_tokens": prof.limits.max_tokens,
                    "max_rounds": prof.limits.max_rounds,
                    "max_steps": prof.limits.max_steps,
                    "max_attempts": prof.limits.max_attempts,
                    "max_errors": prof.limits.max_errors,
                    "max_same_task": prof.limits.max_same_task,
                    "tool_result_chars": prof.limits.tool_result_chars,
                },
                "problems": prof.validate(role=role),
            }
            for role, prof in profiles.items()
        },
    }
