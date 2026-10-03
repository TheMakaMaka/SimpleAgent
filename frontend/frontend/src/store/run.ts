/**
 * 运行状态归约器：把后端事件流翻译成「可以直接渲染的界面状态」。
 *
 * 两条设计约束
 * ------------
 * 1. **组件不该自己解析事件。** 把「事件 → 状态」集中在一处：实时流与历史回放
 *    共用同一段代码；动画需要的中间态有唯一来源。
 *
 * 2. **不写死任何后端事实。** 阶段清单、事件的中文名与色调、工具名、状态色
 *    全部来自后端标定（`GET /api/spec`，见 `@/api/spec`）。
 *    后端加一个阶段 / 一个事件 / 一个工具，这里不用改。
 *
 *    只有**语义**（哪些事件会改变界面状态）是固定的——那是前端自己的职责，
 *    标定管不着：`task_start` 要往任务列表里塞一条，`phase` 要推流水线。
 *    这类事件用 `case` 处理；**其余全部走 `renderGeneric()`**，
 *    由标定的 label/tone/模板渲染，永远不会出现裸 kind。
 */
import { computed, reactive } from 'vue'
import { config } from '@/config'
import { collectTransparency, ingestReport } from '@/store/transparency'
// 工具参数摘要的实现搬到了 `store/args.ts`（A3 面板要用同一份）。
// 这里重新导出，是为了让既有调用点（ArtifactPanel 等）不用改。
export { describeArgs } from '@/store/args'
import { describeArgs } from '@/store/args'
import {
  autoDetail,
  eventSpec,
  render,
  spec,
  statusSpec,
  toolLabel,
} from '@/api/spec'
import type {
  AgentEvent,
  AttemptView,
  CheckStepView,
  DecisionView,
  ManifestView,
  RunState,
  RunStatus,
  StageState,
  StageView,
  TaskView,
  TimelineEntry,
  ToolCallView,
  VerifyView,
} from '@/types'

/** 阶段清单来自标定。标定没加载时用兜底 spec（见 @/api/spec）。 */
export function stageDefs(): StageView[] {
  const stages = spec.pipeline?.stages ?? []
  if (stages.length) {
    return stages.map((s) => ({
      id: s.id,
      label: s.label || s.id.toUpperCase(),
      hint: s.hint || '',
      icon: s.icon || 'generic',
      state: 'idle' as StageState,
    }))
  }
  // 极端情况：spec 连兜底都没有。让流水线至少有"失败"以外的可渲染内容。
  return []
}

function freshStages(): StageView[] {
  return stageDefs()
}

export function createInitialState(): RunState {
  return {
    runId: null,
    goal: '',
    status: 'queued',
    demo: false,
    connected: 'idle',
    startedAt: 0,
    endedAt: null,
    attempt: 0,
    maxAttempts: 2,
    stages: freshStages(),
    attempts: [],
    tasks: [],
    currentTaskId: null,
    toolCalls: [],
    checks: [],
    files: [],
    manifest: null,
    verify: null,
    verifyProbes: 0,
    verifySkipped: [],
    rounds: 0,

    // TRANSPARENCY-UI：四块「为什么」视图的初值。
    // 注意 `selfReport` 的初值是 **null 而不是空对象** —— 空对象会被渲染成
    // "有自述、内容为空"，那是把"没有"说成了"空"。见 selfReportAbsentReason。
    decisionRounds: [],
    modelTurns: [],
    criteria: [],
    selfReport: null,
    selfReportAbsentReason: '',
    factCheck: null,
    outcome: { value: 'unknown', raw: '', source: '', reason: '', legacyVocabulary: false },
    // P3/P4：后端**权威**的结局与两条机械关卡的结论（都由报告/事件带来，取不到就是 null）
    verdict: null,
    decomposeReview: null,
    reuse: null,
    transparencySeq: 0,

    steps: 0,
    modelReplies: 0,
    events: 0,
    rollbacks: 0,
    decisions: [],
    timeline: [],
    reasoning: [],
    error: '',
    answer: '',
    commit: '',
    phaseKey: 0,
  }
}

/**
 * 事件的色调来自标定，不再写死在这里。
 * 标定没给就用 info —— 界面永远不会因为后端加事件而崩。
 */
