/**
 * 任务面板的**纯逻辑**：分组与"要不要自动跟随"。
 *
 * 为什么单独一个文件：这两件事都是**可判定的规则**，藏在 `.vue` 的 `computed`
 * 里就只能靠人点。抽出来之后可以机械断言（见 `frontend/scripts/replay-check.mjs`
 * 的 `[P2]` 段）：「19 个任务时当前项与失败项一定在可见集合里」「用户手动滚过就不抢」。
 *
 * 起因（用户原话）：「右上角的每一个任务状态，这个设计不错，但是**太多了就会压缩，
 * 也不会自动滚动**，完全失去可视化价值。」实测那两次运行分别是 **14 与 19** 个任务。
 */

import type { TaskView } from '@/types'

/** 超过这么多"已完成"就开始折叠（当前项与失败项永不受影响） */
export const COLLAPSE_AT = 6

export type TaskRow =
  | { kind: 'task'; key: string; task: TaskView }
  | { kind: 'group'; key: string; count: number; expanded: boolean }

const KEY_SEP = '#'

/** 任务在**原数组**里的下标 → 唯一 key。 */
export function taskKey(index: number, task: TaskView): string {
  // ★ 必须带上位置：任务 id 会在同一轮里被复用
  //   （实测 `run_20260927_225939_f4daaa` 里 `t9` 出现了两次）。
  //   只用 id 做 `:key`，Vue 在 patch 时会复用错节点 ——
  //   而这类错误**只在运行时报 warning**，构建与类型检查都看不出来。
  return `${index}${KEY_SEP}${task.id}`
}

/**
 * 把任务列表切成"要渲染的行"（工作单 P2 的第 1、4 条）。
 *
 * 1. **当前项（running）与失败项永远可见** —— 不参与折叠，且排在前面；
 * 2. **已完成**超过 `COLLAPSE_AT` 时聚合成一行「已完成 N 项 ▾」，展开后按原顺序列出；
 * 3. 数量少时不聚合（**不要为了整齐把简单情形也搞复杂**）。
 *
 * ⚠ 这是**显示分组**，会改变渲染顺序（已完成挪到折叠区）——所以折叠行**必须**
 * 明写「已完成 N 项」，让人知道那些项还在、只是收起来了。
 * 把"收起"做成"看不见"而不说明，正是这一轮要防的那种事。
 *
 * 入参顺序沿用面板既有的**新 → 旧**。
 */
export function taskRows(
  tasks: TaskView[],
  opts: { expanded?: boolean; collapseAt?: number; keepIndex?: number } = {},
): TaskRow[] {
  const expanded = opts.expanded ?? false
  const collapseAt = opts.collapseAt ?? COLLAPSE_AT
  const keepIndex = opts.keepIndex ?? -1

  const indexed = tasks.map((task, index) => ({ task, index }))
  // ★ **当前项永远可见**（工作单第 4 条的硬要求）：一次运行跑完之后，"当前项"
  //   的状态也是 `done` —— 按状态分它就该进折叠区，于是"当前项可见"在**运行结束时**
  //   恰好失效（而那正是人回头看的时候）。所以按**下标**把它单独捞出来。
  const isKeep = (i: number) => i === keepIndex
  const active = indexed.filter((x) => x.task.status !== 'done' || isKeep(x.index))
  const done = indexed.filter((x) => x.task.status === 'done' && !isKeep(x.index))

  const rows: TaskRow[] = active.map((x) => ({
    kind: 'task' as const,
    key: taskKey(x.index, x.task),
    task: x.task,
  }))

  if (done.length > collapseAt) {
    rows.push({ kind: 'group', key: '__done__', count: done.length, expanded })
    if (expanded) {
      for (const x of done) {
        rows.push({ kind: 'task', key: taskKey(x.index, x.task), task: x.task })
      }
    }
    return rows
  }

  for (const x of done) {
    rows.push({ kind: 'task', key: taskKey(x.index, x.task), task: x.task })
  }
  return rows
}

/** 渲染出来的任务项 key（断言用；key 唯一，id 会重复） */
export function visibleKeys(rows: TaskRow[]): string[] {
  return rows
    .filter((r): r is Extract<TaskRow, { kind: 'task' }> => r.kind === 'task')
    .map((r) => r.key)
}

/** 被折叠**藏起来**的那些任务（断言用：藏起来的必须全是 `done`） */
export function hiddenTasks(tasks: TaskView[], rows: TaskRow[]): TaskView[] {
  const shown = new Set(visibleKeys(rows))
  return tasks.filter((t, i) => !shown.has(taskKey(i, t)))
}

/** 自动跟随的两种状态：`follow` = 跟着当前项；`manual` = 用户手动滚过，别抢 */
export type FollowMode = 'follow' | 'manual'

/**
 * 该不该自动把当前项滚进视野？
 *
 * ★ 只在 `follow` 模式下滚 —— **用户手动滚过就不抢**（工作单第 3 条）。
 * 抢滚动是最容易让人恼火的一种"贴心"，而它恰恰会让"回看历史"变得不可能。
 */
export function shouldAutoFollow(mode: FollowMode): boolean {
  return mode === 'follow'
}

/**
 * 滚动之后模式怎么变。
 *
 * - 用户自己滚（`user`）：离开 `follow`，除非他已经滚回当前项附近（`nearCurrent`）；
 * - 程序自己滚（`program`）：**不动模式** —— 否则程序一滚就变成"用户滚过"，
 *   跟随会自己把自己关掉（这是最容易写错的一处）。
 */
export function modeAfterScroll(
  mode: FollowMode,
  cause: 'user' | 'program',
  nearCurrent: boolean,
): FollowMode {
  if (cause === 'program') return mode
  return nearCurrent ? 'follow' : 'manual'
}
