/**
 * 责任自审查客户端。
 *
 * 启动时把前端「按什么写死的」报给服务，服务判「该谁改」：
 *
 *     服务声明了 X，前端不认识 X   → frontend（服务守约了）
 *     服务声明了 X，实际不做 X     → backend（自相矛盾）
 *     服务不可达 / 前端没构建      → ops
 *     无法从事实源单方面判定       → both（需人工协商）
 *
 * 归属边界由 `.interface_contract` 定义：**`bridge/` 属于 frontend**。
 *
 * ## 报什么，以及为什么必须按来源分开
 *
 * 上报体用契约 `client_report_schema.canonical_fields` 的字段名。
 * **事件与阶段按来源分开报**是硬要求（契约 gap_G2 / gap_G3）：
 *
 *   平铺上报事件 → 上游对 bridge 自产的 21 个事件报 P-event-gone-upstream
 *                → 结论从 ok 掉到 need-negotiation，21 条全是噪声
 *   平铺上报阶段 → 上游对 bridge 自补的 `manifest` 报 P-phase-unknown(owner=backend)
 *                → **让后端去恢复一个它从未拥有的阶段**
 *
 * 分区的**判据来自服务**（`spec.event_partition` / `spec.pipeline.upstream_phases`），
 * 成员来自前端**构建期生成**的期望（`@/generated/expectations`）。
 * 两边一交，得到的就是"前端认得的东西里，哪些属上游"。
 *
 * 拿不到结论时**不阻断界面**——只是没有徽标而已。
 */
import { reactive } from 'vue'
import { EXPECTATIONS, SUPPORTED_SPEC } from '@/generated/expectations'
import { endpoint, spec } from '@/api/spec'
import { url } from '@/config'

export interface AuditIssue {
  id: string
  owner: 'backend' | 'frontend' | 'ops' | 'both'
  owner_label: string
  severity: 'breaking' | 'degraded' | 'info'
  blocking: boolean
  title: string
  detail: string
  evidence: string[]
  fix: string
  crosswalk_id: string
}

export interface AuditResult {
  spec_version: string
  implements_contract_version: string
  contract_version_source: string
  client_reported: boolean
  client_legacy_shape: boolean
  verdict: string
  verdict_text: string
  fail_count: number
  blocking_count: number
  info_count: number
  issue_count: number
  responsibility: Record<string, AuditIssue[]>
  /**
   * ★ 非阻塞的语义提示（契约 v1.0.5 `response_contract.warnings`）。
   *
   * 当前唯一来源：**被传输层证伪的 ops 事实**——请求已成功送达，却报了
   * `service_down`。这类事实不参与 verdict，所以**只看 verdict 会看到 `ok`
   * 而看不到那条陈旧标志**，契约因此立了一条消费方义务：
   *
   * > 展示 verdict 的消费方**应当同时展示 warnings**。
   *
   * additive：后端不给时按 `[]` 处理，旧代码不会坏。
   */
  warnings: string[]
  /**
   * `ops` 栏：**全部**被上报的运行态事实（含未参与判定的），
   * 便于运维看到「上次已知状态」（契约 `response_contract.ops_column`）。
   */
  ops: Record<string, boolean>
  checked: string[]
  markdown?: string
}

export type AuditStatus = 'idle' | 'checking' | 'ok' | 'issues' | 'unavailable'

export const auditState = reactive<{
  status: AuditStatus
  message: string
  result: AuditResult | null
}>({
  status: 'idle',
  message: '',
  result: null,
})

/** 所有需要人处理的问题（按 ops → backend → frontend → both，"谁先改"的顺序） */
export function auditIssues(): AuditIssue[] {
  const r = auditState.result
  if (!r) return []
  const order = ['ops', 'backend', 'frontend', 'both']
  return order
    .flatMap((g) => r.responsibility[g] ?? [])
    .sort((a, b) => Number(b.blocking) - Number(a.blocking))
}

/**
 * 非阻塞提示。**必须与 verdict 一起展示**（契约的消费方义务）。
 *
 * 为什么不能只显示 verdict：被传输层证伪的 ops 事实不参与判定，
 * 于是结论是 `ok`，而那条陈旧标志只在这里。界面若只报「兼容」，
 * 用户就永远看不到它 —— 义务针对的正是这条"只看 verdict"的路径。
 */
export function auditWarnings(): string[] {
  return auditState.result?.warnings ?? []
}

