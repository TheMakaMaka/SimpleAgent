/**
 * 构建期生成：前端「按什么写死的」。
 *
 * 为什么必须生成而不是手写
 * ------------------------
 * 责任自审查要拿前端的期望去和服务声明比对。如果这份期望是**人写的**，
 * 它迟早会和代码不一致——那时审查就会给出错误的责任判定，
 * 比不审查更糟（会让人去改不该改的那一方）。
 *
 * 所以从**源码里扫**：
 *   events           ← store/run.ts 的 `case '...'`
 *   endpoints        ← api/client.ts 的 need('...')
 *   stages           ← api/spec.ts 的 DEFAULT_SPEC
 *   proxied_upstream ← vite.config.ts 的 proxy 表
 *
 * 扫不到就报错退出——宁可构建失败，也不要生成一份假的期望。
 *
 * 用法：
 *     node scripts/gen-expectations.mjs           # 写文件
 *     node scripts/gen-expectations.mjs --check   # 只校验是否最新（CI/测试用）
 */

import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const SRC = join(HERE, '..', 'src')
const OUT = join(SRC, 'generated', 'expectations.ts')

const CHECK = process.argv.includes('--check')

function read(rel) {
  const p = join(SRC, rel)
  if (!existsSync(p)) throw new Error(`源文件不存在: ${rel}`)
  return readFileSync(p, 'utf-8')
}

/** 归约器里 `case 'xxx':` 就是它认得的事件 */
function scanEvents() {
  const text = read('store/run.ts')
  const set = new Set()
  for (const m of text.matchAll(/case '([a-z_]+)':/g)) set.add(m[1])
  if (!set.size) throw new Error('store/run.ts 里没扫到任何 case —— 归约器结构变了？')
  return [...set].sort()
}

/**
 * 前端用到的端点 key。
 *
 * 两种写法都要扫，否则会漏：
 *   client.ts    need('runs')        —— 走默认客户端的
 *   audit.ts     endpoint('audit')   —— 直接取路径的
 * 漏了会让服务端把"前端没用到这个端点"当成事实，判定就会偏。
 */
function scanEndpoints() {
  const set = new Set()
  for (const rel of ['api/client.ts', 'api/audit.ts', 'api/sse.ts', 'api/spec.ts']) {
    let text
    try {
      text = read(rel)
    } catch {
      continue
    }
    for (const m of text.matchAll(/(?:need|endpoint)\('([a-z_]+)'/g)) set.add(m[1])
  }
  if (!set.size) throw new Error('没扫到任何端点 key —— 客户端结构变了？')
  return [...set].sort()
}

/** DEFAULT_SPEC 里的阶段 id 就是它内置预期的阶段 */
function scanStages() {
  const text = read('api/spec.ts')
  const set = new Set()
  for (const m of text.matchAll(/\{\s*id:\s*'([a-z_]+)'/g)) set.add(m[1])
  if (!set.size) throw new Error('api/spec.ts 的 DEFAULT_SPEC 里没扫到阶段 —— 结构变了？')
  return [...set].sort()
}

/**
 * 前端要代理的**上游**端点 —— 事实源是 vite.config.ts 的 proxy 表。
 *
 * 为什么不能只扫 `endpoint('...')`：那只覆盖走 bridge 的那些。dev server
 * 还把 `/skills` `/candidates` `/encode` `/run` **直接**代理给上游，绕过 bridge。
 * 那几条同样是前端真实依赖的上游面：上游一删，前端静默少一块，
 * 而按下面那种扫法**没有任何一条判定会指向上游**。
 *
 * `/api` 是 bridge 自己的前缀，不算上游。
 */
function scanProxiedUpstream() {
  const cfg = readFileSync(join(HERE, '..', 'vite.config.ts'), 'utf-8')
  const m = cfg.match(/Object\.fromEntries\(\s*\[(.*?)\]\s*\.map/s)
  if (!m) throw new Error('vite.config.ts 里没找到 proxy 表 —— 结构变了？')
  const paths = [...m[1].matchAll(/'([^']+)'/g)].map((x) => x[1])
  return paths.filter((p) => p.startsWith('/') && p !== '/api').sort()
}

/** 前端能渲染的 spec 主版本。服务主版本更高时判定为「前端要适配」。 */
const SUPPORTED_SPEC = '1.0'

const events = scanEvents()
const endpoints = scanEndpoints()
const stages = scanStages()
const proxiedUpstream = scanProxiedUpstream()

const body = `/**
 * ⚠ 本文件由 scripts/gen-expectations.mjs 生成，**不要手改**。
 *
 * 内容 = 前端从源码里实际认得的东西。责任自审查（POST /api/audit）
 * 拿它去和服务声明比对，判断「该改前端还是后端接口定义有问题」。
 *
 * 重新生成：npm run gen:expectations
 */

export const SUPPORTED_SPEC = '${SUPPORTED_SPEC}'

export const EXPECTATIONS = {
  spec_version: SUPPORTED_SPEC,
  /** store/run.ts 的 case 列表 */
  events: ${JSON.stringify(events)},
  /** api/client.ts 用到的端点 key */
  endpoints: ${JSON.stringify(endpoints)},
  /** api/spec.ts 的 DEFAULT_SPEC 内置阶段 */
  stages: ${JSON.stringify(stages)},
  /**
   * 前端要代理的**上游**端点（vite.config.ts 的 proxy 表）。
   * ★ 上报责任自审查时用的就是它——不含 bridge 自己的 /api/*。
   */
  proxied_upstream: ${JSON.stringify(proxiedUpstream)},
} as const

export type Expectations = typeof EXPECTATIONS
`

const current = existsSync(OUT) ? readFileSync(OUT, 'utf-8') : ''

if (CHECK) {
  if (current !== body) {
    console.error('✗ src/generated/expectations.ts 不是最新的。')
    console.error('  跑：npm run gen:expectations')
    process.exit(1)
  }
  console.log(
    `✓ expectations 最新（${events.length} 事件 / ${stages.length} 阶段 / ` +
    `${endpoints.length} 端点 / ${proxiedUpstream.length} 上游代理）`,
  )
  process.exit(0)
}

mkdirSync(dirname(OUT), { recursive: true })
writeFileSync(OUT, body, 'utf-8')
console.log(
  `✓ 已生成 src/generated/expectations.ts` +
  `（${events.length} 事件 / ${stages.length} 阶段 / ${endpoints.length} 端点 / ` +
  `${proxiedUpstream.length} 上游代理）`,
)
