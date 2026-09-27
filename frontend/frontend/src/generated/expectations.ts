/**
 * ⚠ 本文件由 scripts/gen-expectations.mjs 生成，**不要手改**。
 *
 * 内容 = 前端从源码里实际认得的东西。责任自审查（POST /api/audit）
 * 拿它去和服务声明比对，判断「该改前端还是后端接口定义有问题」。
 *
 * 重新生成：npm run gen:expectations
 */

export const SUPPORTED_SPEC = '1.0'

export const EXPECTATIONS = {
  spec_version: SUPPORTED_SPEC,
  /** store/run.ts 的 case 列表 */
  events: ["attempt_start","baseline","cancel_requested","cancelled","cycle_end","cycle_start","decision_action","decision_notified","decision_opened","error","files","lint","manifest","model_reply","orchestrator_decision","phase","plan","queued","retry","rollback","rollback_denied","round_start","run_end","run_start","syntax","task_done","task_result","task_start","tool_call","tool_result","verify","verify_probe","verify_skipped","worker_step"],
  /** api/client.ts 用到的端点 key */
  endpoints: ["answer_decision","audit","decisions","health","insights","profile","run","run_events","run_stream","runs","spec","workspace_file","workspace_tree"],
  /** api/spec.ts 的 DEFAULT_SPEC 内置阶段 */
  stages: ["check","manifest","plan","record","verify","write"],
  /**
   * 前端要代理的**上游**端点（vite.config.ts 的 proxy 表）。
   * ★ 上报责任自审查时用的就是它——不含 bridge 自己的 /api/*。
   */
  proxied_upstream: ["/candidates","/decisions","/encode","/profile","/reflect","/run","/skills"],
} as const

export type Expectations = typeof EXPECTATIONS
