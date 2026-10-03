/**
 * 用**真实样例事件流**跑一遍**真实归约器**，把「界面应该显示什么」机械地打出来。
 *
 * 为什么要有这个脚本
 * ------------------
 * 这一轮的验收是「打开界面看四条」。而在此之前，本仓库对前端的机械验证只有
 * `vue-tsc`（类型）与 `vite build`（能构建）—— 它们**都不执行归约器**，
 * 也**不渲染任何组件**。于是「面板上到底会不会出现那行字」只能靠人点，
 * 改动归约器后也无法立刻知道「我是不是把某条读数弄丢了」。
 *
 * 四段，全部用**生产代码本身**：
 *
 *   [B4][A2][A3][C3][D3]  固定样例 `run_20260927_125647_5a3297` → 真实归约器 → 读数断言
 *   [E]                   按**契约字段**造的合成事件 → 新事件（A1/B1/C1）的读取
 *   [F]                   `tests/fixtures/transparency-fixture.json`（**后端自己的
 *                         `fact_check()` 产出**）→ 自述 + 矛盾
 *   [R]                   vite SSR 构建 + `vue/server-renderer` → 断言那几行字**真在 HTML 里**
 *
 * 用法（在 frontend/ 下）:
 *     node scripts/replay-check.mjs                    # 打印读数
 *     node scripts/replay-check.mjs --assert           # 打印并断言，失败退出码 1
 *     node scripts/replay-check.mjs --sample <目录>     # 换一条运行
 *
 * 注意：它**不是**替代人眼验收。验收标准是"不用翻原始 JSON 就能看懂"，
 * 那件事只能由人打开界面确认；这里证明的是"归约器给出的读数是对的、
 * 那几行字确实渲染出来了"。
 */
import { build } from 'esbuild'
import { build as viteBuild } from 'vite'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { dirname, resolve } from 'node:path'
import { readFileSync, mkdirSync, rmSync, writeFileSync, readdirSync, existsSync } from 'node:fs'

const HERE = dirname(fileURLToPath(import.meta.url))
const ROOT = resolve(HERE, '..')            // frontend/
const REPO = resolve(ROOT, '..')            // 仓库根
const DEFAULT_SAMPLE = 'data/storage_data/runs/run_20260927_125647_5a3297'
const FIXTURE = resolve(REPO, 'tests/fixtures/transparency-fixture.json')

const argv = process.argv.slice(2)
const ASSERT = argv.includes('--assert')
const sampleArg = argv.indexOf('--sample')
const SAMPLE = resolve(REPO, sampleArg >= 0 ? argv[sampleArg + 1] : DEFAULT_SAMPLE)

/* ------------------------------------------------------------------ */
/* 1. 就地打包归约器（不复制逻辑）                                      */
/* ------------------------------------------------------------------ */
async function loadReducer() {
  // ★ 产物必须落在 `frontend/` **里面**（node_modules/.cache 下）：
  //   它 import 了 `vue`，而 `vue` 只在 frontend/node_modules 里解析得到。
  //   放到系统临时目录会 ERR_MODULE_NOT_FOUND。
  const outdir = resolve(ROOT, 'node_modules/.cache/dsh-replay')
  mkdirSync(outdir, { recursive: true })
  const bundle = async (entry, name) => {
    const outfile = resolve(outdir, name)
    await build({
      entryPoints: [resolve(ROOT, entry)],
      outfile,
      bundle: true,
      format: 'esm',
      platform: 'node',
      external: ['vue'],
      alias: { '@': resolve(ROOT, 'src') },
      // config.ts 读 `import.meta.env`；node 里没有，给个空对象（走内置默认值）
      define: { 'import.meta.env': '{}' },
      logLevel: 'silent',
    })
    return await import(pathToFileURL(outfile).href)
  }
  // 归约器（含透明化采集器）
  const reducer = await bundle('src/store/run.ts', 'reducer.mjs')
  // 任务面板的纯逻辑（`taskRows` / 跟随决策）—— 单独打一份，别为了它去改 run.ts 的依赖
  const tasklist = await bundle('src/store/tasklist.ts', 'tasklist.mjs')
  return { ...reducer, tasklist }
}

function loadEvents(dir) {
  const raw = readFileSync(resolve(dir, 'events.jsonl'), 'utf8')
  return raw.split('\n').map((l) => l.trim()).filter(Boolean).map((l) => JSON.parse(l))
}