function toneOf(kind: string): TimelineEntry['tone'] {
  const tone = eventSpec(kind)?.tone
  const known: TimelineEntry['tone'][] = ['info', 'ok', 'warn', 'error', 'model', 'tool', 'phase']
  return (known as string[]).includes(tone ?? '') ? (tone as TimelineEntry['tone']) : 'info'
}

/**
 * 通用渲染：**没有专门 `case` 的事件全部走这里**。
 *
 * 标题/详情优先用标定里的模板（`"调用 {tool}"`），没模板就自动从 payload
 * 里挑一个可读字段。结果是：后端加事件，前端不写一行也能显示得像样，
 * 而不是出现标题为 `review_start` 的裸文本行。
 */
function renderGeneric(kind: string, payload: Record<string, unknown>) {
  const s = eventSpec(kind)
  const limit = config.limits.detailChars
  const title = s?.title
    ? render(s.title, payload)
    : s?.label
      ? render(s.label, payload)
      : kind
  const detail = s?.detail
    ? render(s.detail, payload)
    : autoDetail(payload, limit)
  return {
    title,
    detail: detail && detail !== title ? detail : '',
    tone: toneOf(kind),
  }
}

function clockOf(ts?: string): string {
  if (!ts) return new Date().toLocaleTimeString('zh-CN', { hour12: false })
  const m = /(\d{2}):(\d{2}):(\d{2})/.exec(ts)
  return m ? `${m[1]}:${m[2]}:${m[3]}` : ts.slice(11, 19)
}

/**
 * 后端时间戳 → 毫秒。
 *
 * 回放历史运行时必须用**事件自己的时间**，否则「耗时」会显示成 0.0s
 * （所有历史事件都是同一瞬间被喂进来的）。实时流则用本地时钟，
 * 精度更高、也不受两台机器时钟差影响。
 */
function tsToMs(ts?: string): number {
  if (!ts) return Date.now()
  const t = Date.parse(ts)
  return Number.isFinite(t) ? t : Date.now()
}

function push(
  state: RunState,
  now: number,
  entry: Omit<TimelineEntry, 'seq' | 'at' | 'clock'> & { seq?: number; ts?: string },
) {
  state.timeline.unshift({
    seq: entry.seq ?? 0,
    at: now,
    clock: clockOf(entry.ts),
    kind: entry.kind,
    tone: entry.tone,
    title: entry.title,
    detail: entry.detail,
  })
  if (state.timeline.length > config.limits.timeline) {
    state.timeline.length = config.limits.timeline
  }
}

/**
 * 取阶段下标；**标定里没有的阶段会动态补一个**。
 *
 * 这是「预留接口」的落地：上游加了新阶段（比如 REVIEW）而标定还没更新时，
 * 它会作为新节点出现在流水线上（label 用 id 大写），而不是被静默丢掉。
 * 悄悄少一个阶段，比多一个长得丑的节点危险得多。
 */
function stageIndexOf(state: RunState, id: string): number {
  const idx = state.stages.findIndex((s) => s.id === id)
  if (idx !== -1) return idx
  state.stages.push({
    id,
    label: id.toUpperCase(),
    hint: '（标定里未声明，按运行时补上）',
    state: 'idle',
  })
  return state.stages.length - 1
}

function setStage(state: RunState, id: string, next: StageState) {
  state.stages[stageIndexOf(state, id)].state = next
}

/** 当前正在进行的阶段（用于「失败时把红灯打在正确的节点上」） */
function activeStageId(state: RunState): string | null {
  const found = state.stages.find((s) => s.state === 'active')
  return found ? found.id : null
}

function markAllBefore(state: RunState, id: string) {
  const idx = stageIndexOf(state, id)
  for (let i = 0; i < idx; i++) {
    if (state.stages[i].state === 'idle' || state.stages[i].state === 'active') {
      state.stages[i].state = 'done'
    }
  }
}

