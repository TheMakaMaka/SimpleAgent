/**
 * TRANSPARENCY-UI：把「**为什么**」从事件流里还原出来（A2 / A3 / B4 / C3 / D3）。
 *
 * 为什么单独一个模块，而不是往 `run.ts` 的 `switch` 里加 `case`
 * ---------------------------------------------------------------
 * `run.ts` 的 `case` 列表被 `tests/unit/test_event_contract.py` 当作
 * **「前端认的事件词表」**审查，其中第 `[3]` 组判据是
 * **「前端认了、后端不发 = 死代码」**。
 *
 * 而本轮上游（`core/contract.py:172/181/189`）新增的三个事件 ——
 * `orchestrator_round` / `verify_criterion` / `self_report` —— **还不在契约主本里**
 * （主本 v1.0.24；上游把它们标成 `since="1.2"`，但上游自己的 `CONTRACT_VERSION`
 * 还写着 `"1.1"`，见 `core/contract.py:57`）。所以：
 *
 *   - 写 `case` → **自带旧副本那种配置**下会被判成死代码；
 *   - 不写 `case` → **指向真上游时** `[2]`（后端发的必须被认下）会红。
 *
 * 两个都要满足，靠的是**采集器自己声明词表**：`RECOGNIZED_KINDS` 是这条底线，
 * 由 `test_event_contract.py` 与 `case` 列表**合并**起来算"前端认得的词"。
 * 于是两边都绿，而门禁没有被放宽 —— 它只是从"必须写 case"改成了
 * "必须有一个地方**明确声明**你认得它"，且那份声明是**代码真的用到的**（见 `HANDLERS`）。
 *
 * 铁律（这一轮的全部意义所在）
 * --------------------------
 * **只显示事件流里真实存在的东西。** 后端没给的字段，要么显示
 * 「后端未提供」，要么用**实测的替代物**顶上并**标明它是替代物**。
 * 编一个字，就等于把这次要修的毛病（"判据换了、界面看不见"）换个地方再犯一次。
 */
import type {
  AgentEvent,
  CriterionAction,
  CriterionOutcome,
  DecomposeReviewView,
  FactCheckView,
  OutcomeValue,
  OutcomeView,
  ReuseView,
  ReviewPrincipleView,
  RunState,
  SelfReportView,
  TimelineEntry,
  VerdictView,
} from '@/types'
import { describeArgs } from '@/store/args'

/* ------------------------------------------------------------------ */
/* 采集器**声明**的词表                                                */
/* ------------------------------------------------------------------ */

/**
 * 本模块认下（并自己解释）的、`store/run.ts` 里**没有** `case` 的事件。
 *
 * ★ 这份声明是**真的被用到的**（`HANDLERS` 的键就是它），不是给人看的注释 ——
 * 声明与行为分家，就等于又做了一个会漂的副本。
 */
export const RECOGNIZED_KINDS = [
  'orchestrator_round',
  'verify_criterion',
  'self_report',
  'reuse',
  'decompose_review',
] as const
export type RecognizedKind = (typeof RECOGNIZED_KINDS)[number]

const asArray = (v: unknown): string[] => {
  if (Array.isArray(v)) {
    return v
      .map((x) => (typeof x === 'string' ? x : x === null || x === undefined ? '' : JSON.stringify(x)))
      .filter((s) => s.length > 0)
  }
  if (typeof v === 'string' && v.trim()) {
    // 后端可能把一段文字塞进一个"数组"字段。**照实当一条**，不按换行猜拆。
    return [v]
  }
  return []
}

const asText = (v: unknown): string =>
  typeof v === 'string' ? v : v === null || v === undefined ? '' : JSON.stringify(v)

const obj = (v: unknown): Record<string, unknown> =>
  v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {}

const asBool = (v: unknown): boolean | null => (typeof v === 'boolean' ? v : null)

/* ------------------------------------------------------------------ */
/* B4 · 判据演化                                                       */
/* ------------------------------------------------------------------ */