const checks = []
function check(name, ok, detail = '') {
  checks.push([name, !!ok])
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `   ${detail}` : ''}`)
}
const line = (t = '') => console.log(t)
function head(t) {
  line()
  line('='.repeat(74))
  line(t)
  line('='.repeat(74))
}

const { createInitialState, applyEvent, tasklist, useRunStore } = await loadReducer()
const events = loadEvents(SAMPLE)
const raw = new Map(events.map((e) => [Number(e.seq), e]))

/** 回放路径与界面一致：`attach()` 用 `tsToMs(ev.ts)` 作为事件在界面上的时间点 */
function replay(evs) {
  const s = createInitialState()
  for (const ev of evs) {
    const at = Date.parse(ev.ts)
    applyEvent(s, ev, Number.isFinite(at) ? at : 0)
  }
  return s
}

const state = replay(events)

/* ------------------------------------------------------------------ */
/* P2/P3/P4 的输入**先加载好**                                          */
/* ------------------------------------------------------------------ */
// 为什么放在这里：JS 的 `let`/`const` 有 TDZ —— 后面的段落（含 SSR 断言）要用
// `bigState` / `fx`，而后面的段落里再声明就会"用到还没初始化的变量"。
// 这类错只有真的跑到那一行才炸，所以宁可提前声明。
const BIG_RUNS = ['run_20260927_230240_0a42df', 'run_20260927_225939_f4daaa']
let bigState = null
let bigName = ''
for (const rid of BIG_RUNS) {
  const dir = resolve(REPO, 'data/storage_data/runs', rid)
  if (!existsSync(dir)) continue
  const st = replay(loadEvents(dir))
  if (!bigState || st.tasks.length > bigState.tasks.length) {
    bigState = st
    bigName = rid
  }
}
/** P3/P4 夹具（后端自己的函数产出，见 tests/diagnostics/make_transparency_fixture.py） */
const fx = existsSync(FIXTURE) ? JSON.parse(readFileSync(FIXTURE, 'utf8')) : null

head(`样例：${SAMPLE}`)
line(`事件 ${events.length} 条 · 状态 ${state.status} · 轮次 ${state.rounds}`)
line('（下列读数全部来自 frontend/src/store/run.ts 的**实际派生结果**，不是本文重算）')

/* ============================ B4 判据演化 ============================ */
head('B4 验收判据演化（按 seq 原序，不重写因果）')
const crit = state.criteria ?? []
line(`共 ${crit.length} 条候选/采纳记录，seq 顺序 = ${crit.map((c) => c.seq).join(' → ')}`)
const badgeOf = { passed: '通过', failed: '未通过', rejected: '候选被拒', unknown: '结果未知' }
for (const c of crit) {
  line(`  seq=${String(c.seq).padStart(3)} [${badgeOf[c.outcome] ?? c.outcome}][${c.action}]` +
    `${c.adopted ? '[最终被记录]' : ''} ${c.command ? c.command.split('\n')[0] : '（命令未单独记录）'}`)
  if (c.previousPassed === false || c.previousCommand) {
    line(`        ⚠ 后端显式前因：上一条=${JSON.stringify((c.previousCommand || '').split('\n')[0])} passed=${c.previousPassed}`)
  } else if (c.afterFailure) {
    line(`        ⚠ 上一条判据执行失败了（seq=${c.afterFailure.seq}）→ 本条紧随其后（按序号相邻推断）`)
  }
  if (c.reason) line(`        理由：${c.reason.replace(/\s+/g, ' ').slice(0, 110)}…`)
}
const failIdx = crit.findIndex((c) => c.outcome === 'failed')
const failed = failIdx >= 0 ? crit[failIdx] : null
const nextAfterFail = failIdx >= 0 ? crit[failIdx + 1] : null
check('(b) 存在"执行且失败"的判据', !!failed, `seq=${failed?.seq}`)
check(
  '★ (b) 失败之后的下一条带"上一条失败了"标记，且指向 (b) 的 seq',
  !!nextAfterFail?.afterFailure && nextAfterFail.afterFailure.seq === failed?.seq,
  `seq=${nextAfterFail?.seq} 指向 seq=${nextAfterFail?.afterFailure?.seq}`,
)
check(
  '★ (c) 该条已执行且通过，命令是 `assert generate_obstacles`',
  nextAfterFail?.outcome === 'passed' && /assert\s+generate_obstacles/.test(nextAfterFail?.command ?? ''),
  JSON.stringify((nextAfterFail?.command ?? '').split('\n')[1] ?? ''),
)
check('被拒候选带理由（B2 要的"必须给理由"这一半）',
  crit.some((c) => c.outcome === 'rejected' && c.reason.length > 0))
check('被拒候选的命令**没有**单独记录 → 界面必须如实说，而不是编一个命令',
  crit.filter((c) => c.outcome === 'rejected').every((c) => c.command === ''))
check('最终被记录的那条被标出（adopted）', crit.some((c) => c.adopted))
check('顺序未被重排：记录的 seq 严格递增', crit.every((c, i) => i === 0 || c.seq > crit[i - 1].seq))
check('老事件流没有后端显式前因（所以必须靠 seq 相邻推断 + 标明来源）',
  crit.every((c) => c.previousPassed === null && c.previousCommand === ''))

/* ============================ A2 决策依据 ============================ */
head('A2 决策依据（编排器每轮的 reasoning + 这一轮打算做什么）')
const rounds = state.decisionRounds ?? []
for (const r of rounds) {
  line(`  第 ${r.round} 轮 · status=${r.status} · 声明 ${r.taskCount} 个任务 · 打算做什么来源=${r.intentSource}`)
  line(`    reasoning: ${r.reasoning || '（空）'}`)
  if (r.intentSource === 'field') line(`    intent   : ${r.intent}`)
  else if (r.intentSource === 'tasks') line('    intent   : 来自 orchestrator_round.tasks（后端声明）')
  else line('    intent   : 后端未提供 intent 字段，也没有 orchestrator_round.tasks')
  for (const p of r.planned) {
    line(`    打算做   : [${p.source === 'declared' ? '声明' : '已派发'}] ${p.id} ${p.description}` +
      `${p.expectedOutput ? ` → ${p.expectedOutput}` : ''}` +
      `${p.toolHint.length ? ` [${p.toolHint.join(',')}]` : ''}${p.ok === null ? '' : p.ok ? ' → 完成' : ' → 失败'}`)
  }
  if (!r.planned.length) line('    打算做   : （本轮没有任何任务记录）')
}
check('每一轮都有非空 reasoning', rounds.length > 0 && rounds.every((r) => r.reasoning.trim().length > 0), `${rounds.length} 轮`)
check(
  '★ 有一轮的 reasoning 解释了"为什么又去改 obstacle_generator.py"，且本轮确实派了这件事',
  rounds.some((r) => /generate_obstacles/.test(r.reasoning) &&
    r.planned.some((p) => /generate_obstacles/.test(p.description))),
)
check(
  '`intent` 的来源如实标注（本样例没有生产者发 intent 字段 → none）',
  rounds.every((r) => r.intentSource === 'none'),
  rounds.map((r) => r.intentSource).join(','),
)
check('"打算做什么"有实测替代物（本轮派发的任务，标为已派发）',
  rounds.some((r) => r.planned.some((p) => p.source === 'dispatched')))

/* ============================ A3 模型回合原话 ============================ */
head('A3 模型回合原话（task/step → 模型说了什么 → 调了什么工具 → 结果）')
const turns = state.modelTurns ?? []
for (const t of turns) {
  const said = t.content
    ? `原话：${t.content.replace(/\s+/g, ' ')}`
    : t.calls.length
      ? '（本轮无文字，直接调用工具）'
      : '（本轮既无文字、也无工具调用）'
  line(`  ${t.taskId} 第 ${t.step} 步 · ${said}`)
  for (const c of t.calls) {
    line(`      工具 ${c.tool}：${c.summary}  →  ${c.status}${c.preview ? `  ${c.preview.replace(/\s+/g, ' ').slice(0, 56)}` : ''}`)
  }
}
const said = (id) => turns.filter((t) => t.taskId === id && t.content.trim().length > 0).map((t) => t.content.trim())
check('★ t2 有模型原话', said('t2').length > 0, JSON.stringify(said('t2')[0] ?? ''))
check('★ t3 有模型原话', said('t3').length > 0, JSON.stringify(said('t3')[0] ?? ''))
check('★ 回合与工具调用并成一条链（t1 第 1 步 = 说 → write_file → 结果）',
  turns.some((t) => t.taskId === 't1' && t.step === 1 &&
    t.calls.some((c) => c.tool === 'write_file' && c.status === 'ok')))
check('★ "什么都没干"的空回合被保留下来（不能与"只调工具"混成一句）',
  turns.some((t) => !t.content && !t.calls.length),
  `例如 ${turns.find((t) => !t.content && !t.calls.length)?.taskId} 第 ${turns.find((t) => !t.content && !t.calls.length)?.step} 步`)
check('工具参数摘要用的是**事件里声明的真值**（不是对预览串取 length）',
  turns.flatMap((t) => t.calls).filter((c) => c.tool === 'write_file')
    .some((c) => /（275 字符）/.test(c.summary)),
  JSON.stringify(turns.find((t) => t.taskId === 't1')?.calls[0]?.summary ?? ''))

/* ============================ C3 收尾自述（样例，没有） ============================ */
head('C3 收尾自述（固定样例里没有 —— 它早于后端 C1）')
line(`  selfReport            : ${state.selfReport ? '有' : 'null（无）'}`)
line(`  factCheck             : ${state.factCheck ? `${state.factCheck.contradictions.length} 处矛盾` : 'null（无）'}`)
line(`  selfReportAbsentReason: ${state.selfReportAbsentReason || '（空）'}`)
check('★ 没有自述时给出**可归因的缺席说明**（而不是空面板）',
  state.selfReport === null && state.selfReportAbsentReason.length > 0, state.selfReportAbsentReason)
check('★ 缺席说明点出"这是后端 C1 未交付"，而不是"模型没什么要说的"',
  /C1/.test(state.selfReportAbsentReason) && /不是"模型没什么要说的"/.test(state.selfReportAbsentReason))

/* ============================ D3 结局四值 + 判据来源 ============================ */
head('D3 结局四值 + 判据来源')
const o = state.outcome
line(`  outcome=${o.value}  raw=${o.raw}  旧词表=${o.legacyVocabulary}  判据来源=${o.source || '（未知）'}`)
line('  四值标签：pass / fail / abstain（模型声明做不到） / invalid（任务或工装有问题）')
check('结局取自 run_end', ['pass', 'fail', 'abstain', 'invalid', 'unknown'].includes(o.value), o.value)
check('★ 判据来源 = model（该样例是模型自拟判据，结论旁必须显示这个）', o.source === 'model', o.source)
check('★ 旧词表被标出（四值尚未交付，不能读成"这次不是 abstain/invalid"）',
  o.legacyVocabulary && o.raw === 'passed')

/* ============================ E. 新事件（合成，按契约字段） ============================ */
head('E 新事件按**契约字段**读取（合成事件流，不是样例）')
line('  字段取自上游 core/contract.py 的 EventSpec：')
line('    orchestrator_round → round/status/reasoning/tasks/final_answer')
line('    verify_criterion   → action/command/reason/passed/detail/source/previous_command/previous_passed')
line('    self_report        → ok/phase/done/not_done/why/reflections/approach/confidence/open_questions/fact_check')

let seq = 1000
const mk = (kind, payload) => ({ seq: seq++, ts: '2026-09-27T13:00:00', kind, run_id: 'synthetic', ...payload })
const synthetic = [
  mk('round_start', { round: 1 }),
  mk('orchestrator_round', {
    round: 1,
    status: 'continue',
    reasoning: '先设计障碍物生成规则',
    tasks: [{ id: 't1', description: '实现 generate_obstacles', expected_output: 'obstacle_generator.py' }],
    final_answer: '',
  }),
  mk('verify_criterion', {
    action: 'executed', command: 'python -c "import obstacle_generator"', passed: false,
    detail: '连通性未验证', source: 'model',
  }),
  mk('verify_criterion', {
    action: 'rejected', command: 'assert generate_obstacles',
    reason: '这条判据只证明函数名能导入，恒真', passed: null, source: 'model',
    previous_command: 'python -c "import obstacle_generator"', previous_passed: false,
  }),
  mk('verify_criterion', {
    action: 'executed', command: 'python -c "import obstacle_generator"', passed: true,
    detail: '重新跑通', source: 'model',
  }),
  mk('verify_criterion', {
    action: 'adopted', command: 'python -c "import obstacle_generator"', passed: true,
    detail: '采纳为交付判据', source: 'model',
  }),
]
const st = replay([...events, ...synthetic])
const sc = st.criteria.filter((c) => c.seq >= 1000)
for (const c of sc) {
  line(`  seq=${c.seq} [${badgeOf[c.outcome] ?? c.outcome}][${c.action}]${c.adopted ? '[最终被记录]' : ''} ` +
    `${c.command}`)
  if (c.previousPassed === false || c.previousCommand) {
    line(`        ⚠ 后端显式前因：previous_command=${JSON.stringify(c.previousCommand)} previous_passed=${c.previousPassed}`)
  }
}
check('★ action=executed + passed=false → outcome=failed', sc[0]?.outcome === 'failed' && sc[0]?.action === 'executed')
check('★ action=rejected → outcome=rejected（**没被执行**，与 failed 分开）',
  sc[1]?.outcome === 'rejected' && sc[1]?.action === 'rejected')
check('★ 后端显式前因被读成"后端说的"（previous_command + previous_passed=false）',
  sc[1]?.previousCommand === 'python -c "import obstacle_generator"' && sc[1]?.previousPassed === false)
check('★ 后端给的理由被读出来（B2 的"必须给理由"）', /恒真/.test(sc[1]?.reason ?? ''))
check('★ action=adopted → adopted=true + outcome=passed（三根轴各自独立）',
  sc[3]?.adopted === true && sc[3]?.outcome === 'passed' && sc[3]?.action === 'adopted')

const sr1 = st.decisionRounds.find((r) => r.round === 1)
check('★ orchestrator_round.tasks → "打算做什么"来源标为 tasks（后端声明）', sr1?.intentSource === 'tasks')
check('★ 声明的任务标为 declared（不冒充"已派发"）', sr1?.planned[0]?.source === 'declared' &&
  sr1?.planned[0]?.expectedOutput === 'obstacle_generator.py')

/* ============================ F. C3 夹具（后端 fact_check 产出） ============================ */
head('F C3 夹具（自述是夹具文本，fact_check 由**后端自己的代码**产出）')
let fixtureStates = null
if (!existsSync(FIXTURE)) {
  line(`  （没有 ${FIXTURE}）`)
  line('  SKIP  先跑：AGENT_UPSTREAM_DIR=<SimpleAgent2_Cycle> python tests/diagnostics/make_transparency_fixture.py')
} else {
  const fx = JSON.parse(readFileSync(FIXTURE, 'utf8'))
  line(`  夹具来源：${fx._generator}`)
  line(`  上游：${fx._upstream}`)
  fixtureStates = {}
  for (const [label, key] of [['诚实版', 'self_report_honest'], ['谎报版', 'self_report_lying']]) {
    const sr = fx[key]
    const withReport = replay([...events, mk('self_report', sr)])
    fixtureStates[key] = withReport
    const fc = withReport.factCheck
    line(`  [${label}] not_done=${withReport.selfReport.notDone.length} ` +
      `矛盾=${fc ? fc.contradictions.length : 0}`)
    for (const x of withReport.selfReport.notDone) line(`        not_done: ${x}`)
    for (const c of fc?.contradictions ?? []) line(`        ✗ ${c.kind}: ${c.claim} ⇔ ${c.fact.slice(0, 80)}`)
  }
  const honest = fixtureStates.self_report_honest
  const lying = fixtureStates.self_report_lying
  const nd = honest.selfReport.notDone.join(' ')
  check('★ 验收 4 前半：not_done 含「跑测试」', /跑测试/.test(nd))
  check('★ 验收 4 前半：not_done 含「生成报告」', /生成报告/.test(nd))
  check('★ 诚实版没有矛盾（自述与机械事实一致）', (honest.factCheck?.contradictions.length ?? 0) === 0)
  check('★ 验收 4 后半：谎报版被标出矛盾（后端 fact_check 判的）',
    (lying.factCheck?.contradictions.length ?? 0) > 0,
    (lying.factCheck?.contradictions ?? []).map((c) => c.kind).join(','))
  check('★ 矛盾类型是后端定义的那几种之一',
    (lying.factCheck?.contradictions ?? []).every((c) =>
      ['artifact-missing', 'verify-claim-vs-fact', 'check-claim-vs-fact',
        'lint-failed-not-disclosed', 'requirement-evidence-missing',
        'done-mentions-missing-file'].includes(c.kind)),
    (lying.factCheck?.contradictions ?? []).map((c) => c.kind).join(','))
}

/* ============================ R. 真渲染（SSR） ============================ */
const RENDER_ENTRY = `
import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import TransparencyPanel from '@/components/TransparencyPanel.vue'
import VerifyPanel from '@/components/VerifyPanel.vue'
import TaskPanel from '@/components/TaskPanel.vue'
export async function render(state, initialTab) {
  const app = createSSRApp({ render: () => h(TransparencyPanel, { state, initialTab }) })
  return await renderToString(app)
}
export async function renderVerify(state) {
  const app = createSSRApp({ render: () => h(VerifyPanel, { state }) })
  return await renderToString(app)
}
export async function renderTasks(state) {
  const app = createSSRApp({ render: () => h(TaskPanel, { state }) })
  return await renderToString(app)
}
`

async function loadRenderers() {
  const dir = resolve(ROOT, 'node_modules/.cache/dsh-render')
  mkdirSync(dir, { recursive: true })
  const entry = resolve(dir, 'render-entry.ts')
  writeFileSync(entry, RENDER_ENTRY, 'utf8')
  const outDir = resolve(dir, 'out')
  await viteBuild({
    root: ROOT,
    configFile: resolve(ROOT, 'vite.config.ts'),
    logLevel: 'silent',
    build: { ssr: entry, outDir, emptyOutDir: true, minify: false, copyPublicDir: false },
  })
  const produced = readdirSync(outDir).find((f) => f.endsWith('.mjs') || f.endsWith('.js'))
  return await import(pathToFileURL(resolve(outDir, produced)).href)
}

/** 粗略地把 HTML 变成可读文本（只为打印，不做断言） */
const htmlToText = (html) =>
  html.replace(/<!--[^]*?-->/g, '').replace(/<[^>]+>/g, ' ')
    .replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&')
    .replace(/[ \t]+/g, ' ').trim()

head('R 面板真的渲染出来了吗（vite SSR 构建 + vue/server-renderer）')
let r = null
const TAB_TEXTS = {}
try {
  r = await loadRenderers()
  for (const t of ['criteria', 'decisions', 'turns', 'report']) {
    const html = await r.render(state, t)
    TAB_TEXTS[t] = { html, text: htmlToText(html) }
    line(`  [透明化·${t}] ${html.length} 字节 HTML / ${TAB_TEXTS[t].text.length} 字文本`)
  }
  const vHtml = await r.renderVerify(state)
  TAB_TEXTS.verify = { html: vHtml, text: htmlToText(vHtml) }
  line(`  [门禁 VERIFY] ${vHtml.length} 字节 HTML / ${TAB_TEXTS.verify.text.length} 字文本`)
  check('SSR 渲染成功（透明化四 tab + 门禁面板）', Object.keys(TAB_TEXTS).length === 5)
} catch (e) {
  check('SSR 渲染成功（透明化四 tab + 门禁面板）', false,
    String(e && e.message ? e.message : e).slice(0, 200))
}

if (Object.keys(TAB_TEXTS).length) {
  const T = (t) => TAB_TEXTS[t].html + '\n' + TAB_TEXTS[t].text
  const must = [
    // ★ 验收 1：判据 (b) 失败 → (c) 通过，且标出"上一条失败了"（判据 tab）
    ['[判据] 「上一条判据执行失败了」在 HTML 里', 'criteria', /上一条判据执行失败了/],
    ['[判据] 该标记指向 seq 35', 'criteria', /seq 35/],
    ['[判据] (b) 被标出"未通过"', 'criteria', /未通过/],
    ['[判据] (c) 的命令原文可见（assert generate_obstacles）', 'criteria', /assert generate_obstacles/],
    ['[判据] 推断来源被标明（"按事件序号相邻推断"）', 'criteria', /按事件序号相邻推断/],
    ['[判据] 最终被记录的那条被标出', 'criteria', /最终被记录/],
    ['[判据] 被拒候选被标出"候选被拒"', 'criteria', /候选被拒/],
    ['[判据] 被拒命令未单独记录时如实说明', 'criteria', /该事件未单独记录命令/],
    ['[判据] 判据来源显示"模型"', 'criteria', /判据来自[\s\S]{0,60}模型/],
    // ★ 验收 2：编排器每轮 reasoning（决策 tab）
    ['[决策] 第 3 轮 reasoning 可见（为什么又去改 obstacle_generator.py）', 'decisions', /需要修复 generate_obstacles 函数的参数问题/],
    ['[决策] 第 1、2 轮 reasoning 也在', 'decisions', /首先需要设计障碍物生成规则/],
    ['[决策] 明确写出"后端未提供 intent 字段"', 'decisions', /后端未提供 `intent` 字段/],
    ['[决策] "这一轮打算做什么"（实测替代物）可见', 'decisions', /修改 generate_obstacles 函数/],
    // ★ 验收 3：模型回合原话（回合 tab）
    ['[回合] t2 原话可见', 'turns', /已生成 `ant_colony\.py` 文件/],
    ['[回合] t3 原话可见', 'turns', /总结：已生成 test_ant_colony\.py 文件/],
    ['[回合] 工具调用与结果并排可见', 'turns', /write_file[\s\S]{0,120}返回/],
    // ★ 验收 4 / D3
    ['[自述] 样例里「本次运行没有收尾自述」在 HTML 里', 'report', /本次运行没有收尾自述/],
    ['[自述] 缺席说明点出"后端 C1 未交付"', 'report', /后端 C1/],
    ['[标题栏] 结论 + 判据来源常驻', 'report', /结论[\s\S]{0,80}判据来源[\s\S]{0,40}模型/],
    ['[标题栏] 旧词表被标出（四值尚未交付）', 'report', /旧词表/],
    ['[门禁] 结论格上有四值结局', 'verify', /结论[\s\S]{0,120}>pass</],
    ['[门禁] 结论格旁显示"判据来自 模型自拟"', 'verify', /判据来自[\s\S]{0,20}模型自拟/],
    // ★ 事实变了，这句话也跟着变：四值**已经存在**（上游 `core/outcome.py:26` `OUTCOMES`），
    //   缺的是**这次运行没有产出**。所以现在要求的说明是"未产出"，而不是"没有四值这个词表"。
    ['[门禁] 后端未产出四值时如实说明（不是硬套一个）', 'verify', /后端[\s\S]{0,40}没有产出[\s\S]{0,40}结局四值/],
    ['[门禁] 未产出时**不显示**一个编出来的四值', 'verify', /未产出/],
  ]
  for (const [name, tabId, re] of must) check(name, re.test(T(tabId)))

  // ---- 新事件形状也走一遍真渲染 ----
  if (r) {
    const h = await r.render(st, 'criteria')
    check('★ [渲染] 后端显式前因在 HTML 里（"后端显式"，与推断区分开）',
      /后端显式/.test(h) && /previous_passed/.test(h))
    check('★ [渲染] 被拒判据标为"候选被拒"且带理由', /候选被拒/.test(h) && /恒真/.test(h))
    const hd = await r.render(st, 'decisions')
    check('★ [渲染] orchestrator_round 的声明任务标为"声明"', /声明/.test(hd) && /obstacle_generator\.py/.test(hd))
  }

  // ---- C3 夹具也走一遍真渲染：矛盾必须在最显眼处（自述 tab 的第一块） ----
  if (fixtureStates && r) {
    const honestHtml = await r.render(fixtureStates.self_report_honest, 'report')
    const lyingHtml = await r.render(fixtureStates.self_report_lying, 'report')
    check('★ [渲染] 诚实版：not_done 的两项在 HTML 里',
      /没有跑测试/.test(honestHtml) && /没有生成报告/.test(honestHtml))
    check('★ [渲染] 谎报版：矛盾横幅出现在 HTML 里',
      /自述与机械事实[\s\S]{0,20}矛盾[\s\S]{0,40}2/.test(lyingHtml) || /矛盾/.test(lyingHtml))
    check('★ [渲染] 谎报版：矛盾的"模型说 / 机械事实"两栏都在',
      /模型说/.test(lyingHtml) && /机械事实/.test(lyingHtml))
    check('★ [渲染] 谎报版：report.md 这个不存在的文件被点名', /report\.md/.test(lyingHtml))
    check('★ [渲染] 谎报版：矛盾块排在 done/not_done 之前（最显眼处）',
      lyingHtml.indexOf('矛盾') < lyingHtml.indexOf('done · 做了什么'))
  }
}

/* ---------------- P2：任务面板（真实 19 个任务）SSR ---------------- */
if (bigState && r && r.renderTasks) {
  const h = await r.renderTasks(bigState)
  const text = htmlToText(h)
  line()
  line(`  [任务面板·${bigName}] ${h.length} 字节 HTML / ${text.length} 字文本`)
  const tasksRev = [...bigState.tasks].reverse()
  const failedTasks = tasksRev.filter((t) => t.status === 'failed')
  const currentTask = tasksRev.find((t) => t.id === bigState.currentTaskId)
  check('★ [渲染] 折叠行在 HTML 里，并**写明数量**（收起要说出来）',
    /已完成 \d+ 项/.test(text), (text.match(/已完成 \d+ 项/) ?? [''])[0])
  check('★ [渲染] 当前项的描述在 HTML 里（当前项永远可见）',
    !!currentTask && text.includes(currentTask.description.slice(0, 18)),
    `${bigState.currentTaskId}: ${(currentTask?.description ?? '').slice(0, 24)}`)
  check('★ [渲染] 所有失败项的描述都在 HTML 里（一条都不许藏）',
    failedTasks.every((t) => text.includes(t.description.slice(0, 18))),
    `failed=${failedTasks.length}`)
  check('★ [渲染] 面板说明"折叠的只是已完成"（不许让人以为项丢了）',
    /折叠的只是/.test(text) && /永远在上面/.test(text))
  check('★ [渲染] 顶部有"跟随中/跟随当前项"（跟随状态可见且可逆）',
    /跟随中|跟随当前项/.test(text))
  // CSS 契约（规则 1、2）——「能不能真的滚」要真浏览器，这里断言**样式契约存在**
  const panelSrc = readFileSync(resolve(ROOT, 'src/components/TaskPanel.vue'), 'utf8')
  check('★ [样式] 不压缩：`.task { flex: 0 0 auto }`', /\.task \{[^}]*flex: 0 0 auto/.test(panelSrc))
  check('★ [样式] 内部滚动：`.tasks__body { overflow-y: auto }`',
    /\.tasks__body \{[^}]*overflow-y: auto/.test(panelSrc))
  check('★ [样式] 面板有界高（`max-height: 44vh`）', /\.tasks \{[^}]*max-height: 44vh/.test(panelSrc))
  check('★ [样式] 当前项有视觉锚点（`.task--current`）', /\.task--current/.test(panelSrc))
}

/* ---------------- P3：四种 verdict 各渲染一次（走**事件**那条路） ---------------- */
if (fx && fx.verdicts && r && r.renderVerify) {
  line()
  for (const [name, v] of Object.entries(fx.verdicts)) {
    const st = replay([...events, mk('run_end', {
      status: 'passed', outcome: v.outcome, outcome_kind: v.outcome_kind,
      outcome_reason: v.reason, criterion_source: v.criterion_source,
      criterion_trust: v.criterion_trust, criterion_independent: v.criterion_independent,
    })])
    const tv = htmlToText(await r.renderVerify(st))
    const okOut = tv.includes(String(v.outcome))
    const okSrc = v.criterion_source === 'model' ? /模型自拟/.test(tv)
      : v.criterion_source === 'caller' ? /调用方/.test(tv) : true
    const okIndep = v.criterion_independent === true ? /独立(?!\/)/.test(tv)
      : /非独立\/未启用/.test(tv)
    check(`★ [渲染·门禁] ${name}：${v.outcome} · 来源=${v.criterion_source || '空'} · 独立=${v.criterion_independent}`,
      okOut && okSrc && okIndep, `out=${okOut} src=${okSrc} indep=${okIndep}`)
  }
  // ★ "判不了"不等于"否"：后端没给 `criterion_independent` 时要显示「未给」
  const noIndep = replay([...events, mk('run_end', {
    status: 'passed', outcome: 'pass', outcome_kind: 'verified',
    outcome_reason: '通过', criterion_source: 'model', criterion_trust: 'model-self-authored',
  })])
  const hRaw = await r.renderVerify(noIndep)
  const ht = htmlToText(hRaw)
  // 负向只看**徽标**（`>非独立/未启用<`）：面板里有一句解释性文字会提到这个词，
  // 用整页文本去断言"没出现"会把那句解释也算上 —— 那是**断言写错**，不是实现错。
  check('★ [渲染·门禁] 后端**没给**独立性 → 徽标显示「未给（判不了）」，**不是**"非独立"',
    /未给（判不了）/.test(ht) && !/>非独立\/未启用</.test(hRaw))
}

/* ---------------- P4：拆解合规（走**报告**那条路 —— 事件还没发） ---------------- */
if (fx && fx.decompose_review && r && r.render) {
  const store = useRunStore()
  store.ingestReportInfo({ decompose_review: fx.decompose_review, reuse_checks: fx.reuse })
  const hd = await r.render(store.state, 'decompose')
  const td = htmlToText(hd)
  line()
  line(`  [拆解合规 tab] ${hd.length} 字节 HTML / ${td.length} 字文本`)
  check('★ [渲染] 「违反」与「判不了」分成两块（措辞不同、不混）',
    /违反（/.test(td) && /判不了（/.test(td))
  check('★ [渲染] 违反 5 条、判不了 2 条（照后端的数，不自算）',
    /违反 5/.test(td) || /违反[\s\S]{0,14}5 条/.test(td), (td.match(/违反[^，。]{0,14}/) ?? [''])[0])
  check('★ [渲染] `undecidable` 那块说清"既不是通过也不是违反"',
    /既不是通过也不是违反|审查范围不完整/.test(td))
  check('★ [渲染] **不出现**"全部通过"（`passed=false` 时更不许）', !/全部通过/.test(td))
  check('★ [渲染] 逐条原则里 P2/P5（判不了）与 P3/P7（违反）都在',
    /P2/.test(td) && /P5/.test(td) && /P3/.test(td) && /P7/.test(td))
  check('★ [渲染] `independent=false` 显示为"否/未启用"（不是"通过"）',
    /独立审查[\s\S]{0,30}否/.test(td))
  const empty = useRunStore()
  const he = htmlToText(await r.render(empty.state, 'decompose'))
  check('★ [渲染] 后端未产出时显示「尚未产出」而不是"审查通过"',
    /后端尚未产出拆解合规审查/.test(he) && !/全部通过/.test(he))
}

/* ---------------- 复用性检查（合成事件：后端已发，但那两次运行早于它） ---------------- */
if (r && r.renderVerify) {
  const stR = replay([...events, mk('reuse', {
    checked: true, passed: false,
    blocking: ['未定义的名字 `np`（用了 numpy 却写成 np）'],
    warnings: ['重复符号 AntColony'],
  })])
  const hr = htmlToText(await r.renderVerify(stR))
  check('★ [渲染] 复用性阻塞项在门禁面板里可见（它**有否决权**）',
    /复用性/.test(hr) && /必然崩/.test(hr) && /np/.test(hr))
}

/* ------------------------------------------------------------------ */
/* 载入 P2 用的"任务很多"那两次真实运行 + 载入 P3/P4 夹具                */
/* ------------------------------------------------------------------ */
if (bigState) {
  const { taskRows, hiddenTasks, visibleKeys, shouldAutoFollow, modeAfterScroll, taskKey } = tasklist

  head(`P2 任务面板：真实运行的 ${bigState.tasks.length} 个任务（${bigName}）`)
  const tasks = [...bigState.tasks].reverse()
  const done = tasks.filter((t) => t.status === 'done')
  const failed = tasks.filter((t) => t.status === 'failed')
  line(`  任务 ${tasks.length} 个 · 已完成 ${done.length} · 失败 ${failed.length} · 当前 ${bigState.currentTaskId}`)

  // ★ 与组件**同一套入参**：组件会把"当前项"的下标传进 `taskRows` 钉住它
  //   （跑完之后当前项也是 done，不钉就会被折进去 —— 那是实测踩到的坑）。
  const keepIndex = tasks.findIndex((t) => t.id === bigState.currentTaskId)
  const collapsed = taskRows(tasks, { expanded: false, keepIndex })
  const expandedRows = taskRows(tasks, { expanded: true, keepIndex })
  const group = collapsed.find((r) => r.kind === 'group')
  const shown = visibleKeys(collapsed)
  const hidden = hiddenTasks(tasks, collapsed)
  line(`  折叠视图：渲染 ${collapsed.length} 行（含折叠行）· 折叠 ${group ? group.count : 0} 项`)
  line(`  展开视图：渲染 ${expandedRows.length} 行`)

  check(`★ 任务确实很多（>10，足以复现用户说的"压缩"）`, tasks.length > 10, `${tasks.length}`)
  // 折叠数量 == 真正没被渲染的那些（= 任务数 − 可见任务数）。
  // ★ 不写成 `== done.length`：当前项即使是 done 也会被钉住**不折**（实测坑），
  //   所以它与"已完成数"可以差 1 —— 那个差值是有意的。
  check('★ 量大时出现折叠行，且数量 == 被藏起来的任务数',
    !!group && group.count === tasks.length - visibleKeys(collapsed).length,
    `group=${group ? group.count : 'none'} 藏=${tasks.length - visibleKeys(collapsed).length} done=${done.length}`)
  check('★ 折叠时**当前项永远可见**',
    visibleKeys(collapsed).some((k) => k.endsWith(`#${bigState.currentTaskId}`)),
    `current=${bigState.currentTaskId}`)
  const allKeys = tasks.map((t, i) => taskKey(i, t))
  const keyToTask = new Map(allKeys.map((k, i) => [k, tasks[i]]))
  check('★ 折叠时**失败项永远可见**（一条都不能藏）',
    failed.length === 0 || failed.every((f) => shown.some((k) => keyToTask.get(k) === f)),
    `failed=${failed.length}`)
  check('★ **藏起来的只能是已完成**（不许藏 running/failed）',
    hidden.every((t) => t.status === 'done'), `hidden=${hidden.length}`)
  check('★ 展开后一个都不少（不丢任务）',
    visibleKeys(expandedRows).length === tasks.length, `${visibleKeys(expandedRows).length}/${tasks.length}`)
  check('★ key 唯一（任务 id 会重复：实测同一轮里 t9 出现过两次）',
    new Set(visibleKeys(expandedRows)).size === tasks.length,
    `${new Set(visibleKeys(expandedRows)).size}/${tasks.length}`)

  // ---- 跟随决策（纯函数）：这是"要不要抢用户的滚动"的全部逻辑 ----
  check('★ 跟随模式下会跟随', shouldAutoFollow('follow') === true)
  check('★ 手动滚过之后**不抢**', shouldAutoFollow('manual') === false)
  check('★ 程序自己滚动**不改变**模式（否则跟随会把自己关掉）',
    modeAfterScroll('follow', 'program', false) === 'follow')
  check('★ 用户滚走 → manual；滚回当前项 → 恢复 follow',
    modeAfterScroll('follow', 'user', false) === 'manual'
    && modeAfterScroll('manual', 'user', true) === 'follow')
}

