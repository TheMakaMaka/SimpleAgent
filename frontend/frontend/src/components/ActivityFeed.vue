<script setup lang="ts">
/**
 * 实时事件流。
 *
 * 行为上刻意做成「终端 + 聊天」的混合：
 *   - 新行从底部淡入滑出（能看到正在发生）；
 *   - 贴底时自动跟随，往上翻就自动暂停跟随（不抢用户滚动）；
 *   - 可按色调过滤，方便失败时只看错误。
 */
import { computed, nextTick, ref, watch } from 'vue'
import type { RunState, TimelineEntry } from '@/types'

const props = defineProps<{ state: RunState }>()

const box = ref<HTMLElement | null>(null)
const follow = ref(true)
const filter = ref<'all' | 'phase' | 'tool' | 'model' | 'problem'>('all')

/** 时间线是新→旧存的，渲染时翻过来，让最新一行在底部 */
const ordered = computed(() => [...props.state.timeline].reverse())

const rows = computed(() => {
  switch (filter.value) {
    case 'phase':
      return ordered.value.filter((e) => e.tone === 'phase')
    case 'tool':
      return ordered.value.filter((e) => e.tone === 'tool' || e.tone === 'model')
    case 'model':
      return ordered.value.filter((e) => e.tone === 'model')
    case 'problem':
      return ordered.value.filter((e) => e.tone === 'error' || e.tone === 'warn')
    default:
      return ordered.value
  }
})

const badge: Record<string, string> = {
  phase: '阶段',
  tool: '工具',
  model: '模型',
  ok: 'OK',
  warn: '注意',
  error: '错误',
  info: '信息',
}

function onScroll() {
  const el = box.value
  if (!el) return
  follow.value = el.scrollHeight - el.scrollTop - el.clientHeight < 40
}

watch(
  () => rows.value.length,
  async () => {
    if (!follow.value) return
    await nextTick()
    const el = box.value
    if (el) el.scrollTop = el.scrollHeight
  },
)

function scrollToBottom() {
  follow.value = true
  const el = box.value
  if (el) el.scrollTop = el.scrollHeight
}

const counts = computed(() => {
  const c = { all: 0, phase: 0, tool: 0, model: 0, problem: 0 }
  for (const e of ordered.value) {
    c.all++
    if (e.tone === 'phase') c.phase++
    if (e.tone === 'tool' || e.tone === 'model') c.tool++
    if (e.tone === 'model') c.model++
    if (e.tone === 'error' || e.tone === 'warn') c.problem++
  }
  return c
})
</script>

<template>
  <section class="feed card">
    <div class="card__head">
      <h2 class="card__title">实时事件流</h2>
      <span class="pill tiny mono">{{ rows.length }}</span>
      <span class="spacer" />

      <div class="tabs">
        <button
          v-for="f in (['all', 'phase', 'tool', 'model', 'problem'] as const)"
          :key="f"
          class="tab"
          :class="{ 'tab--on': filter === f }"
          @click="filter = f"
        >
          {{ { all: '全部', phase: '阶段', tool: '工具', model: '模型', problem: '异常' }[f] }}
          <small>{{ counts[f] }}</small>
        </button>
      </div>

      <button v-if="!follow" class="jump" @click="scrollToBottom">↓ 跟随</button>
    </div>

    <div ref="box" class="feed__box" @scroll="onScroll">
      <div v-if="!rows.length" class="feed__empty">
        <div class="feed__emptyIcon">◌</div>
        <p>还没有事件。提交一个目标，或点「演示运行」看一遍完整流程。</p>
      </div>

      <div
        v-for="e in rows"
        :key="e.seq + '-' + e.kind"
        class="row"
        :class="`row--${e.tone}`"
      >
        <span class="row__bar" />
        <span class="row__badge">{{ badge[e.tone] || e.tone }}</span>
        <div class="row__main">
          <div class="row__title">{{ e.title }}</div>
          <div v-if="e.detail" class="row__detail mono">{{ e.detail }}</div>
        </div>
        <span class="row__ts mono">{{ e.clock }}</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.feed {
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1 1 auto;
}

.feed__box {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding: 8px 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 5px;
  scroll-behavior: smooth;
}

.feed__empty {
  margin: auto;
  text-align: center;
  color: var(--fg-2);
  padding: 26px 16px;
  font-size: 12.5px;
  line-height: 1.8;
}
.feed__emptyIcon {
  font-size: 30px;
  opacity: 0.4;
  animation: blink 2.4s ease-in-out infinite;
}

.row {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 8px 6px 12px;
  border-radius: 8px;
  background: rgba(120, 165, 220, 0.045);
  animation: fadeSlideIn 0.28s var(--ease) both;
  border: 1px solid transparent;
}
.row:hover {
  background: rgba(120, 165, 220, 0.1);
}

.row__bar {
  position: absolute;
  left: 3px;
  top: 7px;
  bottom: 7px;
  width: 2.5px;
  border-radius: 2px;
  background: var(--fg-2);
}

.row__badge {
  flex: 0 0 auto;
  font-size: 9.5px;
  letter-spacing: 0.06em;
  padding: 1px 6px;
  border-radius: 5px;
  border: 1px solid var(--line-strong);
  color: var(--fg-2);
  margin-top: 2px;
  min-width: 34px;
  text-align: center;
}

.row__main {
  flex: 1 1 auto;
  min-width: 0;
}
.row__title {
  font-size: 12.5px;
  line-height: 1.5;
  word-break: break-word;
}
.row__detail {
  font-size: 11px;
  color: var(--fg-1);
  margin-top: 2px;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 84px;
  overflow: hidden;
  opacity: 0.85;
}
.row__ts {
  flex: 0 0 auto;
  font-size: 10px;
  color: var(--fg-2);
  opacity: 0.65;
  margin-top: 3px;
}

.row--ok .row__bar {
  background: var(--green);
}
.row--ok .row__badge {
  color: var(--green);
  border-color: rgba(70, 224, 138, 0.45);
}
.row--warn .row__bar {
  background: var(--amber);
}
.row--warn .row__badge {
  color: var(--amber);
  border-color: rgba(245, 196, 81, 0.45);
}
.row--error .row__bar {
  background: var(--red);
}
.row--error .row__badge {
  color: var(--red);
  border-color: rgba(255, 107, 129, 0.5);
}
.row--error {
  background: rgba(255, 107, 129, 0.07);
}
.row--phase .row__bar {
  background: var(--cyan);
}
.row--phase .row__badge {
  color: var(--cyan);
  border-color: rgba(53, 224, 208, 0.45);
}
.row--tool .row__bar {
  background: var(--blue);
}
.row--tool .row__badge {
  color: var(--blue);
  border-color: rgba(90, 169, 255, 0.45);
}
.row--model .row__bar {
  background: var(--violet);
}
.row--model .row__badge {
  color: var(--violet);
  border-color: rgba(167, 139, 250, 0.45);
}

.tabs {
  display: flex;
  gap: 3px;
  margin-right: 6px;
}
.tab {
  font-size: 10.5px;
  padding: 3px 8px;
  border-radius: 6px;
  background: transparent;
  border-color: transparent;
  color: var(--fg-2);
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.tab small {
  font-size: 9px;
  opacity: 0.6;
}
.tab--on {
  background: rgba(53, 224, 208, 0.14);
  color: var(--cyan);
  border-color: rgba(53, 224, 208, 0.35);
}

.jump {
  font-size: 11px;
  padding: 3px 9px;
  color: var(--cyan);
  border-color: rgba(53, 224, 208, 0.4);
  animation: popIn 0.25s var(--ease) both;
}
</style>
