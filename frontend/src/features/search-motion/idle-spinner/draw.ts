// 待机动画的绘制（指南 §4.3、§4.4）。只负责“给定状态画一帧”，状态推进在 idleSpinner.ts。
//
// 射线：8 根圆头线段绕中心匀速旋转；第 i 根的长度、粗细随 sin(时间 × 3 − i × 相位差) 波动。
// 光球（星尘粒子，Barry 2026-11-22 要求参考 OpenAI 发布页头图的粒子光效重做，取代指南 §4.3 的
// “实心圆 + 高光弧 + 涟漪”）：中心是会呼吸的发光核心；两颗亮星沿一个倾斜的椭圆轨道绕核心转，
// 各自拖着一条逐渐散开、变暗的星尘尾巴；尘粒各自闪烁，少数尘粒和两颗亮星带四角星芒。
// 只借鉴“星尘、拖尾、闪烁、星芒”这类通用视觉语言，构图（双星对称绕核心）和配色（项目主色）是自己的，
// 也不涉及任何 logo 造型（指南 §4.3 原创要求）。
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

// ---- 星尘粒子：位置参数在模块加载时用固定种子生成一次，每帧只按时间算位置，画面稳定不跳 ----

/** 两颗亮星（各带一条尾巴），在轨道上相隔半圈 */
const ARMS = 2
const DUST_PER_ARM = 90
/** 尾巴在轨道上拖多长（弧度） */
const TAIL_SWEEP = Math.PI * 1.15
/** 轨道是压扁的椭圆（y 方向 × 0.6），再整体倾斜，看起来像斜着看一个环 */
const SQUASH = 0.6
const TILT = -0.42

interface Dust {
  arm: number
  /** 0 = 紧跟亮星，1 = 尾巴末端 */
  u: number
  /** 垂直于轨道方向的偏移（以 R 为单位），越往尾巴越散 */
  spread: number
  /** 半径，以 R 为单位 */
  size: number
  twinkleSpeed: number
  twinklePhase: number
  /** 带四角星芒 */
  glint: boolean
}