/* ------------------------------------------------------------------ */
/* P3 / P4：用**后端自己的函数**产出的夹具（不是手写样例）              */
/* ------------------------------------------------------------------ */

head('P3 结局四值 + 判据来源 + 审查独立性（verdict 由后端 build_verdict 产出）')
if (!fx || !fx.verdicts) {
  line('  SKIP  夹具里没有 verdicts（先跑 make_transparency_fixture.py）')
} else {
  for (const [name, v] of Object.entries(fx.verdicts)) {
    line(`  ${name}: outcome=${v.outcome} source=${v.criterion_source || '（空）'} ` +
      `trust=${v.criterion_trust} independent=${v.criterion_independent} kind=${v.outcome_kind}`)
  }
  const want = ['pass', 'fail', 'abstain', 'invalid']
  const got = Object.values(fx.verdicts).map((v) => v.outcome)
  check('★ 四值**都**由后端产出过（pass/fail/abstain/invalid）',
    want.every((w) => got.includes(w)), got.join(','))
  check('★ 模型自拟判据的通过带 `model-self-authored` 且 `criterion_independent=false`',
    Object.values(fx.verdicts).some((v) => v.outcome === 'pass'
      && v.criterion_trust === 'model-self-authored' && v.criterion_independent === false))
  check('★ 调用方判据带 `criterion_independent=true`（"这次不是模型自己给自己判的"）',
    Object.values(fx.verdicts).some((v) => v.criterion_independent === true))
  check('★ `abstain` 与 `invalid` 各有可读理由（不是空串）',
    ['abstain', 'invalid'].every((o) => {
      const v = Object.values(fx.verdicts).find((x) => x.outcome === o)
      return v && (v.reason || '').length > 0
    }))
}

