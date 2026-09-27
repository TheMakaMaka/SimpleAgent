import { onUnmounted, ref } from 'vue'

/**
 * 一个永远不会停的「当前时间」心跳。
 * 所有依赖它的派生值（如耗时、进度条）因此能自己动起来，
 * 而不需要在 store 里为计时器造一个假事件。
 */
export function useClock(intervalMs = 100) {
  const now = ref(Date.now())
  const timer = window.setInterval(() => {
    now.value = Date.now()
  }, intervalMs)
  onUnmounted(() => window.clearInterval(timer))
  return now
}
