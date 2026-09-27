/**
 * SSE 客户端（基于 fetch 流，不用 EventSource）。
 *
 * 为什么不用原生 EventSource
 * -------------------------
 * 1. 它只认「默认 message」事件；后端用的是具名事件（`event: tool_call`），
 *    具名事件必须在客户端逐个 addEventListener，词表一扩展就漏事件。
 * 2. 它不能带自定义头，也没法在重连时传 `after` 续订位置。
 *
 * 自己解析只多十几行，换来的是：事件词表随便扩展、按 seq 精确续传、
 * 断开后自动重连且不重复也不丢事件。
 */
import { endpoint } from '@/api/spec'
import { url } from '@/config'
import type { AgentEvent } from '@/types'

export interface StreamHandlers {
  onEvent: (ev: AgentEvent) => void
  /** 服务端明确收尾（运行到终态） */
  onClose?: (payload: Record<string, unknown>) => void
  onOpen?: () => void
  onError?: (message: string) => void
}

export interface StreamHandle {
  close: () => void
  readonly lastSeq: number
}

// 重连参数来自 config：内置默认 → VITE_* → 后端标定的 ui 段
import { config } from '@/config'

export function streamRun(
  runId: string,
  afterSeq: number,
  handlers: StreamHandlers,
): StreamHandle {
  let controller: AbortController | null = null
  let closedByUser = false
  let finished = false
  let retries = 0
  let lastSeq = afterSeq

  const handle: StreamHandle = {
    close() {
      closedByUser = true
      controller?.abort()
    },
    get lastSeq() {
      return lastSeq
    },
  }

  async function connect() {
    if (closedByUser || finished) return
    controller = new AbortController()

    let res: Response
    try {
      res = await fetch(
        url(`${endpoint('run_stream', { run_id: runId })}?after=${lastSeq}`),
        { signal: controller.signal, headers: { Accept: 'text/event-stream' } },
      )
    } catch (e) {
      return retry(e)
    }
    if (!res.ok || !res.body) {
      return retry(new Error(`SSE HTTP ${res.status}`))
    }

    retries = 0
    handlers.onOpen?.()

    const reader = res.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        // SSE 以空行分帧
        let sep = buffer.indexOf('\n\n')
        while (sep !== -1) {
          const raw = buffer.slice(0, sep)
          buffer = buffer.slice(sep + 2)
          handleFrame(raw)
          sep = buffer.indexOf('\n\n')
        }
      }
    } catch (e) {
      if (closedByUser) return
      return retry(e)
    }

    if (closedByUser || finished) return
    retry(new Error('流被服务端关闭'))
  }

  function handleFrame(raw: string) {
    let event = 'message'
    let data = ''
    for (const line of raw.split('\n')) {
      if (!line || line.startsWith(':')) continue // 心跳注释
      const idx = line.indexOf(':')
      const field = idx === -1 ? line : line.slice(0, idx)
      const value = idx === -1 ? '' : line.slice(idx + 1).replace(/^ /, '')
      if (field === 'event') event = value
      else if (field === 'data') data += (data ? '\n' : '') + value
    }
    if (!data) return

    let payload: any
    try {
      payload = JSON.parse(data)
    } catch {
      return
    }

    if (event === 'open') {
      handlers.onOpen?.()
      return
    }
    if (event === 'close') {
      finished = true
      handlers.onClose?.(payload ?? {})
      return
    }
    const seq = Number(payload?.seq ?? 0)
    if (seq) lastSeq = Math.max(lastSeq, seq)
    handlers.onEvent(payload as AgentEvent)
  }

  function retry(err: unknown) {
    if (closedByUser || finished) return
    retries += 1
    if (retries > config.stream.maxReconnects) {
      handlers.onError?.(err instanceof Error ? err.message : String(err))
      return
    }
    handlers.onError?.(err instanceof Error ? err.message : String(err))
    window.setTimeout(connect, config.stream.reconnectMs)
  }

  connect()
  return handle
}
