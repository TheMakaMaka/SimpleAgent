/**
 * 事件与视图模型。
 *
 * 这里的事件词表与后端 `core/progress.py` + `web/runner.py` 发出的 kind 一一对应。
 * 它是**契约**：后端加事件时，前端在这里加一条即可拿到类型提示。
 */

export type RunStatus =
  | 'queued'
  | 'running'
  | 'passed'
  | 'failed'
  | 'relaxed'
  | 'cancelled'
  | 'error'

/**
 * 阶段标识。**刻意是开放的 string**：阶段清单由后端标定决定
 * （`GET /api/spec` 的 `pipeline.stages`），前端不该把阶段名锁死在这里。
 * 后端加一个阶段，这里不用改。
 */
export type Phase = string

export interface AgentEvent {
  seq: number
  ts: string
  kind: string
  run_id?: string
  goal?: string
  attempt?: number
  phase?: string
  [key: string]: unknown
}

export interface RunInfo {
  run_id: string
  goal: string
  status: RunStatus
  created_at: string
  started_at: string
  finished_at: string
  options: Record<string, unknown>
  phase: string
  attempts: number
  touched_files: string[]
  commit: string | null
  rolled_back: boolean
  error: string | null
  answer: string
  summary: Record<string, unknown>
  event_count: number
  demo: boolean
}

/* ---------------- 视图模型 ---------------- */

export type StageState = 'idle' | 'active' | 'done' | 'failed' | 'passed'

export interface StageView {
  /** 流水线上的稳定 id（来自标定） */
  id: string
  /** 显示名（来自标定；未标定的阶段在运行时补上，label = id 大写） */
  label: string
  hint: string
  /** 图标名（来自标定）。前端认不出就回退到通用图标 */
  icon?: string
  state: StageState
  /** 进入该阶段时的事件序号（用于「刚刚完成」的高亮） */
  at?: number
}

export interface TaskView {
  id: string
  description: string
  status: 'running' | 'done' | 'failed'
  steps: number
  maxSteps: number
  ok?: boolean
  output?: string
  error?: string
  toolHint: string[]
}

export interface ToolCallView {
  key: string
  taskId: string
  step: number
  tool: string
  args: Record<string, unknown>
  status: 'running' | 'ok' | 'error'
  preview?: string
  at: number
}

export interface CheckStepView {
  path: string
  tool: 'syntax' | 'lint'
  status: 'passed' | 'failed' | 'skipped'
  message: string
  issues: string[]
}

export interface VerifyView {
  passed: boolean
  detail: string
  command: string
  files: string[]
  at: number
}

export interface ManifestView {
  checked: boolean
  passed: boolean
  violations: Array<{ kind: string; path: string; message: string }>
  actualFiles: string[]
  at: number
}

export interface DecisionView {
  id: string
  kind: string
  question: string
  default: string
  expires_at: string
  options: Array<{ value: string; label: string; hint: string; danger: boolean }>
  context: Record<string, unknown>
}

export interface AttemptView {
  index: number
  status: 'running' | 'passed' | 'failed' | 'relaxed'
  stages: StageView[]
  error: string
  startedAt: number
  endedAt: number | null
  rolledBack: boolean
}

export interface TimelineEntry {
  seq: number
  at: number
  /** 后端事件时间戳格式化后的 HH:MM:SS；回放历史时也是真实时间 */
  clock: string
  kind: string
  tone: 'info' | 'ok' | 'warn' | 'error' | 'model' | 'tool' | 'phase'
  title: string
  detail: string
}

export interface RunState {
  runId: string | null
  goal: string
  status: RunStatus
  demo: boolean
  connected: 'idle' | 'connecting' | 'live' | 'closed' | 'error'
  startedAt: number
  endedAt: number | null
  attempt: number
  maxAttempts: number
  /** 阶段推进记录（当前尝试） */
  stages: StageView[]
  attempts: AttemptView[]
  tasks: TaskView[]
  currentTaskId: string | null
  toolCalls: ToolCallView[]
  checks: CheckStepView[]
  files: string[]
  manifest: ManifestView | null
  verify: VerifyView | null
  verifyProbes: number
  /**
   * 被**跳过**的验证（`verify_skipped` 事件）。
   *
   * 上游刻意把「有验证命令、却没有 pipeline，于是验证回流整块被跳过」变成
   * 一条**显式事实** —— 因为静默跳过会让上层误诊成"缺少验证命令"。
   * 所以它必须在运行视图里**看得见**，而不是混在时间线里被划过去。
   */
  verifySkipped: string[]
  rounds: number
  steps: number
  modelReplies: number
  events: number
  rollbacks: number
  decisions: DecisionView[]
  timeline: TimelineEntry[]
  reasoning: Array<{ round: number; text: string; status: string; at: number }>
  error: string
  answer: string
  commit: string
  /** 每个阶段的进入次数，用于「重试后重置」的动画 */
  phaseKey: number
}