/**
 * `ops` 栏：全部被上报的运行态事实（含未参与判定的）。
 *
 * 用途：**判断环境问题不要只看 `verdict`**。契约 v1.0.5 起的对应关系：
 *
 * | 现象 | verdict | 哪里能看到 |
 * |---|---|---|
 * | 陈旧 `service_down`（送达了却报不可达） | `ok` | **`warnings` / `ops` 栏** |
 * | `frontend_not_built` | 仍是 `ops-action` | verdict 就能看到 |
 *
 * 所以"环境问题横幅"必须读这里或 `warnings`，不能只读 verdict。
 */
export function auditOps(): Array<[string, boolean]> {
  return Object.entries(auditState.result?.ops ?? {}).sort((a, b) =>
    a[0] < b[0] ? -1 : 1,
  )
}

/**
 * 组装契约 canonical 上报体。
 *
 * 分区来自服务声明，成员来自前端生成物 —— 两边取交。
 * 这样"哪些属上游"永远由**服务**说了算，前端不自己猜。
 */
export function buildReport() {
  const upstreamEvents = new Set(spec.event_partition?.upstream ?? [])
  const upstreamPhases = new Set(spec.pipeline?.upstream_phases ?? [])
  // bridge 端点 key → 上游路径
  const mapped: Record<string, string> = spec.endpoint_partition?.mapped ?? {}

  const allEvents = [...EXPECTATIONS.events]
  const allStages = [...EXPECTATIONS.stages]
  const allKeys = [...EXPECTATIONS.endpoints]

  // ★ 上游面来自**两处**，取并集（少一处就会漏报真依赖）：
  //   1. bridge 转发的：客户端用到的 key 里能映射到上游路径的那些
  //      （走 `mapped`，因为 bridge 路径 `/api/profile` ∉ 上游路由）
  //   2. vite proxy 直接代理给上游的：构建期从 `vite.config.ts` 扫出来
  //      （`proxied_upstream`，如 /skills /candidates /encode /run）
  //   只看第 1 处会漏掉第 2 类 —— 上游删了 /skills 就没人被指到。
  //
  // ★ 两侧的**口径不同**，别统一：
  //   upstream_endpoints → 上游路径（比上游真实路由）
  //   frontend_endpoints → bridge 端点 **key**（比 bridge 自己的端点表）
  const viaBridge = allKeys.filter((k) => k in mapped).map((k) => mapped[k])
  const upPaths = [
    ...new Set([...viaBridge, ...(spec.endpoint_partition?.proxied_upstream ?? [])]),
  ].sort()
  // 两个列表**不互斥**：`profile` 既是前端用到的 bridge 端点，也是它依赖的
  // 上游能力，两处都要报。拆成互斥会让服务端以为前端没用 `/api/profile`。
  const feKeys = allKeys

  return {
    // ---- 契约 canonical 字段 ----
    contract_version: spec.implements_contract_version ?? '',
    schema_version: spec.schema_version ?? '',
    upstream_event_kinds: allEvents.filter((e) => upstreamEvents.has(e)),
    frontend_event_kinds: allEvents.filter((e) => !upstreamEvents.has(e)),
    // 上报给上游的 `phases` 只填上游阶段；bridge 自补的门禁走单独字段（gap_G3）
    phases: allStages.filter((s) => upstreamPhases.has(s)),
    bridge_gate_steps: allStages.filter((s) => !upstreamPhases.has(s)),
    upstream_endpoints: upPaths,
    frontend_endpoints: feKeys,
    // ---- bridge 内部修订号（非契约字段）----
    spec_version: SUPPORTED_SPEC,
  }
}

/** 该谁改 —— 一行话，顶栏显示用 */
export function auditSummary(): string {
  const r = auditState.result
  if (!r) return auditState.message || '未审查'
  return r.verdict_text
}

/** 跑一次责任自审查。**永不抛异常**。 */
export async function runAudit(): Promise<AuditStatus> {
  auditState.status = 'checking'
  try {
    const path = endpoint('audit') || '/api/audit'
    const res = await fetch(url(path), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildReport()),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = (await res.json()) as AuditResult
    // additive 字段：旧后端不给 warnings/ops 时按空处理，不让界面坏掉
    data.warnings = data.warnings ?? []
    data.ops = data.ops ?? {}
    auditState.result = data
    auditState.status = data.blocking_count > 0 ? 'issues' : 'ok'
    auditState.message = data.verdict_text
  } catch (e) {
    auditState.status = 'unavailable'
    auditState.result = null
    auditState.message = e instanceof Error ? e.message : String(e)
  }
  return auditState.status
}
