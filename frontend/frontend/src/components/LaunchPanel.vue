<script setup lang="ts">
/** 启动面板：目标、验收命令、预算开关；以及演示运行入口。 */
import { computed, reactive, watch } from 'vue'
import { config } from '@/config'

const props = defineProps<{
  busy: boolean
  activeRunId: string | null
}>()

const emit = defineEmits<{
  (e: 'start', payload: {
    goal: string
    verify_command: string | null
    max_attempts: number
    on_decision: string
    demo: boolean
  }): void
  (e: 'cancel'): void
}>()

// 示例任务来自后端标定（`spec.ui.examples`），前端不写死。
// 改示例不用重新构建前端：改 bridge/spec.py，或写仓库根的 spec.override.json。
const EXAMPLES = computed(() => config.examples)

const form = reactive({
  // 初始留空：示例来自标定，而标定是异步加载的（见下方 watch）
  goal: '',
  verify: '',
  maxAttempts: 2,
  onDecision: 'auto',
  demo: false,
})

const canStart = computed(() => form.goal.trim().length > 0 && !props.busy)

// 标定是异步来的：到了就用第一条示例填好表单，别让用户面对空框
watch(
  () => EXAMPLES.value.length,
  (n) => {
    if (n && !form.goal) {
      form.goal = EXAMPLES.value[0].goal
      form.verify = EXAMPLES.value[0].verify
    }
  },
  { immediate: true },
)

function useExample(i: number) {
  form.goal = EXAMPLES.value[i].goal
  form.verify = EXAMPLES.value[i].verify
}

function submit(demo = false) {
  if (!canStart.value) return
  emit('start', {
    goal: form.goal.trim(),
    verify_command: form.verify.trim() ? form.verify : null,
    max_attempts: form.maxAttempts,
    on_decision: form.onDecision,
    demo,
  })
}
</script>

<template>
  <section class="launch card">
    <div class="card__head">
      <h2 class="card__title">新的编码目标</h2>
      <span class="spacer" />
      <span class="pill tiny muted">POST /api/runs</span>
    </div>

    <div class="card__body">
      <label class="field">
        <span>目标（goal）</span>
        <textarea v-model="form.goal" rows="3" placeholder="描述你要 agent 完成的事情…" />
      </label>

      <div class="examples">
        <button v-for="(ex, i) in EXAMPLES" :key="ex.label" class="chip" @click="useExample(i)">
          {{ ex.label }}
        </button>
      </div>

      <label class="field">
        <span>验收命令（verify_command · 退出码 0 即通过）</span>
        <textarea
          v-model="form.verify"
          rows="4"
          placeholder="import m&#10;assert m.f(1) == 1&#10;print('PASS')"
        />
      </label>
      <p class="hint">
        留空则采纳主循环自拟的 verify。<strong>调用方给出的验收标准不可被模型改写</strong>——
        这是流程里最重要的一条纪律。
      </p>

      <div class="row">
        <label class="field grow">
          <span>最多尝试</span>
          <select v-model.number="form.maxAttempts">
            <option :value="1">1 次</option>
            <option :value="2">2 次</option>
            <option :value="3">3 次</option>
            <option :value="4">4 次</option>
            <option :value="5">5 次</option>
          </select>
        </label>

        <label class="field grow">
          <span>人工决策</span>
          <select v-model="form.onDecision">
            <option value="auto">auto · 自动取保守动作</option>
            <option value="notify">notify · 推送但不等待</option>
            <option value="wait">wait · 阻塞等待作答</option>
          </select>
        </label>
      </div>

      <div class="actions">
        <button class="primary" :disabled="!canStart" @click="submit(false)">
          <span v-if="busy" class="spinner" />
          {{ busy ? '已有运行进行中…' : '开始运行' }}
        </button>
        <button :disabled="!canStart" @click="submit(true)" title="不调用模型，播放一段脚本事件序列">
          演示运行
        </button>
        <button
          v-if="activeRunId && busy"
          class="danger"
          @click="emit('cancel')"
        >
          取消当前运行
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.launch {
  flex: 0 0 auto;
}
.row {
  display: flex;
  gap: 10px;
}
.grow {
  flex: 1 1 0;
}
.examples {
  display: flex;
  gap: 6px;
  margin: -4px 0 12px;
  flex-wrap: wrap;
}
.chip {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 999px;
  color: var(--fg-1);
}
.hint {
  font-size: 11px;
  line-height: 1.6;
  color: var(--fg-2);
  margin: -4px 0 12px;
}
.hint strong {
  color: var(--amber);
  font-weight: 600;
}
.actions {
  display: flex;
  gap: 9px;
  flex-wrap: wrap;
}
.actions .primary {
  flex: 1 1 160px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 16px;
}
.spinner {
  width: 12px;
  height: 12px;
  border: 2px solid rgba(4, 18, 26, 0.35);
  border-top-color: #04121a;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
</style>