/** 该条判据的 `action` 与 `outcome`：**按后端给的字段判**，判不出就 `unknown`。 */
function classifyCriterion(
  ev: AgentEvent,
  action: CriterionAction,
  fallback: CriterionOutcome,
): { action: CriterionAction; outcome: CriterionOutcome } {
  const passed = asBool(ev.passed)
  if (action === 'rejected') return { action, outcome: 'rejected' }
  if (passed === null) {
    // `action=adopted` 且没有 `passed`：**后端没给结果**，不能拿它当"通过"
    return { action, outcome: action === 'unknown' ? 'unknown' : passed === null && action === 'adopted' ? 'unknown' : fallback }
  }
  return { action, outcome: passed ? 'passed' : 'failed' }
}

function pushCriterion(
  state: RunState,
  ev: AgentEvent,
  now: number,
  outcome: CriterionOutcome,
  opts: {
    adopted?: boolean
    action?: CriterionAction
    reason?: string
    detail?: string
    command?: string
  } = {},
): void {
  const last = state.criteria[state.criteria.length - 1] ?? null
  const attempt = Number(ev.attempt ?? state.attempt ?? 1)
  const action = opts.action ?? 'unknown'
  const classified = classifyCriterion(ev, action, outcome)
  state.criteria.push({
    seq: Number(ev.seq ?? 0),
    at: now,
    action: classified.action,
    command: opts.command ?? asText(ev.command),
    detail: opts.detail ?? asText(ev.detail),
    outcome: opts.action ? classified.outcome : outcome,
    adopted: Boolean(opts.adopted),
    reason: opts.reason ?? asText(ev.reason),
    source: asText(ev.source),
    // ★ 只陈述"序号紧邻的上一条是执行且失败的"。这是**顺序事实**，不是因果断言。
    //   并且**只在同一次尝试内**陈述 —— 跨尝试的"上一条失败"属于已被回退的那一轮，
    //   把它当成"这次换上的前因"就是在编因果。
    afterFailure:
      last && last.outcome === 'failed' && last.attempt === attempt
        ? { seq: last.seq, command: last.command }
        : null,
    // ★ 后端 B1 的**显式**前因（`verify_criterion`）；老事件流没有这两样，
    //   所以是 ""/null —— 界面据此分辨"谁说的"。
    previousCommand: asText(ev.previous_command),
    previousPassed: asBool(ev.previous_passed),
    attempt,
  })
}

/* ------------------------------------------------------------------ */
/* C3 · 收尾自述                                                       */
/* ------------------------------------------------------------------ */

/** 自述必需字段（上游 `core/self_report.py:27-30` 的 `REQUIRED_FIELDS`）。 */
const REQUIRED_SELF_REPORT_FIELDS = [
  'done',
  'not_done',
  'why',
  'reflections',
  'approach',
  'confidence',
  'open_questions',
]

/**
 * 读 `fact_check`。
 *
 * ★ 形状来自上游 `core/self_report.py:88-224`：`contradictions` 里的每一条
 * **本身就是矛盾**（`{kind, claim, fact, severity}`），没有 `ok` 字段。
 * 早期版本按"逐行对照 + ok 判定"来读，会把每一条**真矛盾**读成"认不出判定值" ——
 * 那样最该看见的东西反而看不见。
 *
 * 保底分支：若形状是"一个数组"（没有 `contradictions` 容器），按**显式判定值**
 * 挑矛盾（`ok/match/consistent/passed === false`）。认不出就当作笔记，不当矛盾 ——
 * **宁可少报一条，也不要把没核过的东西说成矛盾。**
 */
function readFactCheck(v: unknown): FactCheckView | null {
  if (v === null || v === undefined) return null
  const o = obj(v)

  const rawContradictions = o.contradictions
  if (Array.isArray(rawContradictions)) {
    return {
      checked: o.checked === undefined ? true : Boolean(o.checked),
      contradictions: rawContradictions.map((r) => {
        const c = obj(r)
        return {
          kind: asText(c.kind),
          claim: asText(c.claim),
          fact: asText(c.fact ?? c.detail ?? c.evidence),
          severity: asText(c.severity),
          raw: c,
        }
      }),
      unmentioned: asArray(o.unmentioned),
      notes: asArray(o.notes),
      missingFields: asArray(o.missing_fields ?? o.missingFields),
      facts: obj(o.facts),
      raw: o,
    }
  }

  const rowsRaw = Array.isArray(v) ? v : (o.rows ?? o.items ?? o.checks)
  if (Array.isArray(rowsRaw)) {
    const contradictions = []
    const notes: string[] = []
    for (const r of rowsRaw) {
      const c = obj(r)
      const verdict = c.ok ?? c.match ?? c.consistent ?? c.passed ?? c.agrees
      const claim = asText(c.claim ?? c.item ?? c.statement ?? c.what)
      const fact = asText(c.fact ?? c.detail ?? c.note ?? c.evidence ?? c.message)
      if (verdict === false) {
        contradictions.push({
          kind: asText(c.kind ?? c.target),
          claim,
          fact,
          severity: asText(c.severity),
          raw: c,
        })
      } else if (claim || fact) {
        notes.push([claim, fact].filter(Boolean).join(' — '))
      }
    }
    return {
      checked: true,
      contradictions,
      unmentioned: asArray(o.unmentioned),
      notes,
      missingFields: REQUIRED_SELF_REPORT_FIELDS.filter((f) => !(f in o)),
      facts: obj(o.facts),
      raw: o,
    }
  }

  return null
}

