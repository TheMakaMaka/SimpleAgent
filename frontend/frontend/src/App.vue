<script setup lang="ts">
/**
 * 顶层编排：把后端事件流接到状态归约器，再把状态分发给各个面板。
 *
 * 这里只做三件事：
 *   1. 生命周期（起运行、订阅 SSE、断线重连、回放历史）
 *   2. 轮询（后端健康、历史列表、待决策项）
 *   3. 布局
 * 所有「事件 → 界面状态」的翻译都在 store/run.ts 里，组件保持纯粹。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { api, type HealthInfo, type StartRunPayload } from '@/api/client'
import { streamRun, type StreamHandle } from '@/api/sse'
import { loadSpec, specState } from '@/api/spec'
import { auditState, runAudit } from '@/api/audit'
import { config } from '@/config'
import { useRunStore, useDerived } from '@/store/run'
import type { DecisionView, RunInfo } from '@/types'

import TopBar from '@/components/TopBar.vue'
import LaunchPanel from '@/components/LaunchPanel.vue'
import StatStrip from '@/components/StatStrip.vue'
import PipelineFlow from '@/components/PipelineFlow.vue'
import AttemptTrack from '@/components/AttemptTrack.vue'
import ActivityFeed from '@/components/ActivityFeed.vue'
import TaskPanel from '@/components/TaskPanel.vue'
import VerifyPanel from '@/components/VerifyPanel.vue'
import ArtifactPanel from '@/components/ArtifactPanel.vue'
import RunHistory from '@/components/RunHistory.vue'
import DecisionBar from '@/components/DecisionBar.vue'
import TransparencyPanel from '@/components/TransparencyPanel.vue'

const store = useRunStore()
const { state } = store
const derived = useDerived(state)

const health = ref<HealthInfo | null>(null)
const healthError = ref('')
const runs = ref<RunInfo[]>([])
const runsLoading = ref(false)
const decisions = ref<DecisionView[]>([])
const answering = ref<string | null>(null)
const decisionError = ref('')
const toast = ref('')
/** 「为什么」审查条默认展开：这四块是用户明确要看的，藏起来等于没做 */
const tpCollapsed = ref(false)

let stream: StreamHandle | null = null
let healthTimer = 0
let runsTimer = 0
let decisionTimer = 0

const busy = computed(() => state.status === 'running' || state.status === 'queued')

/* ------------------------------ 数据同步 ------------------------------ */
async function refreshHealth() {
  try {
    health.value = await api.health()
    healthError.value = ''
  } catch (e) {
    health.value = null
    healthError.value = e instanceof Error ? e.message : String(e)
  }
}

async function refreshRuns() {
  runsLoading.value = true
  try {
    const res = await api.listRuns(40)
    runs.value = res.runs
  } catch {
    /* 列表拿不到不影响主流程 */
  } finally {
    runsLoading.value = false
  }
}

async function refreshDecisions() {
  if (!state.runId) {
    decisions.value = []
    return
  }
  try {
    const res = await api.decisions(state.runId)
    decisions.value = res.decisions
  } catch {
    decisions.value = []
  }
}

/* ------------------------------ 订阅 / 回放 ------------------------------ */
/**
 * 取一次运行报告并交给 store。
 *
 * P3/P4 的事实（`outcome` / `verdict` / `decompose_review` / `reuse_checks` /
 * `self_report`）**首先是报告字段**：事件流里只有子集，而**旧运行**（本轮之前跑的）
 * 事件里根本没有 verdict。历史回放走的也是这条路，所以回放与实时看到的是同一批数据。
 *
 * 失败**不弹 toast**：报告拿不到只意味着"少一块明细"，主流程（事件流）照旧。
 */
async function loadReport(runId: string) {
  try {
    const res = await api.getRun(runId)
    // 期间可能已经切到别的运行了 —— 别把上一份报告混进来
    if (state.runId !== runId) return
    store.ingestReportInfo(res.run?.report ?? null)
  } catch {
    /* 报告拿不到不影响主流程 */
  }
}

