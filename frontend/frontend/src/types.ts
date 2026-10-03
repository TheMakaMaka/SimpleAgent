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
  /**
   * ★ 完整报告（`bridge/runner.py` 的 `RunInfo.report`）。
   *
   * 它带 **`outcome` / `outcome_reason` / `verdict` / `self_report` /
   * `decompose_review` / `reuse_checks`** —— 也就是 P3/P4 的事实源。
   * 事件流里拿不到这些（那是**报告**，不是事件），所以运行详情要单独取一次：
   * `GET /api/runs/{id}`（见 `App.vue` 的 `attach()`）。
   */
  report: Record<string, unknown> | null
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

/* ---------------- 透明化视图（TRANSPARENCY-UI） ----------------
 *
 * 这四组视图回答的是「**为什么**」，而不是「到哪一步了」。
 *
 * 公共纪律（这一轮的核心）：
 *   **界面只能显示事件流里真实存在的事实。** 后端还没发的字段，
 *   要么显示"后端未提供"，要么用**实测的替代物**顶上并**标明它是替代物**。
 *   绝不为了"看起来完整"而编一个字 —— 那正是本次要修的毛病
 *   （一次 `passed` 的运行，机械事实是"没跑测试、没有报告"）。
 */

/** A2：编排器某一轮的决策依据 */
export interface DecisionRoundView {
  round: number
  status: string
  /**
   * 编排器给的理由（原文）。
   *
   * 两个来源，**同一个 `_decide` 返回值**（见上游 `core/contract.py:178-180`）：
   *   - `orchestrator_decision.reasoning` —— bridge 发的（老运行、含固定样例）
   *   - `orchestrator_round.reasoning`    —— 上游 A1 发的（`since="1.2"`，新运行）
   */
  reasoning: string
  /** 编排器给出的最终答复（若有） */
  finalAnswer: string
  /** 该轮声明要派发几个任务（只有 bridge 的 `orchestrator_decision` 带这个） */
  taskCount: number
  /**
   * ★「这一轮打算做什么」到底是从哪来的。
   *
   * 需求建议 A1 带一个 `intent` 字段。**实际上没有人发这个键** —— 但上游 A1
   * 发的 `orchestrator_round.tasks` 就是"打算做什么"（声明在前、执行在后），
   * 它比 `intent` 更有用。所以这里记下**取值的来源**，界面按来源分别标注：
   *
   *   - `field`    ：事件真的带了 `intent` 字符串
   *   - `tasks`    ：上游 `orchestrator_round.tasks`（**声明**要做什么）
   *   - `none`     ：两者都没有 —— 界面显示"后端未提供"，并用
   *                  `planned[].source === 'dispatched'` 的**实测替代物**顶上
   */
  intentSource: 'field' | 'tasks' | 'none'
  intent: string
  planned: DecisionPlannedTask[]
  seq: number
  at: number
}

export interface DecisionPlannedTask {
  id: string
  description: string
  /** 上游 `orchestrator_round.tasks[].expected_output`（声明阶段就有） */
  expectedOutput: string
  /** 只有 `task_start` 带工具提示 */
  toolHint: string[]
  /** 该任务的结局（由 `task_done` 回填；未结束为 null） */
  ok: boolean | null
  /**
   * ★ 这条是**声明**还是**实测**。
   *
   * `declared`   = 编排器在决策里说"这一轮要做这个"（`orchestrator_round.tasks`）
   * `dispatched` = 这一轮**真的派发了**这个任务（`task_start`）
   *
   * 两者都必须标明 —— 把"说要做什么"当成"做了什么"，
   * 就是把意图当事实，正是这一轮要修的病。
   */
  source: 'declared' | 'dispatched'
}

/** A3：模型在某一回合说的原话 + 它实际调用的工具 */
export interface ModelTurnView {
  taskId: string
  step: number
  /** 模型当轮的原文（`model_reply.content`）。可能为空 —— 空不等于"没说话" */
  content: string
  contentLen: number
  toolCalls: number
  calls: ModelTurnCall[]
  seq: number
  at: number
}