function applySelfReport(
  state: RunState,
  sr: Record<string, unknown>,
  seq: number,
  now: number,
): void {
  // ★ `confidence` 在实现里是**对象** `{level, basis}`（`core/self_report.py:73-76`），
  //   不是一个字符串。当成字符串读会得到 `[object Object]`。
  const conf = sr.confidence
  const confObj = obj(conf)
  const view: SelfReportView = {
    // `ok=false` = 自述**没生成出来**（`core/contract.py:194-195`）。
    ok: sr.ok === undefined ? true : Boolean(sr.ok),
    error: asText(sr.error),
    phase: asText(sr.phase),
    done: asArray(sr.done),
    notDone: asArray(sr.not_done ?? sr.notDone),
    why: asArray(sr.why ?? sr.reasons),
    reflections: asArray(sr.reflections),
    approach: asArray(sr.approach),
    confidenceLevel: confObj.level !== undefined ? asText(confObj.level) : asText(conf),
    confidenceBasis: asText(confObj.basis),
    openQuestions: asArray(sr.open_questions ?? sr.openQuestions),
    raw: sr,
    seq,
    at: now,
  }
  state.selfReport = view
  const fc = readFactCheck(sr.fact_check)
  if (fc) state.factCheck = fc
}

/**
 * 自述**为什么没有**。这句话必须能归因到一件具体的事 ——
 * 否则空白面板会被读成"模型没什么要说的"。
 */
function absentReason(state: RunState): string {
  if (!state.outcome.raw) return '运行已结束，但事件流里没有收尾自述事件。'
  if (state.outcome.legacyVocabulary) {
    return (
      `本次运行没有收尾自述。该运行的结局词是旧词表「${state.outcome.raw}」——` +
      `后端 C1（收尾自述步骤，上游 \`core/coding_cycle.py:755\`）交付之前，` +
      `这类事件根本不会产生。` +
      `所以这里是"这次运行时还没有这个功能"，不是"模型没什么要说的"。`
    )
  }
  return '运行已结束，但没有收到收尾自述事件（后端没产出，或生产失败）。'
}

/* ------------------------------------------------------------------ */
/* A2 · 决策依据                                                       */
/* ------------------------------------------------------------------ */

function ensureRound(state: RunState, round: number, seq: number, now: number) {
  let row = state.decisionRounds.find((r) => r.round === round)
  if (!row) {
    row = {
      round,
      status: '',
      reasoning: '',
      finalAnswer: '',
      taskCount: 0,
      intentSource: 'none',
      intent: '',
      planned: [],
      seq,
      at: now,
    }
    state.decisionRounds.push(row)
    state.decisionRounds.sort((a, b) => a.round - b.round)
  }
  return row
}

/* ------------------------------------------------------------------ */
/* D3 · 结局四值                                                       */
/* ------------------------------------------------------------------ */

/** 后端 D1 声明的四值。`passed`/`failed` 是**旧词表**，不是四值之一。 */
const FOUR_VALUES = new Set(['pass', 'fail', 'abstain', 'invalid'])
const LEGACY_OUTCOME: Record<string, OutcomeValue> = { passed: 'pass', failed: 'fail' }

