<script setup lang="ts">
/**
 * 任务 / 子循环面板：编排器拆出来的任务，以及每个任务的步数进度。
 *
 * ## 这一版为什么改了（用户原话）
 *
 * > 「右上角的每一个任务状态，这个设计不错，但是**太多了就会压缩，也不会自动滚动**，
 * > 完全失去可视化价值。」
 *
 * 实测那两次运行是 **14 与 19** 个任务。四条要求（只改显示，不改判定）：
 *
 * | # | 要求 | 落点 |
 * |---|---|---|
 * | 1 | **不压缩** | `.task { flex: 0 0 auto }` + `min-height` |
 * | 2 | **可滚动** | `.tasks` 有界高度 + `.tasks__body { overflow-y: auto }` |
 * | 3 | **当前项自动在视野内**（手动滚过则不抢） | `store/tasklist.ts` 的 `FollowMode` |
 * | 4 | **量大时降级可读** | `taskRows()` 折叠已完成，当前项与失败项永远可见 |
 *
 * ★ 两处最容易写错的地方（都已落到 `store/tasklist.ts` 的纯函数里，可机械断言）：
 *
 * - **程序自己滚动不能改变跟随模式**，否则"自动跟随"会在第一次自动滚动之后
 *   把自己关掉（`modeAfterScroll(mode, 'program', …)` 直接返回原模式）；
 * - **任务 id 会在同一轮里被复用**（实测 `t9` 出现两次），`:key` 必须带位置。
 */
import type { RunState } from '@/types'
import { computed, nextTick, ref, watch } from 'vue'
import { toolLabel } from '@/api/spec'
import {
  modeAfterScroll,
  shouldAutoFollow,
  taskRows,
  type FollowMode,
} from '@/store/tasklist'

const props = defineProps<{ state: RunState }>()

const expanded = ref(false)
const mode = ref<FollowMode>('follow')
const body = ref<HTMLElement | null>(null)
const currentRow = ref<HTMLElement | null>(null)

/** "新 → 旧"的视图（面板既有顺序）；`keepIndex` 用来钉住当前项 */
const reversed = computed(() => [...props.state.tasks].reverse())
const keepIndex = computed(() => reversed.value.findIndex((t) => t.id === props.state.currentTaskId))
const rows = computed(() =>
  taskRows(reversed.value, { expanded: expanded.value, keepIndex: keepIndex.value }),
)
const reasoning = computed(() => props.state.reasoning.slice(0, 3))
const doneCount = computed(() => props.state.tasks.filter((t) => t.status === 'done').length)
const failedCount = computed(() => props.state.tasks.filter((t) => t.status === 'failed').length)
const collapsed = computed(() => rows.value.some((r) => r.kind === 'group'))
const following = computed(() => mode.value === 'follow')

function stepPercent(t: { steps: number; maxSteps: number }) {
  if (!t.maxSteps) return 0
  return Math.min(100, Math.round((t.steps / t.maxSteps) * 100))
}

/**
 * "这次滚动是谁发起的"用**截止时间**判，而不是一个一次性布尔量。
 *
 * 理由：`scrollTo({behavior:'smooth'})` 会连续触发**多个** `scroll` 事件。
 * 用一次性标志，第一个事件就把它清掉，后面几个会被当成**用户**滚动 ——
 * 于是"是否在跟随"被自己的动画关掉。这类错只在真浏览器里偶发，
 * 机械测试抓不到，所以要在写的时候就写对。
 */
const PROGRAMMATIC_MS = 700
let programmaticUntil = 0

function onScroll() {
  const el = body.value
  if (!el) return
  const row = currentRow.value
  const near = row
    ? row.offsetTop >= el.scrollTop - 12 && row.offsetTop <= el.scrollTop + el.clientHeight
    : el.scrollTop <= 12
  const cause = Date.now() < programmaticUntil ? 'program' : 'user'
  mode.value = modeAfterScroll(mode.value, cause, near)
}

/** 把当前项滚进视野（只在跟随模式、且它真的不在视野里时动） */
async function followCurrent() {
  if (!shouldAutoFollow(mode.value)) return
  await nextTick()
  const el = body.value
  const row = currentRow.value
  if (!el || !row) return
  const visible =
    row.offsetTop >= el.scrollTop - 12 &&
    row.offsetTop + row.offsetHeight <= el.scrollTop + el.clientHeight
  if (visible) return
  programmaticUntil = Date.now() + PROGRAMMATIC_MS
  el.scrollTo({ top: Math.max(0, row.offsetTop - 8), behavior: 'smooth' })
}

/** 新任务 / 状态变化 / 换当前项 → 跟随（用户手动滚过时 `shouldAutoFollow` 会拦住） */
watch(
  () => props.state.tasks.map((t) => `${t.id}:${t.status}:${t.steps}`).join('|'),
  () => void followCurrent(),
)
watch(() => props.state.currentTaskId, () => void followCurrent())
watch(expanded, () => void followCurrent())

