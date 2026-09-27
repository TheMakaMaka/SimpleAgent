<script setup lang="ts">
/**
 * 人工决策条：命中决策点时浮在底部，可直接在界面里作答。
 * 「保守默认动作」永远显示出来——让人知道「不管它」会发生什么。
 */
import type { DecisionView } from '@/types'

const props = defineProps<{
  decisions: DecisionView[]
  busyId: string | null
  error: string
}>()

const emit = defineEmits<{ (e: 'answer', id: string, value: string): void }>()

const LABEL: Record<string, string> = {
  retry: '再试一次',
  relax: '放宽验收',
  stop: '停止本轮',
  allow: '允许回退',
  keep: '保留改动',
  abort: '不回退',
}
</script>

<template>
  <div v-if="decisions.length" class="bar">
    <div class="bar__icon">⚠</div>
    <div v-for="d in decisions" :key="d.id" class="bar__item">
      <div class="bar__q">
        {{ d.question }}
        <span class="pill tiny muted">默认 {{ LABEL[d.default] || d.default }}</span>
      </div>
      <div class="bar__opts">
        <button
          v-for="o in d.options"
          :key="o.value"
          :class="{ danger: o.danger, primary: !o.danger && ['retry', 'allow'].includes(o.value) }"
          :disabled="busyId === d.id"
          @click="emit('answer', d.id, o.value)"
        >
          {{ LABEL[o.value] || o.label }}
        </button>
        <span v-if="busyId === d.id" class="tiny muted">提交中…</span>
      </div>
    </div>
    <div v-if="error" class="bar__err tiny">{{ error }}</div>
  </div>
</template>

<style scoped>
.bar {
  position: sticky;
  bottom: 0;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 16px;
  border-top: 1px solid rgba(245, 196, 81, 0.35);
  background: linear-gradient(180deg, rgba(245, 196, 81, 0.12), rgba(11, 18, 32, 0.96));
  backdrop-filter: blur(9px);
  animation: fadeSlideIn 0.3s var(--ease) both;
  z-index: 20;
  flex-wrap: wrap;
}
.bar__icon {
  font-size: 19px;
  color: var(--amber);
  animation: blink 1.4s ease-in-out infinite;
}
.bar__item {
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.bar__q {
  font-size: 12.5px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.bar__opts {
  display: flex;
  gap: 7px;
  align-items: center;
  flex-wrap: wrap;
}
.bar__opts button {
  font-size: 12px;
  padding: 5px 14px;
}
.bar__err {
  color: var(--red);
  width: 100%;
}
</style>