export interface ModelTurnCall {
  seq: number
  tool: string
  /** 参数的可读摘要（复用 describeArgs） */
  summary: string
  status: 'running' | 'ok' | 'error'
  preview: string
}

/**
 * B4：一条验收判据在**事件流里的样子**。
 *
 * ★ 三根轴，刻意不压成一个词：
 *
 * | 轴 | 取值 | 说的是 |
 * |---|---|---|
 * | `action`  | `executed` / `rejected` / `adopted` / `unknown` | **这条判据发生了什么**（后端 `verify_criterion.action`，`core/contract.py:185`） |
 * | `outcome` | `passed` / `failed` / `rejected` / `unknown` | **它考过了没有** |
 * | `adopted` | bool | **它是不是最后算数的那一条** |
 *
 * 「被拒」与「失败」必须分开：前者说的是"这张考卷不该用"，后者说的是"用了，没考过"。
 * 混起来就看不出这次到底是"判据写错了"还是"模型没做到"。
 * 同理"执行且通过、但不是最后算数的那条"与"执行且失败、却仍被记录"
 * 也各自需要位置 —— 压成一个词就会丢掉其中一半事实。
 */
export type CriterionAction = 'executed' | 'rejected' | 'adopted' | 'unknown'
export type CriterionOutcome = 'passed' | 'failed' | 'rejected' | 'unknown'

export interface CriterionView {
  seq: number
  at: number
  /** 后端 `verify_criterion.action`；老事件流（`verify_probe`/`verify_skipped`）按事件类型推断 */
  action: CriterionAction
  /** 判据命令原文。**`verify_skipped` 可能没有单独记命令**（`core/coding_cycle.py:384` 传 `command=""`） */
  command: string
  detail: string
  outcome: CriterionOutcome
  /** ★ 它是否就是**最终被记录**的那条判据 */
  adopted: boolean
  /**
   * 拒绝/替换的理由。
   *
   * ★ B2 要求「同一 cycle 内替换一条**已执行且失败**的判据必须给理由」。
   * 后端给了（`verify_criterion.reason`，`core/coding_cycle.py:410`）。
   * 空串 = 后端没给 —— 界面要**显式说"没给理由"**，不能留白。
   */
  reason: string
  /**
   * ★ 判据来源：`caller`（调用方给定）/ `model`（模型自拟）/ `''`（未知）。
   * 来源为 `model` 时，界面必须把它显示在结论旁 —— 否则
   * "这次是模型自己给自己判过的"看不见。
   */
  source: string
  /**
   * ★ 上一条判据**执行失败**了吗（**按 seq 相邻**的事实）。
   *
   * 这不是"替换"的语义断言，而是对事件序号顺序的直述。
   * 它是**老事件流的唯一办法**：`verify_probe`/`verify_skipped` 不带前后关系
   * —— 需求原文说的就是这个（「需要人自己按 seq 拼」）。
   *
   * 只在**同一次尝试内**成立：跨尝试的"上一条失败"属于已被整体回退的那一轮，
   * 把它当成"这次换上的前因"就是在编因果。
   */
  afterFailure: { seq: number; command: string } | null
  /**
   * ★ 后端 B1 **显式**给的"上一条被执行过的判据"
   * （`verify_criterion.previous_command`，`core/contract.py:183`；
   * 由 `core/memory.py:135-140` 自动补齐）。老事件流为空串。
   */
  previousCommand: string
  /**
   * ★ 后端 B1 **显式**给的"上一条执行过了没有"（`previous_passed`）。
   * `null` = 后端没给（**与 `false` 不同**）；老事件流恒为 null。
   *
   * 界面必须把这份**显式事实**与上面的 `afterFailure`（我按序号推断的）
   * **分开显示** —— 两种来源同形，就分不出"谁说的"。
   */
  previousPassed: boolean | null
  /**
   * 该判据发生时**正在进行的尝试序号**（沿用事件里最近一次出现的 `attempt`）。
   */
  attempt: number
}

