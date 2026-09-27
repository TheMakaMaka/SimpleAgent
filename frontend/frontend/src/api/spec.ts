/**
 * 标定客户端：向后端要一份「我长什么样」，前端照单渲染。
 *
 * 为什么要有这个
 * --------------
 * 在这之前，阶段名、事件词表、工具名、状态色**全写死在前端**。
 * 后端一改（加阶段、改事件、加工具），前端就得跟着改 —— 那不是"低定制"。
 *
 * 现在这些事实全部来自 `GET /api/spec`：
 *
 *     后端 scan 代码 → spec → 前端渲染
 *
 * 前端不猜、不写死；后端加东西前端自动跟上。
 *
 * ## 拿不到 spec 怎么办
 *
 * `DEFAULT_SPEC` 是内置兜底：没网、端点没上、后端是旧版本时，界面照常可用。
 * 它是**上一版 spec 的快照**，由 `tests/unit/test_spec.py` 把守，
 * 保证它和真实 spec 的关键部分（阶段、事件词）不脱节。
 */
import { reactive } from 'vue'
import { applySpecUi, config, url } from '@/config'

export interface StageSpec {
  id: string
  label: string
  hint: string
  /** 图标名（前端图标库的 key）。认不出回退到通用图标 */
  icon?: string
  kind: 'phase' | 'gate' | 'custom'
}

export interface EventSpec {
  label: string
  tone: string
  panel: string
  title?: string
  detail?: string
  /** false = 后端自动兜底生成的，还没人工标定 */
  calibrated?: boolean
  sources?: string[]
}

export interface StatusSpec {
  label: string
  tone: string
  terminal: boolean
}

export interface ToolSpec {
  name: string
  label: string
  description: string
  profiles: string[]
  calibrated: boolean
}

export interface SpecDiagnostics {
  event_count: number
  uncalibrated_events: string[]
  dead_calibrations: string[]
  override_file: string | null
  errors: string[]
}

/**
 * 三条**分区**：哪些东西属上游，哪些是本仓库自补的。
 *
 * 为什么前端要拿这个：上报责任自审查时，把自补的东西当上游上报，会让上游
 * 对 bridge 自己造的事件/阶段/端点报「你删了」——归属就指错人了。
 * 分区由**服务**推导（`bridge/partition.py`），前端只做集合求交，不自己猜。
 */
export interface EventPartition {
  /** 上游 `coding_cycle.py` 发出的事件 */
  upstream: string[]
  /** bridge 补的事件 */
  frontend: string[]
  total: number
  /** 按定义恒空，留作断言 */
  overlap: string[]
}

export interface EndpointPartition {
  /**
   * 前端要代理的**上游**端点（路径）。
   *
   * 事实源 **两处**，缺一不可：
   *   1. bridge 转发的那几个（`mapped` 的值）
   *   2. `vite.config.ts` proxy 表里**直接**代理给上游的（`proxied_upstream`）
   *
   * 只看第 1 处会漏掉 `/skills` `/candidates` `/encode` `/run` ——
   * 它们不走 bridge，但同样是前端真实依赖的上游面。
   */
  upstream: string[]
  /** bridge 自己的端点（路径），仅信息 */
  frontend: string[]
  /** bridge 端点 key → 上游路径 */
  mapped: Record<string, string>
  /** `vite.config.ts` 的 proxy 表（上游部分）；空 = 服务没读到那个文件 */
  proxied_upstream: string[]
}

export interface Spec {
  spec_version: string
  generated_at: string
  /**
   * bridge **实现**的契约版本。值来自上游 `core.contract.CONTRACT_VERSION`，
   * 读不到才回退，且必须连来源一起给。
   *
   * ★ 别把它和 `spec_version` 比大小 —— 两者是**不同所有者**的独立轴线：
   *   `implements_contract_version` / `schema_version` 属后端，
   *   `spec_version` 属前端。相减得到的数没有意义。
   */
  implements_contract_version: string
  /** 'upstream' | 'fallback'（fallback 时上游会走降级路径，这是契约允许的） */
  implements_contract_version_source: string
  schema_version: string
  /** 'upstream' | 'absent' */
  schema_version_source: string

  runtime: Record<string, unknown>
  endpoints: Record<string, string>
  endpoint_partition: EndpointPartition
  pipeline: {
    /** 前端要画的**全部**节点（含 bridge 自补的门禁），共 6 个 */
    stages: StageSpec[]
    failure_phase: string
    /** 其中属上游的阶段（5 个）——上报 `phases` 只填这些 */
    upstream_phases: string[]
    /** 其中 bridge 自补的门禁节点（如 `manifest`）——上报走单独的字段 */
    bridge_gate_steps: string[]
  }
  event_partition: EventPartition
  statuses: Record<string, StatusSpec>
  events: Record<string, EventSpec>
  tools: ToolSpec[]
  ui: Record<string, unknown>
  diagnostics: SpecDiagnostics
}

