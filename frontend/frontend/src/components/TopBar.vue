<script setup lang="ts">
/** 顶部状态条：后端是否活着、模型是谁、事件流是否连着。 */
import { computed } from 'vue'
import type { HealthInfo } from '@/api/client'
import {
  auditState, auditSummary, auditIssues, auditWarnings, auditOps,
} from '@/api/audit'
import type { RunState } from '@/types'

const props = defineProps<{
  health: HealthInfo | null
  healthError: string
  state: RunState
}>()

/** 阻塞项（决定"该谁改"）；`info` 级只作参考，不参与结论 */
const blocking = computed(() => auditIssues().filter((i) => i.blocking))
const informational = computed(() => auditIssues().filter((i) => !i.blocking))
const warnings = computed(() => auditWarnings())
const opsFacts = computed(() => auditOps())

/**
 * 结论徽标：ok / 有问题 / 拿不到结论。图标跟着 verdict 的语义走。
 *
 * ★ 契约 v1.0.5 的**消费方义务**：展示 verdict 的消费方应当**同时展示 warnings**。
 * 徽标本身必须体现它（下面 `auditLabel` 会带提示条数）——
 * 否则"✓ 兼容"会盖住那条不参与判定、只存在于 warnings 的陈旧 ops 标志。
 *
 * 另一条认知修正：**判断环境问题不要只看 verdict**。
 * 自 v1.0.5 起，陈旧的 `service_down`（请求送达了却报不可达）判 `ok` + 一条
 * warning；只有 `frontend_not_built` 仍判 `ops-action`。
 * 所以环境问题的依据是 `ops` 栏 / `warnings`，不是 verdict。
 */
const auditTone = computed(() => {
  const v = auditState.result?.verdict
  if (auditState.status === 'ok') return warnings.value.length ? 'warn' : 'ok'
  if (auditState.status === 'unavailable') return 'warn'
  if (v === 'need-negotiation' || v === 'multi-action') return 'warn'
  return 'err'
})

const auditLabel = computed(() => {
  const v = auditState.result?.verdict
  const n = warnings.value.length
  const tail = n ? ` (${n} 提示)` : ''
  if (auditState.status === 'ok') return '✓ 兼容' + tail
  if (auditState.status === 'unavailable') return '? 未审查'
  if (v === 'need-negotiation') return '⇄ 待协商' + tail
  return '⚠ 契约' + tail
})

const connTone = computed(() => {
  switch (props.state.connected) {
    case 'live':
      return 'ok'
    case 'connecting':
      return 'warn'
    case 'error':
      return 'err'
    default:
      return ''
  }
})

const connLabel = computed(() => {
  switch (props.state.connected) {
    case 'live':
      return '事件流已连接'
    case 'connecting':
      return '正在连接…'
    case 'error':
      return '事件流中断'
    case 'closed':
      return '事件流已收尾'
    default:
      return '未订阅'
  }
})
</script>

