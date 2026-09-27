"""Agent Web API：给 Vue 前端用的 JSON + SSE 接口。

与既有接口的关系
----------------
`main.py` 里的 `POST /encode` 是**一次性阻塞**接口，契约已冻结，本模块不去动它。
这里新增的 `/api/*` 是给前端用的**异步可订阅**版本：

    POST /api/runs            起一次运行，立刻返回 run_id（不阻塞）
    GET  /api/runs/{id}/stream  SSE 实时事件流（可断线续传，靠 seq 续订）

为什么用 SSE 而不是 WebSocket
-----------------------------
数据是**单向**的（服务端→浏览器），SSE 原生支持自动重连与 `Last-Event-ID`
续传，且能直接复用 HTTP 的 CORS/代理配置。双向通道在这里没有需求，
引入 WebSocket 只是多一份握手与心跳要维护。
"""

import asyncio
import json
import os
import sys
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .actions import approval_base_url as default_approval_base_url
from .factory import profile_snapshot, resolve_profiles
from .runner import RunNotFound, run_manager

router = APIRouter(prefix="/api", tags=["agent-api"])

from . import paths
from .paths import WORKSPACE_DIR

# SSE 轮询间隔：本地文件读取很便宜，250ms 足够「实时」，又不至于把 CPU 打满
SSE_POLL_SECONDS = 0.25
# 心跳间隔：中间有反代时不至于被判超时
SSE_HEARTBEAT_SECONDS = 15.0


# ============================================================
# 请求模型
# ============================================================
class StartRunRequest(BaseModel):
    goal: str = Field(..., description="目标描述")
    verify_command: str | None = Field(
        None, description="机器可判定的验证命令（一段 Python，退出码为 0 即通过）"
    )
    session_id: str = "default"
    max_attempts: int = 2
    on_decision: str = "auto"          # auto | notify | wait
    max_consecutive_failures: int = 2
    demo: bool = Field(False, description="演示运行：不调用模型，播放脚本事件序列")
    approval_base_url: str = ""


class AnswerRequest(BaseModel):
    value: str
    by: str = "webui"


class AuditRequest(BaseModel):
    """前端上报它「按什么写死的」。

    字段名取契约 `client_report_schema.canonical_fields`，
    由前端**构建期从源码生成**（`frontend/src/generated/expectations.ts`），
    不是手写的——手写的一定会漂，那时审查会给出错误的责任判定。

    ★ **事件与阶段必须按来源分开报**（契约 gap_G2 / gap_G3）：
    平铺上报会让上游对 bridge 自产的事件、自补的门禁节点报"上游没有"，
    把 frontend 的问题判成 backend。

    字段全部可选（契约 `absence_policy`）：少给只降低归因精度，不报错。
    """

    # ---- 契约 canonical 字段 ----
    contract_version: str = ""
    schema_version: str = ""
    upstream_event_kinds: list[str] = Field(default_factory=list)
    frontend_event_kinds: list[str] = Field(default_factory=list)
    phases: list[str] = Field(default_factory=list)
    bridge_gate_steps: list[str] = Field(default_factory=list)
    report_keys: list[str] = Field(default_factory=list)
    upstream_endpoints: list[str] = Field(default_factory=list)
    frontend_endpoints: list[str] = Field(default_factory=list)

    #: 【观测】运行态事实（契约 v1.0.2 的第 9 个字段）。
    #:
    #: ★ **接收但不采信**，理由如下（契约 `client_report_schema.ops_report_constraint`）：
    #: 本端点是**同步**的 —— 请求能成功到达，就等于证明服务可达。所以客户端
    #: 在这里报 `service_down` 是自相矛盾的；而 `ops` 在判定里**优先**，
    #: 一条陈旧标志会压掉其余全部结论。
    #:
    #: 该语义在契约里状态为 `AWAITING_SIDE_CONFIRMATION`（三选项待后端确认），
    #: 因此这里只**收下并如实报告**，不参与 verdict（见 audit.py 的 info 条目）。
    #: 未知事实名一律忽略——契约要求 additive 安全。
    #:
    #: 本仓库前端**当前不上报**这个字段（工作单明示：语义未定前不要照着实现）。
    ops: dict[str, bool] = Field(default_factory=dict)

    #: bridge 内部修订号。**非契约字段**（契约 version_axes：SPEC_VERSION 与兼容性无关）
    spec_version: str = ""

    # ---- 旧格式（过渡期容忍）----
    #: 平铺事件列表。**无法判定来源，所以不猜**——猜了就是 G2 的错误复现。
    events: list[str] = Field(default_factory=list)
    stages: list[str] = Field(default_factory=list)
    endpoints: list[str] = Field(default_factory=list)