function startAttempt(state: RunState, attempt: number, maxAttempts: number, now: number) {
  state.attempt = attempt
  state.maxAttempts = maxAttempts || state.maxAttempts
  state.stages = freshStages()
  state.phaseKey += 1
  state.checks = []
  const view: AttemptView = {
    index: attempt,
    status: 'running',
    stages: freshStages(),
    error: '',
    startedAt: now,
    endedAt: null,
    rolledBack: false,
  }
  const existing = state.attempts.findIndex((a) => a.index === attempt)
  if (existing === -1) state.attempts.push(view)
  else state.attempts[existing] = view
}

/**
 * 结束一次尝试。
 *
 * `now` **刻意不给默认值**：它必须来自触发结束的那条事件。用 `Date.now()` 兜底
 * 会让回放历史时「耗时」变成「从事件发生到现在过了多久」——这是一个已经踩过的坑。
 */
function finishAttempt(
  state: RunState,
  attempt: number,
  status: AttemptView['status'],
  error: string,
  now: number,
) {
  let view = state.attempts.find((a) => a.index === attempt)
  if (!view) {
    view = {
      index: attempt,
      status,
      stages: freshStages(),
      error,
      startedAt: now,
      endedAt: now,
      rolledBack: false,
    }
    state.attempts.push(view)
  }
  view.status = status
  view.error = error
  view.endedAt = now
  view.stages = state.stages.map((s) => ({ ...s }))
}

function currentTask(state: RunState): TaskView | null {
  return lastTask(state, state.currentTaskId)
}

/** 取该 id 最近一次出现的任务（任务 id 会在每次尝试中复用）。 */
function lastTask(state: RunState, id: string | null): TaskView | null {
  if (!id) return null
  for (let i = state.tasks.length - 1; i >= 0; i--) {
    if (state.tasks[i].id === id) return state.tasks[i]
  }
  return null
}

/**
 * 事件 → 状态。
 *
 * `now` 是这条事件在**界面上**对应的时间点：
 *   - 实时流：本地时钟（精度高）
 *   - 历史回放：事件自带的 ts（否则耗时恒为 0）
 */
