<script setup lang="ts">
/** 历史运行列表：点击可把该次运行的历史事件重新回放进同一个界面。 */
import type { RunInfo } from '@/types'
import { computed } from 'vue'

const props = defineProps<{
  runs: RunInfo[]
  activeId: string | null
  loading: boolean
}>()

const emit = defineEmits<{ (e: 'select', runId: string): void; (e: 'refresh'): void }>()

// 状态的中文名的色调来自标定（`spec.statuses`），前端不写死。
// 后端加一个终态（比如 'partial'），界面自动显示它的 label，不会露出裸状态名。
import { statusSpec } from '@/api/spec'

const statusText: Record<string, string> = {
  passed: '通过',
  failed: '失败',
  error: '异常',
  cancelled: '取消',
  relaxed: '放宽',
  running: '执行中',
  queued: '排队',
}

const items = computed(() => props.runs)

/** 标定的 tone（ok/err/warn/live/neutral）→ 进度条小色块用的类名 */
function toneOf(status: string): string {
  const tone = statusSpec(status).tone
  return tone === 'neutral' ? '' : tone
}

function short(goal: string) {
  return goal.length > 74 ? goal.slice(0, 74) + '…' : goal
}
</script>

<template>
  <section class="hist card">
    <div class="card__head">
      <h2 class="card__title">历史运行</h2>
      <span class="pill tiny mono">{{ items.length }}</span>
      <span class="spacer" />
      <button class="mini" :disabled="loading" @click="emit('refresh')">
        {{ loading ? '刷新中…' : '刷新' }}
      </button>
    </div>

    <div class="hist__body">
      <div v-if="!items.length" class="empty tiny">还没有任何运行记录</div>
      <button
        v-for="r in items"
        :key="r.run_id"
        class="run"
        :class="{ 'run--on': r.run_id === activeId }"
        @click="emit('select', r.run_id)"
      >
        <span class="run__tone" :class="`run__tone--${toneOf(r.status)}`" />
        <div class="run__main">
          <div class="run__goal">{{ short(r.goal) }}</div>
          <div class="run__meta mono tiny">
            {{ r.created_at.slice(11, 19) }} · {{ statusSpec(r.status).label }}
            <template v-if="r.demo"> · 演示</template>
            <template v-if="r.attempts"> · {{ r.attempts }} 次尝试</template>
            <template v-if="r.event_count"> · {{ r.event_count }} 事件</template>
          </div>
        </div>
      </button>
    </div>
  </section>
</template>

<style scoped>
.hist {
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.hist__body {
  overflow-y: auto;
  padding: 7px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-height: 0;
}
.empty {
  color: var(--fg-2);
  text-align: center;
  padding: 14px 0;
}
.mini {
  font-size: 10.5px;
  padding: 3px 9px;
}

.run {
  display: flex;
  align-items: stretch;
  gap: 8px;
  text-align: left;
  padding: 7px 9px;
  border-radius: 8px;
  border-color: transparent;
  background: rgba(120, 165, 220, 0.045);
  width: 100%;
}
.run:hover {
  background: rgba(120, 165, 220, 0.11);
}
.run--on {
  border-color: rgba(53, 224, 208, 0.45);
  background: rgba(53, 224, 208, 0.1);
}

.run__tone {
  flex: 0 0 auto;
  width: 3px;
  border-radius: 3px;
  background: var(--fg-2);
  opacity: 0.55;
}
.run__tone--ok {
  background: var(--green);
  opacity: 1;
}
.run__tone--err {
  background: var(--red);
  opacity: 1;
}
.run__tone--warn {
  background: var(--amber);
  opacity: 1;
}
.run__tone--live {
  background: var(--cyan);
  opacity: 1;
  animation: blink 1.3s ease-in-out infinite;
}

.run__main {
  min-width: 0;
  flex: 1 1 auto;
}
.run__goal {
  font-size: 12px;
  line-height: 1.45;
  word-break: break-word;
}
.run__meta {
  color: var(--fg-2);
  margin-top: 2px;
}
</style>
