// 启动动画（动画 2）核心，框架无关；由 useLaunchAnimation 懒加载（不进首屏脚本）。
//
// 图形与待机动画相同：星尘光球（shared/stardust.ts；Barry 2026-11-22 决定两者用同一个动画）。
// 0 – 0.8 s 光球核心在检索框中央闪亮两下 → 0.8 – 1.7 s 星尘从四周聚拢成光球（两颗亮星拖着星尘尾巴绕核心转）
// → 2.1 – 2.9 s 转速放慢，星尘向外铺到胶囊形检索框的轮廓上，核心淡出 → 描边、图标淡入 → 逐字打出占位文字。
//
// 对齐（指南 §5.2）：开始时读真实搜索框的 getBoundingClientRect 和计算样式——胶囊的位置、宽高、
// 圆角、背景、描边色，占位文字的字体、颜色和起始 x，前缀放大镜图标的位置和颜色——全部照它画，
// 不写死尺寸。Canvas 固定定位盖在整个视口上（粒子从四周飞来），pointer-events: none。
// 动画期间真实输入框 visibility: hidden（由 <html data-sm-launch> 控制，见 launch.css）。
// 结束时同一帧内：显示真实输入框 → 移除 Canvas；用户按键 / 点击跳过时再 input.focus({ preventScroll: true })。
// 这里只管一轮；循环播放由 loop.ts 控制。
import { addFrame, createCanvasSurface } from '../shared/canvas'
import { lerp } from '../shared/easing'
import { onReducedMotionChange } from '../shared/reducedMotion'
import { onThemeChange, readTokens, type MotionTokens } from '../shared/tokens'
import {
  ARMS,
  DUST,
  drawCore,
  drawDust,
  drawHead,
  dustAlpha,
  dustPose,
  dustRadius,
  headPose,
  type Pose,
  type StardustView,
} from '../shared/stardust'
import { LAUNCH_TIMING, launchFrame, pointOnOutline, type Box } from './timeline'

export interface LaunchTarget {
  /** 画胶囊用：Element Plus 的 .el-input__wrapper */
  wrapper: HTMLElement
  input: HTMLInputElement
  /** 前缀放大镜图标（svg），可选 */
  icon?: SVGElement | null
}

export type LaunchEndReason = 'end' | 'skip' | 'layout' | 'reduced' | 'destroy'

export interface LaunchOptions {
  placeholder: string
  onFinish?: (reason: LaunchEndReason) => void
}

export interface LaunchHandle {
  skip(): void
  destroy(): void
}

/** 动画期间 <html> 上的标记；有它时真实输入框隐藏（launch.css）。 */
export const LAUNCH_ATTR = 'smLaunch'

const ROTATE_SPEED = Math.PI * 0.7 // 光球转速：每秒 0.35 圈，与待机动画相同
/** 光球半径：与待机动画（120 px 画布 × 0.4）一样大 */
const ORB_R = 48

interface Particle {
  /** 飞来的起点 */
  sx: number
  sy: number
  /** 展开后在轮廓上的位置（周长比例） */
  s: number
}

interface Geometry {
  box: Box
  cx: number
  cy: number
  font: string
  textX: number
  baseline: number
  clipLeft: number
  clipRight: number
  clipTop: number
  clipBottom: number
  caretHeight: number
  placeholderColor: string
  fill: string
  border: string
  icon: { x: number; y: number; size: number; color: string; width: number } | null
  chars: number
}

function measure(target: LaunchTarget, placeholder: string, tokens: MotionTokens, ctx: CanvasRenderingContext2D): Geometry {
  const rect = target.wrapper.getBoundingClientRect()
  const ws = getComputedStyle(target.wrapper)
  const box: Box = {
    x: rect.left,
    y: rect.top,
    width: rect.width,
    height: rect.height,
    radius: parseFloat(ws.borderTopLeftRadius) || 0,
  }

  const ir = target.input.getBoundingClientRect()
  const is = getComputedStyle(target.input)
  const px = (v: string) => parseFloat(v) || 0
  const font = `${is.fontStyle} ${is.fontWeight} ${is.fontSize} ${is.fontFamily}`
  const clipLeft = ir.left + px(is.borderLeftWidth) + px(is.paddingLeft)
  const clipRight = ir.right - px(is.borderRightWidth) - px(is.paddingRight)
  const clipTop = ir.top + px(is.borderTopWidth) + px(is.paddingTop)
  const clipBottom = ir.bottom - px(is.borderBottomWidth) - px(is.paddingBottom)

  // 与浏览器在单行输入框里放文字的方式一致：字体的 ascent + descent 在内容框里垂直居中
  ctx.font = font
  const metrics = ctx.measureText(placeholder || '中')
  const ascent = metrics.fontBoundingBoxAscent || px(is.fontSize) * 0.88
  const descent = metrics.fontBoundingBoxDescent || px(is.fontSize) * 0.24
  const baseline = clipTop + (clipBottom - clipTop - (ascent + descent)) / 2 + ascent

  // 只打到输入框能显示的宽度为止（真实占位文字超出部分也是被裁掉的）
  const room = clipRight - clipLeft
  let chars = 0
  while (chars < placeholder.length && ctx.measureText(placeholder.slice(0, chars + 1)).width <= room) chars++
  chars = Math.min(placeholder.length, chars + 1)

  let icon: Geometry['icon'] = null
  if (target.icon) {
    const r = target.icon.getBoundingClientRect()
    icon = {
      x: r.left,
      y: r.top,
      size: r.width,
      color: getComputedStyle(target.icon).color || tokens.placeholder,
      width: parseFloat(target.icon.getAttribute('stroke-width') ?? '') || 1.8,
    }
  }

  return {
    box,
    cx: rect.left + rect.width / 2,
    cy: rect.top + rect.height / 2,
    font,
    textX: clipLeft,
    baseline,
    clipLeft,
    clipRight,
    clipTop,
    clipBottom,
    caretHeight: Math.min(clipBottom - clipTop, px(is.fontSize) * 1.3),
    placeholderColor: getComputedStyle(target.input, '::placeholder').color || tokens.placeholder,
    fill: ws.backgroundColor,
    border: ws.getPropertyValue('--el-input-border-color').trim() || tokens.border,
    icon,
    chars,
  }
}

