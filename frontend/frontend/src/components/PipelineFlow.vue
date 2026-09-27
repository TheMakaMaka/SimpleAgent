<script setup lang="ts">
/**
 * 流水线可视化：整个界面的主角。
 *
 * 视觉语言：
 *   idle   暗灰描边，静止
 *   active 旋转光环 + 呼吸脉冲（「正在做」）
 *   done   实心 + 打勾（打勾是描边动画画出来的，不是贴图）
 *   failed 红色 + 抖动（「过不去」）
 *
 * 连接线会在前一阶段完成后开始「流动」，把阶段之间的推进关系画出来。
 */
import { computed } from 'vue'
import { statusSpec } from '@/api/spec'
import type { RunStatus, StageView } from '@/types'

const props = defineProps<{
  stages: StageView[]
  status: RunStatus
  phaseKey: number
  attempt: number
  maxAttempts: number
}>()

/**
 * 图标库：**按名字索引**，名字由标定下发（`spec.pipeline.stages[].icon`）。
 *
 * 认不出的名字回退到通用图标——后端加阶段、给个新图标名，界面不会崩，
 * 只是长得朴素一点。这就是「预留接口」的具体样子：
 * 前端不认识新东西时**降级**，而不是报错或空白。
 */
const ICONS: Record<string, string> = {
  route: 'M4 6h9M4 12h9M4 18h5M17 4v16l3-2',
  pencil: 'M4 20h4l10-10-4-4L4 16v4zM13 5l4 4',
  clipboard: 'M8 4h8v3H8zM6 4h1v16h10V4h1M9 11h6M9 15h4',
  shield: 'M12 3l7 3v6c0 4-3 7-7 8-4-1-7-4-7-8V6l7-3zM9 12l2 2 4-4',
  terminal: 'M4 5h16v11H4zM8 20h8M9 11l2 2 4-4',
  bookmark: 'M6 3h9l4 4v14H6zM14 3v5h5M9 14l2 2 4-4',
  magnifier: 'M11 4a7 7 0 105.2 11.7L21 20',
  // 通用图标 = 一个加号：一眼看出"这是个前端没见过的阶段"
  generic: 'M12 6v12M6 12h12',
}

function iconOf(stage: StageView): string {
  return ICONS[stage.icon ?? 'generic'] ?? ICONS.generic
}

function stateOf(i: number): string {
  return props.stages[i]?.state ?? 'idle'
}

/** 连接段 i→i+1 的状态：前一个走完才开始流动 */
function linkState(i: number): string {
  const cur = stateOf(i)
  const next = stateOf(i + 1)
  if (cur === 'failed') return 'failed'
  if (next === 'active') return 'flowing'
  if (cur === 'done' && (next === 'done' || next === 'active')) return 'done'
  if (cur === 'done') return 'done'
  return 'idle'
}

/** 整体色调也来自标定（`statuses`），前端不写死状态到颜色的映射。 */
const overallTone = computed(() => {
  const tone = statusSpec(props.status)?.tone ?? 'neutral'
  return tone === 'neutral' ? '' : tone
})

const overallLabel = computed(() => {
  if (props.status === 'queued' || props.status === 'running') return '执行中'
  return statusSpec(props.status)?.label ?? props.status
})
</script>

<template>
  <div class="pipe card">
    <div class="card__head">
      <h2 class="card__title">执行流水线</h2>
      <span class="pill" :class="`pill--${overallTone}`">
        <i class="dot" />
        {{ overallLabel }}
      </span>
      <span class="spacer" />
      <span class="pill tiny mono">尝试 {{ attempt || 1 }} / {{ maxAttempts }}</span>
    </div>

    <div class="pipe__body" :key="phaseKey">
      <!-- 每次重试时扫过一道光，提示「流水线被重置了」 -->
      <div class="pipe__sweep" aria-hidden="true" />

      <div class="track">
        <template v-for="(s, i) in stages" :key="s.id">
          <div class="node" :class="[`node--${s.state}`, `node--id${i}`]">
            <div class="node__ring" aria-hidden="true" />
            <div class="node__core">
              <svg
                v-if="s.state !== 'done'"
                class="node__icon"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.7"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <path :d="iconOf(s)" />
              </svg>
              <svg v-else class="node__check" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                   stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">
                <path class="check-path" d="M5 12.5l4.5 4.5L19 7" />
              </svg>
            </div>
            <div class="node__label mono">{{ s.label }}</div>
            <div class="node__hint">{{ s.hint }}</div>
          </div>

          <div
            v-if="i < stages.length - 1"
            class="link"
            :class="`link--${linkState(i)}`"
            aria-hidden="true"
          >
            <span class="link__line" />
            <span class="link__comet" />
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pipe__body {
  position: relative;
  padding: 22px 18px 18px;
  overflow: hidden;
}

.pipe__sweep {
  position: absolute;
  top: 0;
  left: -40%;
  width: 40%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(53, 224, 208, 0.14), transparent);
  animation: sweepIn 0.75s var(--ease) 1;
  pointer-events: none;
}
@keyframes sweepIn {
  to {
    left: 120%;
  }
}

