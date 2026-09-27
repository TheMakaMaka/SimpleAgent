import { onUnmounted, ref, watch, type Ref } from 'vue'

/**
 * 数字缓动：目标值变化时，显示值「滚」过去，而不是瞬间跳变。
 * 这是统计卡片看得出来的「动态」的关键——瞬间跳变会让动画失去意义。
 */
export function useTween(source: Ref<number>, duration = 520): Ref<number> {
  const display = ref(source.value)
  let raf = 0
  let from = source.value
  let to = source.value
  let start = 0

  const easeOut = (t: number) => 1 - Math.pow(1 - t, 3)

  function tick(now: number) {
    const t = Math.min(1, (now - start) / duration)
    display.value = from + (to - from) * easeOut(t)
    if (t < 1) raf = requestAnimationFrame(tick)
    else raf = 0
  }

  watch(source, (next) => {
    from = display.value
    to = next
    start = performance.now()
    if (!raf) raf = requestAnimationFrame(tick)
  })

  onUnmounted(() => {
    if (raf) cancelAnimationFrame(raf)
  })

  return display
}

/** 毫秒 → 人类可读；带毫秒是为了让「正在跑」有推进感。 */
export function formatDuration(ms: number): string {
  if (!ms || ms < 0) return '0.0s'
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(1)}s`
  const m = Math.floor(s / 60)
  const rest = s - m * 60
  return `${m}m ${rest.toFixed(0)}s`
}

export function formatClock(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000))
  const m = String(Math.floor(total / 60)).padStart(2, '0')
  const s = String(total % 60).padStart(2, '0')
  return `${m}:${s}`
}