/** 兜底 spec：与服务端不一致时仍能渲染。由 test_spec.py 把守一致性。 */
export const DEFAULT_SPEC: Spec = {
  spec_version: 'fallback',
  generated_at: '',
  // 契约版本轴线。兜底值取自契约 v1.0（bridge/contract_vocab.CONTRACT_FALLBACK_VERSION）。
  // `_source: 'fallback'` 是刻意的：bridge 拿不到上游时**必须承认**，不能冒充后端。
  implements_contract_version: '1.0',
  implements_contract_version_source: 'fallback',
  schema_version: '',
  schema_version_source: 'absent',
  runtime: {},
  endpoints: {
    spec: '/api/spec',
    audit: '/api/audit',
    health: '/api/health',
    profile: '/api/profile',
    runs: '/api/runs',
    run: '/api/runs/{run_id}',
    run_events: '/api/runs/{run_id}/events',
    run_stream: '/api/runs/{run_id}/stream',
    workspace_file: '/api/workspace/file',
    workspace_tree: '/api/workspace/tree',
    decisions: '/api/decisions',
    answer_decision: '/api/decisions/{decision_id}/answer',
    insights: '/api/insights',
    reflect: '/api/reflect',
  },
  // 端点分区（契约 gap_G4）。upstream 是**前端真的要代理的上游面**：
  //   bridge 转发的（/profile /reflect /decisions）+ vite proxy 直接代理的
  //   （/skills /candidates /encode /run）。
  // ★ 绝不能把 14 个 /api/* 全塞进 upstream —— 那会让上游对 11 个它从未
  //   拥有的端点报 P-endpoint-missing(owner=backend)，与 gap_G3 同型。
  endpoint_partition: {
    upstream: [
      '/candidates',
      '/decisions',
      '/encode',
      '/profile',
      '/reflect',
      '/run',
      '/skills',
    ],
    frontend: [
      '/api/audit',
      '/api/decisions',
      '/api/decisions/{decision_id}/answer',
      '/api/health',
      '/api/insights',
      '/api/profile',
      '/api/reflect',
      '/api/runs',
      '/api/runs/{run_id}',
      '/api/runs/{run_id}/events',
      '/api/runs/{run_id}/stream',
      '/api/spec',
      '/api/workspace/file',
      '/api/workspace/tree',
    ],
    mapped: { profile: '/profile', reflect: '/reflect', decisions: '/decisions' },
    proxied_upstream: [
      '/candidates',
      '/decisions',
      '/encode',
      '/profile',
      '/reflect',
      '/run',
      '/skills',
    ],
  },
  pipeline: {
    stages: [
      { id: 'plan', label: 'PLAN', hint: '主模型拆解目标', kind: 'phase' , icon: 'route' },
      { id: 'write', label: 'WRITE', hint: '子模型调用工具落盘', kind: 'phase' , icon: 'pencil' },
      { id: 'manifest', label: 'MANIFEST', hint: '声明的交付 vs 实际产出', kind: 'gate' , icon: 'clipboard' },
      { id: 'check', label: 'CHECK', hint: '语法 / lint · 由程序把关', kind: 'phase' , icon: 'shield' },
      { id: 'verify', label: 'VERIFY', hint: '验收命令退出码', kind: 'phase' , icon: 'terminal' },
      { id: 'record', label: 'RECORD', hint: '检查点 · 失败则回退', kind: 'phase' , icon: 'bookmark' },
    ],
    failure_phase: 'failed',
    // 阶段分区（契约 gap_G3）：`manifest` 是 bridge 在 write/check 之间自补的
    // 门禁节点，上游没有。把它当 `phases` 上报，上游会报
    // P-phase-unknown(owner=backend) —— 让后端去恢复一个它从未拥有的阶段。
    upstream_phases: ['plan', 'write', 'check', 'verify', 'record'],
    bridge_gate_steps: ['manifest'],
  },
  // 事件分区（契约 gap_G2）：上游 12 + bridge 21 = 33，不相交。
  // 兜底只有上游那 12 个（它们由契约固定），bridge 那一侧由构建期生成物补全。
  event_partition: {
    upstream: [
      'cycle_end', 'cycle_start', 'decision_action', 'decision_notified',
      'decision_opened', 'lint', 'manifest', 'plan', 'rollback_denied',
      'syntax', 'task_result', 'verify',
    ],
    frontend: [],
    total: 12,
    overlap: [],
  },
  statuses: {
    queued: { label: '排队', tone: 'neutral', terminal: false },
    running: { label: '执行中', tone: 'live', terminal: false },
    passed: { label: '通过', tone: 'ok', terminal: true },
    failed: { label: '失败', tone: 'err', terminal: true },
    relaxed: { label: '放宽', tone: 'warn', terminal: true },
    cancelled: { label: '取消', tone: 'warn', terminal: true },
    error: { label: '异常', tone: 'err', terminal: true },
  },
  events: {},
  tools: [],
  // 兜底的可调参数。真值由后端 `spec.ui` 覆盖（bridge/spec.py 的 UI_DEFAULTS）。
  // 保持一致由 tests/unit/test_spec.py 把守。
  ui: {
    poll: { health_ms: 12000, runs_ms: 6000, decisions_ms: 2500 },
    stream: { reconnect_ms: 700, max_reconnects: 40 },
    limits: { timeline: 600, tool_calls: 400, reasoning: 40, detail_chars: 300 },
    features: { demo_run: true, cancel: true, artifact_viewer: true, decision_inline: true },
    examples: [
      {
        label: 'L1 · 纯函数',
        goal: '在 workspace 下创建 add.py，实现 add(a, b) 返回两数之和',
        verify: "import add\nassert add.add(2, 3) == 5\nprint('PASS')",
      },
    ],
  },
  diagnostics: {
    event_count: 0,
    uncalibrated_events: [],
    dead_calibrations: [],
    override_file: null,
    errors: [],
  },
}