function readOutcome(state: RunState, ev: AgentEvent): OutcomeView {
  const raw = asText(ev.status).toLowerCase()
  const value: OutcomeValue = FOUR_VALUES.has(raw)
    ? (raw as OutcomeValue)
    : (LEGACY_OUTCOME[raw] ?? 'unknown')
  // 判据来源取**最后一条带来源的判据**：结论旁要说的就是"这次算数的那条判据是谁给的"。
  const withSource = [...state.criteria].reverse().find((c) => c.source !== '')
  return {
    value,
    raw,
    source: withSource?.source ?? '',
    reason: asText(ev.reason ?? ev.error ?? ''),
    // 旧词表（passed/failed）不在 D1 的四值里 —— 界面要如实说明，
    // 否则人会把"这台仪表还没有 abstain/invalid 的刻度"当成"这次不是那两种"。
    legacyVocabulary: !FOUR_VALUES.has(raw),
  }
}

/* ------------------------------------------------------------------ */
/* P3 · 结局四值 + 判据来源 + 审查独立性                                */
/* ------------------------------------------------------------------ */

/**
 * 读**后端权威的** verdict（`core/outcome.py:89 build_verdict`）。
 *
 * ★ 三处刻意的"不猜"：
 *   1. `outcome` 不在四值里 → `unknown`，并把**原词**显示出来（不硬塞成 fail）；
 *   2. `criterion_independent` 缺失 → `null`（**≠ false**）：`false` 是"给了且不独立"，
 *      `null` 是"没给，判不了" —— 把两者合成一个 `false` 就是把"判不了"说成"否"；
 *   3. 没有 verdict 时返回 `null`（而不是一个 `outcome: 'fail'` 的默认值）。
 */
function readVerdict(src: unknown): VerdictView | null {
  const o = obj(src)
  if (!Object.keys(o).length) return null
  const raw = asText(o.outcome)
  // ★ "有键但全是空值"**不算**有 verdict。
  //   踩过的坑：调用方若先拼一个固定键的壳（`{outcome: ev.outcome, …}`）再传进来，
  //   `Object.keys` 一定是满的，于是这里会返回一个 `raw=''` 的"verdict"，
  //   把「后端没产出」伪装成「后端产出了但认不出」—— 旧运行的结局就这么被擦掉了。
  if (!raw && !asText(o.outcome_kind) && !asText(o.reason ?? o.outcome_reason)
      && !asText(o.criterion_source)) {
    return null
  }
  const value: OutcomeValue = FOUR_VALUES.has(raw)
    ? (raw as OutcomeValue)
    : (LEGACY_OUTCOME[raw] ?? 'unknown')
  return {
    outcome: value,
    raw,
    outcomeKind: asText(o.outcome_kind),
    reason: asText(o.reason ?? o.outcome_reason),
    criterionSource: asText(o.criterion_source),
    criterionTrust: asText(o.criterion_trust),
    criterionIndependent: asBool(o.criterion_independent),
    note: asText(o.note),
    absent: false,
  }
}

/** 只有结局词、没有 verdict 对象时（`core/cycle.py:145-146` 顶层那两个键） */
function readBareOutcome(raw: string, reason: string): VerdictView | null {
  if (!raw) return null
  return {
    outcome: FOUR_VALUES.has(raw) ? (raw as OutcomeValue) : (LEGACY_OUTCOME[raw] ?? 'unknown'),
    raw,
    outcomeKind: '',
    reason,
    criterionSource: '',
    criterionTrust: '',
    criterionIndependent: null,
    note: '',
    absent: false,
  }
}

/* ------------------------------------------------------------------ */
/* P4 · 拆解合规审查 + 复用性检查                                        */
/* ------------------------------------------------------------------ */

const PRINCIPLE_VERDICTS = new Set(['violated', 'ok', 'undecidable'])

/**
 * 读 `decompose_review`（`core/contract.py:207-216`）。
 *
 * ★ 认不出的判定值**留空**，**不归到 `ok`** —— 把"判不了"归成"通过"
 * 正是这个项目反复栽的那个坑（契约里为此专门写了警告）。
 */
