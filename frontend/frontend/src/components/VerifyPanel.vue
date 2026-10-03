<script setup lang="ts">
/**
 * 门禁面板：程序判定的结果 —— MANIFEST / CHECK / VERIFY / 复用性 / **结论四值**。
 *
 * 三件这一轮新增的事（工作单 P2/P3）都落在这里：
 *
 * | 项 | 要求 | 落点 |
 * |---|---|---|
 * | **P3** | 按**结局四值**呈现，并把「**判据来自谁**」显示在**结论旁** | `verdict` 条 |
 * | **P3** | **审查是否独立**；`REVIEW` 未启用时必须显示「非独立/未启用」 | `verdict` 条 |
 * | （后端 P2） | 机械层**复用性**检查**有否决权** → 必须可见 | REUSE 块 |
 *
 * ★ 两条"不许把判不了说成通过"：
 *   1. `criterion_independent` 缺失（`null`）显示「未给」，**不显示"不独立"** ——
 *      "没给"与"给了 false"是两件事；
 *   2. 后端**没产出** verdict 时显示「后端未产出结局四值」，而不是拿
 *      `run_end.status` 硬套一个四值（那等于替后端下一个它没下的判断）。
 */
import type { RunState } from '@/types'
import { computed } from 'vue'

const props = defineProps<{ state: RunState }>()

const checks = computed(() => props.state.checks)
const manifest = computed(() => props.state.manifest)
const verify = computed(() => props.state.verify)
/** 被跳过的验证（`verify_skipped`）—— 既非通过也非失败，必须单独显示 */
const skipped = computed(() => props.state.verifySkipped ?? [])
const verdict = computed(() => props.state.verdict)
const reuse = computed(() => props.state.reuse)

const syntaxOk = computed(() => checks.value.filter((c) => c.tool === 'syntax' && c.status === 'passed').length)
const syntaxBad = computed(() => checks.value.filter((c) => c.tool === 'syntax' && c.status === 'failed').length)
const lintSkipped = computed(() => checks.value.filter((c) => c.tool === 'lint' && c.status === 'skipped').length)
const lintIssues = computed(() =>
  checks.value.filter((c) => c.tool === 'lint' && c.status === 'failed').length,
)

/* ---------------- P3：结论四值 + 判据来源 + 独立性 ---------------- */
const OUTCOME_LABEL: Record<string, string> = {
  pass: 'pass',
  fail: 'fail',
  abstain: 'abstain',
  invalid: 'invalid',
  unknown: '未知',
}
const OUTCOME_MEANING: Record<string, string> = {
  pass: '判据执行了，且通过',
  fail: '判据执行了，且失败',
  abstain: '模型自己声明做不到',
  invalid: '任务或工装本身有问题（不是模型的错）',
  unknown: '后端给的结局词不在四值里',
}

/** 没有后端 verdict 时，退回按 `run_end.status` 推的那个（并**标明**它是推的） */
const derived = computed(() => {
  const v = verdict.value
  if (v && !v.absent && v.raw) return null
  const s = props.state.outcome
  return s.raw ? s : null
})

const outcomeTone = computed(() => {
  const v = (verdict.value?.outcome ?? derived.value?.value) || 'unknown'
  if (v === 'pass') return 'ok'
  if (v === 'fail') return 'err'
  if (v === 'abstain') return 'warn'
  if (v === 'invalid') return 'invalid'
  return 'muted'
})
const outcomeWord = computed(() => {
  const raw = verdict.value?.raw || derived.value?.raw || ''
  return OUTCOME_LABEL[verdict.value?.outcome ?? derived.value?.value ?? 'unknown'] ?? raw
})
const outcomeMeaning = computed(
  () => OUTCOME_MEANING[verdict.value?.outcome ?? derived.value?.value ?? 'unknown'] ?? '',
)

const sourceText = computed(() => {
  const s = verdict.value?.criterionSource || props.state.outcome.source
  if (s === 'caller') return '调用方'
  if (s === 'model') return '模型自拟'
  return '未知（事件未带 source）'
})
/** 可信档位：后端 `criterion_trust`；它比"来源"更直接地说出"这张考卷算不算数" */
const trustText = computed(() => {
  const t = verdict.value?.criterionTrust
  if (t === 'caller-authoritative') return '调用方判据（有权威）'
  if (t === 'model-self-authored') return '模型自拟（**不算独立判据**）'
  if (t === 'none') return '（非通过，无档位）'
  return ''
})