function roundRectPath(ctx: CanvasRenderingContext2D, box: Box): void {
  const r = Math.min(box.radius, box.height / 2, box.width / 2)
  ctx.beginPath()
  ctx.roundRect(box.x + 0.5, box.y + 0.5, box.width - 1, box.height - 1, Math.max(0, r - 0.5))
}

export function playLaunch(target: LaunchTarget, options: LaunchOptions): LaunchHandle {
  // 第一轮由适配层在首帧前就打好标记；循环的后续几轮在这里打
  document.documentElement.dataset[LAUNCH_ATTR] = 'playing'
  const canvas = document.createElement('canvas')
  canvas.className = 'sm-launch-canvas'
  document.body.append(canvas)
  const surface = createCanvasSurface(canvas)
  surface.setSize(window.innerWidth, window.innerHeight)
  const { ctx } = surface

  let tokens = readTokens()
  let geo = measure(target, options.placeholder, tokens, ctx)
  // 放大镜直接取真实图标里的 path（24×24 视框），保证结束时完全重合
  const iconPaths = Array.from(target.icon?.querySelectorAll('path') ?? [], (path) => new Path2D(path.getAttribute('d') ?? ''))

  const view = (t: number): StardustView => ({ cx: geo.cx, cy: geo.cy, R: ORB_R, rotation: rotation(t), time: t / 1000, scale: 1 })

  // 星尘和两颗亮星从四周（离中心 120–280 px 的随机位置）飞来；
  // 展开时按它在展开结束那一刻相对中心的方向，分配到轮廓上（从右侧中点顺时针，与 pointOnOutline 一致），不会交叉
  const atEnd = view(LAUNCH_TIMING.expandEnd)
  const toParticle = (pose: Pose): Particle => {
    const a = Math.random() * Math.PI * 2
    const d = 120 + Math.random() * 160
    const dir = (Math.atan2(pose.y - geo.cy, pose.x - geo.cx) + Math.PI * 2) % (Math.PI * 2)
    return { sx: geo.cx + Math.cos(a) * d, sy: geo.cy + Math.sin(a) * d, s: dir / (Math.PI * 2) }
  }
  const dust = DUST.map((d) => toParticle(dustPose(d, atEnd)))
  const heads = Array.from({ length: ARMS }, (_, arm) => toParticle(headPose(arm, atEnd)))

  /** 光球转过的角度：聚拢开始后匀速，展开期间平滑减速到停。 */
  function rotation(t: number): number {
    const T = LAUNCH_TIMING
    const steady = (Math.max(0, Math.min(t, T.expandStart) - T.gatherStart) / 1000) * ROTATE_SPEED
    const p = Math.min(1, Math.max(0, (t - T.expandStart) / (T.expandEnd - T.expandStart)))
    const slowing = ((T.expandEnd - T.expandStart) / 1000) * ROTATE_SPEED * (p - (p * p) / 2)
    return steady + slowing
  }

  let elapsed = 0
  let done = false

  function draw(): void {
    const f = launchFrame(elapsed, geo.chars)
    surface.clear()

    // 胶囊底色、描边、图标淡入
    if (f.stroke > 0) {
      ctx.globalAlpha = f.stroke
      roundRectPath(ctx, geo.box)
      ctx.fillStyle = geo.fill
      ctx.fill()
      ctx.lineWidth = 1
      ctx.strokeStyle = geo.border
      ctx.stroke()
      if (geo.icon && iconPaths.length > 0) {
        ctx.save()
        ctx.translate(geo.icon.x, geo.icon.y)
        ctx.scale(geo.icon.size / 24, geo.icon.size / 24)
        ctx.lineWidth = geo.icon.width
        ctx.lineCap = 'round'
        ctx.lineJoin = 'round'
        ctx.strokeStyle = geo.icon.color
        for (const path of iconPaths) ctx.stroke(path)
        ctx.restore()
      }
    }

    const v = view(elapsed)

    // 光球核心：先闪亮两下，聚拢时常亮，展开时淡出
    const coreAlpha = Math.max(f.cursor, f.gather) * (1 - f.expand)
    if (coreAlpha > 0) drawCore(ctx, v, tokens, coreAlpha)

    // 星尘：从四周聚拢到光球上的位置 → 展开到胶囊轮廓；描边出现后淡出。
    // 展开时闪烁和星芒逐渐收掉，粒子变成大小一致的小点排在轮廓上
    const particleAlpha = f.gather * (1 - f.stroke)
    if (particleAlpha > 0) {
      ctx.fillStyle = tokens.primaryStrong
      const glint = 1 - f.expand
      const place = (p: Particle, pose: Pose) => {
        if (f.expand > 0) {
          const o = pointOnOutline(geo.box, p.s)
          return { x: lerp(pose.x, o.x, f.expand), y: lerp(pose.y, o.y, f.expand) }
        }
        return { x: lerp(p.sx, pose.x, f.gather), y: lerp(p.sy, pose.y, f.gather) }
      }
      DUST.forEach((d, i) => {
        const pose = dustPose(d, v)
        const a = particleAlpha * lerp(dustAlpha(d, pose, v.time), 0.85, f.expand)
        if (a <= 0.01) return
        const { x, y } = place(dust[i], pose)
        ctx.globalAlpha = a
        drawDust(ctx, d, x, y, lerp(dustRadius(d, pose, v), 1.1, f.expand), v, glint)
      })
      heads.forEach((p, arm) => {
        const pose = headPose(arm, v)
        const { x, y } = place(p, pose)
        ctx.globalAlpha = particleAlpha * (0.7 + 0.3 * pose.depth)
        drawHead(ctx, arm, x, y, v, glint)
      })
    }

    // 逐字打出占位文字，裁到输入框内容区内
    if (f.chars > 0) {
      const text = options.placeholder.slice(0, f.chars)
      ctx.save()
      ctx.beginPath()
      ctx.rect(geo.clipLeft, geo.clipTop, geo.clipRight - geo.clipLeft, geo.clipBottom - geo.clipTop)
      ctx.clip()
      ctx.globalAlpha = 1
      ctx.font = geo.font
      ctx.textBaseline = 'alphabetic'
      ctx.fillStyle = geo.placeholderColor
      ctx.fillText(text, geo.textX, geo.baseline)
      if (!f.finished && Math.floor(elapsed / 400) % 2 === 0) {
        const x = Math.min(geo.clipRight - 1, geo.textX + ctx.measureText(text).width + 1)
        ctx.fillStyle = tokens.primary
        ctx.fillRect(x, (geo.clipTop + geo.clipBottom - geo.caretHeight) / 2, 1.5, geo.caretHeight)
      }
      ctx.restore()
    }
    ctx.globalAlpha = 1
    if (f.finished) finish('end')
  }

  const offFrame = addFrame((_now, dt) => {
    // 用累计的 dt 而不是墙钟时间：切到后台时循环暂停，回来接着播，不会直接跳到结尾
    elapsed += dt
    draw()
  })

  const offTheme = onThemeChange((value) => {
    tokens = value
    geo = { ...measure(target, options.placeholder, tokens, ctx), chars: geo.chars }
  })
  const offReduced = onReducedMotionChange((reduced) => {
    if (reduced) finish('reduced')
  })

  // 任意按键 / 点击跳过：捕获阶段先聚焦输入框，不阻止默认行为，按下的字符就会进入输入框
  const onKey = () => finish('skip')
  const onPointer = () => finish('skip')
  // 动画中窗口尺寸或滚动位置变化：直接跳到结束状态，不重算
  const onLayout = () => finish('layout')
  window.addEventListener('keydown', onKey, true)
  window.addEventListener('pointerdown', onPointer, true)
  window.addEventListener('resize', onLayout)
  window.addEventListener('scroll', onLayout, { capture: true, passive: true })

  function finish(reason: LaunchEndReason): void {
    if (done) return
    done = true
    offFrame()
    offTheme()
    offReduced()
    window.removeEventListener('keydown', onKey, true)
    window.removeEventListener('pointerdown', onPointer, true)
    window.removeEventListener('resize', onLayout)
    window.removeEventListener('scroll', onLayout, { capture: true })
    // 同一帧内：显示真实输入框 → 移除 Canvas →（用户按键或点击跳过时）聚焦。
    // 自然播完不聚焦：动画会循环播放，聚焦后“输入框有焦点”会让循环停下（loop.ts）
    delete document.documentElement.dataset[LAUNCH_ATTR]
    surface.destroy()
    canvas.remove()
    if (reason === 'skip') target.input.focus({ preventScroll: true })
    options.onFinish?.(reason)
  }

  return {
    skip: () => finish('skip'),
    destroy: () => finish('destroy'),
  }
}
