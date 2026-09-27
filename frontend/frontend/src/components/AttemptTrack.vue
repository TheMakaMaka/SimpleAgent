<script setup lang="ts">
/** 尝试轨迹：把「第几次尝试、哪次失败、是否回退」画成一条横向轨道。 */
import type { AttemptView } from '@/types'
import { computed } from 'vue'

const props = defineProps<{ attempts: AttemptView[]; current: number; max: number }>()

const slots = computed(() => {
  const out: Array<{ index: number; view: AttemptView | null }> = []
  for (let i = 1; i <= Math.max(1, props.max); i++) {
    out.push({ index: i, view: props.attempts.find((a) => a.index === i) ?? null })
  }
  return out
})

function label(v: AttemptView | null, index: number) {
  if (!v) return index > props.current ? '待定' : '—'
  switch (v.status) {
    case 'running':
      return '进行中'
    case 'passed':
      return '通过'
    case 'relaxed':
      return '放宽'
    default:
      return '失败'
  }
}

function duration(v: AttemptView | null) {
  if (!v || !v.endedAt) return ''
  return `${((v.endedAt - v.startedAt) / 1000).toFixed(1)}s`
}
</script>

<template>
  <div class="track2">
    <span class="track2__label">尝试轨迹</span>

    <template v-for="(s, i) in slots" :key="s.index">
      <div
        class="pill2"
        :class="[
          s.view ? `pill2--${s.view.status}` : s.index === current ? 'pill2--active' : 'pill2--idle',
        ]"
      >
        <span class="pill2__idx mono">{{ s.index }}</span>
        <span class="pill2__txt">{{ label(s.view, s.index) }}</span>
        <span v-if="duration(s.view)" class="pill2__dur mono">{{ duration(s.view) }}</span>
        <span v-if="s.view?.rolledBack" class="pill2__rb" title="本次尝试的改动已被回退">↺</span>
      </div>

      <span v-if="i < slots.length - 1" class="arrow" aria-hidden="true">→</span>
    </template>
  </div>
</template>

<style scoped>
.track2 {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
  padding: 8px 14px 10px;
  border-top: 1px solid var(--line);
}
.track2__label {
  font-size: 10px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--fg-2);
  margin-right: 3px;
}

.pill2 {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 11px;
  border: 1px solid var(--line-strong);
  color: var(--fg-2);
  background: rgba(120, 165, 220, 0.05);
  transition: all 0.3s var(--ease);
}
.pill2__idx {
  font-size: 10px;
  opacity: 0.75;
}
.pill2__dur {
  font-size: 9.5px;
  opacity: 0.7;
}
.pill2__rb {
  color: var(--amber);
}

.pill2--active,
.pill2--running {
  color: var(--cyan);
  border-color: rgba(53, 224, 208, 0.55);
  background: rgba(53, 224, 208, 0.12);
  animation: pulseGlow 1.6s ease-out infinite;
}
.pill2--passed {
  color: var(--green);
  border-color: rgba(70, 224, 138, 0.5);
  background: rgba(70, 224, 138, 0.12);
  animation: popIn 0.35s var(--ease) both;
}
.pill2--failed {
  color: var(--red);
  border-color: rgba(255, 107, 129, 0.5);
  background: rgba(255, 107, 129, 0.12);
  animation: popIn 0.35s var(--ease) both;
}
.pill2--relaxed {
  color: var(--amber);
  border-color: rgba(245, 196, 81, 0.5);
  background: rgba(245, 196, 81, 0.12);
}

.arrow {
  color: var(--fg-2);
  opacity: 0.5;
  font-size: 11px;
}
</style>