<template>
  <header class="top">
    <div class="brand">
      <div class="brand__mark" :class="{ 'brand__mark--live': state.status === 'running' }">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
             stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3z" />
          <path d="M12 12l8-4.5M12 12v9M12 12L4 7.5" />
        </svg>
      </div>
      <div>
        <div class="brand__name">SimpleAgent<span>·</span>Cycle</div>
        <div class="brand__sub">执行流程可视化 / 门禁由程序判定，不由模型自称</div>
      </div>
    </div>

    <div class="spacer" />

    <div class="chips">
      <span class="pill" :class="health ? 'pill--ok' : 'pill--err'">
        <i class="led" :class="health ? 'led--ok' : 'led--err'" />
        {{ health ? '后端在线' : healthError ? '后端不可达' : '检测中…' }}
      </span>

      <span v-if="health" class="pill mono tiny">
        模型 {{ health.model.name }}
      </span>
      <span v-if="health" class="pill mono tiny">
        检查点 {{ health.checkpoint_backend }}
      </span>
      <span v-if="health && health.problems.length" class="pill pill--err tiny">
        接入自检 {{ health.problems.length }} 项问题
      </span>

      <span class="pill" :class="connTone ? `pill--${connTone}` : ''">
        <i class="led" :class="connTone ? `led--${connTone}` : 'led--idle'" />
        {{ connLabel }}
      </span>

      <!-- 责任自审查：点开看「该谁改」。不用人去比对两份定义。 -->
      <details v-if="auditState.status !== 'idle'" class="audit">
        <summary
          class="pill"
          :class="{
            'pill--ok': auditTone === 'ok',
            'pill--err': auditTone === 'err',
            'pill--warn': auditTone === 'warn',
          }"
        >
          {{ auditLabel }}
        </summary>
        <div class="audit__pop">
          <div class="audit__head">{{ auditSummary() }}</div>

          <!-- ★ 提示段：契约 v1.0.5 的消费方义务。
               被传输层证伪的 ops 事实不参与 verdict，所以结论是 ok 而标志只在这里。
               放在阻塞项**之前**——藏在末尾等于没有展示。 -->
          <div v-if="warnings.length" class="audit__warn">
            <div class="audit__warn-head">⚠ 提示（不参与结论，但应当一并展示）</div>
            <div v-for="(w, idx) in warnings" :key="idx" class="audit__warn-item">
              {{ w }}
            </div>
          </div>

          <div v-if="!auditIssues().length && !warnings.length" class="audit__ok">
            服务声明与前端期望完全一致。
          </div>

          <!-- 阻塞项：结论只看这些 -->
          <div
            v-for="i in blocking"
            :key="i.id"
            class="audit__item"
            :class="`audit__item--${i.severity}`"
          >
            <div class="audit__owner">{{ i.owner_label }}</div>
            <div class="audit__title">{{ i.title }}</div>
            <div v-if="i.detail" class="audit__detail">{{ i.detail }}</div>
            <div v-if="i.fix" class="audit__fix">→ {{ i.fix }}</div>
            <div v-for="e in i.evidence.slice(0, 4)" :key="e" class="audit__ev mono">{{ e }}</div>
          </div>

          <!-- 参考项：`info` 永不影响结论，量大时折起来 -->
          <details v-if="informational.length" class="audit__info">
            <summary class="audit__info-head">
              {{ informational.length }} 项参考信息（不影响结论）
            </summary>
            <div
              v-for="i in informational"
              :key="i.id"
              class="audit__item audit__item--info"
            >
              <div class="audit__owner">{{ i.owner_label }}</div>
              <div class="audit__title">{{ i.title }}</div>
              <div v-if="i.detail" class="audit__detail">{{ i.detail }}</div>
            </div>
          </details>

          <!-- ops 栏：全部被上报的运行态事实（含未参与判定的）。
               判断环境问题看这里，**不要只看 verdict**。 -->
          <div v-if="opsFacts.length" class="audit__ops mono">
            运行态观测：
            <span v-for="([k, v], idx) in opsFacts" :key="k">
              {{ k }}={{ v }}<template v-if="idx < opsFacts.length - 1"> · </template>
            </span>
          </div>

          <div class="audit__foot mono">
            spec v{{ auditState.result?.spec_version ?? '?' }} ·
            实现契约 v{{ auditState.result?.implements_contract_version ?? '?' }}
            <template v-if="auditState.result?.contract_version_source === 'fallback'">
              （回退值）
            </template>
            · 核对 {{ auditState.result?.checked?.length ?? 0 }} 项
          </div>
        </div>
      </details>
    </div>
  </header>
</template>

<style scoped>
.top {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 18px;
  border-bottom: 1px solid var(--line);
  background: linear-gradient(180deg, rgba(16, 26, 45, 0.9), rgba(7, 11, 20, 0.6));
  backdrop-filter: blur(8px);
  position: relative;
  z-index: 3;
  flex: 0 0 auto;
}

