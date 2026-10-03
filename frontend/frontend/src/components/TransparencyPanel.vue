<script setup lang="ts">
/**
 * 透明化审查面板（TRANSPARENCY-UI）：四块「为什么」。
 *
 *   判据演化 (B4) · 决策依据 (A2) · 模型回合原话 (A3) · 收尾自述 (C3)
 *
 * 三条设计纪律（都是这一轮的**验收**逼出来的）
 * -------------------------------------------
 * 1. **默认落在「判据演化」**。需求原话说它是"本次最该被看见的东西"：
 *    一次 `passed` 的运行，判据在失败之后被换成了一张必过的考卷。
 *    这块不该藏在第三个 tab 里等人去找。
 *
 * 2. **反面事实挂在标题栏上，不随 tab 藏起来。**
 *    `fact_check.contradictions`、以及"本次没有自述"这类**缺席**，
 *    都在标题栏上有一行常驻提示 —— 切到别的 tab 也看得见。
 *    折叠在角落里等于没做（需求原文：「放在最显眼处」「不是折叠在角落里」）。
 *
 * 3. **推断必须与后端给的显式事实分开显示。** 「上一条执行失败了」有两个来源：
 *    后端 `verify_criterion.previous_passed`（他说的）与我按 seq 相邻读出来的。
 *    两者同形，就分不出"谁说的"。
 */
import { computed, ref } from 'vue'
import type { CriterionView, RunState } from '@/types'

type TabId = 'criteria' | 'decisions' | 'turns' | 'report' | 'decompose'

const props = defineProps<{
  state: RunState
  /**
   * 初始落在哪个 tab。默认 `criteria` —— 见上面第 1 条设计纪律。
   * 之所以做成 prop：`frontend/scripts/replay-check.mjs` 要**逐个 tab 渲染**
   * 并断言关键字符串真的在 HTML 里（不然"读数对、面板没显示"查不出来）。
   */
  initialTab?: TabId
}>()

const tab = ref<TabId>(props.initialTab ?? 'criteria')

const criteria = computed(() => props.state.criteria ?? [])
const rounds = computed(() => props.state.decisionRounds ?? [])
const turns = computed(() => props.state.modelTurns ?? [])
const report = computed(() => props.state.selfReport)
const factCheck = computed(() => props.state.factCheck)
const contradictions = computed(() => factCheck.value?.contradictions ?? [])
const unmentioned = computed(() => factCheck.value?.unmentioned ?? [])
const missingFields = computed(() => factCheck.value?.missingFields ?? [])
const notes = computed(() => factCheck.value?.notes ?? [])
const facts = computed(() => factCheck.value?.facts ?? {})
/** P4：③ 拆解合规审查（后端**已声明形状、尚未发出**时为 null） */
const review = computed(() => props.state.decomposeReview)
const violated = computed(() => review.value?.violated ?? [])
const undecidable = computed(() => review.value?.undecidable ?? [])

/** 换了判据的位置（不论来源） */
const swapped = computed(() =>
  criteria.value.filter((c) => c.previousPassed === false || c.afterFailure !== null),
)

const tabs = computed(() => [
  {
    id: 'criteria' as TabId,
    label: '验收判据演化',
    count: criteria.value.length,
    alarm: swapped.value.length,
    alarmText: swapped.value.length ? `换过 ${swapped.value.length} 次` : '',
  },
  { id: 'decisions' as TabId, label: '决策依据', count: rounds.value.length, alarm: 0, alarmText: '' },
  { id: 'turns' as TabId, label: '模型回合原话', count: turns.value.length, alarm: 0, alarmText: '' },
  {
    id: 'report' as TabId,
    label: '收尾自述',
    count: report.value ? 1 : 0,
    alarm: contradictions.value.length + unmentioned.value.length,
    alarmText: report.value ? '' : '缺失',
  },
  {
    id: 'decompose' as TabId,
    label: '拆解合规',
    count: review.value ? review.value.principles.length : 0,
    // ★ `undecidable` **也算告警**：它意味着"审查范围不完整"，
    //   不是"没问题"（"判不了 ≠ 通过"是本项目反复栽的坑）。
    alarm: violated.value.length + undecidable.value.length,
    alarmText: review.value ? '' : '未产出',
  },
])

/* ---------------- D3：结论 + 判据来源 ---------------- */
const OUTCOME_LABEL: Record<string, string> = {
  pass: 'pass（判据执行且通过）',
  fail: 'fail（判据执行且未通过）',
  abstain: 'abstain（模型声明做不到）',
  invalid: 'invalid（任务或工装本身有问题）',
  unknown: '未产出',
}

/** 运行还没结束时 `outcome.raw` 为空 —— 用运行状态兜一句，别把"未产出"当成结论 */
const outcomeLabel = computed(() => {
  const o = props.state.outcome
  if (!o.raw) {
    const s = props.state.status
    return s === 'running' || s === 'queued' ? `进行中（${s}）` : `未产出结局（${s}）`
  }
  return OUTCOME_LABEL[o.value] ?? o.value
})

const sourceText = computed(() => {
  const s = props.state.verdict?.criterionSource || props.state.outcome.source
  if (s === 'caller') return '调用方给定'
  if (s === 'model') return '模型自拟'
  return '未知（事件未带 source）'
})

/**
 * ★ P3：审查独立性三态。
 * `true` → 独立；`false` → **非独立/未启用**（`REVIEW` 没配）；`null` → 后端**没给**。
 * 把 `null` 显示成"非独立"就是把"判不了"说成"否"。
 */