export const spec = reactive<Spec>(structuredClone(DEFAULT_SPEC))

/** 标定加载状态。'fallback' = 端点拿不到，在用内置兜底 spec */
export type SpecStatus = 'idle' | 'loading' | 'ready' | 'fallback' | 'error'

export const specState = reactive<{
  status: SpecStatus
  message: string
  applied: string[]
}>({
  status: 'idle',
  message: '',
  applied: [],
})

/** 加载标定。**永不抛异常**——拿不到就用内置兜底，界面不能因此起不来。 */
export async function loadSpec(): Promise<SpecStatus> {
  specState.status = 'loading'
  try {
    // 优先用标定自己的端点表，`config.specPath` 是拿不到标定时的入口。
    // 顺带让 `gen-expectations.mjs` 扫得到这个 key —— 否则服务端会以为
    // 前端根本没用 `/api/spec`（它确实在用，只是写法绕过了扫描规则）。
    const path = endpoint('spec') || config.specPath
    const res = await fetch(url(path), {
      headers: { Accept: 'application/json' },
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = (await res.json()) as Spec

    // 关键字段缺失就认为不可信，退回兜底（避免半份 spec 把界面画歪）
    if (!data?.pipeline?.stages?.length || !data?.endpoints) {
      throw new Error('spec 缺少 pipeline.stages 或 endpoints')
    }

    Object.assign(spec, DEFAULT_SPEC, data)
    // `pipeline` / `*_partition` 是嵌套对象，浅合并会让**旧版后端**的半份 spec
    // 把兜底整个冲掉：少了 `upstream_phases`，就会把 bridge 自补的门禁节点
    // 当上游阶段上报（正是 gap_G3 那个错误）。所以这几个按字段补齐。
    spec.pipeline = { ...DEFAULT_SPEC.pipeline, ...(data.pipeline ?? {}) }
    if (!spec.pipeline.stages?.length) {
      spec.pipeline.stages = DEFAULT_SPEC.pipeline.stages
    }
    spec.endpoint_partition = {
      ...DEFAULT_SPEC.endpoint_partition,
      ...(data.endpoint_partition ?? {}),
    }
    spec.event_partition = {
      ...DEFAULT_SPEC.event_partition,
      ...(data.event_partition ?? {}),
    }
    specState.applied = applySpecUi(data.ui as Record<string, unknown>)
    specState.status = 'ready'
    specState.message = `spec v${data.spec_version}`
  } catch (e) {
    Object.assign(spec, DEFAULT_SPEC)
    specState.status = 'fallback'
    specState.message = e instanceof Error ? e.message : String(e)
  }
  return specState.status
}

/* ------------------------------------------------------------------ */
/* 便捷取用                                                            */
/* ------------------------------------------------------------------ */

export function eventSpec(kind: string): EventSpec | null {
  return spec.events?.[kind] ?? null
}

export function statusSpec(status: string): StatusSpec {
  return (
    spec.statuses?.[status] ?? {
      label: status,
      tone: 'neutral',
      terminal: false,
    }
  )
}

export function toolLabel(name: string): string {
  const t = spec.tools?.find((x) => x.name === name)
  return t?.label || name
}

/** 端点路径（带 `{name}` 占位）。找不到就返回空串，调用方自己决定怎么办。 */
export function endpoint(key: string, params?: Record<string, string>): string {
  let path = spec.endpoints?.[key] ?? ''
  for (const [k, v] of Object.entries(params ?? {})) {
    path = path.replace(`{${k}}`, encodeURIComponent(v))
  }
  return path
}

/**
 * 模板渲染：`"调用 {tool}"` + `{tool: "write_file"}` → `"调用 write_file"`。
 * 未提供的占位符原样保留，便于一眼看出"这个字段后端没给"。
 */
export function render(template: string, payload: Record<string, unknown>): string {
  return template.replace(/\{(\w+)\}/g, (_m, key: string) => {
    const v = payload[key]
    if (v === undefined || v === null || v === '') return `{${key}}`
    return String(v)
  })
}

/** 没写模板时，从 payload 里自动挑一个可读的字段当详情。 */
const DETAIL_KEYS = [
  'detail', 'error', 'output', 'message', 'description',
  'preview', 'reason', 'question', 'content', 'summary',
]

export function autoDetail(payload: Record<string, unknown>, limit: number): string {
  for (const key of DETAIL_KEYS) {
    const v = payload[key]
    if (typeof v === 'string' && v.trim()) return v.trim().slice(0, limit)
  }
  return ''
}
