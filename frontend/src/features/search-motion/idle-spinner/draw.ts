// 待机动画的绘制（指南 §4.3、§4.4）。只负责“给定状态画一帧”，状态推进在 idleSpinner.ts。
//
// 射线：8 根圆头线段绕中心匀速旋转；第 i 根的长度、粗细随 sin(时间 × 3 − i × 相位差) 波动。
// 光球：实心圆呼吸缩放（4 秒一个周期）+ 一道绕圈的高光弧 + 外圈周期性扩散的涟漪。
// 两种样式读同一个 rotation，切换时不重置。
// morph 0 = 射线，1 = 光球：射线外端长度 ×(1 − morph) 向中心回收、线宽同步变细，缩成一圈小点；
// morph > 0.3 起光球从 60% 放大到 100% 并淡入。两者叠画。
import { clamp01, easeOutCubic } from '../shared/easing'
import type { MotionTokens } from '../shared/tokens'

// 颜色用 primaryStrong：待机图形是常驻页面上的图形元素，浅色下 primary 对白底只有约 2.8:1，达不到 3:1

export interface IdleFrame {
  /** 共用旋转角（弧度） */
  rotation: number
  /** 秒 */
  time: number
  /** 0 = 射线，1 = 光球 */
  morph: number
  /** 整体透明度 */
  alpha: number
}

const RAYS = 8
const PHASE = (Math.PI * 2) / RAYS

export function drawIdle(ctx: CanvasRenderingContext2D, size: number, tokens: MotionTokens, frame: IdleFrame): void {
  ctx.clearRect(0, 0, size, size)
  if (frame.alpha <= 0 || size <= 0) return
  const c = size / 2
  const R = size * 0.4
  const m = clamp01(frame.morph)
  const orb = easeOutCubic(clamp01((m - 0.3) / 0.7))

  // ---- 光球（在下层） ----
  if (orb > 0) {
    const scale = 0.6 + 0.4 * orb
    const breath = 1 + 0.06 * Math.sin((frame.time / 4) * Math.PI * 2)
    const r = R * 0.55 * breath * scale

    // 涟漪：每 2.4 秒从球边扩散一圈
    const p = (frame.time % 2.4) / 2.4
    ctx.globalAlpha = frame.alpha * orb * 0.4 * (1 - p)
    ctx.strokeStyle = tokens.primaryStrong
    ctx.lineWidth = 1.5
    ctx.beginPath()
    ctx.arc(c, c, r * (1 + 0.7 * easeOutCubic(p)), 0, Math.PI * 2)
    ctx.stroke()

    ctx.globalAlpha = frame.alpha * orb
    ctx.fillStyle = tokens.primaryStrong
    ctx.beginPath()
    ctx.arc(c, c, r, 0, Math.PI * 2)
    ctx.fill()

    // 高光弧：用页面底色画，绕圈转动
    ctx.globalAlpha = frame.alpha * orb * 0.7
    ctx.strokeStyle = tokens.surface
    ctx.lineWidth = Math.max(1.5, R * 0.08)
    ctx.lineCap = 'round'
    ctx.beginPath()
    ctx.arc(c, c, r * 0.68, frame.rotation, frame.rotation + Math.PI * 0.55)
    ctx.stroke()
  }

  // ---- 射线（在上层，随光球出现淡出） ----
  const rayAlpha = frame.alpha * (1 - orb)
  if (rayAlpha > 0) {
    const inner = R * 0.3
    ctx.globalAlpha = rayAlpha
    ctx.strokeStyle = tokens.primaryStrong
    ctx.lineCap = 'round'
    for (let i = 0; i < RAYS; i++) {
      const wave = (Math.sin(frame.time * 3 - i * PHASE) + 1) / 2
      const length = R * 0.7 * (0.45 + 0.55 * wave) * (1 - m)
      const width = R * 0.15 * (0.65 + 0.35 * wave) * (1 - 0.5 * m)
      const a = frame.rotation + i * PHASE
      const cos = Math.cos(a)
      const sin = Math.sin(a)
      ctx.lineWidth = width
      ctx.beginPath()
      ctx.moveTo(c + cos * inner, c + sin * inner)
      // 长度为 0 时圆头线段画成一个点
      ctx.lineTo(c + cos * (inner + length + 0.001), c + sin * (inner + length + 0.001))
      ctx.stroke()
    }
  }
  ctx.globalAlpha = 1
}