const independentText = computed(() => {
  const v = props.state.verdict?.criterionIndependent
  if (v === true) return '独立'
  if (v === false) return '非独立/未启用'
  return '未给（判不了）'
})

/** B2：「替换一条已执行且失败的判据」必须给理由。没给就要看得见。 */
const missingReason = computed(() =>
  criteria.value.filter(
    (c) => c.outcome === 'rejected' && !c.reason.trim() && (c.previousPassed === false || c.afterFailure),
  ),
)

/* ---------------- 纯展示辅助 ---------------- */
function firstLine(s: string): string {
  const t = (s || '').trim()
  return t ? t.split('\n')[0] : ''
}

/** 判据命令的首行摘要：一行就够读出"这张考卷要考什么" */
function head(command: string, n = 96): string {
  const t = firstLine(command) || '（该事件未单独记录命令）'
  return t.length > n ? t.slice(0, n) + '…' : t
}

/** 同一条命令是否在前面已经出现过（样例里 (c) 出现了两次：回流 + 最终记录） */
function sameAsEarlier(rows: CriterionView[], i: number): number | null {
  const cur = rows[i]
  if (!cur.command) return null
  for (let k = 0; k < i; k += 1) if (rows[k].command === cur.command) return rows[k].seq
  return null
}

const OUTCOME_BADGE: Record<string, string> = {
  passed: '通过',
  failed: '未通过',
  rejected: '候选被拒',
  unknown: '结果未知',
}
const outcomeBadge = (c: CriterionView) => OUTCOME_BADGE[c.outcome] ?? c.outcome

const ACTION_LABEL: Record<string, string> = {
  executed: 'executed（真执行了）',
  rejected: 'rejected（候选被拒）',
  adopted: 'adopted（被采纳）',
  unknown: 'action 未知',
}

function sourceLabel(s: string): string {
  if (s === 'model') return '模型'
  if (s === 'caller') return '调用方'
  return s || '未知'
}

/** 原话被 bridge 截断了吗（`content_len` 是真值，`content` 是截断值） */
function truncated(t: { content: string; contentLen: number }): boolean {
  return t.contentLen > t.content.length
}

const confidence = computed(() => {
  const r = report.value
  if (!r) return ''
  const parts = [r.confidenceLevel, r.confidenceBasis].filter((x) => x && x.length)
  return parts.join(' · ')
})
</script>