head('P4 拆解合规审查（review 由后端 review_decomposition 产出，输入是**真实那次拆分**）')
if (!fx || !fx.decompose_review) {
  line('  SKIP  夹具里没有 decompose_review')
} else {
  const dr = fx.decompose_review
  line(`  输入：${JSON.stringify(fx.decompose_input)}`)
  line(`  passed=${dr.passed} independent=${dr.independent} checked_by=${dr.checked_by}`)
  line(`  violated(${(dr.violated || []).length}) = ${JSON.stringify(dr.violated)}`)
  line(`  undecidable(${(dr.undecidable || []).length}) = ${JSON.stringify(dr.undecidable)}`)
  for (const p of dr.principles || []) {
    line(`    ${p.principle} [${p.verdict}] ${String(p.evidence?.[0] ?? '').slice(0, 74)}`)
  }
  check('★ violated 与 undecidable **同时存在**（这样才能验"两者分开显示"）',
    (dr.violated || []).length > 0 && (dr.undecidable || []).length > 0,
    `${(dr.violated || []).length}/${(dr.undecidable || []).length}`)
  check('★ `undecidable` 非空时 `passed=false`（后端自己就不把它算通过）', dr.passed === false)
  check('★ `independent=false`（REVIEW 未启用 —— 界面必须说"非独立/未启用"）',
    dr.independent === false)
  check('★ 逐条原则有 8 条（P1–P8），每条带 verdict 与 evidence',
    (dr.principles || []).length === 8
    && (dr.principles || []).every((p) => p.verdict && (p.evidence || []).length > 0))
}

/* ------------------------------------------------------------------ */
line()
line('='.repeat(74))
const bad = checks.filter(([, ok]) => !ok)
line(`通过 ${checks.length - bad.length}/${checks.length}`)
if (bad.length) line(`失败: ${bad.map(([n]) => n).join('; ')}`)
if (ASSERT && bad.length) process.exit(1)