function mulberry32(seed: number): () => number {
  let a = seed
  return () => {
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const DUST: Dust[] = (() => {
  const random = mulberry32(20261122)
  const list: Dust[] = []
  for (let arm = 0; arm < ARMS; arm++) {
    for (let i = 0; i < DUST_PER_ARM; i++) {
      // 靠近亮星的粒子更密
      const u = random() ** 1.6
      list.push({
        arm,
        u,
        spread: (random() - 0.5) * (0.08 + 0.5 * u),
        size: 0.018 + random() * 0.04 * (1 - 0.5 * u),
        twinkleSpeed: 1.5 + random() * 3,
        twinklePhase: random() * Math.PI * 2,
        glint: false,
      })
    }
  }
  // 每条尾巴挑两颗做星芒
  for (let arm = 0; arm < ARMS; arm++) {
    const mine = list.filter((d) => d.arm === arm && d.u > 0.2 && d.u < 0.75)
    mine.slice(0, 2).forEach((d) => (d.glint = true))
  }
  return list
})()

/** 把 CSS 颜色换成指定透明度的 rgba（借 Canvas 把任意写法规范成 #rrggbb）；解析不了就原样返回。
 *  径向渐变不能直接渐变到 transparent：那是透明的黑色，中间会发灰。 */
function withAlpha(ctx: CanvasRenderingContext2D, color: string, alpha: number): string {
  ctx.fillStyle = '#000'
  ctx.fillStyle = color
  const hex = String(ctx.fillStyle)
  const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex)
  if (!m) return color
  return `rgba(${parseInt(m[1], 16)}, ${parseInt(m[2], 16)}, ${parseInt(m[3], 16)}, ${alpha})`
}

/** 四角星芒：一横一竖两条中间粗、两头尖的细线 */
function drawGlint(ctx: CanvasRenderingContext2D, x: number, y: number, length: number, width: number): void {
  ctx.beginPath()
  ctx.moveTo(x - length, y)
  ctx.lineTo(x, y - width)
  ctx.lineTo(x + length, y)
  ctx.lineTo(x, y + width)
  ctx.closePath()
  ctx.moveTo(x, y - length)
  ctx.lineTo(x + width, y)
  ctx.lineTo(x, y + length)
  ctx.lineTo(x - width, y)
  ctx.closePath()
  ctx.fill()
}

function drawStardust(ctx: CanvasRenderingContext2D, c: number, R: number, tokens: MotionTokens, frame: IdleFrame, orb: number): void {
  const scale = 0.6 + 0.4 * orb
  const t = frame.time
  const cosT = Math.cos(TILT)
  const sinT = Math.sin(TILT)
  const orbitR = R * 0.92 * scale

  /** 轨道角 angle、径向偏移 offset（以 R 为单位）→ 画布坐标；depth 0（远端）～ 1（近端） */
  const place = (angle: number, offset: number) => {
    const r = orbitR * (1 + offset)
    const ex = Math.cos(angle) * r
    const ey = Math.sin(angle) * r * SQUASH
    return { x: c + ex * cosT - ey * sinT, y: c + ex * sinT + ey * cosT, depth: (Math.sin(angle) + 1) / 2 }
  }

  ctx.fillStyle = tokens.primaryStrong

  // 核心：外圈柔光 + 呼吸的实心核
  const breath = 1 + 0.08 * Math.sin((t / 4) * Math.PI * 2)
  const glowR = R * 0.5 * scale * breath
  const glow = ctx.createRadialGradient(c, c, 0, c, c, glowR)
  glow.addColorStop(0, withAlpha(ctx, tokens.primaryStrong, 0.55))
  glow.addColorStop(0.3, withAlpha(ctx, tokens.primaryStrong, 0.2))
  glow.addColorStop(1, withAlpha(ctx, tokens.primaryStrong, 0))
  ctx.globalAlpha = frame.alpha * orb
  ctx.fillStyle = glow
  ctx.beginPath()
  ctx.arc(c, c, glowR, 0, Math.PI * 2)
  ctx.fill()
  ctx.fillStyle = tokens.primaryStrong
  ctx.beginPath()
  ctx.arc(c, c, R * 0.1 * scale * breath, 0, Math.PI * 2)
  ctx.fill()

  // 尾巴上的星尘：亮星往前走，尾巴在它后面（角度更小处）
  for (const d of DUST) {
    const head = frame.rotation + d.arm * Math.PI
    const angle = head - d.u * TAIL_SWEEP
    // 尾巴越往后越向内收一点，形成螺旋感
    const p = place(angle, d.spread - 0.18 * d.u)
    const twinkle = 0.5 + 0.5 * Math.sin(t * d.twinkleSpeed + d.twinklePhase)
    const fade = (1 - d.u) ** 0.6
    const a = frame.alpha * orb * fade * (0.45 + 0.55 * twinkle) * (0.6 + 0.4 * p.depth)
    if (a <= 0.01) continue
    ctx.globalAlpha = a
    const size = d.size * R * scale * (0.8 + 0.2 * p.depth)
    if (d.glint && twinkle > 0.6) {
      drawGlint(ctx, p.x, p.y, size * 2 + R * 0.1 * (twinkle - 0.6) * 2.5, size * 0.45)
    }
    ctx.beginPath()
    ctx.arc(p.x, p.y, size, 0, Math.PI * 2)
    ctx.fill()
  }

  // 两颗亮星：实心点 + 缓慢脉动的星芒
  for (let arm = 0; arm < ARMS; arm++) {
    const p = place(frame.rotation + arm * Math.PI, 0)
    const pulse = 0.5 + 0.5 * Math.sin(t * 1.8 + arm * Math.PI)
    ctx.globalAlpha = frame.alpha * orb * (0.7 + 0.3 * p.depth)
    ctx.beginPath()
    ctx.arc(p.x, p.y, R * 0.075 * scale, 0, Math.PI * 2)
    ctx.fill()
    drawGlint(ctx, p.x, p.y, R * (0.14 + 0.08 * pulse) * scale, R * 0.03 * scale)
  }
}

export function drawIdle(ctx: CanvasRenderingContext2D, size: number, tokens: MotionTokens, frame: IdleFrame): void {
  ctx.clearRect(0, 0, size, size)
  if (frame.alpha <= 0 || size <= 0) return
  const c = size / 2
  const R = size * 0.4
  const m = clamp01(frame.morph)
  const orb = easeOutCubic(clamp01((m - 0.3) / 0.7))

  // ---- 光球（在下层） ----
  if (orb > 0) drawStardust(ctx, c, R, tokens, frame, orb)

  // ---- 射线（在上层，随光球出现淡出） ----
  const rayAlpha = frame.alpha * (1 - orb)
  if (rayAlpha > 0) {
    const inner = R * 0.3
    // 线宽封顶 4.5 px：画布放大到 120 px 时，射线按比例放大会显得太粗
    const rayWidth = Math.min(R * 0.15, 4.5)
    ctx.globalAlpha = rayAlpha
    ctx.strokeStyle = tokens.primaryStrong
    ctx.lineCap = 'round'
    for (let i = 0; i < RAYS; i++) {
      const wave = (Math.sin(frame.time * 3 - i * PHASE) + 1) / 2
      const length = R * 0.7 * (0.45 + 0.55 * wave) * (1 - m)
      const width = rayWidth * (0.65 + 0.35 * wave) * (1 - 0.5 * m)
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