/** 用户点「跟随当前项」= 明确要求回到跟随模式（手动滚过之后的可逆出口） */
function resumeFollow() {
  mode.value = 'follow'
  void followCurrent()
}

/** 给当前任务行挂 ref（用函数 ref：只有当前项需要它） */
function bindCurrent(el: Element | { $el?: Element } | null, id: string) {
  if (id !== props.state.currentTaskId) return
  const node = (el as HTMLElement | null) ?? null
  currentRow.value = node && node.nodeType === 1 ? node : null
}
</script>

<template>
  <section class="tasks card">
    <div class="card__head">
      <h2 class="card__title">任务与子循环</h2>
      <span class="pill tiny mono">{{ state.tasks.length }}</span>
      <span v-if="doneCount" class="pill tiny muted mono">已完成 {{ doneCount }}</span>
      <span v-if="failedCount" class="pill tiny pill--err mono">失败 {{ failedCount }}</span>
      <span class="spacer" />
      <button
        v-if="!following"
        type="button"
        class="tasks__follow"
        title="回到自动跟随当前任务"
        @click="resumeFollow"
      >
        ↓ 跟随当前项
      </button>
      <span v-else class="pill tiny muted" title="新任务会自动滚到当前项；你手动滚动后会暂停跟随">
        跟随中
      </span>
      <span class="pill tiny mono">步数 {{ state.steps }} · 响应 {{ state.modelReplies }}</span>
    </div>

    <!-- ★ 滚动容器：格子自己有界高（`.tasks` 的 max-height），这里只负责**内部**滚 -->
    <div ref="body" class="card__body tasks__body" @scroll.passive="onScroll">
      <div v-if="!rows.length" class="empty">暂无任务</div>

      <template v-for="r in rows" :key="r.key">
        <!-- 折叠行：**明写数量**，让人知道那些项还在、只是收起来了 -->
        <button
          v-if="r.kind === 'group'"
          type="button"
          class="taskGroup"
          :aria-expanded="r.expanded"
          @click="expanded = !expanded"
        >
          已完成 {{ r.count }} 项 {{ r.expanded ? '▴ 收起' : '▾ 展开' }}
        </button>

        <div
          v-else
          :ref="(el) => bindCurrent(el as Element | null, r.task.id)"
          class="task"
          :class="[`task--${r.task.status}`, { 'task--current': r.task.id === state.currentTaskId }]"
        >
          <div class="task__top">
            <span class="task__id mono">{{ r.task.id }}</span>
            <span class="task__desc">{{ r.task.description }}</span>
            <span class="task__state">
              <template v-if="r.task.status === 'running'">
                <i class="spinner" />
                进行中
              </template>
              <template v-else-if="r.task.status === 'done'">✓ 完成</template>
              <template v-else>✕ 失败</template>
            </span>
          </div>

          <div class="task__meta">
            <span v-for="h in r.task.toolHint" :key="h" class="pill tiny">
              {{ toolLabel(h) }}   <!-- 标定里没这个名字时返回原名 -->
            </span>
            <span v-if="r.task.maxSteps" class="tiny muted mono">
              步 {{ r.task.steps }} / {{ r.task.maxSteps }}
            </span>
          </div>

          <div v-if="r.task.status === 'running' && r.task.maxSteps" class="task__bar">
            <div class="task__barFill" :style="{ width: stepPercent(r.task) + '%' }" />
          </div>

          <div v-if="r.task.error" class="task__err mono">{{ r.task.error }}</div>
          <div v-else-if="r.task.output" class="task__out mono">{{ r.task.output.slice(0, 220) }}</div>
        </div>
      </template>

      <div v-if="collapsed && !expanded" class="tasks__note">
        折叠的只是<b>已完成</b>项；进行中与失败的<b>永远在上面</b>。
      </div>
    </div>

    <!--
      ★ 编排器的决策依据放在**滚动区之外**：它是"现在为什么这么做"，
      不该因为任务列表滚到别处而看不见。
      （这一块原先标的是「主模型推理」——**说错了人**：这些文字来自
      `orchestrator_decision.reasoning`，是编排器给的理由，不是子模型的推理。）
    -->
    <div v-if="reasoning.length" class="reasoning">
      <div class="reasoning__head">编排器决策依据（最近 {{ reasoning.length }} 轮 · 完整视图见下方「为什么」）</div>
      <div v-for="r in reasoning" :key="r.at" class="reasoning__item">
        <span class="reasoning__round mono">R{{ r.round }}</span>
        <span class="reasoning__text">{{ r.text || '（无说明）' }}</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.tasks {
  display: flex;
  flex-direction: column;
  min-height: 0;
  /* ★ 有界高度：滚动发生在**面板内部**，不是整页滚（工作单第 2 条） */
  max-height: 44vh;
}
.tasks__body {
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 7px;
  min-height: 0;
}