.track {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0;
}

.node {
  position: relative;
  flex: 0 0 92px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 7px;
  text-align: center;
}

.node__ring {
  position: absolute;
  top: -4px;
  width: 60px;
  height: 60px;
  border-radius: 50%;
  opacity: 0;
  pointer-events: none;
}

.node__core {
  position: relative;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  border: 1.6px solid var(--line-strong);
  background: radial-gradient(circle at 50% 35%, rgba(120, 165, 220, 0.12), rgba(7, 11, 20, 0.9));
  color: var(--fg-2);
  transition:
    color 0.25s var(--ease),
    border-color 0.25s var(--ease),
    background 0.25s var(--ease),
    transform 0.25s var(--ease);
  z-index: 1;
}

.node__icon {
  width: 24px;
  height: 24px;
}

.node__check {
  width: 26px;
  height: 26px;
}
.check-path {
  stroke-dasharray: 30;
  stroke-dashoffset: 30;
  animation: drawCheck 0.45s var(--ease) 0.05s forwards;
}
@keyframes drawCheck {
  to {
    stroke-dashoffset: 0;
  }
}

.node__label {
  font-size: 11px;
  letter-spacing: 0.1em;
  color: var(--fg-2);
  transition: color 0.25s var(--ease);
}
.node__hint {
  font-size: 10px;
  line-height: 1.35;
  color: rgba(109, 129, 156, 0.72);
  max-width: 84px;
}

/* -------- idle -------- */
.node--idle .node__core {
  opacity: 0.62;
}

/* -------- active -------- */
.node--active .node__core {
  color: var(--cyan);
  border-color: rgba(53, 224, 208, 0.85);
  background: radial-gradient(circle at 50% 35%, rgba(53, 224, 208, 0.28), rgba(7, 11, 20, 0.9));
  transform: scale(1.07);
  animation: pulseGlow 1.5s ease-out infinite;
}
.node--active .node__ring {
  opacity: 1;
  background: conic-gradient(
    from 0deg,
    transparent 0deg,
    rgba(53, 224, 208, 0.05) 120deg,
    var(--cyan) 300deg,
    #ffffff 360deg
  );
  -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 2.5px), #000 calc(100% - 2.5px));
  mask: radial-gradient(farthest-side, transparent calc(100% - 2.5px), #000 calc(100% - 2.5px));
  animation: spin 1.3s linear infinite;
}
.node--active .node__label {
  color: var(--cyan);
}

/* -------- done -------- */
.node--done .node__core {
  color: #06231a;
  border-color: var(--green);
  background: linear-gradient(160deg, var(--green), #1fae6a);
  box-shadow: 0 0 18px -4px rgba(70, 224, 138, 0.6);
}
.node--done .node__label {
  color: var(--green);
}

/* -------- failed -------- */
.node--failed .node__core {
  color: #2b0710;
  border-color: var(--red);
  background: linear-gradient(160deg, var(--red), #c93b52);
  box-shadow: 0 0 22px -4px rgba(255, 107, 129, 0.75);
  animation: shake 0.5s var(--ease) 1;
}
.node--failed .node__label {
  color: var(--red);
}

/* -------- 连接线 -------- */
.link {
  position: relative;
  flex: 1 1 auto;
  min-width: 18px;
  height: 52px;
  display: flex;
  align-items: center;
}
.link__line {
  position: relative;
  display: block;
  width: 100%;
  height: 2px;
  border-radius: 2px;
  background: rgba(120, 165, 220, 0.18);
  overflow: hidden;
}
.link--done .link__line,
.link--flowing .link__line {
  background: linear-gradient(90deg, rgba(70, 224, 138, 0.85), rgba(53, 224, 208, 0.85));
}
.link--flowing .link__line::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255, 255, 255, 0.85) 45%,
    transparent 90%
  );
  background-size: 220% 100%;
  animation: shimmer 1.1s linear infinite;
}
.link--failed .link__line {
  background: linear-gradient(90deg, rgba(255, 107, 129, 0.8), rgba(255, 107, 129, 0.25));
}

.link__comet {
  position: absolute;
  top: 50%;
  left: 0;
  width: 7px;
  height: 7px;
  margin-top: -3.5px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 0 12px 3px rgba(53, 224, 208, 0.85);
  opacity: 0;
}
.link--flowing .link__comet {
  opacity: 1;
  animation: comet 1.5s var(--ease) infinite;
}
@keyframes comet {
  0% {
    left: -2%;
    opacity: 0;
  }
  15% {
    opacity: 1;
  }
  85% {
    opacity: 1;
  }
  100% {
    left: 100%;
    opacity: 0;
  }
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  animation: blink 1.2s ease-in-out infinite;
}

@media (max-width: 900px) {
  .node {
    flex-basis: 62px;
  }
  .node__hint {
    display: none;
  }
  .node__core {
    width: 42px;
    height: 42px;
  }
  .node__icon {
    width: 20px;
    height: 20px;
  }
}
</style>