/**
 * ★ 独立性三态 —— 这里最容易把"判不了"说成"否"：
 *   `true` → 独立；`false` → **不独立**；`null` → 后端**没给**这个字段。
 */
const independentText = computed(() => {
  const v = verdict.value
  if (!v) return '未产出（后端无此字段）'
  if (v.criterionIndependent === true) return '独立'
  if (v.criterionIndependent === false) return '非独立/未启用'
  return '未给（判不了）'
})
const independentTone = computed(() => {
  const v = verdict.value?.criterionIndependent
  if (v === true) return 'ok'
  if (v === false) return 'warn'
  return 'muted'
})

/* ---------------- 复用性检查（后端 P2，**有否决权**） ---------------- */
const reuseBlocking = computed(() => reuse.value?.blocking ?? [])
const reuseWarnings = computed(() => reuse.value?.warnings ?? [])
</script>

<template>
  <section class="gate card">
    <div class="card__head">
      <h2 class="card__title">门禁结果</h2>
      <span class="spacer" />
      <span class="pill tiny muted">程序判定 · 模型绕不过</span>
    </div>

    <div class="card__body gate__body">
      <!-- ★ P3：结论四值 —— 放在**最上面**，因为它是"这次到底算不算达成" -->
      <div class="block block--verdict" :class="`block--${outcomeTone}`">
        <div class="block__head">
          <span class="block__name">结论</span>
          <span class="pill tiny" :class="`pill--${outcomeTone}`">{{ outcomeWord }}</span>
          <span class="tiny muted">{{ outcomeMeaning }}</span>
          <span class="spacer" />
          <span class="pill tiny" :class="verdict ? 'pill--ok' : 'muted'">
            {{ verdict ? '后端判定' : '未产出' }}
          </span>
        </div>
        <div class="block__body verdict">
          <!-- 判据来自谁：需求原话是「**显示在结论旁**」，所以它就在这一格里 -->
          <div class="verdict__row">
            <span class="verdict__tag">判据来自</span>
            <span class="verdict__val" :class="{ 'verdict__val--warn': sourceText === '模型自拟' }">
              {{ sourceText }}
            </span>
            <span v-if="trustText" class="tiny muted">{{ trustText }}</span>
          </div>
          <div class="verdict__row">
            <span class="verdict__tag">审查是否独立</span>
            <span class="pill tiny" :class="`pill--${independentTone}`">{{ independentText }}</span>
            <span class="tiny muted">
              `REVIEW` 未启用时后端会给 `independent=false` —— 那是「非独立/未启用」，不是"审查通过"
            </span>
          </div>
          <div v-if="verdict?.reason" class="verdict__reason">
            <span class="verdict__tag">理由</span>{{ verdict.reason }}
          </div>
          <div v-if="verdict?.outcomeKind" class="tiny muted mono">
            outcome_kind = {{ verdict.outcomeKind }}
          </div>
          <!-- 后端没产出时**如实说**，不拿 status 硬套四值 -->
          <div v-if="!verdict" class="legacy">
            后端**没有产出**结局四值（`report.verdict` 缺席）—— 这一格显示
            「未产出」，而不是替后端下一个它没下的判断。
            <template v-if="derived">
              下面那一行是<strong>按运行状态推的</strong>兜底值（{{ derived.raw }}），仅供参考。
            </template>
          </div>
          <div v-else-if="derived" class="tiny muted">
            兜底推导值：{{ derived.raw }}（后端 verdict 已优先，此行仅备注）
          </div>
        </div>
      </div>

      <!-- MANIFEST -->
      <div class="block">
        <div class="block__head">
          <span class="block__name">MANIFEST</span>
          <span
            v-if="manifest"
            class="pill tiny"
            :class="manifest.passed ? 'pill--ok' : 'pill--err'"
          >
            {{ manifest.passed ? '通过' : '未通过' }}
          </span>
          <span v-else class="pill tiny muted">未执行</span>
        </div>
        <div v-if="manifest" class="block__body">
          <div class="kv tiny mono">
            实际产出 {{ manifest.actualFiles.length }} 个文件 · 声明与实际的差异
            {{ manifest.violations.length }} 处
          </div>
          <ul v-if="manifest.violations.length" class="violations">
            <li v-for="(v, i) in manifest.violations" :key="i">
              <span class="vkind">{{ v.kind }}</span>
              <span class="mono">{{ v.path }}</span>
              <div class="vmsg">{{ v.message }}</div>
            </li>
          </ul>
        </div>
      </div>

      <!-- CHECK -->
      <div class="block">
        <div class="block__head">
          <span class="block__name">CHECK</span>
          <span v-if="!checks.length" class="pill tiny muted">未执行</span>
          <template v-else>
            <span class="pill tiny" :class="syntaxBad ? 'pill--err' : 'pill--ok'">
              语法 {{ syntaxOk }} 通过<template v-if="syntaxBad"> / {{ syntaxBad }} 失败</template>
            </span>
            <span v-if="lintIssues" class="pill tiny pill--warn">lint {{ lintIssues }} 文件有问题</span>
            <span v-else-if="lintSkipped" class="pill tiny pill--warn">lint 未执行（ruff 缺失）</span>
          </template>
        </div>
        <div v-if="checks.length" class="block__body">
          <div v-for="(c, i) in checks" :key="i" class="checkline">
            <span class="checkline__dot" :class="`checkline__dot--${c.status}`" />
            <span class="mono tiny">{{ c.tool === 'syntax' ? '语法' : 'lint' }}</span>
            <span class="mono tiny checkline__path">{{ c.path }}</span>
            <span class="tiny" :class="`status--${c.status}`">
              {{ c.status === 'passed' ? '通过' : c.status === 'skipped' ? '未执行' : '失败' }}
            </span>
          </div>
        </div>
      </div>

      <!-- 复用性检查（后端 P2，**有否决权**：调用了不存在的符号 / 用了没导入） -->
      <div v-if="reuse" class="block" :class="{ 'block--err': reuseBlocking.length }">
        <div class="block__head">
          <span class="block__name">复用性</span>
          <span
            class="pill tiny"
            :class="reuseBlocking.length ? 'pill--err' : reuseWarnings.length ? 'pill--warn' : 'pill--ok'"
          >
            {{ reuseBlocking.length ? `${reuseBlocking.length} 项阻塞` : reuseWarnings.length ? `${reuseWarnings.length} 项提示` : '通过' }}
          </span>
          <span class="spacer" />
          <span class="tiny muted">机械 · 有否决权</span>
        </div>
        <div class="block__body">
          <ul v-if="reuseBlocking.length" class="violations">
            <li v-for="(b, i) in reuseBlocking" :key="i">
              <span class="vkind">必然崩</span>
              <div class="vmsg">{{ b }}</div>
            </li>
          </ul>
          <ul v-if="reuseWarnings.length" class="skipped">
            <li v-for="(w, i) in reuseWarnings" :key="i" class="tiny">
              <span class="skipped__mark">⚠ 提示</span>
              <span class="skipped__why">{{ w }}</span>
            </li>
          </ul>
          <div v-if="!reuseBlocking.length && !reuseWarnings.length" class="tiny muted">
            没有重复符号 / 未用导入 / 命名不一致
          </div>
        </div>
      </div>

      <!-- VERIFY -->
      <div class="block">
        <div class="block__head">
          <span class="block__name">VERIFY</span>
          <span
            v-if="verify"
            class="pill tiny"
            :class="verify.passed ? 'pill--ok' : 'pill--err'"
          >
            {{ verify.passed ? '退出码 0' : '未通过' }}
          </span>
          <span v-else class="pill tiny muted">未执行</span>
          <!-- ★ 被跳过的验证必须**单独可见**：它既不是"通过"也不是"失败"，
               而是"本该验、却没验"。上游把它做成显式事件，正是为了不让
               上层误诊成"缺少验证命令"。混进上面的状态里就等于白做了。 -->
          <span v-if="skipped.length" class="pill tiny pill--warn">
            跳过 {{ skipped.length }} 次
          </span>
          <span class="spacer" />
          <span v-if="state.verifyProbes" class="pill tiny muted">
            循环内回流 {{ state.verifyProbes }} 次
          </span>
        </div>
        <div class="block__body">
          <pre v-if="verify?.command" class="codebox mono">{{ verify.command }}</pre>
          <pre v-if="verify?.detail" class="codebox mono" :class="{ 'codebox--err': !verify.passed }">{{
            verify.detail
          }}</pre>
          <div v-if="!verify" class="tiny muted">尚无验收结果</div>
          <ul v-if="skipped.length" class="skipped">
            <li v-for="(s, i) in skipped" :key="i" class="tiny">
              <span class="skipped__mark">⚠ 验证被跳过</span>
              <span class="skipped__why">{{ s }}</span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.gate {
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.gate__body {
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow-y: auto;
  min-height: 0;
}

.block {
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: rgba(11, 18, 32, 0.5);
  overflow: hidden;
}
.block__head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background: rgba(120, 165, 220, 0.06);
  border-bottom: 1px solid var(--line);
  flex-wrap: wrap;
}
.block__name {
  font-family: var(--mono);
  font-size: 10.5px;
  letter-spacing: 0.12em;
  color: var(--fg-1);
}
.block__body {
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

/* ---------------- 结论四值（P3） ---------------- */
.block--verdict {
  border-left-width: 3px;
}
.block--ok {
  border-left-color: var(--green);
}
.block--err {
  border-left-color: var(--red);
}
.block--warn {
  border-left-color: var(--amber);
}
.block--invalid {
  border-left-color: var(--violet);
}
.block--muted {
  border-left-color: var(--line-strong);
}
.pill--ok {
  color: var(--green);
  border-color: rgba(70, 224, 138, 0.45);
}
.pill--err {
  color: var(--red);
  border-color: rgba(255, 107, 129, 0.45);
}
.pill--warn {
  color: var(--amber);
  border-color: rgba(255, 190, 90, 0.45);
}
.pill--invalid {
  color: var(--violet);
  border-color: rgba(160, 130, 255, 0.5);
}
.verdict {
  gap: 4px;
}
.verdict__row {
  display: flex;
  align-items: baseline;
  gap: 7px;
  flex-wrap: wrap;
  font-size: 11.5px;
}
.verdict__tag {
  flex: 0 0 auto;
  min-width: 84px;
  font-size: 9.5px;
  letter-spacing: 0.06em;
  color: var(--violet);
}
.verdict__val {
  color: var(--fg-1);
}
.verdict__val--warn {
  color: var(--amber);
  font-weight: 600;
}
.verdict__reason {
  font-size: 11px;
  line-height: 1.6;
  color: var(--fg-2);
  border-left: 2px solid var(--line-strong);
  padding-left: 7px;
}

.kv {
  color: var(--fg-1);
}

.violations {
  list-style: none;
  margin: 4px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
/* 被跳过的验证：用琥珀色（"要留意"），与 violations 的红色（"出错"）区分开 */
.skipped {
  list-style: none;
  margin: 6px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.skipped li {
  font-size: 11px;
  border-left: 2px solid var(--amber);
  padding-left: 7px;
}
.skipped__mark {
  color: var(--amber);
  margin-right: 5px;
}
.skipped__why {
  color: var(--fg-2);
  word-break: break-word;
}
.violations li {
  font-size: 11px;
  border-left: 2px solid var(--red);
  padding-left: 7px;
  animation: fadeSlideIn 0.3s var(--ease) both;
}
.vkind {
  display: inline-block;
  font-size: 9.5px;
  color: var(--red);
  border: 1px solid rgba(255, 107, 129, 0.4);
  border-radius: 4px;
  padding: 0 4px;
  margin-right: 5px;
}
.vmsg {
  color: var(--fg-1);
  font-size: 10.5px;
  margin-top: 2px;
  word-break: break-word;
}

.checkline {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 11px;
  animation: fadeSlideIn 0.24s var(--ease) both;
}
.checkline__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--fg-2);
}
.checkline__dot--passed {
  background: var(--green);
}
.checkline__dot--failed {
  background: var(--red);
}
.checkline__dot--skipped {
  background: var(--amber);
}
.checkline__path {
  flex: 1 1 auto;
  color: var(--fg-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.status--passed {
  color: var(--green);
}
.status--failed {
  color: var(--red);
}
.status--skipped {
  color: var(--amber);
}

.codebox {
  margin: 0;
  padding: 7px 9px;
  border-radius: 7px;
  background: rgba(4, 9, 18, 0.72);
  border: 1px solid var(--line);
  font-size: 10.5px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 130px;
  overflow: auto;
  color: var(--fg-1);
}
.codebox--err {
  border-color: rgba(255, 107, 129, 0.35);
  color: #ffb3bf;
}

/* 旧词表 / 未产出提示：琥珀色（"要留意"），不是红色（"出错"）—— 它本身不是错误 */
.legacy {
  font-size: 10.5px;
  line-height: 1.65;
  color: var(--amber);
  border-left: 2px solid var(--amber);
  padding-left: 7px;
  opacity: 0.92;
}
</style>
