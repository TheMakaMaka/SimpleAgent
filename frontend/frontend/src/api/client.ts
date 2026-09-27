/**
 * 后端 HTTP 客户端。
 *
 * **路径不写死在这里**——它们来自后端标定（`spec.endpoints`，见 `@/api/spec`）。
 * 后端把某个端点挪了位置，前端跟着走，不用改代码。
 *
 * 唯一的例外是**标定端点自己**（`config.specPath`）：拿到 spec 之前没有别的办法。
 */
import { config, url } from '@/config'
import { endpoint } from '@/api/spec'
import type { DecisionView, RunInfo } from '@/types'

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url(path), {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  const text = await res.text()
  let data: unknown = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = { detail: text }
  }
  if (!res.ok) {
    const detail =
      (data as any)?.detail ??
      (data as any)?.message ??
      `HTTP ${res.status} ${res.statusText}`
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return data as T
}

/** 端点缺失时给出可诊断的错误，而不是往空路径发请求 */
function need(key: string, params?: Record<string, string>): string {
  const path = endpoint(key, params)
  if (!path) throw new Error(`标定里没有端点 "${key}"（GET ${config.specPath} 可查看）`)
  return path
}

export interface HealthInfo {
  ok: boolean
  checkpoint_backend: string
  model: { name: string; base_url: string; context_window: number | null }
  problems: string[]
  runs_root: string
  approval_base_url: string
}

export interface StartRunPayload {
  goal: string
  verify_command?: string | null
  session_id?: string
  max_attempts?: number
  on_decision?: string
  max_consecutive_failures?: number
  demo?: boolean
}

export const api = {
  health: () => http<HealthInfo>(need('health')),

  profile: () => http<Record<string, any>>(need('profile')),

  startRun: (payload: StartRunPayload) =>
    http<{ ok: boolean; run: RunInfo }>(need('runs'), {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  listRuns: (limit = 30) =>
    http<{ count: number; active: number; runs: RunInfo[] }>(`${need('runs')}?limit=${limit}`),

  getRun: (runId: string) => http<{ run: RunInfo }>(need('run', { run_id: runId })),

  cancelRun: (runId: string) =>
    http<{ ok: boolean; message: string }>(need('run', { run_id: runId }), {
      method: 'DELETE',
    }),

  runEvents: (runId: string, after = 0, limit = 5000) =>
    http<{ run_id: string; status: string; terminal: boolean; last_seq: number; events: any[] }>(
      `${need('run_events', { run_id: runId })}?after=${after}&limit=${limit}`,
    ),

  workspaceFile: (path: string) =>
    http<{ path: string; size: number; lines: number; content: string; truncated: boolean }>(
      `${need('workspace_file')}?path=${encodeURIComponent(path)}`,
    ),

  workspaceTree: () =>
    http<{
      count: number
      root: string
      files: Array<{ path: string; size: number; mtime: number }>
    }>(need('workspace_tree')),

  decisions: (runId?: string, all = false) =>
    http<{ count: number; decisions: DecisionView[] }>(
      `${need('decisions')}?${runId ? `run_id=${encodeURIComponent(runId)}&` : ''}all=${all ? 1 : 0}`,
    ),

  answerDecision: (id: string, value: string, by = 'webui') =>
    http<{ ok: boolean; message: string }>(need('answer_decision', { decision_id: id }), {
      method: 'POST',
      body: JSON.stringify({ value, by }),
    }),

  insights: () => http<Record<string, any>>(need('insights')),
}
