<script setup lang="ts">
/** 统计条：每个数字都会「滚」到新值，让进度可感。 */
import { computed, toRef } from 'vue'
import type { RunState } from '@/types'
import { useTween, formatDuration } from '@/composables/useTween'
import { useClock } from '@/composables/useClock'

const props = defineProps<{ state: RunState; progress: number }>()

const clock = useClock(120)

const elapsed = computed(() => {
  if (!props.state.startedAt) return 0
  return (props.state.endedAt ?? clock.value) - props.state.startedAt
})

const cards = computed(() => [
  { key: 'attempt', label: '尝试次数', value: props.state.attempt, suffix: `/ ${props.state.maxAttempts}`, tone: '' },
  { key: 'round', label: '主循环轮次', value: props.state.rounds, suffix: '', tone: '' },
  { key: 'step', label: '子循环步数', value: props.state.steps, suffix: '', tone: '' },
  { key: 'tool', label: '工具调用', value: props.state.toolCalls.length, suffix: '', tone: 'cyan' },
  { key: 'file', label: '产物文件', value: props.state.files.length, suffix: '', tone: 'green' },
  { key: 'event', label: '事件数', value: props.state.events, suffix: '', tone: '' },
])

const tweens = cards.value.map((c) => useTween(toRef(() => c.value), 480))

const rollbacks = computed(() => props.state.rollbacks)
</script>

<template>
  <div class="stats">
    <div class="stats__progress">
      <div class="stats__progressHead">
        <span class="tiny muted">流水线进度</span>
        <span class="tiny mono">{{ Math.round(progress) }}%</span>
      </div>
      <div class="bar">
        <div
          class="bar__fill"
          :class="{ 'bar__fill--failed': ['failed', 'error', 'cancelled'].includes(state.status) }"
          :style="{ width: Math.min(100, Math.max(2, progress)) + '%' }"
        />
      </div>
    </div>

    <div class="stats__grid">
      <div v-for="(c, i) in cards" :key="c.key" class="stat" :class="`stat--${c.tone}`">
        <div class="stat__label">{{ c.label }}</div>
        <div class="stat__value mono">
          {{ Math.round(tweens[i].value) }}<small v-if="c.suffix">{{ c.suffix }}</small>
        </div>
      </div>

      <div class="stat" :class="{ 'stat--warn': rollbacks > 0 }">
        <div class="stat__label">回退次数</div>
        <div class="stat__value mono">{{ rollbacks }}</div>
      </div>

      <div class="stat stat--time">
        <div class="stat__label">耗时</div>
        <div class="stat__value mono">{{ formatDuration(elapsed) }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.stats {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.stats__progressHead {
  display: flex;
  justify-content: space-between;
  margin-bottom: 5px;
}

.bar {
  height: 6px;
  border-radius: 6px;
  background: rgba(120, 165, 220, 0.14);
  overflow: hidden;
}
.bar__fill {
  height: 100%;
  border-radius: 6px;
  background: linear-gradient(90deg, var(--cyan), var(--blue));
  box-shadow: 0 0 14px -2px rgba(53, 224, 208, 0.9);
  transition: width 0.6s var(--ease), background 0.4s var(--ease);
  position: relative;
}
.bar__fill::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.55), transparent);
  background-size: 220% 100%;
  animation: shimmer 1.6s linear infinite;
}
.bar__fill--failed {
  background: linear-gradient(90deg, var(--red), #ff9a6b);
  box-shadow: 0 0 14px -2px rgba(255, 107, 129, 0.9);
}

.stats__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(88px, 1fr));
  gap: 8px;
}

.stat {
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  padding: 7px 10px;
  background: rgba(11, 18, 32, 0.6);
  transition: border-color 0.3s var(--ease), transform 0.2s var(--ease);
}
.stat__label {
  font-size: 10px;
  letter-spacing: 0.07em;
  color: var(--fg-2);
  text-transform: uppercase;
  white-space: nowrap;
}
.stat__value {
  font-size: 19px;
  font-weight: 600;
  line-height: 1.3;
  margin-top: 1px;
}
.stat__value small {
  font-size: 11px;
  color: var(--fg-2);
  margin-left: 3px;
}

.stat--cyan {
  border-color: rgba(53, 224, 208, 0.35);
}
.stat--cyan .stat__value {
  color: var(--cyan);
}
.stat--green {
  border-color: rgba(70, 224, 138, 0.35);
}
.stat--green .stat__value {
  color: var(--green);
}
.stat--warn {
  border-color: rgba(245, 196, 81, 0.45);
}
.stat--warn .stat__value {
  color: var(--amber);
}
.stat--time .stat__value {
  font-size: 16px;
}
</style>