.empty {
  color: var(--fg-2);
  font-size: 12px;
  text-align: center;
  padding: 18px 0;
}

/* ★ 不压缩（工作单第 1 条）。
   在有界高度的 flex 列里，子项默认 `flex-shrink: 1` —— 它们会**先被压缩、
   永远不溢出**，于是 `overflow-y: auto` 永远不生效：**同一个机制同时解释了
   用户的两句话**（"太多了就会压缩" + "也不会自动滚动"）。 */
.task {
  flex: 0 0 auto;
  min-height: 46px;
  box-sizing: border-box;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  padding: 8px 10px;
  background: rgba(11, 18, 32, 0.55);
  animation: fadeSlideIn 0.3s var(--ease) both;
  position: relative;
  overflow: hidden;
}
.task--running {
  border-color: rgba(53, 224, 208, 0.4);
}
/* 当前项：左侧一条竖线，滚动时一眼能找到它 */
.task--current {
  box-shadow: inset 2px 0 0 var(--cyan);
}
.task--running::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, transparent, rgba(53, 224, 208, 0.09), transparent);
  background-size: 240% 100%;
  animation: shimmer 1.8s linear infinite;
  pointer-events: none;
}
.task--done {
  border-color: rgba(70, 224, 138, 0.3);
}
/* ★ 失败项永远可见：它**不参与折叠**（`taskRows` 只收 `done`），
   这里再给它一个不依赖顺序的视觉锚点。 */
.task--failed {
  border-color: rgba(255, 107, 129, 0.4);
  background: rgba(255, 107, 129, 0.06);
}

.taskGroup {
  flex: 0 0 auto;
  width: 100%;
  text-align: left;
  font-size: 11px;
  font-family: var(--mono);
  color: var(--fg-2);
  background: rgba(120, 165, 220, 0.07);
  border: 1px dashed var(--line-strong);
  border-radius: var(--radius-sm);
  padding: 6px 10px;
  cursor: pointer;
}
.taskGroup:hover {
  color: var(--cyan);
  border-color: rgba(53, 224, 208, 0.45);
}
.tasks__note {
  font-size: 10px;
  color: var(--fg-2);
  padding: 2px 2px 4px;
}
.tasks__follow {
  font-size: 10.5px;
  padding: 2px 8px;
  border-radius: 6px;
  border: 1px solid rgba(53, 224, 208, 0.5);
  background: rgba(53, 224, 208, 0.1);
  color: var(--cyan);
  cursor: pointer;
}

.task__top {
  display: flex;
  align-items: baseline;
  gap: 7px;
}
.task__id {
  font-size: 10px;
  color: var(--fg-2);
  border: 1px solid var(--line-strong);
  border-radius: 4px;
  padding: 0 4px;
}
.task__desc {
  flex: 1 1 auto;
  font-size: 12.5px;
  line-height: 1.5;
  word-break: break-word;
}
.task__state {
  font-size: 10.5px;
  color: var(--fg-2);
  white-space: nowrap;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.task--done .task__state {
  color: var(--green);
}
.task--failed .task__state {
  color: var(--red);
}
.task--running .task__state {
  color: var(--cyan);
}

.spinner {
  width: 9px;
  height: 9px;
  border: 1.6px solid rgba(53, 224, 208, 0.28);
  border-top-color: var(--cyan);
  border-radius: 50%;
  animation: spin 0.75s linear infinite;
  display: inline-block;
}

.task__meta {
  display: flex;
  gap: 5px;
  align-items: center;
  flex-wrap: wrap;
  margin-top: 5px;
}

.task__bar {
  height: 3px;
  margin-top: 6px;
  border-radius: 3px;
  background: rgba(120, 165, 220, 0.14);
  overflow: hidden;
}
.task__barFill {
  height: 100%;
  background: linear-gradient(90deg, var(--cyan), var(--blue));
  transition: width 0.4s var(--ease);
}

.task__err,
.task__out {
  margin-top: 5px;
  font-size: 10.5px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 70px;
  overflow: hidden;
}
.task__err {
  color: var(--red);
}
.task__out {
  color: var(--fg-1);
}

.reasoning {
  flex: 0 0 auto;
  border-top: 1px dashed var(--line);
  padding: 8px 10px 4px;
  max-height: 22vh;
  overflow-y: auto;
}
.reasoning__head {
  font-size: 10px;
  letter-spacing: 0.1em;
  color: var(--violet);
  margin-bottom: 5px;
}
.reasoning__item {
  display: flex;
  gap: 6px;
  font-size: 11.5px;
  line-height: 1.55;
  color: var(--fg-1);
  margin-bottom: 4px;
}
.reasoning__round {
  flex: 0 0 auto;
  color: var(--violet);
  font-size: 10px;
  padding-top: 1px;
}
.reasoning__text {
  word-break: break-word;
}
</style>
