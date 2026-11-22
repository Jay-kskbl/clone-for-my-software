// 待机动画（动画 1）核心，框架无关。画的是星尘光球（shared/stardust.ts），与启动动画同一个图形
// （Barry 2026-11-22 决定；取代指南 §4.3、§4.4 的“射线 / 光球两种样式互相切换”）。
//
// active ──(idleAfter 无操作)──▶ idle（星尘光球淡入并略微放大）
//    ▲                                │
//    └──(任意操作：淡出 0.4 秒)────────┘
//
// 淡入淡出是“从当前值出发”的补间：淡入到一半时用户有操作，直接从当前画面淡出。
import { addFrame, createCanvasSurface } from '../shared/canvas'
import { easeOutCubic, lerp, progress } from '../shared/easing'
import { onReducedMotionChange, prefersReducedMotion } from '../shared/reducedMotion'
import { drawStardust } from '../shared/stardust'
import { onThemeChange, readTokens } from '../shared/tokens'
import { createIdleTracker } from './idleTracker'

export interface IdleSpinnerOptions {
  /** 进入待机的等待时间，默认 8000 ms */
  idleAfter?: number
  onIdle?: () => void
  onActive?: () => void
}

export interface IdleSpinner {
  readonly visible: boolean
  /** 手动进入待机（调试、设计走查用） */
  show(): void
  /** 手动退出待机并重新计时 */
  hide(): void
  destroy(): void
}

const FADE_MS = 400
const TURNS_PER_SECOND = 0.35

interface Tween {
  from: number
  to: number
  start: number
  duration: number
  ease: (t: number) => number
}

function tweenValue(tween: Tween, t: number): number {
  return lerp(tween.from, tween.to, tween.ease(progress(t, tween.start, tween.start + tween.duration)))
}

export function createIdleSpinner(canvas: HTMLCanvasElement, options: IdleSpinnerOptions = {}): IdleSpinner {
  const surface = createCanvasSurface(canvas, {
    observe: canvas.parentElement ?? canvas,
    onResize: () => {
      if (!looping) paint()
    },
  })
  canvas.style.pointerEvents = 'none'

  let tokens = readTokens()
  let reduced = prefersReducedMotion()
  let visible = false
  let looping = false
  let offFrame: (() => void) | null = null

  // 动画时间（毫秒），只在循环运行时前进；旋转角跨多次出现累计、不重置
  let clock = 0
  let rotation = 0
  let fade: Tween = { from: 0, to: 0, start: 0, duration: FADE_MS, ease: easeOutCubic }

  function paint(): void {
    const size = Math.min(surface.width, surface.height)
    surface.clear()
    const view = { cx: size / 2, cy: size / 2, R: size * 0.4 }
    if (reduced) {
      // 减少动效：不转动、不闪烁，只显示一帧静止的星尘光球
      if (visible) drawStardust(surface.ctx, tokens, { ...view, rotation: -Math.PI / 4, time: 0, scale: 1 }, 1)
      return
    }
    const alpha = tweenValue(fade, clock)
    // 出现时从 80% 放大到原大，消失时反过来
    drawStardust(surface.ctx, tokens, { ...view, rotation, time: clock / 1000, scale: 0.8 + 0.2 * alpha }, alpha)
  }

  function startLoop(): void {
    if (looping) return
    looping = true
    offFrame = addFrame((_now, dt) => {
      clock += dt
      rotation += (dt / 1000) * TURNS_PER_SECOND * Math.PI * 2
      paint()
      // 完全淡出后停帧
      if (!visible && clock >= fade.start + fade.duration) stopLoop()
    })
  }

  function stopLoop(): void {
    offFrame?.()
    offFrame = null
    looping = false
    surface.clear()
  }

  function show(): void {
    if (visible) return
    visible = true
    if (reduced) {
      paint()
      return
    }
    // 淡出到一半又被叫回来：从当前透明度接着淡入，避免跳变
    fade = { ...fade, from: tweenValue(fade, clock), to: 1, start: clock }
    startLoop()
  }

  function hide(): void {
    if (!visible) return
    visible = false
    // 页面在后台时直接清掉，不留到回前台再播淡出
    if (reduced || document.hidden) {
      stopLoop()
      surface.clear()
      return
    }
    fade = { ...fade, from: tweenValue(fade, clock), to: 0, start: clock }
    startLoop()
  }

  const tracker = createIdleTracker({
    idleAfter: options.idleAfter ?? 8000,
    onIdle: () => {
      show()
      options.onIdle?.()
    },
    onActive: () => {
      hide()
      options.onActive?.()
    },
  })

  const offTheme = onThemeChange((value) => {
    tokens = value
    if (!looping) paint()
  })
  const offReduced = onReducedMotionChange((value) => {
    if (value === reduced) return
    const wasVisible = visible
    // 按新模式重新进入当前状态
    visible = false
    stopLoop()
    reduced = value
    fade = { ...fade, from: 0, to: 0, start: clock }
    if (wasVisible) show()
  })

  return {
    get visible() {
      return visible
    },
    show,
    hide() {
      tracker.poke()
      hide()
    },
    destroy() {
      tracker.destroy()
      stopLoop()
      offTheme()
      offReduced()
      surface.destroy()
    },
  }
}