def _is_legacy_report(req: "AuditRequest") -> bool:
    """旧格式：给了平铺字段，却没给任何 canonical 字段。"""
    legacy = bool(req.events or req.stages or req.endpoints)
    canonical = bool(
        req.upstream_event_kinds or req.frontend_event_kinds
        or req.phases or req.upstream_endpoints or req.contract_version
    )
    return legacy and not canonical


def _client_from_request(req: "AuditRequest") -> dict:
    return {
        "contract_version": req.contract_version,
        "schema_version": req.schema_version,
        "upstream_event_kinds": req.upstream_event_kinds,
        "frontend_event_kinds": req.frontend_event_kinds,
        "phases": req.phases,
        "bridge_gate_steps": req.bridge_gate_steps,
        "report_keys": req.report_keys,
        "upstream_endpoints": req.upstream_endpoints,
        "frontend_endpoints": req.frontend_endpoints,
        "ops": dict(req.ops or {}),
        "spec_version": req.spec_version,
    }


# ============================================================
# 责任自审查
# ============================================================
def _collect_audit_inputs(request: Request):
    """把自审查需要的三样东西凑齐：上游契约、挂钩、真实路由。"""
    from . import contract as contract_mod
    from . import hooks as hooks_mod

    try:
        contract_report = contract_mod.check()
    except Exception as e:  # noqa: BLE001
        contract_report = None
        print(f"[bridge] 契约自检失败（已忽略）: {e}", file=sys.stderr)

    try:
        hooks_report = hooks_mod.report()
    except Exception:  # noqa: BLE001
        hooks_report = None

    routes = {
        getattr(r, "path", "")
        for r in getattr(request.app, "routes", [])
        if getattr(r, "path", "").startswith("/api/")
    }
    return contract_report, hooks_report, routes


@router.get("/audit")
async def audit_get(request: Request) -> dict:
    """**服务自审**：我声明的，我真的做到了吗？

    不传前端期望时只审自洽性——「声明了却不做」「声明了端点没注册」
    这类问题在这里就能抓出来。
    """
    from .audit import run as run_audit
    from .spec import build_spec

    spec = build_spec()
    contract_report, hooks_report, routes = _collect_audit_inputs(request)
    result = run_audit(
        spec, None,
        contract_report=contract_report,
        hooks_report=hooks_report,
        routes=routes,
        frontend_built=os.path.isdir(paths.FRONTEND_DIST),
    )
    return result.to_dict()


@router.post("/audit")
async def audit_post(request: Request, req: AuditRequest) -> dict:
    """**责任自审查**：前端报上它的期望，服务判「该谁改」。

    判定分界线（详见 `bridge/audit.py`）：

        服务声明了 X，前端不认识 X   → **frontend**（服务守约了）
        服务声明了 X，实际不做 X     → **backend**（自相矛盾）
        服务不可达 / 前端没构建      → **ops**
        无法从事实源单方面判定       → **both**（需人工协商）

    归属边界由 `.interface_contract` 定义：**`bridge/` 属于 frontend**。

    前端在启动时调这个，把结论显示出来——**不需要人去比对两份定义**。
    """
    from .audit import Issue, run as run_audit
    from .spec import build_spec

    spec = build_spec()
    contract_report, hooks_report, routes = _collect_audit_inputs(request)

    legacy = _is_legacy_report(req)
    # 旧格式无法判定事件来源 → **不猜**。
    # 猜了就会复现契约里 G2 的错误：把 bridge 自产事件当成上游事件上报，
    # 于是上游报 21 条 P-event-gone-upstream，结论从 ok 掉到 need-negotiation。
    client = None if legacy else _client_from_request(req)

    result = run_audit(
        spec, client,
        contract_report=contract_report,
        hooks_report=hooks_report,
        routes=routes,
        frontend_built=os.path.isdir(paths.FRONTEND_DIST),
        client_legacy_shape=legacy,
    )
    if legacy:
        result.issues.append(Issue(
            id="frontend.legacy_report_shape", owner="frontend", severity="info",
            title="上报体是旧格式（平铺 events/stages/endpoints）",
            detail=("无法判定事件的发出方，因此**没有做兼容性比对**——"
                    "猜来源会把 frontend 的问题判给 backend（契约 gap_G2/G3）。"),
            fix="重新构建前端（npm run build），上报体会改成契约的 canonical 字段",
        ))
    payload = result.to_dict()
    payload["markdown"] = result.to_markdown()
    return payload