function readDecomposeReview(src: Record<string, unknown>, now: number, seq: number): DecomposeReviewView {
  const ev = src
  const raw = (ev.principles as unknown[]) || []
  const principles: ReviewPrincipleView[] = raw.map((p) => {
    const o = obj(p)
    const v = asText(o.verdict).toLowerCase()
    return {
      principle: asText(o.principle),
      verdict: PRINCIPLE_VERDICTS.has(v) ? v : '',
      evidence: asText(o.evidence),
      checkedBy: asText(o.checked_by),
      independent: asBool(o.independent),
    }
  })
  return {
    passed: asBool(ev.passed),
    summary: asText(ev.summary),
    checkedBy: asText(ev.checked_by),
    independent: asBool(ev.independent),
    violated: asArray(ev.violated),
    undecidable: asArray(ev.undecidable),
    principles,
    at: now,
    seq,
  }
}

/**
 * 读 `reuse`（`core/contract.py:200`，`core/coding_cycle.py:507` 发出）。
 *
 * `blocking` 是**必然崩**的两类（调用了不存在的符号 / 用了没导入）——
 * 它**有否决权**，所以在门禁面板里必须看得见，不能只留在报告里。
 */
function readReuse(src: Record<string, unknown>, now: number, seq: number): ReuseView {
  const ev = src
  return {
    checked: ev.checked === undefined ? true : Boolean(ev.checked),
    passed: asBool(ev.passed),
    blocking: asArray(ev.blocking),
    warnings: asArray(ev.warnings),
    at: now,
    seq,
  }
}

/* ------------------------------------------------------------------ */
/* 主入口                                                              */
/* ------------------------------------------------------------------ */

/**
 * ★ 从**运行报告**（`GET /api/runs/{id}` 的 `run.report`）补进同一批视图。
 *
 * 为什么需要这条路：P3/P4 的事实（`outcome` / `verdict` / `decompose_review` /
 * `reuse_checks` / `self_report`）**首先是报告字段**。事件流里有它们的子集
 * （`run_end` 带 verdict、`self_report`/`reuse`/`decompose_review` 各自有事件），
 * 但：
 *
 * - **旧运行**（本轮之前跑的）事件里没有 verdict，只有报告里有；
 * - `decompose_review` 现在是"**已声明、尚未发出**"（上游 `core/contract.py:207`）——
 *   只有报告里可能有；
 * - 历史**回放**走的是事件，报告那条路能补上事件没带的字段。
 *
 * ★ 解析**只在这里做一次**（与事件路径共用 `readVerdict`/`applySelfReport`/
 *   `readDecomposeReview`/`readReuse`）——两份解析就是两个会漂的口径。
 *
 * 取不到就**什么都不改**：报告里没有的字段，界面显示"未产出"，不编。
 */
export function ingestReport(state: RunState, report: unknown, now: number = Date.now()): void {
  const r = obj(report)
  if (!Object.keys(r).length) return

  const v = readVerdict(r.verdict) ?? readBareOutcome(asText(r.outcome), asText(r.outcome_reason))
  if (v) {
    state.verdict = v
    state.outcome = {
      value: v.outcome,
      raw: v.raw,
      source: v.criterionSource || state.outcome.source,
      reason: v.reason,
      legacyVocabulary: !FOUR_VALUES.has(v.raw),
    }
  }

  const sr = obj(r.self_report)
  if (Object.keys(sr).length) {
    applySelfReport(state, sr, Number(sr.seq ?? 0) || state.transparencySeq, now)
    if (state.selfReport) state.selfReportAbsentReason = ''
  }

  const dr = obj(r.decompose_review)
  if (Object.keys(dr).length) state.decomposeReview = readDecomposeReview(dr, now, 0)

  if (r.reuse_checks !== undefined) state.reuse = mergeReuse(r.reuse_checks, now)
}

/** `reuse_checks` 在报告里可能是**一条**也可能是**一组**（按文件/按符号）—— 合并呈现 */
function mergeReuse(src: unknown, now: number): ReuseView {
  const items = (Array.isArray(src) ? src : [src])
    .map((x) => obj(x))
    .filter((x) => Object.keys(x).length)
  const blocking: string[] = []
  const warnings: string[] = []
  let passed: boolean | null = null
  let checked = false
  for (const it of items) {
    blocking.push(...asArray(it.blocking))
    warnings.push(...asArray(it.warnings))
    if (it.checked !== undefined) checked = true
    const p = asBool(it.passed)
    if (p === false) passed = false
    else if (p === true && passed === null) passed = true
  }
  return { checked, passed, blocking, warnings, at: now, seq: 0 }
}