export function applyEvent(state: RunState, ev: AgentEvent, now: number = Date.now()): void {
  state.events += 1
  const kind = String(ev.kind || '')
  const attempt = Number(ev.attempt ?? state.attempt ?? 1)

  // 透明化视图（A2/A3/B4/C3/D3）先采一遍。它**声明**自己渲染的事件
  // （目前只有后端尚未交付的 `self_report`/`fact_check`）由它出时间线行，
  // 其余一律返回 null，照旧走下面的 switch —— 所以既有的渲染没有被挪动。
  const claimed = collectTransparency(state, ev, now)
  if (claimed) {
    push(state, now, claimed)
    return
  }

  switch (kind) {
    case 'queued': {
      state.status = 'queued'
      state.goal = String(ev.goal ?? state.goal)
      state.demo = Boolean(ev.demo)
      push(state, now, { kind, tone: 'info', title: '已入队', detail: '等待工作线程接管' })
      break
    }

    case 'run_start': {
      state.status = 'running'
      state.startedAt = now
      state.maxAttempts = Number(ev.max_attempts ?? state.maxAttempts)
      state.goal = String(ev.goal ?? state.goal)
      push(state, now, {
        kind,
        tone: 'info',
        title: '开始执行',
        detail: `检查点后端 ${ev.backend ?? '?'} · 最多 ${ev.max_attempts ?? '?'} 次尝试`,
      })
      break
    }

    case 'baseline': {
      push(state, now, {
        kind,
        tone: 'info',
        title: '记录基线检查点',
        detail: String(ev.ref || '（无可用后端）'),
      })
      break
    }

    case 'cycle_start': {
      const prior = (ev.prior_files as string[]) || []
      push(state, now, {
        kind,
        tone: 'info',
        title: 'cycle 开始',
        detail: prior.length ? `工作区已有 ${prior.length} 个文件` : '工作区为空',
      })
      break
    }

    case 'attempt_start': {
      startAttempt(state, attempt, Number(ev.max_attempts ?? state.maxAttempts), now)
      push(state, now, {
        kind,
        tone: 'phase',
        title: `第 ${attempt} / ${ev.max_attempts ?? state.maxAttempts} 次尝试`,
        detail: '阶段流水线已重置',
        seq: ev.seq,
        ts: ev.ts,
      })
      break
    }

    case 'retry': {
      state.rollbacks += 0 // 回退单独计数
      push(state, now, {
        kind,
        tone: 'warn',
        title: `准备重试（第 ${attempt} 次）`,
        detail: String(ev.reason || '').slice(0, 300),
        seq: ev.seq,
        ts: ev.ts,
      })
      break
    }

    case 'phase': {
      const phase = String(ev.phase || '')
      if (phase === 'failed') {
        const active = activeStageId(state)
        if (active) setStage(state, active, 'failed')
        finishAttempt(state, attempt, 'failed', state.error, now)
        push(state, now, {
          kind,
          tone: 'error',
          title: '本阶段失败',
          detail: state.error || '未通过门禁',
          seq: ev.seq,
          ts: ev.ts,
        })
        break
      }
      markAllBefore(state, phase)
      if (phase === 'write') {
        // MANIFEST 是程序步骤，不产生 phase 事件；在 write 完成后先标为待命
        setStage(state, 'manifest', 'idle')
      }
      setStage(state, phase, 'active')
      push(state, now, {
        kind,
        tone: 'phase',
        title: `进入 ${phase.toUpperCase()}`,
        detail: stageHint(phase),
        seq: ev.seq,
        ts: ev.ts,
      })
      break
    }

    case 'round_start': {
      state.rounds = Math.max(state.rounds, Number(ev.round ?? 0))
      push(state, now, {
        kind,
        tone: 'info',
        title: `主循环第 ${ev.round} 轮`,
        detail: `上限 ${ev.max_rounds} 轮`,
        seq: ev.seq,
        ts: ev.ts,
      })
      break
    }

    case 'orchestrator_decision': {
      state.reasoning.unshift({
        round: Number(ev.round ?? 0),
        text: String(ev.reasoning || ev.final_answer || ''),
        status: String(ev.status || ''),
        at: now,
      })
      if (state.reasoning.length > config.limits.reasoning) {
        state.reasoning.length = config.limits.reasoning
      }
      push(state, now, {
        kind,
        tone: 'model',
        // ★ 是**编排器**的决策，不是"主模型"。事件名就叫 `orchestrator_decision`，
        //   而这里原先写成「主模型决策」——透明化先说清"这是谁在说话"。
        title: `编排器决策 → ${ev.status}`,
        detail: String(ev.reasoning || ev.final_answer || '').slice(0, 400),
        seq: ev.seq,
        ts: ev.ts,
      })
      break
    }

    // 上游 `_emit` 自带的事件。bridge 的挂钩把它们原样透传过来，
    // 所以这三个也必须翻译——漏了的话时间线上会出现标题就是
    // `plan` / `task_result` / `decision_notified` 的裸文本行。
    // （这件事由 tests/unit/test_event_contract.py 把守。）
    case 'plan': {
      const declared = ((ev.declared as any[]) || []).map((d) =>
        typeof d === 'string' ? d : String(d?.path ?? ''),
      )
      push(state, now, {
        kind,
        tone: 'info',
        title: `计划：${ev.tasks ?? 0} 个任务，声明交付 ${declared.length} 个文件`,
        detail:
          (declared.length ? declared.join(', ') : '（未声明文件清单）') +
          (ev.verify_command ? `\n验收命令：${String(ev.verify_command).slice(0, 200)}` : ''),
        seq: ev.seq,
        ts: ev.ts,
      })
      break
    }

    case 'task_result': {
      // 模型自述的任务结果。在压缩层里它只能算 assumed（未被程序校验），
      // 这里照实显示，但色调与门禁事件区分开。
      push(state, now, {
        kind,
        tone: ev.ok ? 'info' : 'warn',
        title: `任务 ${ev.task_id} 自述：${ev.ok ? '完成' : '未完成'}`,
        detail: String(ev.error || ev.output || '').slice(0, 300),
        seq: ev.seq,
        ts: ev.ts,
      })
      break
    }

    case 'decision_notified': {
      push(state, now, {
        kind,
        tone: ev.ok === false ? 'warn' : 'info',
        title: `决策已推送（通道 ${ev.channel ?? '?'}）`,
        detail: ev.ok === false
          ? `推送失败：${String(ev.detail || '')} —— 流程不会挂死，将采用保守默认动作`
          : String(ev.detail || ''),
        seq: ev.seq,
        ts: ev.ts,
      })
      break
    }

    case 'task_start': {
      const id = String(ev.task_id || '?')
      state.currentTaskId = id
      state.tasks.push({
        id,
        description: String(ev.description || ''),
        status: 'running',
        steps: 0,
        maxSteps: 0,
        toolHint: (ev.tool_hint as string[]) || [],
      })
      push(state, now, {
        kind,
        tone: 'info',
        title: `派发任务 ${id}`,
        detail: String(ev.description || ''),
        seq: ev.seq,
        ts: ev.ts,
      })
      break
    }

    case 'worker_step': {
      state.steps += 1
      const t = currentTask(state)
      if (t) {
        t.steps = Number(ev.step ?? t.steps)
        t.maxSteps = Number(ev.max_steps ?? t.maxSteps)
      }
      break // 步骤太密，不进时间线
    }

    case 'model_reply': {
      state.modelReplies += 1
      push(state, now, {
        kind,
        tone: 'model',
        title: `子模型响应（${ev.tool_calls ?? 0} 个工具调用）`,
        detail: String(ev.content || '').slice(0, 300) || '（仅工具调用）',
        seq: ev.seq,
        ts: ev.ts,
      })
      break
    }

    case 'tool_call': {
      const call: ToolCallView = {
        key: `${ev.task_id}-${ev.step}-${state.toolCalls.length}`,
        taskId: String(ev.task_id || ''),
        step: Number(ev.step ?? 0),
        tool: String(ev.tool || ''),
        args: (ev.args as Record<string, unknown>) || {},
        status: 'running',
        at: now,
      }
      state.toolCalls.unshift(call)
      if (state.toolCalls.length > config.limits.toolCalls) {
        state.toolCalls.length = config.limits.toolCalls
      }
      push(state, now, {
        kind,
        tone: 'tool',
        title: `调用 ${call.tool}`,
        detail: describeArgs(call.tool, call.args),
        seq: ev.seq,
        ts: ev.ts,
      })
      break
    }

    case 'tool_result': {
      const call = state.toolCalls.find((c) => c.tool === ev.tool && c.status === 'running')
      if (call) {
        call.status = ev.ok === false ? 'error' : 'ok'
        call.preview = String(ev.preview || '')
      }
      push(state, now, {
        kind,
        tone: ev.ok === false ? 'error' : 'tool',
        title: `${ev.tool} ${ev.ok === false ? '出错' : '返回'}`,
        detail: String(ev.preview || '').slice(0, 300),
        seq: ev.seq,
        ts: ev.ts,
      })
      break
    }

    case 'task_done': {
      const id = String(ev.task_id || '')
      // 任务 id 会在每次尝试里复用（t1、t2…），所以必须命中**最新**的那个，
      // 否则上一轮的 t1 被标记完成，本轮的同名任务会一直挂在「进行中」。
      const t = lastTask(state, id)
      if (t) {
        t.status = ev.ok ? 'done' : 'failed'
        t.ok = Boolean(ev.ok)
        t.output = String(ev.output || '')
        t.error = String(ev.error || '')
      }
      push(state, now, {
        kind,
        tone: ev.ok ? 'ok' : 'error',
        title: `任务 ${id} ${ev.ok ? '完成' : '失败'}`,
        detail: String(ev.error || ev.output || '').slice(0, 300),
        seq: ev.seq,
        ts: ev.ts,
      })
      break
    }

    case 'files': {
      const list = (ev.touched as string[]) || []
      state.files = Array.from(new Set([...state.files, ...list]))
      push(state, now, {
        kind,
        tone: 'info',
        title: `本轮产物 ${list.length} 个文件`,
        detail: list.join(', ') || '（无）',
        seq: ev.seq,
        ts: ev.ts,
      })
      break
    }

    case 'manifest': {
      const violations = ((ev.violations as any[]) || []).map((v) => ({
        kind: String(v.kind || ''),
        path: String(v.path || v.from || ''),
        message: String(v.message || ''),
      }))
      const view: ManifestView = {
        checked: Boolean(ev.checked),
        passed: Boolean(ev.passed),
        violations,
        // 后端的 actual_files 是符号索引条目（含 symbols/sha1），这里只取路径。
        // 它只用于展示「实际产出几个文件」，把结构事实留在后端。
        actualFiles: ((ev.actual_files as any[]) || [])
          .map((f) => (typeof f === 'string' ? f : String(f?.path ?? '')))
          .filter(Boolean),
        at: now,
      }
      state.manifest = view
      setStage(state, 'manifest', view.passed ? 'done' : 'failed')
      setStage(state, 'write', 'done')
      push(state, now, {
        kind,
        tone: view.passed ? 'ok' : 'error',
        title: view.passed ? '交付清单通过' : '交付清单未通过',
        detail: view.passed
          ? `实际产出 ${view.actualFiles.length} 个文件`
          : violations.map((v) => `${v.kind}: ${v.path}`).join('；'),
        seq: ev.seq,
        ts: ev.ts,
      })
      break
    }

    case 'syntax':
    case 'lint': {
      const step: CheckStepView = {
        path: String(ev.path || ''),
        tool: kind as 'syntax' | 'lint',
        status:
          kind === 'syntax'
            ? ev.ok
              ? 'passed'
              : 'failed'
            : (String(ev.status || 'passed') as CheckStepView['status']),
        message: String(ev.message || ev.reason || ''),
        issues: ((ev.issues as any[]) || []).map((i) => String(i)),
      }
      state.checks.push(step)
      if (step.status === 'failed') setStage(state, 'check', 'failed')
      push(state, now, {
        kind,
        tone: step.status === 'failed' ? 'error' : step.status === 'skipped' ? 'warn' : 'ok',
        title:
          kind === 'syntax'
            ? `语法检查 ${step.path} ${step.status === 'passed' ? '通过' : '失败'}`
            : `lint ${step.path} ${statusLabel(step.status)}`,
        detail: step.message || step.issues.join('；'),
        seq: ev.seq,
        ts: ev.ts,
      })
      break
    }

    case 'verify_skipped': {
      // 上游 `FIX-VERIFY-WIRING` 加性新增的事件：把「有验证命令、却没有 pipeline，
      // 于是验证回流整块被跳过」变成一条**显式事实**。
      //
      // ★ 为什么单独立一个 case，而不是让它走默认分支：
      //   默认分支只会渲染成一行裸文本，而这条恰恰是**最需要被看见**的那种 ——
      //   静默跳过会让上层（和人）误诊成"缺少验证命令"，把定位带偏一整轮。
      //   `reason` 最长 600 字，所以时间线里截断显示，完整值进 `verifySkipped`。
      const reason = String(ev.reason || '（未给原因）')
      const command = String(ev.command || '')
      state.verifySkipped.push(command ? `${reason}〔命令：${command}〕` : reason)
      push(state, now, {
        kind,
        tone: 'warn',
        title: '⚠ 验证被跳过',
        detail: reason.slice(0, 400),
        seq: ev.seq,
        ts: ev.ts,
      })
      break
    }

    case 'verify_probe': {
      state.verifyProbes += 1
      push(state, now, {
        kind,
        tone: ev.passed ? 'ok' : 'warn',
        title: `循环内验证回流 → ${ev.passed ? '通过' : '未通过'}`,
        detail: String(ev.detail || '').slice(0, 300),
        seq: ev.seq,
        ts: ev.ts,
      })
      break
    }

    case 'verify': {
      const view: VerifyView = {
        passed: Boolean(ev.passed),
        detail: String(ev.detail || ''),
        command: String(ev.command || ''),
        files: [],
        at: now,
      }
      state.verify = view
      setStage(state, 'verify', view.passed ? 'done' : 'failed')
      push(state, now, {
        kind,
        tone: view.passed ? 'ok' : 'error',
        title: `验收命令 ${view.passed ? '退出码 0 ✓' : '未通过'}`,
        detail: view.detail.slice(0, 400),
        seq: ev.seq,
        ts: ev.ts,
      })
      break
    }

    case 'rollback': {
      state.rollbacks += 1
      const a = state.attempts.find((x) => x.index === attempt)
      if (a) a.rolledBack = true
      push(state, now, {
        kind,
        tone: 'warn',
        title: '已回退到基线',
        detail: `ref=${ev.ref} · ${ev.ok ? '成功' : '失败'}`,
        seq: ev.seq,
        ts: ev.ts,
      })
      break
    }

    case 'rollback_denied': {
      push(state, now, { kind, tone: 'warn', title: '未获准回退', detail: '保留当前改动', seq: ev.seq })
      break
    }

    case 'decision_opened': {
      state.decisions.unshift({
        id: String(ev.decision_id || ''),
        // ★ 决策种类读 `decision_kind`，**不是** `ev.kind`。
        //
        // `ev.kind` 是**事件类型**（`'decision_opened'`）—— 它由 runner 的记录
        // 构造决定：`{seq, ts, kind, **payload}`，`**payload` 在 `kind` **之后**
        // 展开。所以上游原先在 payload 里也叫 `kind` 时，它**覆盖**了事件类型，
        // `ev.kind` 才是决策种类；上游把 payload 键改名 `decision_kind` 之后，
        // 覆盖不再发生，`ev.kind` 变回事件类型 —— 这里就会把决策种类显示成
        // `'decision_opened'`。
        //
        // 顺带一提：那次改名同时**修好了**上面的 `switch (kind)` ——
        // 覆盖存在时 `case 'decision_opened'` 根本匹配不上，这个分支是死的。
        kind: String(ev.decision_kind || ''),
        question: String(ev.question || ''),
        default: String(ev.default || ''),
        expires_at: '',
        options: ((ev.options as string[]) || []).map((v) => ({
          value: String(v),
          label: String(v),
          hint: '',
          danger: v === 'relax' || v === 'allow',
        })),
        context: {},
      })
      push(state, now, {
        kind,
        tone: 'warn',
        title: '打开人工决策点',
        detail: String(ev.question || ''),
        seq: ev.seq,
        ts: ev.ts,
      })
      break
    }

    case 'decision_action': {
      push(state, now, {
        kind,
        tone: 'warn',
        title: `人工决策生效：${ev.action}`,
        detail: '',
        seq: ev.seq,
        ts: ev.ts,
      })
      break
    }

    case 'cycle_end': {
      const status = String(ev.status || 'failed')
      state.error = String(ev.error || '')
      state.commit = String(ev.commit || '')
      const map: Record<string, AttemptView['status']> = {
        passed: 'passed',
        failed: 'failed',
        relaxed: 'relaxed',
      }
      const st = map[status] ?? 'failed'
      if (st === 'passed') {
        state.stages.forEach((s) => {
          if (s.state !== 'failed') s.state = 'done'
        })
      }
      finishAttempt(state, attempt, st, state.error, now)
      push(state, now, {
        kind,
        tone: status === 'passed' ? 'ok' : status === 'relaxed' ? 'warn' : 'error',
        title: status === 'passed' ? 'cycle 通过校验' : status === 'relaxed' ? '人工放宽验收' : 'cycle 未通过',
        detail: state.error || (ev.commit ? `检查点 ${ev.commit}` : ''),
        seq: ev.seq,
        ts: ev.ts,
      })
      break
    }

    case 'run_end': {
      state.status = (ev.status as RunStatus) ?? 'failed'
      state.endedAt = now
      state.error = String(ev.error || '')
      state.commit = String(ev.commit || '')
      state.files = ((ev.touched_files as string[]) || state.files).slice()
      push(state, now, {
        kind,
        tone: state.status === 'passed' ? 'ok' : state.status === 'relaxed' ? 'warn' : 'error',
        title: `运行结束：${state.status}`,
        detail: state.error || state.commit || '',
        seq: ev.seq,
        ts: ev.ts,
      })
      break
    }

    case 'cancel_requested': {
      push(state, now, { kind, tone: 'warn', title: '收到取消请求', detail: '将在下一个进度点生效', seq: ev.seq })
      break
    }

    case 'cancelled': {
      state.status = 'cancelled'
      state.error = String(ev.message || '已取消')
      state.endedAt = now
      push(state, now, { kind, tone: 'error', title: '运行已取消', detail: state.error, seq: ev.seq })
      break
    }

    case 'error': {
      state.status = 'error'
      state.error = String(ev.message || '未知错误')
      state.endedAt = now
      push(state, now, { kind, tone: 'error', title: '运行出错', detail: state.error, seq: ev.seq })
      break
    }

    default: {
      // 没有专门 case 的事件：交给标定驱动的通用渲染。
      // 后端加事件时这里不用改，也不会出现标题为裸 kind 的行。
      const g = renderGeneric(kind, ev as Record<string, unknown>)
      push(state, now, {
        kind,
        tone: g.tone,
        title: g.title,
        detail: g.detail,
        seq: ev.seq,
        ts: ev.ts,
      })
    }
  }
}

