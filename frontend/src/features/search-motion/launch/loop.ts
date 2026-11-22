// 启动动画的循环控制（Barry 2026-11-22 决定：检索框没有输入时循环播放，输入后停止）。
// 只管“什么时候播下一轮”，一轮怎么画在 launchAnimation.ts。
//
// - 一轮播完（或因窗口尺寸、滚动变化提前结束）后，停 gap 毫秒再播下一轮；这段时间里有操作
//   （点击、按键、滚轮、触摸）就重新计时，避免用户正在操作页面时动画反复冒出来。
// - 每次开播前问 canPlay()：输入框有内容、输入框有焦点（用户准备输入）、减少动效打开时都不播，
//   也不再排下一轮，等 wake()（输入框失焦、减少动效关闭）再重新排。
// - 用户按键或点击会让当前这一轮立即结束（launchAnimation.ts 的 skip），之后同样按上面的规则决定。
import type { LaunchEndReason, LaunchHandle } from './launchAnimation'

export const LAUNCH_LOOP_GAP = 3000

const ACTIVITY = ['pointerdown', 'keydown', 'wheel', 'touchstart'] as const

export interface LaunchLoopOptions {
  /** 播一轮；这一轮结束时必须调用 onEnd */
  play(onEnd: (reason: LaunchEndReason) => void): LaunchHandle
  canPlay(): boolean
  gap?: number
  /** 监听操作的对象，默认 window（测试时可以换） */
  target?: EventTarget
}

export interface LaunchLoop {
  /** 立即尝试播第一轮，返回是否开播 */
  start(): boolean
  /** 条件可能变了（输入框失焦、减少动效关闭）：没在播就重新排下一轮 */
  wake(): void
  readonly running: boolean
  destroy(): void
}

export function createLaunchLoop(options: LaunchLoopOptions): LaunchLoop {
  const gap = options.gap ?? LAUNCH_LOOP_GAP
  const target = options.target ?? window
  let current: LaunchHandle | null = null
  let timer: ReturnType<typeof setTimeout> | null = null
  let destroyed = false

  function clearTimer(): void {
    if (timer !== null) clearTimeout(timer)
    timer = null
  }

  function schedule(): void {
    clearTimer()
    if (!destroyed) timer = setTimeout(tryPlay, gap)
  }

  function tryPlay(): boolean {
    timer = null
    if (destroyed || current || !options.canPlay()) return false
    let ended = false
    const handle = options.play((reason) => {
      ended = true
      if (current === handle) current = null
      // 减少动效打开、组件卸载：不再循环
      if (reason !== 'reduced' && reason !== 'destroy') schedule()
    })
    // play 里同步结束（例如刚开播就碰上减少动效）时不记为正在播
    if (!ended) current = handle
    return !ended
  }

  // 等待下一轮期间有操作就重新计时
  const onActivity = () => {
    if (timer !== null) schedule()
  }
  for (const type of ACTIVITY) target.addEventListener(type, onActivity, { capture: true, passive: true })

  return {
    start: tryPlay,
    wake() {
      if (!current) schedule()
    },
    get running() {
      return current !== null
    },
    destroy() {
      if (destroyed) return
      destroyed = true
      clearTimer()
      for (const type of ACTIVITY) target.removeEventListener(type, onActivity, { capture: true })
      const handle = current
      current = null
      handle?.destroy()
    },
  }
}