<template>
  <section class="tp card">
    <div class="card__head tp__head">
      <h2 class="card__title">为什么（透明化审查）</h2>

      <!-- ★ 常驻：结论 + 判据来源（D3 —— "这次是模型自己给自己判过的"必须一眼可见） -->
      <span class="tp__outcome" :class="`tp__outcome--${state.outcome.value}`">
        结论 {{ outcomeLabel }}
        <span class="tp__src">判据来源：<strong>{{ sourceText }}</strong></span>
        <!-- ★ P3：审查独立性 —— 三态如实显示（`未给` 不等于 `非独立`） -->
        <span class="tp__src">独立审查：<strong>{{ independentText }}</strong></span>
      </span>

      <!-- ★ P4：拆解合规的坏消息也**常驻**（`undecidable` 同样算坏消息） -->
      <span v-if="violated.length" class="tp__alarm">⚠ 拆解合规：违反 {{ violated.length }} 条</span>
      <span v-else-if="undecidable.length" class="tp__alarm tp__alarm--soft">
        拆解合规：{{ undecidable.length }} 条<b>判不了</b>（≠ 通过）
      </span>

      <!-- ★ 常驻：自述与机械事实的矛盾（不随 tab 隐藏） -->
      <span v-if="contradictions.length" class="tp__alarm">
        ⚠ 自述与机械事实矛盾 {{ contradictions.length }} 处
      </span>
      <span v-else-if="unmentioned.length" class="tp__alarm tp__alarm--soft">
        目标里有 {{ unmentioned.length }} 项要求<b>没被自述提及</b>
      </span>
      <span v-else-if="!report" class="tp__alarm tp__alarm--soft">本次运行没有收尾自述</span>
      <span v-else-if="missingReason.length" class="tp__alarm">⚠ 有判据被换掉但<b>没给理由</b></span>

      <span class="spacer" />

      <nav class="tp__tabs">
        <button
          v-for="t in tabs"
          :key="t.id"
          type="button"
          class="tp__tab"
          :class="{ 'tp__tab--on': tab === t.id, 'tp__tab--alarm': t.alarm > 0 }"
          @click="tab = t.id"
        >
          {{ t.label }}
          <span class="mono">{{ t.count }}</span>
          <span v-if="t.alarmText" class="tp__tabAlarm">{{ t.alarmText }}</span>
        </button>
      </nav>
    </div>

    <div class="card__body tp__body">
      <!-- ============================ B4 判据演化 ============================ -->
      <div v-if="tab === 'criteria'" class="pane">
        <p class="pane__note">
          按<b>事件序号原序</b>列出每一条候选 / 采纳 / 执行的判据 —— 不重排、不改写因果。
          新事件（<code class="mono">verify_criterion</code>）自带前后关系，那部分标为
          <b>后端显式</b>；老事件流（<code class="mono">verify_probe</code> /
          <code class="mono">verify_skipped</code>）不带，只能按序号相邻读，标为
          <b>按序号相邻推断</b>。两种来源分开显示。
        </p>

        <div v-if="!criteria.length" class="empty">本次运行没有任何判据事件</div>

        <div
          v-for="(c, i) in criteria"
          :key="c.seq"
          class="crit"
          :class="[`crit--${c.outcome}`, { 'crit--adopted': c.adopted }]"
        >
          <div class="crit__top">
            <span class="mono crit__seq">seq {{ c.seq }}</span>
            <span class="pill tiny" :class="`pill--${c.outcome}`">{{ outcomeBadge(c) }}</span>
            <span class="pill tiny muted mono">{{ ACTION_LABEL[c.action] ?? c.action }}</span>
            <span v-if="c.adopted" class="pill tiny pill--adopt">最终被记录</span>
            <span
              v-if="c.source"
              class="pill tiny"
              :class="c.source === 'model' ? 'pill--warn' : 'pill--ok'"
            >
              判据来自 {{ sourceLabel(c.source) }}
            </span>
            <span v-if="sameAsEarlier(criteria, i) !== null" class="pill tiny muted">
              与 seq {{ sameAsEarlier(criteria, i) }} 同一条命令
            </span>
            <span class="spacer" />
            <span class="tiny muted mono">{{ new Date(c.at).toLocaleTimeString('zh-CN', { hour12: false }) }}</span>
          </div>

          <!-- ★ 验收点 1：失败的判据被换掉时，必须在<b>这一行</b>上直接标出来 -->
          <div v-if="c.previousPassed === false || c.previousCommand" class="crit__swap">
            <span class="crit__swapMark">
              ⚠ 上一条被判据执行过了{{ c.previousPassed === false ? '，并且失败' : '' }}
            </span>
            <span v-if="c.previousCommand" class="crit__swapWhy">
              上一条命令：<code class="mono">{{ head(c.previousCommand, 120) }}</code>
            </span>
            <span class="crit__swapProv">来源：<b>后端显式</b>（`verify_criterion.previous_command`
              / `previous_passed`）—— 不是本界面推断的</span>
          </div>
          <div v-else-if="c.afterFailure" class="crit__swap">
            <span class="crit__swapMark">⚠ 上一条判据执行失败了（seq {{ c.afterFailure.seq }}）</span>
            <span class="crit__swapWhy">
              本条紧随其后 —— 上一条的命令：<code class="mono">{{ head(c.afterFailure.command, 120) }}</code>
            </span>
            <span class="crit__swapProv">来源：<b>按事件序号相邻推断</b>（这条事件本身不带前后关系）</span>
          </div>

          <pre v-if="c.command" class="codebox mono">{{ c.command }}</pre>
          <div v-else class="crit__nocmd">
            该事件未单独记录命令
            <span v-if="c.outcome === 'rejected'">
              （后端在 <code class="mono">verify_skipped</code> 里传了空命令，被拒的命令写在下面的理由原文里）
            </span>
          </div>

          <div v-if="c.detail && c.detail !== c.command" class="crit__detail">{{ c.detail }}</div>

          <div v-if="c.reason && c.reason !== c.detail" class="crit__reason">
            <span class="crit__reasonTag">理由</span>{{ c.reason }}
          </div>
          <!-- B2 要求"换判据必须给理由"；没给就要看得见 -->
          <div
            v-if="c.outcome === 'rejected' && !c.reason"
            class="crit__reason crit__reason--missing"
          >
            <span class="crit__reasonTag">理由</span>⚠ 该次拒绝<b>没有给理由</b> —— B2 要求换判据必须给理由
          </div>
        </div>
      </div>

      <!-- ============================ A2 决策依据 ============================ -->
      <div v-else-if="tab === 'decisions'" class="pane">
        <p class="pane__note">
          编排器每一轮的 <code class="mono">reasoning</code>（原文）。两个生产者同源：
          上游 A1 的 <code class="mono">orchestrator_round</code>（新运行）与 bridge 的
          <code class="mono">orchestrator_decision</code>（含固定样例的老运行）。
        </p>

        <div v-if="!rounds.length" class="empty">本次运行没有编排器决策事件</div>

        <div v-for="r in rounds" :key="r.round" class="round">
          <div class="round__head">
            <span class="round__no mono">第 {{ r.round }} 轮</span>
            <span class="pill tiny" :class="r.status === 'continue' ? 'pill--ok' : 'pill--warn'">
              status {{ r.status || '?' }}
            </span>
            <span v-if="r.taskCount" class="pill tiny muted">声明 {{ r.taskCount }} 个任务</span>
          </div>

          <div class="round__reason">
            <span class="round__tag">reasoning</span>
            <span class="round__text">{{ r.reasoning || '（本轮的 reasoning 是空串 —— 后端没给）' }}</span>
          </div>

          <div class="round__intent">
            <span class="round__tag">打算做什么</span>
            <template v-if="r.intentSource === 'field'">
              <span class="round__text">{{ r.intent }}</span>
            </template>
            <template v-else-if="r.intentSource === 'tasks'">
              <span class="round__text">
                来源：后端 <code class="mono">orchestrator_round.tasks</code>（编排器<b>声明</b>的本轮任务）
              </span>
            </template>
            <template v-else>
              <span class="round__text round__text--absent">
                后端未提供 `intent` 字段，本轮也没有 `orchestrator_round.tasks` ——
                下面是<b>实测替代物</b>（本轮实际派发的任务）
              </span>
            </template>
          </div>

          <ul v-if="r.planned.length" class="planned">
            <li v-for="p in r.planned" :key="`${p.source}-${p.id}`" class="planned__item">
              <span class="mono planned__id">{{ p.id || '?' }}</span>
              <span class="planned__desc">
                {{ p.description || '（无描述）' }}
                <span v-if="p.expectedOutput" class="planned__expected">→ {{ p.expectedOutput }}</span>
              </span>
              <!-- ★ 声明 vs 实测：把"说要做什么"当成"做了什么"就是把意图当事实 -->
              <span class="pill tiny" :class="p.source === 'declared' ? 'pill--declared' : 'pill--ok'">
                {{ p.source === 'declared' ? '声明' : '已派发' }}
              </span>
              <span v-if="p.ok !== null" class="pill tiny" :class="p.ok ? 'pill--ok' : 'pill--err'">
                {{ p.ok ? '完成' : '失败' }}
              </span>
              <span v-for="h in p.toolHint" :key="h" class="pill tiny muted mono">{{ h }}</span>
            </li>
          </ul>
          <div v-else class="planned__none">本轮没有任务记录（status={{ r.status || '?' }}）</div>

          <div v-if="r.finalAnswer" class="round__final">
            <span class="round__tag">final_answer</span>
            <span class="round__text">{{ r.finalAnswer }}</span>
          </div>
        </div>
      </div>

      <!-- ============================ A3 模型回合原话 ============================ -->
      <div v-else-if="tab === 'turns'" class="pane">
        <p class="pane__note">
          按任务 / 步组织：<b>模型这一轮说了什么 → 调了什么工具 → 结果如何</b>。
          原话来自 <code class="mono">model_reply.content</code>（bridge 截断上限 400 字符，真实长度另标）。
        </p>

        <div v-if="!turns.length" class="empty">本次运行没有模型回合事件</div>

        <div
          v-for="t in turns"
          :key="`${t.taskId}-${t.step}`"
          class="turn"
          :class="{ 'turn--quiet': !t.content && !t.calls.length }"
        >
          <div class="turn__head">
            <span class="mono turn__id">{{ t.taskId }}</span>
            <span class="turn__step">第 {{ t.step }} 步</span>
            <span class="pill tiny muted">工具调用 {{ t.toolCalls }}</span>
            <span v-if="truncated(t)" class="pill tiny muted">
              原话共 {{ t.contentLen }} 字，此处显示前 {{ t.content.length }}
            </span>
          </div>

          <div v-if="t.content" class="turn__said">
            <span class="turn__tag">原话</span>
            <span class="turn__text">{{ t.content }}</span>
          </div>
          <!-- ★ 三种"没说话"要分开：只调工具 / 什么都没干。混成一句就是把事实抹平 -->
          <div v-else-if="t.calls.length" class="turn__said turn__said--none">
            本轮无文字输出，<b>直接调用工具</b>
          </div>
          <div v-else class="turn__said turn__said--none">
            本轮既无文字输出、<b>也没有工具调用</b>（这一步什么都没发生）
          </div>

          <ul v-if="t.calls.length" class="calls">
            <li v-for="c in t.calls" :key="c.seq" class="calls__item">
              <span class="mono calls__tool">{{ c.tool }}</span>
              <span class="calls__sum">{{ c.summary }}</span>
              <span class="calls__arrow">→</span>
              <span class="calls__res" :class="`calls__res--${c.status}`">
                {{ c.status === 'running' ? '进行中' : c.status === 'error' ? '出错' : '返回' }}
              </span>
              <span v-if="c.preview" class="calls__preview mono">{{ c.preview }}</span>
            </li>
          </ul>
        </div>
      </div>

      <!-- ============================ C3 收尾自述 ============================ -->
      <div v-else-if="tab === 'report'" class="pane">
        <!-- ★ 矛盾放最显眼处：面板第一块，不折叠 -->
        <div v-if="contradictions.length" class="contra">
          <div class="contra__head">
            ⚠ 自述与机械事实<b>矛盾</b> {{ contradictions.length }} 处
          </div>
          <ul class="contra__list">
            <li v-for="(r, i) in contradictions" :key="i">
              <div class="contra__claim">
                <span class="contra__where">模型说</span>{{ r.claim || '（未给主张原文）' }}
                <span v-if="r.kind" class="pill tiny muted mono">{{ r.kind }}</span>
                <span v-if="r.severity" class="pill tiny muted">{{ r.severity }}</span>
              </div>
              <div class="contra__detail">
                <span class="contra__where">机械事实</span>{{ r.fact || '（对照行未给细节）' }}
              </div>
            </li>
          </ul>
        </div>

        <!-- ★ C2 对照表第 4 行：目标要求了、但自述里既没 done 也没 not_done -->
        <div v-if="unmentioned.length" class="unmentioned">
          <div class="unmentioned__head">
            目标里明确了、但自述<b>既没写成 done 也没写成 not_done</b> 的要求 {{ unmentioned.length }} 项
          </div>
          <ul>
            <li v-for="(u, i) in unmentioned" :key="i">{{ u }}</li>
          </ul>
        </div>

        <div v-if="!report" class="absent">
          <div class="absent__head">本次运行没有收尾自述</div>
          <p class="absent__why">{{ state.selfReportAbsentReason || '运行尚未结束，或事件流里没有自述事件。' }}</p>
          <p class="absent__dep">
            <b>这不是"模型没什么要说的"。</b>后端 C1（上游
            <code class="mono">core/coding_cycle.py:755</code> 的 <code class="mono">self_report</code> 事件）
            交付后，这里会出现 done / not_done / why / reflections / approach / confidence /
            open_questions，并带 <code class="mono">fact_check</code> 与机械事实逐条对照。
          </p>
        </div>

        <template v-else>
          <!-- 自述本身没生成出来：这是**失败**，不是"模型说没事" -->
          <div v-if="!report.ok" class="srfail">
            <b>自述生成失败</b>（<code class="mono">ok=false</code>）：
            {{ report.error || '（未给 error）' }}
            <span class="srfail__note">
              —— 后端契约特别强调过：`ok=false` 指的是"自述没生成出来"，
              <b>不是</b>"模型说没事"。（phase={{ report.phase || '?' }}）
            </span>
          </div>

          <div class="sr__conf">
            <span class="sr__confTag">self-confidence</span>
            <span>{{ confidence || '（未给）' }}</span>
          </div>

          <div class="sr">
            <div class="sr__col sr__col--notdone">
              <div class="sr__head">not_done · 没做什么</div>
              <ul v-if="report.notDone.length">
                <li v-for="(x, i) in report.notDone" :key="i">{{ x }}</li>
              </ul>
              <div v-else class="sr__none">（空 —— 声称全都做了）</div>
            </div>

            <div class="sr__col">
              <div class="sr__head">done · 做了什么</div>
              <ul v-if="report.done.length">
                <li v-for="(x, i) in report.done" :key="i">{{ x }}</li>
              </ul>
              <div v-else class="sr__none">（空）</div>
            </div>
          </div>

          <div
            v-for="grp in [
              { title: 'why · 没做的原因', items: report.why },
              { title: 'reflections · 反思', items: report.reflections },
              { title: 'approach · 思路', items: report.approach },
              { title: 'open_questions · 未决问题', items: report.openQuestions },
            ]"
            :key="grp.title"
            class="sr__group"
          >
            <div class="sr__head">{{ grp.title }}</div>
            <ul v-if="grp.items.length">
              <li v-for="(x, i) in grp.items" :key="i">{{ x }}</li>
            </ul>
            <div v-else class="sr__none">（空）</div>
          </div>

          <div v-if="missingFields.length" class="fc">
            <div class="fc__sum">自述缺了必需字段：{{ missingFields.join('、') }}</div>
          </div>

          <details v-if="notes.length" class="fc">
            <summary class="fc__sum">fact_check 的「一致」记录 {{ notes.length }} 条</summary>
            <ul class="fc__list">
              <li v-for="(n, i) in notes" :key="i"><span class="mono">✓</span> {{ n }}</li>
            </ul>
          </details>

          <details v-if="Object.keys(facts).length" class="fc">
            <summary class="fc__sum">核对用的机械事实快照</summary>
            <ul class="fc__list">
              <li v-for="(v, k) in facts" :key="k">
                <span class="mono">{{ k }}</span>：{{ Array.isArray(v) ? v.join('、') || '（空）' : v }}
              </li>
            </ul>
          </details>

          <p class="sr__src">
            自述与对照均由后端产出（上游 <code class="mono">core/self_report.py</code>）。
            本面板只呈现，不在前端重算 —— 重算就成了"第二个体检口径"。
          </p>
        </template>
      </div>

      <!-- ============================ P4 拆解合规审查 ============================ -->
      <div v-else-if="tab === 'decompose'" class="pane">
        <p class="pane__note">
          ③ 拆解合规关卡（后端 <code class="mono">core/contract.py:207 decompose_review</code>）：
          逐条原则显示判定。★ <b>「判不了」不是「通过」</b> —— `undecidable` 与 `violated`
          <b>分开列</b>，且 `passed=true` <b>不足以</b>把这页画成绿色
          （后端契约原话：`passed` 只代表<b>机械条款</b>通过，`undecidable` 非空说明
          审查范围不完整，<b>不得</b>呈现为「审查通过」）。
        </p>

        <div v-if="!review" class="absent">
          <div class="absent__head">后端尚未产出拆解合规审查</div>
          <p class="absent__why">
            该事件<b>已在上游声明的词表里</b>（`since="1.3"`），但<b>还没有发出</b> ——
            我核对过：`core/contract.py:207` 有它的 <code class="mono">EventSpec</code>，
            而全仓 <code class="mono">_emit("decompose_review"…)</code> 一处都没有。
          </p>
          <p class="absent__dep">
            所以这里显示「未产出」，<b>而不是</b>画一个绿色的"审查通过"。
            上游一开始发这个事件，这一页就自动有内容（字段名照抄契约，不改、不猜）。
          </p>
        </div>

        <template v-else>
          <!-- 总览：三个数字 + 一句结论，**不显示"通过"字样**除非真的没有 violated/undecidable -->
          <div class="dr" :class="`dr--${violated.length ? 'bad' : undecidable.length ? 'unknown' : 'ok'}`">
            <div class="dr__head">
              <span class="pill tiny" :class="violated.length ? 'pill--failed' : undecidable.length ? 'pill--rejected' : 'pill--passed'">
                {{ violated.length ? `违反 ${violated.length}` : undecidable.length ? `判不了 ${undecidable.length}` : '全部通过' }}
              </span>
              <span class="pill tiny" :class="review.passed ? 'pill--passed' : 'pill--failed'">
                机械条款 {{ review.passed === null ? '未给' : review.passed ? '通过' : '未通过' }}
              </span>
              <span class="pill tiny" :class="review.independent === true ? 'pill--passed' : 'pill--rejected'">
                独立审查 {{ review.independent === true ? '是' : review.independent === false ? '否/未启用' : '未给' }}
              </span>
              <span v-if="review.checkedBy" class="pill tiny muted mono">checked_by={{ review.checkedBy }}</span>
              <span v-if="violated.length || undecidable.length" class="dr__warn">
                ⚠ 这一行<b>不是</b>「审查通过」：{{ violated.length }} 条违反、{{ undecidable.length }} 条判不了
              </span>
            </div>
            <div v-if="review.summary" class="dr__sum">{{ review.summary }}</div>
          </div>

          <!-- ★ violated 与 undecidable **视觉分开**（两块，颜色与措辞都不同） -->
          <div v-if="violated.length" class="dr__block dr__block--violated">
            <div class="dr__blockHead">违反（<b>要改</b>）{{ violated.length }} 条</div>
            <ul>
              <li v-for="(v, i) in violated" :key="i">{{ v }}</li>
            </ul>
          </div>
          <div v-if="undecidable.length" class="dr__block dr__block--undecidable">
            <div class="dr__blockHead">
              判不了（<b>审查范围不完整</b>，既不是通过也不是违反）{{ undecidable.length }} 条
            </div>
            <ul>
              <li v-for="(u, i) in undecidable" :key="i">{{ u }}</li>
            </ul>
          </div>

          <div v-if="review.principles.length" class="dr__list">
            <div class="dr__listHead">逐条原则（{{ review.principles.length }} 条）</div>
            <div
              v-for="(p, i) in review.principles"
              :key="i"
              class="dr__row"
              :class="`dr__row--${p.verdict || 'unknown'}`"
            >
              <span class="mono dr__pid">{{ p.principle || '?' }}</span>
              <span class="pill tiny" :class="{
                'pill--failed': p.verdict === 'violated',
                'pill--passed': p.verdict === 'ok',
                'pill--rejected': p.verdict === 'undecidable',
                'muted': !p.verdict,
              }">
                {{ p.verdict === 'violated' ? '违反' : p.verdict === 'ok' ? '通过' : p.verdict === 'undecidable' ? '判不了' : '认不出' }}
              </span>
              <span v-if="p.checkedBy" class="pill tiny muted mono">{{ p.checkedBy }}</span>
              <span v-if="p.independent === false" class="pill tiny pill--rejected">非独立</span>
              <span v-if="p.evidence" class="dr__ev">{{ p.evidence }}</span>
            </div>
          </div>
        </template>
      </div>
    </div>
  </section>