function stageHint(phase: string): string {
  return spec.pipeline?.stages?.find((s) => s.id === phase)?.hint ?? ''
}

function statusLabel(status: CheckStepView['status']): string {
  return status === 'passed' ? '通过' : status === 'skipped' ? '未执行' : '有问题'
}

/* ------------------------------------------------------------------ */
/* 一个可复用的运行状态实例                                            */
/* ------------------------------------------------------------------ */
export interface RunStore {
  state: RunState
  reset: (runId?: string | null) => void
  ingest: (ev: AgentEvent) => void
  ingestMany: (evs: AgentEvent[]) => void
  /**
   * 收下**运行报告**（`GET /api/runs/{id}` 的 `run.report`）。
   *
   * P3/P4 的事实（结局四值、判据来源、独立性、拆解合规审查、复用性检查）
   * **首先是报告字段** —— 旧运行的事件里没有它们。所以运行详情要单独取一次。
   */
  ingestReportInfo: (report: unknown) => void
  /** 标定加载后刷新阶段清单（不动进行中的运行） */
  syncStages: () => void
}

export function useRunStore(): RunStore {
  const state = reactive<RunState>(createInitialState())

  /**
   * 标定加载完成后刷新阶段清单。
   *
   * store 是在 spec 之前建出来的（那时只有内置兜底），所以后端如果声明了
   * 不同的阶段集合，要在这里对齐一次。运行中的 state 不动——重画流水线会把
   * 已经点亮的阶段清掉。
   */
  function syncStages() {
    if (state.startedAt) return   // 有运行在进行/刚结束，别动它
    state.stages = freshStages()
  }

  function reset(runId: string | null = null) {
    Object.assign(state, createInitialState())
    state.runId = runId
  }

  function ingest(ev: AgentEvent) {
    // 实时流：用本地时钟，精度高
    applyEvent(state, ev, Date.now())
  }

  function ingestMany(evs: AgentEvent[]) {
    // 历史回放：用事件自带时间，否则「耗时」会恒为 0
    for (const ev of evs) applyEvent(state, ev, tsToMs(ev.ts))
  }

  function ingestReportInfo(report: unknown) {
    ingestReport(state, report, Date.now())
  }

  return { state, reset, ingest, ingestMany, ingestReportInfo, syncStages }
}

