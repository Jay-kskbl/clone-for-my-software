// 「减少动态效果」（指南 §3.2）：三个动效都从这里读，不各自写 matchMedia。
// 支持运行中变化：系统设置改了，订阅者会收到通知。

const QUERY = '(prefers-reduced-motion: reduce)'

type Listener = (reduced: boolean) => void

const listeners = new Set<Listener>()
let media: MediaQueryList | null = null
// 演示页用来强制打开 / 关闭（浏览器开发工具之外没有别的办法模拟系统设置）；null 表示跟随系统
let override: boolean | null = null

function getMedia(): MediaQueryList | null {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return null
  media ??= window.matchMedia(QUERY)
  return media
}

export function prefersReducedMotion(): boolean {
  if (override !== null) return override
  return getMedia()?.matches ?? false
}

function notify(): void {
  const reduced = prefersReducedMotion()
  for (const listener of [...listeners]) listener(reduced)
}

/** 订阅变化，返回取消订阅的函数。最后一个订阅者离开时移除系统监听。 */
export function onReducedMotionChange(listener: Listener): () => void {
  if (listeners.size === 0) getMedia()?.addEventListener('change', notify)
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
    if (listeners.size === 0) getMedia()?.removeEventListener('change', notify)
  }
}

/** 仅供调试 / 设计走查：强制减少动效（true）、强制正常（false）或恢复跟随系统（null）。 */
export function setReducedMotionOverride(value: boolean | null): void {
  override = value
  notify()
}