/**
 * C3：模型收尾自述。
 *
 * ★ 形状**来自实现，不是猜的**：上游 `core/self_report.py:67-85` 的 `normalize()`
 * 与 `core/coding_cycle.py:755-768` 的 `self_report` 事件。
 */
export interface SelfReportView {
  /**
   * `false` = **自述本身没生成出来**（带 `error`），
   * **不是**「模型说没事」（`core/contract.py:194-195` 特别强调过这一点）。
   */
  ok: boolean
  error: string
  phase: string
  done: string[]
  notDone: string[]
  why: string[]
  reflections: string[]
  approach: string[]
  /** `confidence` 在实现里是**对象** `{level, basis}`，不是一个字符串 */
  confidenceLevel: string
  confidenceBasis: string
  openQuestions: string[]
  /** 原始对象，供"形状不认识"时原样展开，避免丢信息 */
  raw: Record<string, unknown>
  seq: number
  at: number
}

/**
 * C3：自述与机械事实的逐条对照（后端 C2）。
 *
 * ★ 形状来自上游 `core/self_report.py:88-224` 的 `fact_check()`。
 * `contradictions` 里的每一条**本身就是矛盾**（不需要再看某个 `ok` 字段）。
 */
export interface FactCheckRow {
  /** `artifact-missing` / `verify-claim-vs-fact` / `check-claim-vs-fact` /
   *  `lint-failed-not-disclosed` / `requirement-evidence-missing` / `done-mentions-missing-file` */
  kind: string
  /** 自述那一侧说了什么 */
  claim: string
  /** 机械事实那一侧是什么 */
  fact: string
  severity: string
  raw: Record<string, unknown>
}

export interface FactCheckView {
  checked: boolean
  contradictions: FactCheckRow[]
  /**
   * ★「目标里明确要求、但既没写成 done 也没写成 not_done」的清单
   * （C2 对照表的第 4 行，上游 `core/self_report.py:178-186`）。
   */
  unmentioned: string[]
  notes: string[]
  /** 自述缺了哪些必需字段（`done/not_done/why/reflections/approach/confidence/open_questions`） */
  missingFields: string[]
  /** 机械事实快照：`{phase, verify_passed, verify_source, check_status, lint_failed, workspace_files}` */
  facts: Record<string, unknown>
  raw: Record<string, unknown>
}

/** D3：结局四值 + 判据来源 */
export type OutcomeValue = 'pass' | 'fail' | 'abstain' | 'invalid' | 'unknown'

export interface OutcomeView {
  value: OutcomeValue
  /** 后端给出的原始结局词（可能是 `passed`/`failed` 这套旧词） */
  raw: string
  /** 判据来源：`caller` / `model` / `''` */
  source: string
  /** 结局的可读理由（`abstain`/`invalid` 必须带） */
  reason: string
  /** 结局词是否**不在**后端声明的四值里 —— 界面要如实说这是旧词表 */
  legacyVocabulary: boolean
}

/**
 * ★ P3：后端**权威**的结局判定（`TRANSPARENCY2-BACKEND` P1 / D19）。
 *
 * 形状**照抄实现**，不是我定的：`D:\PythonProject\SimpleAgent2_Cycle\core\outcome.py:89`
 * 的 `build_verdict()` 与 `core/cycle.py:145-146`。字段名一律不改、不重算 ——
 * 前端只呈现，**不做第二个体检口径**。
 */
export interface VerdictView {
  /** 四值之一；`unknown` = 后端给的词不在四值里（那时要如实说） */
  outcome: OutcomeValue
  /** 后端给的**原始**结局词（`outcome_of()` 的结果或报告顶层的 `outcome`） */
  raw: string
  /** 失败/通过的种类（`outcome_kind`，例如 `verify-failed`） */
  outcomeKind: string
  reason: string
  /** 判据来源：`caller` / `model` / `''`（`criterion_source`） */
  criterionSource: string
  /** 判据可信档位（`criterion_trust`：`none`/`caller-authoritative`/`model-self-authored`） */
  criterionTrust: string
  /**
   * 判据是不是**独立第三方**给的（`criterion_independent`）。
   * `null` = 后端**没给**这个字段 —— **与 `false` 不同**：
   * `false` 是"给了，且不独立"，`null` 是"没给，判不了"。
   */
  criterionIndependent: boolean | null
  note: string
  /** 后端**没给** verdict（旧报告）时为 true —— 界面据此说"未产出"而不是编一个 */
  absent: boolean
}

