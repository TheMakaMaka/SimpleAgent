<script setup lang="ts">
/** 任务 / 子循环面板：主模型拆出来的任务，以及每个任务的步数进度。 */
import type { RunState } from '@/types'
import { computed } from 'vue'

const props = defineProps<{ state: RunState }>()

const tasks = computed(() => [...props.state.tasks].reverse())
const reasoning = computed(() => props.state.reasoning.slice(0, 6))

function stepPercent(t: { steps: number; maxSteps: number }) {
  if (!t.maxSteps) return 0
  return Math.min(100, Math.round((t.steps / t.maxSteps) * 100))
}

// 工具中文名来自后端标定（`spec.tools`），前端不写死。
// 标定里没标的中文名会回退成工具原名——不会崩，只是不够亲切。
import { toolLabel } from '@/api/spec'
</script>

<template>
  <section class="tasks card">
    <div class="card__head">
      <h2 class="card__title">任务与子循环</h2>
      <span class="pill tiny mono">{{ state.tasks.length }}</span>
      <span class="spacer" />
      <span class="pill tiny mono">步数 {{ state.steps }} · 响应 {{ state.modelReplies }}</span>
    </div>

    <div class="card__body tasks__body">
      <div v-if="!tasks.length" class="empty">暂无任务</div>

      <div
        v-for="t in tasks"
        :key="t.id"
        class="task"
        :class="`task--${t.status}`"
      >
        <div class="task__top">
          <span class="task__id mono">{{ t.id }}</span>
          <span class="task__desc">{{ t.description }}</span>
          <span class="task__state">
            <template v-if="t.status === 'running'">
              <i class="spinner" />
              进行中
            </template>
            <template v-else-if="t.status === 'done'">✓ 完成</template>
            <template v-else>✕ 失败</template>
          </span>
        </div>

        <div class="task__meta">
          <span v-for="h in t.toolHint" :key="h" class="pill tiny">
            {{ toolLabel(h) }}   <!-- 标定里没这个名字时返回原名 -->
          </span>
          <span v-if="t.maxSteps" class="tiny muted mono">
            步 {{ t.steps }} / {{ t.maxSteps }}
          </span>
        </div>

        <div v-if="t.status === 'running' && t.maxSteps" class="task__bar">
          <div class="task__barFill" :style="{ width: stepPercent(t) + '%' }" />
        </div>

        <div v-if="t.error" class="task__err mono">{{ t.error }}</div>
        <div v-else-if="t.output" class="task__out mono">{{ t.output.slice(0, 220) }}</div>
      </div>

      <div v-if="reasoning.length" class="reasoning">
        <div class="reasoning__head">主模型推理</div>
        <div v-for="r in reasoning" :key="r.at" class="reasoning__item">
          <span class="reasoning__round mono">R{{ r.round }}</span>
          <span class="reasoning__text">{{ r.text || '（无说明）' }}</span>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.tasks {
  display: flex;
  flex-direction: column;
  min-height: 0;
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

.task {
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
.task--failed {
  border-color: rgba(255, 107, 129, 0.4);
  background: rgba(255, 107, 129, 0.06);
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
  margin-top: 6px;
  border-top: 1px dashed var(--line);
  padding-top: 8px;
}
.reasoning__head {
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
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