</template>

<style scoped>
.tp {
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 0 0 auto;
}
.tp__head {
  flex-wrap: wrap;
  row-gap: 4px;
}
.tp__outcome {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 6px;
  border: 1px solid var(--line-strong);
  color: var(--fg-1);
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.tp__outcome--pass {
  border-color: rgba(70, 224, 138, 0.45);
  color: var(--green);
}
.tp__outcome--fail {
  border-color: rgba(255, 107, 129, 0.45);
  color: var(--red);
}
.tp__outcome--abstain,
.tp__outcome--invalid {
  border-color: rgba(255, 190, 90, 0.5);
  color: var(--amber);
}
.tp__outcome--unknown {
  border-color: var(--line-strong);
  color: var(--fg-2);
}
.tp__src {
  color: var(--fg-2);
}
.tp__src strong {
  color: var(--amber);
}

.tp__alarm {
  font-size: 11px;
  color: #ffc2cb;
  background: rgba(255, 107, 129, 0.14);
  border: 1px solid rgba(255, 107, 129, 0.5);
  border-radius: 6px;
  padding: 2px 8px;
}
.tp__alarm--soft {
  color: var(--amber);
  background: rgba(255, 190, 90, 0.1);
  border-color: rgba(255, 190, 90, 0.38);
}

.tp__tabs {
  display: flex;
  gap: 4px;
}
.tp__tab {
  font-size: 11px;
  padding: 3px 9px;
  border-radius: 7px;
  border: 1px solid var(--line-strong);
  background: rgba(11, 18, 32, 0.6);
  color: var(--fg-2);
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.tp__tab--on {
  border-color: rgba(53, 224, 208, 0.6);
  color: var(--cyan);
  background: rgba(53, 224, 208, 0.1);
}
.tp__tab--alarm:not(.tp__tab--on) {
  border-color: rgba(255, 107, 129, 0.45);
}
.tp__tabAlarm {
  color: var(--amber);
  font-weight: 600;
}

.tp__body {
  overflow-y: auto;
  min-height: 0;
}
.pane {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.pane__note {
  margin: 0;
  font-size: 11px;
  line-height: 1.6;
  color: var(--fg-2);
  border-left: 2px solid var(--line-strong);
  padding-left: 8px;
}
.empty {
  color: var(--fg-2);
  font-size: 12px;
  padding: 14px 0;
  text-align: center;
}

/* ---------------- B4 ---------------- */
.crit {
  border: 1px solid var(--line);
  border-left-width: 3px;
  border-radius: var(--radius-sm);
  padding: 7px 10px;
  background: rgba(11, 18, 32, 0.55);
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.crit--passed {
  border-left-color: var(--green);
}
.crit--failed {
  border-left-color: var(--red);
  background: rgba(255, 107, 129, 0.07);
}
.crit--rejected {
  border-left-color: var(--amber);
  background: rgba(255, 190, 90, 0.05);
}
.crit--unknown {
  border-left-color: var(--line-strong);
}
.crit--adopted {
  border-right: 2px solid var(--cyan);
}
.crit__top {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.crit__seq {
  font-size: 10px;
  color: var(--fg-2);
}
.pill--passed {
  color: var(--green);
  border-color: rgba(70, 224, 138, 0.45);
}
.pill--failed {
  color: var(--red);
  border-color: rgba(255, 107, 129, 0.45);
}
.pill--rejected {
  color: var(--amber);
  border-color: rgba(255, 190, 90, 0.45);
}
.pill--unknown {
  color: var(--fg-2);
}
.pill--adopt {
  color: var(--cyan);
  border-color: rgba(53, 224, 208, 0.5);
}
.pill--declared {
  color: var(--violet);
  border-color: rgba(160, 130, 255, 0.45);
}

.crit__swap {
  display: flex;
  flex-direction: column;
  gap: 2px;
  border: 1px solid rgba(255, 190, 90, 0.45);
  background: rgba(255, 190, 90, 0.12);
  border-radius: 6px;
  padding: 5px 8px;
}
.crit__swapMark {
  color: var(--amber);
  font-size: 11.5px;
  font-weight: 600;
}
.crit__swapWhy {
  font-size: 10.5px;
  color: var(--fg-1);
  word-break: break-word;
}
.crit__swapProv {
  font-size: 10px;
  color: var(--fg-2);
}
.crit__nocmd {
  font-size: 11px;
  color: var(--amber);
}
.crit__detail {
  font-size: 11px;
  color: var(--fg-1);
  line-height: 1.55;
  word-break: break-word;
}
.crit__reason {
  font-size: 11px;
  color: var(--fg-2);
  line-height: 1.6;
  word-break: break-word;
  border-left: 2px solid var(--line-strong);
  padding-left: 7px;
}
.crit__reason--missing {
  color: var(--red);
  border-left-color: var(--red);
}
.crit__reasonTag {
  color: var(--fg-2);
  margin-right: 5px;
  font-size: 10px;
}
.codebox {
  margin: 0;
  padding: 6px 8px;
  border-radius: 7px;
  background: rgba(4, 9, 18, 0.72);
  border: 1px solid var(--line);
  font-size: 10.5px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 132px;
  overflow: auto;
  color: var(--fg-1);
}

/* ---------------- A2 ---------------- */
.round {
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  padding: 7px 10px;
  background: rgba(11, 18, 32, 0.55);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.round__head {
  display: flex;
  align-items: center;
  gap: 6px;
}
.round__no {
  font-size: 11px;
  color: var(--cyan);
}
.round__reason,
.round__intent,
.round__final {
  display: flex;
  gap: 7px;
  font-size: 11.5px;
  line-height: 1.6;
}
.round__tag {
  flex: 0 0 auto;
  font-size: 9.5px;
  letter-spacing: 0.06em;
  color: var(--violet);
  padding-top: 2px;
  min-width: 70px;
}
.round__text {
  word-break: break-word;
  color: var(--fg-1);
}
.round__text--absent {
  color: var(--amber);
}
.planned {
  list-style: none;
  margin: 2px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.planned__item {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 11px;
  padding-left: 77px;
  flex-wrap: wrap;
}
.planned__id {
  color: var(--fg-2);
  font-size: 10px;
}
.planned__desc {
  flex: 1 1 auto;
  color: var(--fg-1);
  word-break: break-word;
}
.planned__expected {
  color: var(--fg-2);
  font-size: 10.5px;
}
.planned__none {
  font-size: 10.5px;
  color: var(--fg-2);
  padding-left: 77px;
}

/* ---------------- A3 ---------------- */
.turn {
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  padding: 7px 10px;
  background: rgba(11, 18, 32, 0.55);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.turn--quiet {
  border-style: dashed;
}
.turn__head {
  display: flex;
  align-items: center;
  gap: 7px;
}
.turn__id {
  font-size: 10.5px;
  color: var(--cyan);
  border: 1px solid rgba(53, 224, 208, 0.35);
  border-radius: 4px;
  padding: 0 5px;
}
.turn__step {
  font-size: 10.5px;
  color: var(--fg-2);
}
.turn__said {
  display: flex;
  gap: 7px;
  font-size: 11.5px;
  line-height: 1.6;
}
.turn__said--none {
  color: var(--fg-2);
  font-size: 11px;
}
.turn__tag {
  flex: 0 0 auto;
  font-size: 9.5px;
  color: var(--violet);
  padding-top: 2px;
  min-width: 32px;
}
.turn__text {
  color: var(--fg-1);
  word-break: break-word;
}
.calls {
  list-style: none;
  margin: 2px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.calls__item {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 11px;
  padding-left: 39px;
  flex-wrap: wrap;
}
.calls__tool {
  color: var(--cyan);
  font-size: 10.5px;
}
.calls__sum {
  color: var(--fg-1);
}
.calls__arrow {
  color: var(--fg-2);
}
.calls__res--ok {
  color: var(--green);
}
.calls__res--error {
  color: var(--red);
}
.calls__res--running {
  color: var(--amber);
}
.calls__preview {
  flex: 1 1 100%;
  color: var(--fg-2);
  font-size: 10px;
  word-break: break-word;
  max-height: 34px;
  overflow: hidden;
}

/* ---------------- C3 ---------------- */
.contra {
  border: 1px solid rgba(255, 107, 129, 0.55);
  background: rgba(255, 107, 129, 0.12);
  border-radius: var(--radius-sm);
  padding: 8px 10px;
}
.contra__head {
  color: var(--red);
  font-size: 12.5px;
  font-weight: 600;
  margin-bottom: 6px;
}
.contra__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.contra__list li {
  border-left: 2px solid var(--red);
  padding-left: 8px;
}
.contra__where {
  font-size: 9.5px;
  color: var(--fg-2);
  margin-right: 6px;
  border: 1px solid var(--line-strong);
  border-radius: 4px;
  padding: 0 4px;
}
.contra__claim {
  font-size: 11.5px;
  color: #ffd7dd;
}
.contra__detail {
  font-size: 11px;
  color: var(--fg-1);
  margin-top: 2px;
}
.unmentioned {
  border: 1px solid rgba(255, 190, 90, 0.45);
  background: rgba(255, 190, 90, 0.08);
  border-radius: var(--radius-sm);
  padding: 8px 10px;
}
.unmentioned__head {
  color: var(--amber);
  font-size: 11.5px;
  font-weight: 600;
  margin-bottom: 4px;
}
.unmentioned ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.unmentioned li {
  font-size: 11px;
  line-height: 1.6;
  color: var(--fg-1);
  border-left: 2px solid var(--amber);
  padding-left: 7px;
  word-break: break-word;
}
.absent {
  border: 1px dashed rgba(255, 190, 90, 0.5);
  background: rgba(255, 190, 90, 0.07);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.absent__head {
  color: var(--amber);
  font-size: 12.5px;
  font-weight: 600;
}
.absent__why {
  margin: 0;
  font-size: 11.5px;
  line-height: 1.65;
  color: var(--fg-1);
}
.absent__dep {
  margin: 0;
  font-size: 11px;
  line-height: 1.65;
  color: var(--fg-2);
}
.srfail {
  border: 1px solid rgba(255, 107, 129, 0.45);
  background: rgba(255, 107, 129, 0.1);
  border-radius: var(--radius-sm);
  padding: 8px 10px;
  font-size: 11.5px;
  line-height: 1.65;
  color: #ffd7dd;
}
.srfail__note {
  color: var(--fg-2);
  font-size: 10.5px;
}
.sr__conf {
  display: flex;
  gap: 8px;
  font-size: 11.5px;
  color: var(--fg-1);
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-sm);
  padding: 6px 10px;
}
.sr__confTag {
  color: var(--violet);
  font-size: 10px;
}
.sr {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.sr__col {
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  padding: 7px 10px;
  background: rgba(11, 18, 32, 0.5);
}
.sr__col--notdone {
  border-color: rgba(255, 190, 90, 0.4);
}
.sr__group {
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  padding: 7px 10px;
  background: rgba(11, 18, 32, 0.5);
}
.sr__head {
  font-size: 10px;
  letter-spacing: 0.08em;
  color: var(--violet);
  margin-bottom: 4px;
}
.sr__col ul,
.sr__group ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.sr__col li,
.sr__group li {
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--fg-1);
  border-left: 2px solid var(--line-strong);
  padding-left: 7px;
  word-break: break-word;
}
.sr__none {
  font-size: 11px;
  color: var(--fg-2);
}
.fc {
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  padding: 6px 10px;
  background: rgba(11, 18, 32, 0.5);
}
.fc__sum {
  font-size: 11px;
  color: var(--fg-2);
  cursor: pointer;
}
.fc__list {
  list-style: none;
  margin: 6px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.fc__list li {
  font-size: 11px;
  line-height: 1.55;
  color: var(--fg-1);
  word-break: break-word;
}
.sr__src {
  margin: 0;
  font-size: 10.5px;
  color: var(--fg-2);
  line-height: 1.6;
}

/* ---------------- P4：拆解合规审查 ---------------- */
.dr {
  border: 1px solid var(--line);
  border-left-width: 3px;
  border-radius: var(--radius-sm);
  padding: 7px 10px;
  background: rgba(11, 18, 32, 0.55);
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.dr--ok {
  border-left-color: var(--green);
}
.dr--bad {
  border-left-color: var(--red);
}
.dr--unknown {
  border-left-color: var(--amber);
}
.dr__head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.dr__warn {
  font-size: 10.5px;
  color: var(--amber);
}
.dr__sum {
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--fg-1);
}

/* ★ 两块分开：violated 用红、undecidable 用琥珀 —— 颜色与措辞都不许混 */
.dr__block {
  border-radius: var(--radius-sm);
  padding: 7px 10px;
}
.dr__block--violated {
  border: 1px solid rgba(255, 107, 129, 0.5);
  background: rgba(255, 107, 129, 0.1);
}
.dr__block--undecidable {
  border: 1px dashed rgba(255, 190, 90, 0.55);
  background: rgba(255, 190, 90, 0.08);
}
.dr__blockHead {
  font-size: 11.5px;
  font-weight: 600;
  margin-bottom: 4px;
}
.dr__block--violated .dr__blockHead {
  color: var(--red);
}
.dr__block--undecidable .dr__blockHead {
  color: var(--amber);
}
.dr__block ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.dr__block li {
  font-size: 11px;
  line-height: 1.6;
  color: var(--fg-1);
  border-left: 2px solid currentColor;
  padding-left: 7px;
  word-break: break-word;
}

.dr__list {
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  padding: 7px 10px;
  background: rgba(11, 18, 32, 0.5);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.dr__listHead {
  font-size: 10px;
  letter-spacing: 0.08em;
  color: var(--violet);
}
.dr__row {
  display: flex;
  align-items: baseline;
  gap: 6px;
  flex-wrap: wrap;
  font-size: 11px;
  border-left: 2px solid var(--line-strong);
  padding-left: 7px;
}
.dr__row--violated {
  border-left-color: var(--red);
}
.dr__row--undecidable {
  border-left-color: var(--amber);
}
.dr__row--ok {
  border-left-color: var(--green);
}
.dr__pid {
  color: var(--fg-2);
  font-size: 10px;
}
.dr__ev {
  flex: 1 1 100%;
  color: var(--fg-2);
  font-size: 10.5px;
  line-height: 1.55;
  word-break: break-word;
}
</style>