# ============================================================
# 服务状态
# ============================================================
@router.get("/spec")
async def get_spec() -> dict:
    """★ 标定方案：后端把「自己长什么样」声明出来，前端照单渲染。

    前端**不应该**写死任何后端事实——阶段名、事件词表、工具名、状态色都在这里。
    加一个阶段 / 加一个事件 / 加一个工具，前端不用改一行。

    里面的事实是**从代码扫出来的**（上游 `PHASE_ORDER`、AST 扫事件、`TOOLS_MAP`），
    不是手写的，所以不会漂移；只有「中文名、色调」这类**标定**是可改的，
    也可以通过仓库根的 `spec.override.json` 覆盖。
    """
    from .spec import build_spec

    return build_spec()


@router.get("/health")
async def health() -> dict:
    """前端顶栏用：一眼看出后端到底行不行。

    ★ 架构清单 A2：**必须暴露 `backend_dir` 与 `backend_is_bundled`**。
    理由（实测）：仓库自带的 `backend/` 副本缺 `core/contract.py`，
    于是新契约机制静默不可用，而服务照常启动、界面照常显示。
    把"我在用哪份上游"变成探针可读的事实，用户才能自己发现。
    顺带给出陈旧结论（`backend_stale` / `backend_stale_reason`）。
    """
    from . import staleness

    profiles = resolve_profiles()
    orch = profiles.get("ORCH")
    problems: list[str] = []
    for role, prof in profiles.items():
        problems.extend(prof.validate(role=role))

    probe = staleness.probe(reference_dir=staleness.reference_dir_from_env() or None)

    return {
        "ok": True,
        "checkpoint_backend": profile_snapshot()["checkpoint_backend"]["selected"],
        "model": {
            "name": getattr(orch, "model", "?"),
            "base_url": getattr(orch, "base_url", "?"),
            "context_window": getattr(getattr(orch, "capabilities", None), "context_window", None),
        },
        "problems": problems,
        "runs_root": run_manager().root,
        "approval_base_url": default_approval_base_url(),
        # ---- 上游来源与陈旧检测（A2/A3）----
        # 与启动日志共用 `staleness.provenance()`，免得两处对"在跑哪一份"给出不同答案。
        "backend_dir": probe["backend_dir"],
        "backend_is_bundled": probe["is_bundled"],
        "backend_stale": probe["stale"],
        "backend_stale_reason": probe["summary"],
        "backend_core_modules": probe["core_module_count"],
        "backend_contract_version": probe["contract_version"],
        # ---- A2b：降级必须留痕 ----
        # 用了 `--allow-bundled` / `AGENT_ALLOW_BUNDLED=1` 才起得来，那就必须
        # 在探针上看得见 —— 否则逃生舱会变成一条新的静默通道，把这次的事重演一遍。
        "backend_bundled_override": bool(staleness.allow_bundled_requested()),
        # 用户要的"版本追溯性"：**我打开看到的到底是哪一版**。
        "frontend_asset": staleness.frontend_asset(),
    }


@router.get("/profile")
async def profile() -> dict:
    """与 `GET /profile` 同源，只是换成前端友好的一层包装。"""
    snap = profile_snapshot()
    snap["workspace"] = WORKSPACE_DIR
    return snap


# ============================================================
# 运行
# ============================================================
@router.post("/runs")
async def start_run(req: StartRunRequest) -> dict:
    if not req.goal.strip():
        raise HTTPException(400, "goal 不能为空")

    info = run_manager().start(
        goal=req.goal.strip(),
        verify_command=req.verify_command,
        max_attempts=req.max_attempts,
        on_decision=req.on_decision,
        max_consecutive_failures=req.max_consecutive_failures,
        session_id=req.session_id,
        approval_base_url=req.approval_base_url or default_approval_base_url(),
        demo=req.demo,
    )
    return {"ok": True, "run": info.to_dict()}