async function attach(runId: string, replayOnly = false) {
  stream?.close()
  stream = null
  store.reset(runId)
  state.runId = runId

  try {
    const res = await api.runEvents(runId, 0, 20000)
    store.ingestMany(res.events)
    // ★ P3/P4：报告的字段（结局四值 / 判据来源 / 独立性 / 拆解合规 / 复用性）
    //   **事件流里只有子集，旧运行更是没有** —— 所以运行详情单独取一次。
    //   取不到不影响界面（`store.ingestReportInfo` 对空报告是 no-op）。
    void loadReport(runId)

    if (res.terminal || replayOnly) {
      state.connected = 'closed'
      state.endedAt = state.endedAt ?? Date.now()
      return
    }

    state.connected = 'connecting'
    const from = res.last_seq || 0
    stream = streamRun(runId, from, {
      onEvent: (ev) => store.ingest(ev),
      onOpen: () => {
        state.connected = 'live'
      },
      onClose: () => {
        state.connected = 'closed'
        state.endedAt = state.endedAt ?? Date.now()
        void refreshRuns()
      },
      onError: (msg) => {
        state.connected = 'error'
        if (msg && !toast.value) toast.value = `事件流异常：${msg}`
      },
    })
  } catch (e) {
    state.connected = 'error'
    toast.value = e instanceof Error ? e.message : String(e)
  }
}

/* ------------------------------ 动作 ------------------------------ */
async function onStart(payload: StartRunPayload & { demo: boolean }) {
  toast.value = ''
  decisionError.value = ''
  try {
    const res = await api.startRun({
      goal: payload.goal,
      verify_command: payload.verify_command,
      max_attempts: payload.max_attempts,
      on_decision: payload.on_decision,
      demo: payload.demo,
      max_consecutive_failures: 2,
    })
    await attach(res.run.run_id)
    void refreshRuns()
  } catch (e) {
    toast.value = e instanceof Error ? e.message : String(e)
  }
}

async function onCancel() {
  if (!state.runId) return
  try {
    await api.cancelRun(state.runId)
  } catch (e) {
    toast.value = e instanceof Error ? e.message : String(e)
  }
}

async function onSelectRun(runId: string) {
  await attach(runId)
}

async function onAnswer(id: string, value: string) {
  answering.value = id
  decisionError.value = ''
  try {
    await api.answerDecision(id, value)
    await refreshDecisions()
  } catch (e) {
    decisionError.value = e instanceof Error ? e.message : String(e)
  } finally {
    answering.value = null
  }
}

/* ------------------------------ 生命周期 ------------------------------ */
watch(
  () => state.status,
  (s) => {
    const prefix = s === 'passed' ? '✓ ' : busy.value ? '▶ ' : s === 'failed' ? '✕ ' : ''
    document.title = `${prefix}SimpleAgent · 执行可视化`
  },
)

// 运行结束后把决策条清理掉，避免留下已失效的按钮
watch(
  () => busy.value,
  (b) => {
    if (!b) decisions.value = []
  },
)

onMounted(async () => {
  // 先拿标定：阶段清单、事件中文名、工具名、可调参数全在里面。
  // 拿不到会自动退回内置兜底，界面照常可用（specState.status === 'fallback'）。
  await loadSpec()
  store.syncStages()
  await refreshHealth()
  // 责任自审查：把「前端按什么写死的」报给服务，服务判该谁改。
  // 不阻断界面——拿不到结论就只是没有徽标。
  void runAudit()
  await refreshRuns()

  // 间隔全部来自 config（内置默认 → VITE_* → 后端标定的 ui 段）
  healthTimer = window.setInterval(refreshHealth, config.poll.healthMs)
  runsTimer = window.setInterval(() => {
    if (!document.hidden) void refreshRuns()
  }, config.poll.runsMs)
  decisionTimer = window.setInterval(() => {
    if (busy.value) void refreshDecisions()
  }, config.poll.decisionsMs)

  // 自动接管最近一次仍在运行的会话（刷新页面不丢进度）
  const active = runs.value.find((r) => r.status === 'running' || r.status === 'queued')
  if (active) await attach(active.run_id)
  else if (runs.value[0]) await attach(runs.value[0].run_id, true)
})