/* ------------------------------------------------------------------ */
/* 派生量                                                              */
/* ------------------------------------------------------------------ */
export function useDerived(state: RunState) {
  const elapsedMs = computed(() => {
    if (!state.startedAt) return 0
    return (state.endedAt ?? Date.now()) - state.startedAt
  })

  const running = computed(() => state.status === 'queued' || state.status === 'running')

  const progress = computed(() => {
    // 已完成阶段占 90%，终态占满 100%
    const done = state.stages.filter((s) => s.state === 'done').length
    const failed = state.stages.some((s) => s.state === 'failed')
    const base = (done / Math.max(1, state.stages.length)) * 92
    if (state.status === 'passed') return 100
    if (failed) return Math.max(base, 20)
    if (state.status === 'failed' || state.status === 'error' || state.status === 'cancelled') {
      return Math.max(base, 15)
    }
    return base + (running.value ? 4 : 0)
  })

  const activeToolCalls = computed(() => state.toolCalls.filter((t) => t.status === 'running'))

  const wroteFiles = computed(() =>
    state.toolCalls
      .filter((t) => t.tool === 'write_file')
      .map((t) => String(t.args.filename ?? ''))
      .filter(Boolean),
  )

  return { elapsedMs, running, progress, activeToolCalls, wroteFiles }
}