@router.get("/runs")
async def list_runs(limit: int = Query(30, ge=1, le=200)) -> dict:
    mgr = run_manager()
    items = [r.to_dict() for r in mgr.list_runs(limit=limit)]
    active = sum(1 for r in mgr.list_runs(limit=200) if not r.terminal)
    return {"count": len(items), "active": active, "runs": items}


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    try:
        info = run_manager().require(run_id)
    except RunNotFound:
        raise HTTPException(404, f"运行不存在: {run_id}")
    return {"run": info.to_dict()}


@router.delete("/runs/{run_id}")
async def cancel_run(run_id: str) -> dict:
    ok, msg = run_manager().cancel(run_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


@router.get("/runs/{run_id}/events")
async def run_events(
    run_id: str,
    after: int = Query(0, ge=0),
    limit: int = Query(2000, ge=1, le=20000),
) -> dict:
    """轮询式读取（SSE 不可用时的兜底，也方便调试）。"""
    try:
        events = run_manager().events(run_id, after_seq=after, limit=limit)
        info = run_manager().require(run_id)
    except RunNotFound:
        raise HTTPException(404, f"运行不存在: {run_id}")
    return {
        "run_id": run_id,
        "status": info.status,
        "terminal": info.terminal,
        "last_seq": events[-1]["seq"] if events else after,
        "events": events,
    }


def _sse(payload: dict, event: str | None = None, event_id: int | None = None) -> str:
    parts: list[str] = []
    if event:
        parts.append(f"event: {event}")
    if event_id is not None:
        parts.append(f"id: {event_id}")
    parts.append("data: " + json.dumps(payload, ensure_ascii=False, default=str))
    return "\n".join(parts) + "\n\n"


@router.get("/runs/{run_id}/stream")
async def stream_run(
    request: Request,
    run_id: str,
    after: int = Query(0, ge=0),
    offset: int = Query(0, ge=0),
) -> StreamingResponse:
    """SSE 实时事件流。

    `after` 用于按事件序号续订（`Last-Event-ID` 同理），
    `offset` 是文件字节偏移——两者都提供是为了让「重连」既简单又便宜：
    浏览器重连只需要带上 last_seq。
    """
    mgr = run_manager()
    try:
        mgr.require(run_id)
    except RunNotFound:
        raise HTTPException(404, f"运行不存在: {run_id}")

    async def gen() -> AsyncIterator[str]:
        nonlocal offset, after

        yield _sse({"run_id": run_id, "resumed_after": after}, event="open")

        idle = 0.0
        while True:
            if await request.is_disconnected():
                break

            events, new_offset = await asyncio.to_thread(mgr.tail, run_id, offset)
            offset = new_offset
            for ev in events:
                seq = int(ev.get("seq", 0))
                if seq <= after:
                    continue
                after = seq
                yield _sse(ev, event=str(ev.get("kind") or "event"), event_id=seq)
                idle = 0.0

            info = mgr.get(run_id)
            if info is not None and info.terminal:
                # 收尾：再读一次，确保终态事件不丢，然后关闭
                tail, offset = await asyncio.to_thread(mgr.tail, run_id, offset)
                for ev in tail:
                    seq = int(ev.get("seq", 0))
                    if seq <= after:
                        continue
                    after = seq
                    yield _sse(ev, event=str(ev.get("kind") or "event"), event_id=seq)
                yield _sse(
                    {"run_id": run_id, "status": info.status, "run": info.to_dict()},
                    event="close",
                )
                break

            idle += SSE_POLL_SECONDS
            if idle >= SSE_HEARTBEAT_SECONDS:
                idle = 0.0
                yield ": ping\n\n"
            await asyncio.sleep(SSE_POLL_SECONDS)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ============================================================
# 产物文件
# ============================================================
def _safe_workspace_path(rel: str) -> str:
    normalized = (rel or "").replace("\\", "/").lstrip("/")
    if normalized.startswith("workspace/"):
        normalized = normalized[len("workspace/"):]
    target = os.path.abspath(os.path.join(WORKSPACE_DIR, normalized))
    if target != WORKSPACE_DIR and not target.startswith(WORKSPACE_DIR + os.sep):
        raise HTTPException(400, f"非法路径: {rel}")
    return target


@router.get("/workspace/file")
async def read_workspace_file(path: str = Query(..., description="相对 workspace 的路径")) -> dict:
    target = _safe_workspace_path(path)
    if not os.path.isfile(target):
        raise HTTPException(404, f"文件不存在: {path}")
    try:
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError as e:
        raise HTTPException(500, f"读取失败: {e}")
    return {
        "path": path,
        "size": os.path.getsize(target),
        "lines": content.count("\n") + 1,
        "content": content[:200_000],
        "truncated": len(content) > 200_000,
    }


@router.get("/workspace/tree")
async def workspace_tree(limit: int = Query(400, ge=1, le=4000)) -> dict:
    """workspace 当前文件清单（不含临时目录）。"""
    out: list[dict] = []
    for root, dirs, names in os.walk(WORKSPACE_DIR):
        dirs[:] = [d for d in dirs if d not in ("_tmp", "_debug", "__pycache__", ".git")]
        for name in names:
            if name.endswith(".pyc") or name == ".gitignore":
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, WORKSPACE_DIR).replace("\\", "/")
            try:
                stat = os.stat(full)
            except OSError:
                continue
            out.append({
                "path": rel,
                "size": stat.st_size,
                "mtime": int(stat.st_mtime),
            })
            if len(out) >= limit:
                break
        if len(out) >= limit:
            break
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return {"count": len(out), "root": WORKSPACE_DIR, "files": out}