/** P4：③ 拆解合规关卡里的**单条原则**（上游 `core/contract.py:207-216`） */
export interface ReviewPrincipleView {
  /** `P1`…`P8` */
  principle: string
  /** `violated` / `ok` / `undecidable` / `''`（认不出就留空，**不归到 ok**） */
  verdict: string
  evidence: string
  checkedBy: string
  /** `null` = 没给（≠ `false`） */
  independent: boolean | null
}

/**
 * P4：③ 拆解合规审查的整体结论。
 *
 * ★ 这个视图存在的**唯一**理由是让「**判不了**」不被读成「通过」：
 *   `undecidable` 必须与 `violated` 分开展示，且**不得**因为 `passed=true`
 *   就把整块画成绿色（上游 `core/contract.py:214-216` 明写：
 *   `passed` 只代表**机械条款**通过，`undecidable` 非空 = 审查范围不完整，
 *   **不得呈现为「审查通过」**）。
 */
export interface DecomposeReviewView {
  /** 机械条款是否通过（后端给的 `passed`；`null` = 没给） */
  passed: boolean | null
  summary: string
  checkedBy: string
  independent: boolean | null
  violated: string[]
  undecidable: string[]
  principles: ReviewPrincipleView[]
  at: number
  seq: number
}

/** 机械层**复用性**检查（上游 `core/contract.py:200`，`coding_cycle.py:507` 发出） */
export interface ReuseView {
  checked: boolean
  passed: boolean | null
  /** **必然崩**的两类（调用了不存在的符号 / 用了没导入）—— 这是**阻塞**项 */
  blocking: string[]
  warnings: string[]
  at: number
  seq: number
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

  /* ---- TRANSPARENCY-UI：四块「为什么」视图 ---- */
  /** A2 编排器每轮的决策依据（按轮次升序） */
  decisionRounds: DecisionRoundView[]
  /** A3 模型的每个回合：原话 + 工具调用链 */
  modelTurns: ModelTurnView[]
  /** B4 验收判据的完整演化（**严格按 seq 升序**，不重排因果） */
  criteria: CriterionView[]
  /** C3 收尾自述；后端 C1 未交付时为 null */
  selfReport: SelfReportView | null
  /**
   * ★ C3 自述**为什么没有**。
   *
   * 空面板会被读成"模型没什么要说的" —— 那是最坏的一种误导。
   * 所以缺席必须带一句可归因的说明（运行早于 C1 / 事件形状不认识 / 运行还没结束）。
   */
  selfReportAbsentReason: string
  /** C3 自述与机械事实的对照（后端 C2）；没有自述时为 null */
  factCheck: FactCheckView | null
  /** D3 结局四值 + 判据来源（结论旁要显示的那个；**从 `run_end.status` 推的兜底值**） */
  outcome: OutcomeView
  /**
   * ★ P3：后端**权威**的结局判定（`report.verdict` 或 `run_end` 上的那组字段）。
   * `null` = 后端没给（旧报告 / 后端未产出）—— 界面必须说"未产出"，**不许编**。
   */
  verdict: VerdictView | null
  /** P4：③ 拆解合规审查（后端已声明形状、尚未发出时为 null） */
  decomposeReview: DecomposeReviewView | null
  /** 机械层复用性检查（**有否决权**，所以必须可见） */
  reuse: ReuseView | null
  /**
   * 透明化采集器的**序号高水位**。
   *
   * 判据演化与"上一条失败了"是**顺序敏感**的读数：同一条事件被重放两次，
   * 就会多出一行，并把"上一条"指错。重连/重放路径可能重复投递，
   * 所以这里挡一道（不是 UI 字段，是采集器的状态）。
   */
  transparencySeq: number

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