onUnmounted(() => {
  stream?.close()
  window.clearInterval(healthTimer)
  window.clearInterval(runsTimer)
  window.clearInterval(decisionTimer)
})
</script>

<template>
  <div class="shell">
    <TopBar :health="health" :health-error="healthError" :state="state" />

    <main class="grid">
      <!-- 左：发起 + 概览 + 历史 -->
      <div class="col col--left">
        <LaunchPanel :busy="busy" :active-run-id="state.runId" @start="onStart" @cancel="onCancel" />
        <div class="card">
          <div class="card__head">
            <h2 class="card__title">运行概览</h2>
            <span class="spacer" />
            <span v-if="state.demo" class="pill tiny pill--warn">演示数据</span>
            <span v-if="state.runId" class="pill tiny mono">{{ state.runId }}</span>
          </div>
          <div class="card__body">
            <StatStrip :state="state" :progress="derived.progress.value" />
          </div>
        </div>
        <RunHistory
          class="col__grow"
          :runs="runs"
          :active-id="state.runId"
          :loading="runsLoading"
          @select="onSelectRun"
          @refresh="refreshRuns"
        />
      </div>

      <!-- 中：流水线 + 实时事件流 -->
      <div class="col col--center">
        <PipelineFlow
          :stages="state.stages"
          :status="state.status"
          :phase-key="state.phaseKey"
          :attempt="state.attempt"
          :max-attempts="state.maxAttempts"
        >
        </PipelineFlow>

        <div class="card attempts">
          <AttemptTrack :attempts="state.attempts" :current="state.attempt" :max="state.maxAttempts" />
          <div v-if="state.goal" class="goal">
            <span class="goal__tag">目标</span>
            <span class="goal__text">{{ state.goal }}</span>
          </div>
          <div v-if="state.error" class="errbox">
            <strong>最后错误</strong>
            <span>{{ state.error }}</span>
          </div>
          <div v-else-if="state.commit" class="okbox">
            <strong>检查点</strong>
            <span class="mono">{{ state.commit }}</span>
          </div>
        </div>

        <ActivityFeed class="col__grow" :state="state" />
      </div>

      <!-- 右：任务、门禁、产物 -->
      <div class="col col--right">
        <TaskPanel class="panel" :state="state" />
        <VerifyPanel class="panel" :state="state" />
        <ArtifactPanel class="panel" :state="state" />
      </div>
    </main>

    <!-- 下：透明化审查（A2/A3/B4/C3/D3）—— 通栏，因为读的是"链条"而不是"格子" -->
    <TransparencyPanel class="tpbar" :state="state" :class="{ 'tpbar--collapsed': tpCollapsed }" />
    <button type="button" class="tpbar__toggle" @click="tpCollapsed = !tpCollapsed">
      {{ tpCollapsed ? '▲ 展开「为什么」审查' : '▼ 收起「为什么」审查' }}
    </button>

    <DecisionBar
      :decisions="decisions"
      :busy-id="answering"
      :error="decisionError"
      @answer="onAnswer"
    />

    <Transition name="toast">
      <div v-if="toast" class="toast" @click="toast = ''">
        <strong>提示</strong>
        <span>{{ toast }}</span>
        <button class="toast__x">×</button>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.shell {
  position: relative;
  z-index: 1;
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.grid {
  flex: 1 1 auto;
  min-height: 0;
  display: grid;
  grid-template-columns: 344px minmax(0, 1fr) 372px;
  gap: 12px;
  padding: 12px;
}

.col {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
  min-width: 0;
}
.col--left,
.col--right {
  overflow-y: auto;
  padding-right: 3px;
}
.col--center {
  overflow: hidden;
}
.col__grow {
  flex: 1 1 auto;
  min-height: 190px;
}

.panel {
  flex: 0 0 auto;
  max-height: 44vh;
}

.attempts {
  flex: 0 0 auto;
}

/* 「为什么」审查条：通栏放在三列之下。
   为什么给它**固定高度**而不是 max-height：四块视图都是"链条"
   （判据演化、决策轮次、模型回合），高度会跳会让阅读位置漂移。 */
.tpbar {
  flex: 0 0 auto;
  height: 34vh;
  min-height: 210px;
  margin: 0 12px 4px;
}
.tpbar--collapsed {
  display: none;
}
.tpbar__toggle {
  flex: 0 0 auto;
  align-self: center;
  margin-bottom: 6px;
  font-size: 10.5px;
  padding: 2px 10px;
  border-radius: 6px;
  border: 1px solid var(--line-strong);
  background: rgba(11, 18, 32, 0.6);
  color: var(--fg-2);
}
.tpbar__toggle:hover {
  color: var(--cyan);
  border-color: rgba(53, 224, 208, 0.5);
}

.goal {
  display: flex;
  gap: 8px;
  padding: 8px 14px;
  border-top: 1px solid var(--line);
  font-size: 12.5px;
  line-height: 1.55;
}
.goal__tag {
  flex: 0 0 auto;
  font-size: 10px;
  letter-spacing: 0.1em;
  color: var(--cyan);
  border: 1px solid rgba(53, 224, 208, 0.4);
  border-radius: 5px;
  padding: 1px 6px;
  height: fit-content;
  margin-top: 1px;
}
.goal__text {
  color: var(--fg-1);
  word-break: break-word;
}

.errbox,
.okbox {
  display: flex;
  gap: 8px;
  padding: 8px 14px;
  border-top: 1px solid var(--line);
  font-size: 12px;
  line-height: 1.5;
  animation: fadeSlideIn 0.3s var(--ease) both;
}
.errbox {
  background: rgba(255, 107, 129, 0.08);
  color: #ffc2cb;
}
.errbox strong {
  color: var(--red);
  flex: 0 0 auto;
}
.okbox {
  background: rgba(70, 224, 138, 0.07);
  color: #b7f5d0;
}
.okbox strong {
  color: var(--green);
  flex: 0 0 auto;
}

.toast {
  position: fixed;
  left: 50%;
  transform: translateX(-50%);
  bottom: 22px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  border-radius: 11px;
  border: 1px solid rgba(255, 107, 129, 0.45);
  background: rgba(30, 10, 18, 0.96);
  box-shadow: var(--shadow);
  font-size: 12.5px;
  max-width: min(720px, 90vw);
  z-index: 80;
}
.toast strong {
  color: var(--red);
}
.toast__x {
  border: none;
  background: none;
  font-size: 16px;
  line-height: 1;
  padding: 0 2px;
  color: var(--fg-2);
}

.toast-enter-active,
.toast-leave-active {
  transition: all 0.28s var(--ease);
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translate(-50%, 14px);
}

@media (max-width: 1360px) {
  .grid {
    grid-template-columns: 300px minmax(0, 1fr) 320px;
  }
}

@media (max-width: 1120px) {
  .grid {
    grid-template-columns: minmax(0, 1fr) 330px;
    grid-template-areas: 'center right' 'left right';
  }
  .col--center {
    grid-area: center;
  }
  .col--right {
    grid-area: right;
  }
  .col--left {
    grid-area: left;
  }
}

@media (max-width: 860px) {
  .grid {
    grid-template-columns: minmax(0, 1fr);
    grid-template-areas: 'left' 'center' 'right';
  }
  .shell {
    height: auto;
  }
  .panel {
    max-height: none;
  }
  .col--center {
    overflow: visible;
  }
  .col__grow {
    min-height: 320px;
  }
  /* 窄屏时整页滚动，固定高度会变成"里面再滚一层"，很难用 */
  .tpbar {
    height: auto;
  }
}
</style>

<style>
/* 窄屏时整页滚动，不再把内容锁在视口里（scoped 样式够不到 body） */
@media (max-width: 1120px) {
  html,
  body,
  #app {
    height: auto;
    min-height: 100%;
    overflow: visible;
  }
}
</style>
