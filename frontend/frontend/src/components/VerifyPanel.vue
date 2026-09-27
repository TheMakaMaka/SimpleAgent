<script setup lang="ts">
/** 门禁面板：MANIFEST / CHECK / VERIFY 三个「由程序判定」的结果。 */
import type { RunState } from '@/types'
import { computed } from 'vue'

const props = defineProps<{ state: RunState }>()

const checks = computed(() => props.state.checks)
const manifest = computed(() => props.state.manifest)
const verify = computed(() => props.state.verify)
/** 被跳过的验证（`verify_skipped`）—— 既非通过也非失败，必须单独显示 */
const skipped = computed(() => props.state.verifySkipped ?? [])

const syntaxOk = computed(() => checks.value.filter((c) => c.tool === 'syntax' && c.status === 'passed').length)
const syntaxBad = computed(() => checks.value.filter((c) => c.tool === 'syntax' && c.status === 'failed').length)
const lintSkipped = computed(() => checks.value.filter((c) => c.tool === 'lint' && c.status === 'skipped').length)
const lintIssues = computed(() =>
  checks.value.filter((c) => c.tool === 'lint' && c.status === 'failed').length,
)
</script>

<template>
  <section class="gate card">
    <div class="card__head">
      <h2 class="card__title">门禁结果</h2>
      <span class="spacer" />
      <span class="pill tiny muted">程序判定 · 模型绕不过</span>
    </div>

    <div class="card__body gate__body">
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
</style>