/**
 * 采集器**声明**要自己渲染的那条时间线行。
 *
 * `clock` 由 `run.ts` 的 `push()` 从事件 `ts` 算出来（时间线的时钟只有那一处实现），
 * 所以这里不给 —— 类型上就不允许两边各算一个时间。
 */
export type ClaimedTimeline = Omit<TimelineEntry, 'seq' | 'at' | 'clock'> & {
  seq?: number
  ts?: string
}

/** 三个新事件各自的处理（键就是 `RECOGNIZED_KINDS` —— 声明与行为同一处）。 */
const HANDLERS: Record<RecognizedKind, (s: RunState, ev: AgentEvent, now: number) => ClaimedTimeline | null> = {
  /** A1 上游侧：`core/contract.py:172`，`tasks` 就是"这一轮打算做什么" */
  orchestrator_round(state, ev, now) {
    const row = ensureRound(state, Number(ev.round ?? 0), Number(ev.seq ?? 0), now)
    row.status = asText(ev.status) || row.status
    row.reasoning = asText(ev.reasoning) || row.reasoning
    row.finalAnswer = asText(ev.final_answer) || row.finalAnswer
    const tasks = (ev.tasks as unknown[]) || []
    const declared = tasks
      .map((t) => obj(t))
      .map((t) => ({
        id: asText(t.id),
        description: asText(t.description),
        expectedOutput: asText(t.expected_output),
        toolHint: asArray(t.tool_hint),
        ok: null as boolean | null,
        source: 'declared' as const,
      }))
      .filter((t) => t.description || t.id)
    if (declared.length) {
      // 只保留声明来的那几条（`task_start` 的实测条目由 task_start 分支负责）
      row.planned = [...declared, ...row.planned.filter((p) => p.source === 'dispatched')]
      row.intentSource = 'tasks'
    }
    return null
  },

  /** B1：`core/contract.py:181`，自带 `previous_*` 与 `reason`，**不用按 seq 拼** */
  verify_criterion(state, ev, now) {
    const actionRaw = asText(ev.action)
    const action: CriterionAction =
      actionRaw === 'executed' || actionRaw === 'rejected' || actionRaw === 'adopted' ? actionRaw : 'unknown'
    pushCriterion(state, ev, now, action === 'rejected' ? 'rejected' : 'unknown', {
      action,
      adopted: action === 'adopted',
    })
    return null
  },

  /** C1+C2：`core/contract.py:189`，自述 + 与机械事实的对照 */
  self_report(state, ev, now) {
    applySelfReport(state, ev as Record<string, unknown>, Number(ev.seq ?? 0), now)
    state.selfReportAbsentReason = ''
    const sr = state.selfReport
    const bad = state.factCheck?.contradictions.length ?? 0
    return {
      seq: Number(ev.seq ?? 0),
      kind: 'self_report',
      tone: bad ? 'error' : 'model',
      title: bad
        ? `收尾自述（与机械事实矛盾 ${bad} 处）`
        : `收尾自述（${sr?.done.length ?? 0} 项做了 / ${sr?.notDone.length ?? 0} 项没做）`,
      detail: bad
        ? (state.factCheck?.contradictions ?? [])
            .map((c) => c.claim || c.fact)
            .join('；')
            .slice(0, 200)
        : sr?.confidenceLevel ?? '',
    }
  },

  /** P2-后端：机械层**复用性**检查（**有否决权**，`core/coding_cycle.py:507`） */
  reuse(state, ev, now) {
    state.reuse = readReuse(ev as Record<string, unknown>, now, Number(ev.seq ?? 0))
    const n = state.reuse.blocking.length
    return {
      seq: Number(ev.seq ?? 0),
      kind: 'reuse',
      // 阻塞项用 error 色：它是"必然崩"的两类，不是风格问题
      tone: n ? 'error' : state.reuse.warnings.length ? 'warn' : 'ok',
      title: n ? `复用性检查：${n} 项阻塞` : '复用性检查通过',
      detail: state.reuse.blocking.concat(state.reuse.warnings).join('；').slice(0, 200),
    }
  },

  /**
   * P4：③ **拆解合规审查**（`core/contract.py:207`）。
   *
   * ★ 时间线的色调**只**看 `violated` 与 `undecidable`：
   *   有 `violated` → error；只有 `undecidable` → warn（**不是** ok）；
   *   两者都空才 ok。`passed=true` **不足以**画成绿色 ——
   *   `passed` 只代表机械条款通过，而"判不了"说明审查范围不完整。
   */
  decompose_review(state, ev, now) {
    state.decomposeReview = readDecomposeReview(ev as Record<string, unknown>, now, Number(ev.seq ?? 0))
    const dr = state.decomposeReview
    const v = dr.violated.length
    const u = dr.undecidable.length
    return {
      seq: dr.seq,
      kind: 'decompose_review',
      tone: v ? 'error' : u ? 'warn' : 'ok',
      title: v
        ? `拆解合规审查：违反 ${v} 条`
        : u
          ? `拆解合规审查：${u} 条判不了`
          : '拆解合规审查通过',
      detail: (dr.summary || dr.violated.concat(dr.undecidable).join('；')).slice(0, 200),
    }
  },
}

