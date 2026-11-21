// 待机转动动画（动画 1）核心，框架无关。
//
// active ──(idleAfter 无操作)──▶ idle:rays ──(switchEvery)──▶ morphing ──▶ idle:orb ──▶ …
//    ▲                                                                              │
//    └─────────────────────────(任意操作：淡出 0.4 秒)─────────────────────────────────┘
//
// 淡入淡出和样式切换都是“从当前值出发”的补间：切换到一半时用户有操作，直接从当前画面整体淡出。
import { addFrame, createCanvasSurface } from '../shared/canvas'
import { easeInOutCubic, easeOutCubic, lerp, progress } from '../shared/easing'
import { onReducedMotionChange, prefersReducedMotion } from '../shared/reducedMotion'
import { TimerGroup } from '../shared/timers'
import { onThemeChange, readTokens } from '../shared/tokens'
import { drawIdle } from './draw'
import { createIdleTracker } from './idleTracker'

export type IdleStyle = 'auto' | 'rays' | 'orb'

export interface IdleSpinnerOptions {
  /** 进入待机的等待时间，默认 8000 ms */
  idleAfter?: number
  /** 两种样式自动互换的间隔，默认 30000 ms */
  switchEvery?: number
  /** 'auto' 自动轮换；'rays' / 'orb' 固定（如 AI 语音页固定光球） */
  style?: IdleStyle
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
const MORPH_MS = 800
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
  const style = options.style ?? 'auto'
  const switchEvery = options.switchEvery ?? 30_000
  const surface = createCanvasSurface(canvas, {
    observe: canvas.parentElement ?? canvas,
    onResize: () => {
      if (!looping) paint()
    },
  })
  canvas.style.pointerEvents = 'none'

  const timers = new TimerGroup()
  let tokens = readTokens()
  let reduced = prefersReducedMotion()
  let visible = false
  let looping = false
  let offFrame: (() => void) | null = null

  // 动画时间（毫秒），只在循环运行时前进；rotation 跨样式共用、不重置
  let clock = 0
  let rotation = 0
  let fade: Tween = { from: 0, to: 0, start: 0, duration: FADE_MS, ease: easeOutCubic }
  let morph: Tween = { from: 0, to: 0, start: 0, duration: MORPH_MS, ease: easeInOutCubic }

  function paint(): void {
    const size = Math.min(surface.width, surface.height)
    if (reduced) {
      // 减少动效：不轮换、不转动，只显示静止的射线
      drawIdle(surface.ctx, size, tokens, { rotation: -Math.PI / 2, time: Math.PI / 6, morph: 0, alpha: visible ? 1 : 0 })
      return
    }
    drawIdle(surface.ctx, size, tokens, {
      rotation,
      time: clock / 1000,
      morph: tweenValue(morph, clock),
      alpha: tweenValue(fade, clock),
    })
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

  function scheduleSwitch(): void {
    if (style !== 'auto' || reduced) return
    timers.after(switchEvery, () => {
      const current = tweenValue(morph, clock)
      morph = { ...morph, from: current, to: morph.to === 0 ? 1 : 0, start: clock }
      scheduleSwitch()
    })
  }

  function show(): void {
    if (visible) return
    visible = true
    timers.clear()
    // 完全隐藏后再出现：从初始样式开始；淡出到一半又被叫回来：保持当前画面，避免跳变
    if (reduced || tweenValue(fade, clock) === 0) {
      const initial = style === 'orb' ? 1 : 0
      morph = { ...morph, from: initial, to: initial, start: clock }
    }
    if (reduced) {
      paint()
      return
    }
    fade = { ...fade, from: tweenValue(fade, clock), to: 1, start: clock }
    startLoop()
    scheduleSwitch()
  }

  function hide(): void {
    if (!visible) return
    visible = false
    timers.clear()
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
    timers.clear()
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
      timers.clear()
      stopLoop()
      offTheme()
      offReduced()
      surface.destroy()
    },
  }
}
