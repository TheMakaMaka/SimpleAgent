<script setup lang="ts">
/** 产物面板：本轮改动的文件 + 最近工具调用；点文件可直接看落盘内容。 */
import { computed, ref } from 'vue'
import { api } from '@/api/client'
import type { RunState } from '@/types'
import { describeArgs } from '@/store/run'

const props = defineProps<{ state: RunState }>()

const files = computed(() => {
  const fromCalls = props.state.toolCalls
    .filter((t) => t.tool === 'write_file' && typeof t.args.filename === 'string')
    .map((t) => t.args.filename as string)
  return Array.from(new Set([...props.state.files, ...fromCalls]))
})

const recentTools = computed(() => props.state.toolCalls.slice(0, 14))

const openPath = ref<string | null>(null)
const content = ref('')
const loading = ref(false)
const loadError = ref('')

async function open(path: string) {
  openPath.value = path
  loading.value = true
  loadError.value = ''
  content.value = ''
  try {
    const res = await api.workspaceFile(path)
    content.value = res.content
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

function close() {
  openPath.value = null
  content.value = ''
}

const lines = computed(() => content.value.split('\n'))
</script>

<template>
  <section class="art card">
    <div class="card__head">
      <h2 class="card__title">产物与工具调用</h2>
      <span class="pill tiny mono">{{ files.length }} 文件</span>
      <span class="spacer" />
      <span class="pill tiny mono">{{ state.toolCalls.length }} 次调用</span>
    </div>

    <div class="card__body art__body">
      <div class="sect">
        <div class="sect__head">workspace 产物</div>
        <div v-if="!files.length" class="empty tiny">本轮还没有写出文件</div>
        <div class="filelist">
          <button
            v-for="f in files"
            :key="f"
            class="file"
            :class="{ 'file--new': state.toolCalls.some((t) => t.args.filename === f) }"
            @click="open(f)"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"
                 stroke-linecap="round" stroke-linejoin="round">
              <path d="M14 3v5h5M14 3H7v18h10V8l-3-5z" />
            </svg>
            <span class="mono">{{ f }}</span>
          </button>
        </div>
      </div>

      <div class="sect">
        <div class="sect__head">最近工具调用</div>
        <div v-if="!recentTools.length" class="empty tiny">暂无调用</div>
        <div
          v-for="t in recentTools"
          :key="t.key"
          class="call"
          :class="`call--${t.status}`"
        >
          <span class="call__dot" />
          <span class="call__tool mono">{{ t.tool }}</span>
          <span class="call__desc">{{ describeArgs(t.tool, t.args) }}</span>
          <span v-if="t.status === 'running'" class="spinner" />
          <span v-else-if="t.status === 'error'" class="call__flag">✕</span>
          <span v-else class="call__flag call__flag--ok">✓</span>
        </div>
      </div>
    </div>

    <!-- 文件查看器 -->
    <Teleport to="body">
      <div v-if="openPath" class="modal" @click.self="close">
        <div class="modal__box">
          <div class="modal__head">
            <span class="mono">{{ openPath }}</span>
            <span class="spacer" />
            <span class="tiny muted mono">{{ lines.length }} 行</span>
            <button @click="close">关闭</button>
          </div>
          <div class="modal__body">
            <div v-if="loading" class="empty">读取中…</div>
            <div v-else-if="loadError" class="empty err">{{ loadError }}</div>
            <pre v-else class="code"><code><span
              v-for="(l, i) in lines"
              :key="i"
              class="code__line"
            ><span class="code__ln">{{ i + 1 }}</span>{{ l }}
</span></code></pre>
          </div>
        </div>
      </div>
    </Teleport>
  </section>
</template>

<style scoped>
.art {
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.art__body {
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
}

.sect__head {
  font-size: 10px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--fg-2);
  margin-bottom: 6px;
}

.empty {
  color: var(--fg-2);
  padding: 6px 0;
}

.filelist {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.file {
  display: flex;
  align-items: center;
  gap: 7px;
  text-align: left;
  padding: 6px 9px;
  font-size: 11.5px;
  border-radius: 7px;
  background: rgba(120, 165, 220, 0.05);
  border-color: var(--line);
  width: 100%;
}
.file svg {
  width: 14px;
  height: 14px;
  color: var(--fg-2);
  flex: 0 0 auto;
}
.file span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file--new {
  border-color: rgba(53, 224, 208, 0.35);
  animation: popIn 0.35s var(--ease) both;
}
.file--new svg {
  color: var(--cyan);
}

.call {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 11px;
  padding: 4px 2px;
  border-bottom: 1px dashed rgba(120, 165, 220, 0.12);
  animation: fadeSlideIn 0.26s var(--ease) both;
}
.call__dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--fg-2);
  flex: 0 0 auto;
}
.call--ok .call__dot {
  background: var(--green);
}
.call--error .call__dot {
  background: var(--red);
}
.call--running .call__dot {
  background: var(--cyan);
  animation: blink 0.9s ease-in-out infinite;
}
.call__tool {
  color: var(--blue);
  flex: 0 0 auto;
}
.call__desc {
  flex: 1 1 auto;
  color: var(--fg-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.call__flag {
  color: var(--red);
  font-size: 10px;
}
.call__flag--ok {
  color: var(--green);
}
.spinner {
  width: 9px;
  height: 9px;
  border: 1.5px solid rgba(53, 224, 208, 0.3);
  border-top-color: var(--cyan);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
  flex: 0 0 auto;
}

/* ---------- 文件查看器 ---------- */
.modal {
  position: fixed;
  inset: 0;
  background: rgba(3, 6, 12, 0.72);
  backdrop-filter: blur(5px);
  display: grid;
  place-items: center;
  z-index: 60;
  animation: fadeSlideIn 0.2s var(--ease) both;
  padding: 34px;
}
.modal__box {
  width: min(920px, 100%);
  max-height: 84vh;
  display: flex;
  flex-direction: column;
  background: linear-gradient(180deg, #101a2d, #0a1120);
  border: 1px solid var(--line-strong);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  overflow: hidden;
}
.modal__head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--line);
  font-size: 12.5px;
}
.modal__body {
  overflow: auto;
  padding: 12px 14px;
}
.code {
  margin: 0;
  font-family: var(--mono);
  font-size: 11.5px;
  line-height: 1.62;
}
.code__line {
  display: block;
  white-space: pre;
}
.code__ln {
  display: inline-block;
  width: 42px;
  color: var(--fg-2);
  opacity: 0.5;
  user-select: none;
  text-align: right;
  padding-right: 12px;
}
</style>
