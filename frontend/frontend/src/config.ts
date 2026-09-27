/**
 * 前端可调参数。
 *
 * 原则：**能做成变量的，不要写成常量。**
 *
 * 分三层，越靠后优先级越高：
 *
 *   1. 这里的内置默认值            —— 保证任何时候都能跑
 *   2. 构建期环境变量 VITE_*        —— 部署时按环境改（见 .env.example）
 *   3. 后端标定 `GET /api/spec` 的 `ui` 段
 *      —— 运行期改，**不用重新构建前端**
 *
 * 第 3 层是关键：想调轮询间隔、改示例任务、开关某个面板，
 * 改后端标定就行（甚至只改仓库根的 spec.override.json），前端不用动。
 */
import { reactive } from 'vue'

function env(key: string, fallback: string): string {
  const v = (import.meta.env as Record<string, unknown>)[key]
  return typeof v === 'string' && v.length ? v : fallback
}

function envInt(key: string, fallback: number): number {
  const raw = (import.meta.env as Record<string, unknown>)[key]
  const n = Number(raw)
  return Number.isFinite(n) && n > 0 ? n : fallback
}

function envBool(key: string, fallback: boolean): boolean {
  const raw = (import.meta.env as Record<string, unknown>)[key]
  if (raw === undefined || raw === '') return fallback
  return String(raw) === 'true' || String(raw) === '1'
}

export interface AppConfig {
  /** API 基地址。空 = 同源（生产由 bridge 托管；开发由 Vite 代理） */
  apiBase: string
  /** 标定端点的路径。**唯一允许写死的路径**——拿到 spec 之前没有别的办法 */
  specPath: string

  poll: { healthMs: number; runsMs: number; decisionsMs: number }
  stream: { reconnectMs: number; maxReconnects: number }
  limits: { timeline: number; toolCalls: number; reasoning: number; detailChars: number }
  features: {
    demoRun: boolean
    cancel: boolean
    artifactViewer: boolean
    decisionInline: boolean
  }
  /** 启动面板的示例任务。由后端标定下发，前端不写死 */
  examples: Array<{ label: string; goal: string; verify: string }>

  /** 真实来源：'builtin' | 'env' | 'spec'，顶栏可显示，便于排查"参数怎么没生效" */
  source: string
}

export const config = reactive<AppConfig>({
  apiBase: env('VITE_API_BASE', ''),
  specPath: env('VITE_SPEC_PATH', '/api/spec'),

  poll: {
    healthMs: envInt('VITE_POLL_HEALTH_MS', 12000),
    runsMs: envInt('VITE_POLL_RUNS_MS', 6000),
    decisionsMs: envInt('VITE_POLL_DECISIONS_MS', 2500),
  },
  stream: {
    reconnectMs: envInt('VITE_STREAM_RECONNECT_MS', 700),
    maxReconnects: envInt('VITE_STREAM_MAX_RECONNECTS', 40),
  },
  limits: {
    timeline: envInt('VITE_LIMIT_TIMELINE', 600),
    toolCalls: envInt('VITE_LIMIT_TOOL_CALLS', 400),
    reasoning: envInt('VITE_LIMIT_REASONING', 40),
    detailChars: envInt('VITE_LIMIT_DETAIL_CHARS', 300),
  },
  features: {
    demoRun: envBool('VITE_FEATURE_DEMO', true),
    cancel: envBool('VITE_FEATURE_CANCEL', true),
    artifactViewer: envBool('VITE_FEATURE_ARTIFACTS', true),
    decisionInline: envBool('VITE_FEATURE_DECISIONS', true),
  },
  examples: [],

  source: 'builtin',
})

/** 用后端标定覆盖运行期参数。缺项保持原值，不会把配置清空。 */
export function applySpecUi(ui: Record<string, any> | undefined | null): string[] {
  if (!ui || typeof ui !== 'object') return []
  const applied: string[] = []

  const num = (v: unknown): number | null => {
    const n = Number(v)
    return Number.isFinite(n) && n > 0 ? n : null
  }
  const bool = (v: unknown): boolean | null => (typeof v === 'boolean' ? v : null)

  const set = (target: Record<string, any>, key: string, value: unknown, label: string) => {
    if (value === null || value === undefined) return
    target[key] = value
    applied.push(label)
  }

  const groups: Array<[string, Record<string, any>, (v: unknown) => unknown]> = [
    ['poll', config.poll, (v) => num(v)],
    ['stream', config.stream, (v) => num(v)],
    ['limits', config.limits, (v) => num(v)],
    ['features', config.features, (v) => bool(v)],
  ]

  for (const [group, target, coerce] of groups) {
    const incoming = ui[group]
    if (!incoming || typeof incoming !== 'object') continue
    for (const key of Object.keys(target)) {
      // 后端用 snake_case，前端用 camelCase：`health_ms` ↔ `healthMs`
      const snake = key.replace(/[A-Z]/g, (m) => '_' + m.toLowerCase())
      const raw = incoming[key] ?? incoming[snake]
      if (raw === undefined) continue
      set(target, key, coerce(raw), `${group}.${key}`)
    }
  }

  if (Array.isArray(ui.examples) && ui.examples.length) {
    config.examples = ui.examples.filter(
      (e: any) => e && typeof e.goal === 'string',
    )
    applied.push('examples')
  }

  if (applied.length) config.source = 'spec'
  return applied
}

/** 完整 URL：把相对端点接到 apiBase 上。 */
export function url(path: string): string {
  if (!path) return config.apiBase
  if (/^https?:\/\//i.test(path)) return path
  return config.apiBase + path
}
