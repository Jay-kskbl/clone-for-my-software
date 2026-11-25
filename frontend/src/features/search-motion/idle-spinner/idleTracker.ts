// 待机计时（指南 §4.1）：一段时间没有操作就进入待机，任意操作退出。
// - 「操作」= pointermove、pointerdown、keydown、wheel、touchstart（passive 监听）；在输入框打字也算（keydown）。
// - pointermove 很频繁：200 ms 内只重置一次计时；已在待机时任何操作立即退出，不节流。
// - 页面在后台时停止计时（待机中则直接退出），回到前台从 0 重新计时。

export const ACTIVITY_EVENTS = ['pointermove', 'pointerdown', 'keydown', 'wheel', 'touchstart'] as const

export interface IdleTrackerOptions {
  idleAfter: number
  onIdle: () => void
  onActive: () => void
  throttleMs?: number
  /** 监听操作的对象，默认 window */
  target?: EventTarget
  /** 提供 hidden 与 visibilitychange 的对象，默认 document */
  visibility?: EventTarget & { readonly hidden: boolean }
  now?: () => number
}

export interface IdleTracker {
  readonly idle: boolean
  /** 当作发生了一次操作（手动退出待机并重新计时） */
  poke(): void
  destroy(): void
}

export function createIdleTracker(options: IdleTrackerOptions): IdleTracker {
  const target = options.target ?? window
  const visibility = options.visibility ?? document
  const throttle = options.throttleMs ?? 200
  const now = options.now ?? (() => Date.now())

  let idle = false
  let timer: ReturnType<typeof setTimeout> | null = null
  let lastReset = -Infinity

  function clear(): void {
    if (timer !== null) clearTimeout(timer)
    timer = null
  }

  function arm(): void {
    clear()
    lastReset = now()
    if (visibility.hidden) return
    timer = setTimeout(() => {
      timer = null
      idle = true
      options.onIdle()
    }, options.idleAfter)
  }

  function wake(): void {
    if (!idle) return
    idle = false
    options.onActive()
  }

  function onActivity(): void {
    if (idle) {
      wake()
      arm()
      return
    }
    if (now() - lastReset < throttle) return
    arm()
  }

  function onVisibility(): void {
    if (visibility.hidden) {
      clear()
      wake()
    } else {
      arm()
    }
  }

  const listen = { passive: true } as const
  for (const type of ACTIVITY_EVENTS) target.addEventListener(type, onActivity, listen)
  visibility.addEventListener('visibilitychange', onVisibility)
  arm()

  return {
    get idle() {
      return idle
    },
    poke() {
      wake()
      arm()
    },
    destroy() {
      clear()
      for (const type of ACTIVITY_EVENTS) target.removeEventListener(type, onActivity)
      visibility.removeEventListener('visibilitychange', onVisibility)
    },
  }
}