/**
 * 采集一块透明化事实。返回非空表示这条事件**由本模块渲染时间线**
 * （调用方应跳过 `switch`，避免"同一件事渲染两次"）。
 */
export function collectTransparency(
  state: RunState,
  ev: AgentEvent,
  now: number,
): ClaimedTimeline | null {
  const kind = String(ev.kind || '')
  const seq = Number(ev.seq ?? 0)

  // 幂等：重放/重连可能把同一 seq 再喂一次。判据演化和"上一条失败了"
  // 这类**顺序敏感**的读数一旦重入就会说错话，所以在这里挡住。
  if (seq > 0 && seq <= state.transparencySeq) return null
  if (seq > 0) state.transparencySeq = seq

  // 先看**声明的**那几个事件（`RECOGNIZED_KINDS`）：它们没有 `case`，
  // 由这里认下并自己渲染时间线。
  const handler = HANDLERS[kind as RecognizedKind]
  if (handler) return handler(state, ev, now)

  switch (kind) {
    case 'round_start': {
      // 开一轮就建一条决策轮次，`orchestrator_decision` 再往里填 reasoning。
      ensureRound(state, Number(ev.round ?? 0), seq, now)
      return null
    }

    case 'orchestrator_decision': {
      // bridge 侧的 A1（`bridge/hooks.py` 的 `_decide` 挂钩）：
      // 与上游 `orchestrator_round` **同源**（同一个 `_decide` 返回值），
      // 只是键名与 `task_count` 不同。老运行（含固定样例）只有这一条。
      const row = ensureRound(state, Number(ev.round ?? 0), seq, now)
      row.status = asText(ev.status) || row.status
      row.reasoning = asText(ev.reasoning) || row.reasoning
      row.finalAnswer = asText(ev.final_answer) || row.finalAnswer
      row.taskCount = Number(ev.task_count ?? row.taskCount)
      if (seq) row.seq = seq
      // ★ `intent` 这个键**没有任何生产者发**。真发了就照用，没发就如实记为 none。
      const hasIntent = typeof ev.intent === 'string' && ev.intent.trim().length > 0
      if (hasIntent) {
        row.intentSource = 'field'
        row.intent = String(ev.intent)
      }
      return null
    }

    case 'task_start': {
      const id = asText(ev.task_id)
      const round = state.decisionRounds[state.decisionRounds.length - 1]
      if (round && id) {
        // 声明里已经有同一条就不再叠一份 —— 但**保留两份不同来源的字面**
        // 会让"声明 vs 实测"混成一堆，所以按 id 去重，来源以声明优先。
        const dup = round.planned.find((p) => p.id === id)
        if (dup) {
          dup.toolHint = asArray(ev.tool_hint)
        } else {
          round.planned.push({
            id,
            description: asText(ev.description),
            expectedOutput: '',
            toolHint: asArray(ev.tool_hint),
            ok: null,
            source: 'dispatched',
          })
        }
      }
      return null
    }

    case 'task_done': {
      const id = asText(ev.task_id)
      // 同名任务 id 会在每次尝试里复用 —— 从后往前找第一条还没结局的
      for (let i = state.decisionRounds.length - 1; i >= 0; i -= 1) {
        const p = [...state.decisionRounds[i].planned].reverse().find((x) => x.id === id && x.ok === null)
        if (p) {
          p.ok = Boolean(ev.ok)
          break
        }
      }
      return null
    }

    /* ---------------- A3 模型回合 ---------------- */
    case 'model_reply': {
      const taskId = asText(ev.task_id)
      const step = Number(ev.step ?? 0)
      let turn = state.modelTurns.find((t) => t.taskId === taskId && t.step === step)
      if (!turn) {
        turn = {
          taskId,
          step,
          content: '',
          contentLen: 0,
          toolCalls: Number(ev.tool_calls ?? 0),
          calls: [],
          seq,
          at: now,
        }
        state.modelTurns.push(turn)
      }
      turn.content = asText(ev.content)
      turn.contentLen = Number(ev.content_len ?? turn.content.length)
      turn.toolCalls = Number(ev.tool_calls ?? turn.toolCalls)
      return null
    }

    case 'tool_call': {
      const taskId = asText(ev.task_id)
      const step = Number(ev.step ?? 0)
      const turn = state.modelTurns.find((t) => t.taskId === taskId && t.step === step)
      if (!turn) return null
      const tool = asText(ev.tool)
      const args = obj(ev.args)
      turn.calls.push({
        seq,
        tool,
        // 复用既有的参数摘要规则：**同一事实只有一处实现**
        summary: describeArgs(tool, args),
        status: 'running',
        preview: '',
      })
      return null
    }

    case 'tool_result': {
      const taskId = asText(ev.task_id)
      const step = Number(ev.step ?? 0)
      const tool = asText(ev.tool)
      const turn = state.modelTurns.find((t) => t.taskId === taskId && t.step === step)
      const call = [...(turn?.calls ?? [])].reverse().find((c) => c.tool === tool && c.status === 'running')
      if (call) {
        call.status = ev.ok === false ? 'error' : 'ok'
        call.preview = asText(ev.preview)
      }
      return null
    }

    /* ---------------- B4 判据演化（老事件流） ---------------- */
    case 'verify_probe': {
      pushCriterion(state, ev, now, ev.passed ? 'passed' : 'failed', { action: 'executed' })
      return null
    }
    case 'verify_skipped': {
      // 候选被拒：**没被执行**。"被拒"和"失败"是两件事 —— 前者说的是
      // "这张考卷不该用"，后者说的是"用了，没考过"。混起来就看不出
      // 这次到底是"判据写错了"还是"模型没做到"。
      pushCriterion(state, ev, now, 'rejected', { action: 'rejected' })
      return null
    }
    case 'verify': {
      pushCriterion(state, ev, now, ev.passed ? 'passed' : 'failed', { action: 'adopted', adopted: true })
      return null
    }

    /* ---------------- 结局（D3/P3）+ 自述缺席说明 ---------------- */
    case 'run_end':
    case 'cycle_end':
    case 'run_failed': {
      // 有的生产方把 `self_report` 塞在收尾事件里（报告字段），一并收下
      const embedded = obj((ev as Record<string, unknown>).self_report)
      if (Object.keys(embedded).length) applySelfReport(state, embedded, seq, now)
      const fc = readFactCheck(ev.fact_check)
      if (fc) state.factCheck = fc
      // ★ P3：**后端权威的**结局优先（`run_end` 上由 `bridge/runner.py` 带出来）。
      //   它缺席时**不覆盖**已有的 verdict —— 一次运行的 `cycle_end` 先到、
      //   `run_end` 后到，后者才带 verdict；反过来把 `cycle_end` 的缺席当成
      //   "后端没产出"就会把已经拿到的结论擦掉。
      //   直接把 `ev` 交给 `readVerdict`（别拼壳：见该函数里那条注释）。
      const v = readVerdict(ev) ?? readBareOutcome(asText(ev.outcome), asText(ev.outcome_reason))
      if (v) state.verdict = v
      // 四值结局也回填到 `outcome`（结论旁显示的就是它）；没给就沿用兜底推导
      if (v) {
        state.outcome = {
          value: v.outcome,
          raw: v.raw,
          source: v.criterionSource || state.outcome.source,
          reason: v.reason,
          legacyVocabulary: !FOUR_VALUES.has(v.raw),
        }
      } else {
        state.outcome = readOutcome(state, ev)
      }
      if (kind === 'run_end' && !state.selfReport && !state.selfReportAbsentReason) {
        state.selfReportAbsentReason = absentReason(state)
      }
      return null
    }

    default:
      return null
  }
}