# ============================================================
# 决策（SPA 内联作答）
# ============================================================
@router.get("/decisions")
async def list_decisions(run_id: str | None = None, all: int = 0) -> dict:
    mgr = run_manager()
    if all:
        from core import DecisionManager

        raw = DecisionManager().store.list()
        items = [
            {
                "id": d.id, "kind": d.kind, "cycle_id": d.cycle_id,
                "question": d.question, "context": d.context,
                "default": d.default, "created_at": d.created_at,
                "expires_at": d.expires_at, "status": d.status, "answer": d.answer,
                "options": [o.to_dict() for o in d.options],
            }
            for d in raw
            if not run_id or d.cycle_id == run_id
        ]
    else:
        items = mgr.pending_decisions(run_id)
    return {"count": len(items), "decisions": items}


@router.post("/decisions/{decision_id}/answer")
async def answer_decision(decision_id: str, req: AnswerRequest) -> dict:
    ok, msg = run_manager().answer_decision(decision_id, req.value, by=req.by)
    if not ok:
        raise HTTPException(400, msg)
    return {"ok": True, "message": msg}


# ============================================================
# 只读分析接口（技能 / 候选 / 反思）
# ============================================================
@router.get("/insights")
async def insights() -> dict:
    """把三个只读分析入口合成一次请求，前端只发一次 HTTP。"""
    out: dict = {}

    try:
        from core import SkillStore

        skills = SkillStore().list()
        out["skills"] = {
            "count": len(skills),
            "items": [
                {
                    "id": s.id, "name": s.name, "goal_template": s.goal_template,
                    "uses": s.uses, "successes": s.successes,
                    "files": [f.path for f in s.files],
                    "problems": s.validate(),
                }
                for s in skills
            ],
        }
    except Exception as e:
        out["skills"] = {"count": 0, "items": [], "error": str(e)}

    try:
        from core import CandidateStore

        cands = CandidateStore().list()
        out["candidates"] = {
            "count": len(cands),
            "items": [
                {"candidate_id": c.candidate_id, "score": c.score,
                 "cycles": c.cycles, "shape": c.shape_desc, "status": c.status}
                for c in cands
            ],
        }
    except Exception as e:
        out["candidates"] = {"count": 0, "items": [], "error": str(e)}

    return out


@router.get("/reflect")
async def reflect(limit_cycles: int = Query(20, ge=1, le=100)) -> dict:
    from core import reflect_from_storage

    try:
        report = reflect_from_storage(limit_cycles=limit_cycles)
    except Exception as e:
        raise HTTPException(500, f"反思分析失败: {e}")
    return {
        "cycles_analyzed": report.cycles_analyzed,
        "summary": report.summary,
        "pattern_count": len(report.patterns),
        "patterns": [p.to_dict() for p in report.patterns],
        "markdown": report.to_markdown(),
    }
