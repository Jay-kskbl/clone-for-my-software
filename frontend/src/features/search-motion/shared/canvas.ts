// Canvas 公共层（指南 §3.3）：高清屏适配、容器尺寸监听、全页面唯一的 rAF 循环。

// ---- 唯一的 rAF 循环 ----
// 所有 Canvas 动效都把每帧要做的事登记到这里，同一时间页面上最多一个 requestAnimationFrame；
// 没有登记者时停帧，页面切到后台时暂停，回到前台再继续。

export type FrameCallback = (now: number, dt: number) => void

const frames = new Set<FrameCallback>()
let rafId = 0
let last = 0

function tick(now: number): void {
  // 切回前台后的第一帧 dt 可能很大，截到 100 ms，避免画面一下跳很远
  const dt = last === 0 ? 1000 / 60 : Math.min(now - last, 100)
  last = now
  rafId = 0
  for (const frame of [...frames]) frame(now, dt)
  schedule()
}

function schedule(): void {
  if (rafId === 0 && frames.size > 0 && !document.hidden) rafId = requestAnimationFrame(tick)
}

function stop(): void {
  if (rafId !== 0) cancelAnimationFrame(rafId)
  rafId = 0
  last = 0
}

function onVisibility(): void {
  if (document.hidden) stop()
  else schedule()
}

/** 登记每帧回调，返回注销函数。最后一个回调注销后循环停止，可见性监听也一起移除。 */
export function addFrame(frame: FrameCallback): () => void {
  if (frames.size === 0) document.addEventListener('visibilitychange', onVisibility)
  frames.add(frame)
  schedule()
  return () => {
    if (!frames.delete(frame)) return
    if (frames.size > 0) return
    stop()
    document.removeEventListener('visibilitychange', onVisibility)
  }
}

/** 当前登记的每帧回调数量（自测用：动画隐藏、路由离开后应为 0）。 */
export function activeFrameCount(): number {
  return frames.size
}

// ---- 画布尺寸 ----

export interface CanvasSurface {
  readonly ctx: CanvasRenderingContext2D
  /** CSS 像素 */
  readonly width: number
  readonly height: number
  /** 手动设置尺寸（不监听容器时用） */
  setSize(width: number, height: number): void
  clear(): void
  destroy(): void
}

export interface SurfaceOptions {
  /** 监听这个元素的尺寸，画布跟着变；不传则只能手动 setSize */
  observe?: Element
  onResize?: (width: number, height: number) => void
}

/**
 * 按 devicePixelRatio 设置画布实际像素，绘制坐标仍用 CSS 像素。
 * 用 ResizeObserver 而不是 window.resize：侧栏展开等布局变化也会改尺寸。
 */
export function createCanvasSurface(canvas: HTMLCanvasElement, options: SurfaceOptions = {}): CanvasSurface {
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Canvas 2D 不可用')
  canvas.setAttribute('aria-hidden', 'true')

  let width = 0
  let height = 0

  function setSize(w: number, h: number): void {
    const dpr = window.devicePixelRatio || 1
    width = Math.max(0, w)
    height = Math.max(0, h)
    canvas.width = Math.round(width * dpr)
    canvas.height = Math.round(height * dpr)
    canvas.style.width = `${width}px`
    canvas.style.height = `${height}px`
    ctx!.setTransform(dpr, 0, 0, dpr, 0, 0)
  }

  let observer: ResizeObserver | null = null
  if (options.observe) {
    const rect = options.observe.getBoundingClientRect()
    setSize(rect.width, rect.height)
    observer = new ResizeObserver((entries) => {
      const box = entries[0]?.contentRect
      if (!box || (box.width === width && box.height === height)) return
      setSize(box.width, box.height)
      options.onResize?.(width, height)
    })
    observer.observe(options.observe)
  }

  return {
    ctx,
    get width() {
      return width
    },
    get height() {
      return height
    },
    setSize,
    clear() {
      ctx.clearRect(0, 0, width, height)
    },
    destroy() {
      observer?.disconnect()
      observer = null
    },
  }
}