.brand {
  display: flex;
  align-items: center;
  gap: 11px;
}
.brand__mark {
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border-radius: 11px;
  color: var(--cyan);
  border: 1px solid rgba(53, 224, 208, 0.35);
  background: rgba(53, 224, 208, 0.09);
}
.brand__mark svg {
  width: 22px;
  height: 22px;
}
.brand__mark--live {
  animation: pulseGlow 1.8s ease-out infinite;
}
.brand__name {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.03em;
}
.brand__name span {
  color: var(--cyan);
  margin: 0 1px;
}
.brand__sub {
  font-size: 11px;
  color: var(--fg-2);
  margin-top: 1px;
}

.chips {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.led {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--fg-2);
}
.led--ok {
  background: var(--green);
  box-shadow: 0 0 8px rgba(70, 224, 138, 0.9);
  animation: blink 1.6s ease-in-out infinite;
}
.led--warn {
  background: var(--amber);
}
.led--err {
  background: var(--red);
}
.led--idle {
  background: var(--fg-2);
}

/* ---------- 责任自审查 ---------- */
.audit {
  position: relative;
}
.audit > summary {
  cursor: pointer;
  list-style: none;
  user-select: none;
}
.audit > summary::-webkit-details-marker {
  display: none;
}

.audit__pop {
  position: absolute;
  right: 0;
  top: calc(100% + 6px);
  z-index: 40;
  width: min(520px, 78vw);
  max-height: 60vh;
  overflow-y: auto;
  padding: 12px 14px;
  border-radius: var(--radius);
  border: 1px solid var(--line-strong);
  background: linear-gradient(180deg, #16233b, #0b1220);
  box-shadow: var(--shadow);
  text-align: left;
}
.audit__head {
  font-size: 12.5px;
  margin-bottom: 8px;
}
.audit__ok {
  font-size: 12px;
  color: var(--green);
}
/* 提示段：与结论并列展示（契约的消费方义务），所以给它醒目的边框 */
.audit__warn {
  border: 1px solid rgba(240, 180, 60, 0.45);
  background: rgba(240, 180, 60, 0.08);
  border-radius: 6px;
  padding: 7px 9px;
  margin-bottom: 9px;
}
.audit__warn-head {
  font-size: 11.5px;
  color: var(--amber);
  margin-bottom: 3px;
}
.audit__warn-item {
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--fg-1);
}
.audit__ops {
  font-size: 10.5px;
  color: var(--fg-2);
  margin-top: 5px;
}
.audit__item {
  border-left: 2px solid var(--line-strong);
  padding: 6px 0 6px 9px;
  margin-bottom: 7px;
  font-size: 12px;
}
/* 严重度配色跟契约词表走：breaking / degraded / info（旧名 fail / warn 已废） */
.audit__item--breaking {
  border-left-color: var(--red);
}
.audit__item--degraded {
  border-left-color: var(--amber);
}
.audit__item--info {
  border-left-color: var(--line);
  opacity: 0.75;
}
.audit__info {
  margin-top: 4px;
}
.audit__info-head {
  cursor: pointer;
  font-size: 11px;
  color: var(--fg-2);
  padding: 3px 0;
  user-select: none;
}
.audit__info-head::-webkit-details-marker {
  display: none;
}
.audit__info-head::before {
  content: '▸ ';
}
.audit__info[open] > .audit__info-head::before {
  content: '▾ ';
}
.audit__owner {
  display: inline-block;
  font-size: 10px;
  padding: 0 6px;
  border-radius: 4px;
  border: 1px solid var(--line-strong);
  color: var(--fg-1);
  margin-bottom: 3px;
}
.audit__title {
  line-height: 1.45;
}
.audit__detail {
  color: var(--fg-2);
  font-size: 11px;
  margin-top: 2px;
  line-height: 1.5;
}
.audit__fix {
  color: var(--cyan);
  font-size: 11px;
  margin-top: 3px;
}
.audit__ev {
  font-size: 10px;
  color: var(--fg-2);
  margin-top: 2px;
  word-break: break-all;
}
.audit__foot {
  margin-top: 8px;
  padding-top: 7px;
  border-top: 1px dashed var(--line);
  font-size: 10px;
  color: var(--fg-2);
}
</style>
