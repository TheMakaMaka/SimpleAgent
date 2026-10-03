/**
 * 工具调用的可读摘要 —— 「它现在到底在干什么」的答案。
 *
 * 为什么单独一个文件：`store/run.ts`（时间线/工具面板）与
 * `store/transparency.ts`（A3 模型回合原话）都要用同一套摘要。
 * 复制一份到两边，就会出现"同一个工具调用在两张面板上写法不同"——
 * 那是**同一事实的两处实现**，迟早会分叉。
 *
 * 少量**结构化摘要**规则留在这里：它们依赖各工具参数的具体形状，
 * 后端标定表达不了。其余情况回退到"列出参数名"，够用且不会因为新工具而崩。
 */

/**
 * 长内容在事件里是**预览**，不是全文。
 *
 * `bridge/hooks.py:62-79` 的 `preview_args()` 把超过 200 字符的字符串换成
 * 「前 6 行 + `…（共 N 字符）`」。所以：
 *
 *   - **不能再对预览串取 `.length` 当"文件多大"** —— 实测样例里
 *     `obstacle_generator.py` 事件串长 235、真实 275，面板上会显示 235，
 *     而"275"就写在同一个字符串里。一个对不上机械事实的数字，
 *     正是这一轮要消灭的东西。
 *   - 真值优先取**同一个字符串里已经声明的那个数**。
 */
const DECLARED_LEN = /…（共 (\d+) 字符）/

/** 事件串里声明的真实长度；没有声明（未被截断）返回 null。 */
export function declaredLength(v: unknown): number | null {
  if (typeof v !== 'string') return null
  const m = DECLARED_LEN.exec(v)
  return m ? Number(m[1]) : null
}

/** 内容的真实字符数：优先用事件里声明的真值，否则按原文数。 */
export function contentLength(v: unknown): number {
  const declared = declaredLength(v)
  if (declared !== null) return declared
  return typeof v === 'string' ? v.length : 0
}

const ARG_SUMMARY: Record<string, (args: Record<string, unknown>) => string> = {
  write_file: (a) => `写入 ${a.filename ?? '?'}（${contentLength(a.content)} 字符）`,
  read_file: (a) => `读取 ${a.filename ?? '?'}`,
  run_python: (a) => `执行 ${String(a.code ?? '').split('\n').length} 行 Python`,
  check_and_run: (a) => `执行 ${String(a.code ?? '').split('\n').length} 行 Python`,
  check_syntax: (a) => `语法检查 ${contentLength(a.code)} 字符`,
}

export function describeArgs(tool: string, args: Record<string, unknown>): string {
  if (!args || typeof args !== 'object') return ''
  const fn = ARG_SUMMARY[tool]
  if (fn) return fn(args)
  const keys = Object.keys(args)
  return keys.length ? keys.join(', ') : ''
}
