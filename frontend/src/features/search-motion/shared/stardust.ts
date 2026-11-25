// 星尘光球：待机动画和启动动画共用的图形（Barry 2026-11-22 决定两者用同一个动画）。
//
// 参考 OpenAI《Introducing GPT-6.2 Astra and Sol》发布页头图的粒子光效：中心是会呼吸的发光核心；
// 两颗亮星沿一个倾斜的椭圆轨道绕核心转，各自拖着一条逐渐散开、变暗的星尘尾巴；
// 尘粒各自闪烁，少数尘粒和两颗亮星带四角星芒。
// 只借鉴“星尘、拖尾、闪烁、星芒”这类通用视觉语言，构图（双星对称绕核心）和配色（项目主色）是自己的，
// 也不涉及任何 logo 造型（指南 §4.3 原创要求）。
//
// 这里只提供“某一时刻每颗粒子在哪、多亮、多大”和几个画图小函数；
// 待机动画直接整幅画（drawStardust），启动动画拿粒子位置做聚拢和展开（launchAnimation.ts）。
// 颜色用 primaryStrong：常驻页面上的图形元素，浅色下 primary 对白底只有约 2.8:1，达不到 3:1。
import type { MotionTokens } from './tokens'

/** 两颗亮星（各带一条尾巴），在轨道上相隔半圈 */
export const ARMS = 2
const DUST_PER_ARM = 90
/** 尾巴在轨道上拖多长（弧度） */
const TAIL_SWEEP = Math.PI * 1.15
/** 轨道是压扁的椭圆（y 方向 × 0.6），再整体倾斜，看起来像斜着看一个环 */
const SQUASH = 0.6
export const TILT = -0.42
/** 轨道半径占 R 的比例 */
const ORBIT = 0.92

export interface Dust {
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

/** 粒子参数用固定种子在模块加载时生成一次，每帧只按时间算位置，画面稳定不跳。 */
export const DUST: readonly Dust[] = (() => {
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

export interface StardustView {
  cx: number
  cy: number
  /** 整体半径（待机动画取画布边长 × 0.4） */
  R: number
  /** 共用旋转角（弧度）：亮星在轨道上的位置 */
  rotation: number
  /** 秒：驱动闪烁、呼吸、星芒脉动 */
  time: number
  /** 整体缩放，1 为原大 */
  scale: number
  /** 只缩放轨道（星尘和亮星离核心的距离），不改粒子和核心的大小；默认 1。登录页 logo 用它让光圈一张一缩 */
  orbitScale?: number
  /** 轨道在长轴方向（倾斜前的水平方向）再拉长的倍数，默认 1。登录页 logo 用它让光圈放大时主要往左右展开 */
  orbitStretch?: number
  /** 轨道倾斜角（弧度，画布 y 轴向下，正值顺时针），默认 TILT。登录页 logo 用它让光圈在两条对角线之间来回摆 */
  tilt?: number
}

export interface Pose {
  x: number
  y: number
  /** 0（轨道远端）～ 1（近端） */
  depth: number
}

/** 轨道角 angle、径向偏移 offset（以 R 为单位）→ 画布坐标 */
function place(v: StardustView, angle: number, offset: number): Pose {
  const r = v.R * ORBIT * v.scale * (v.orbitScale ?? 1) * (1 + offset)
  const ex = Math.cos(angle) * r * (v.orbitStretch ?? 1)
  const ey = Math.sin(angle) * r * SQUASH
  const tilt = v.tilt ?? TILT
  const cos = Math.cos(tilt)
  const sin = Math.sin(tilt)
  return { x: v.cx + ex * cos - ey * sin, y: v.cy + ex * sin + ey * cos, depth: (Math.sin(angle) + 1) / 2 }
}

/** 亮星往前走，尾巴在它后面（角度更小处），越往后越向内收一点，形成螺旋感 */
export function dustPose(d: Dust, v: StardustView): Pose {
  return place(v, v.rotation + d.arm * Math.PI - d.u * TAIL_SWEEP, d.spread - 0.18 * d.u)
}

export function headPose(arm: number, v: StardustView): Pose {
  return place(v, v.rotation + arm * Math.PI, 0)
}

export function twinkle(d: Dust, time: number): number {
  return 0.5 + 0.5 * Math.sin(time * d.twinkleSpeed + d.twinklePhase)
}

/** 尘粒自身的透明度（不含整体淡入淡出）：越往尾巴越暗，各自闪烁，远端稍暗 */
export function dustAlpha(d: Dust, pose: Pose, time: number): number {
  return (1 - d.u) ** 0.6 * (0.45 + 0.55 * twinkle(d, time)) * (0.6 + 0.4 * pose.depth)
}

export function dustRadius(d: Dust, pose: Pose, v: StardustView): number {
  return d.size * v.R * v.scale * (0.8 + 0.2 * pose.depth)
}

/** 把 CSS 颜色换成指定透明度的 rgba（借 Canvas 把任意写法规范成 #rrggbb）；解析不了就原样返回。
 *  径向渐变不能直接渐变到 transparent：那是透明的黑色，中间会发灰。 */
function withAlpha(ctx: CanvasRenderingContext2D, color: string, alpha: number): string {
  ctx.fillStyle = '#000'
  ctx.fillStyle = color
  const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(String(ctx.fillStyle))
  if (!m) return color
  return `rgba(${parseInt(m[1], 16)}, ${parseInt(m[2], 16)}, ${parseInt(m[3], 16)}, ${alpha})`
}

/** 四角星芒：一横一竖两条中间粗、两头尖的细线（用当前 fillStyle） */
export function drawGlint(ctx: CanvasRenderingContext2D, x: number, y: number, length: number, width: number): void {
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

export interface StardustOptions {
  /** 实心核的半径（px）；不给时为 R × 0.1。登录页 logo 把它放大，好在中间放文档图标 */
  coreRadius?: number
}

/** 中心核心：径向渐变柔光 + 呼吸的实心核（4 秒一个周期）。画完 fillStyle 为 primaryStrong。 */
export function drawCore(
  ctx: CanvasRenderingContext2D,
  v: StardustView,
  tokens: MotionTokens,
  alpha: number,
  options: StardustOptions = {},
): void {
  const breath = 1 + 0.08 * Math.sin((v.time / 4) * Math.PI * 2)
  const coreR = (options.coreRadius ?? v.R * 0.1) * v.scale * breath
  const glowR = Math.max(v.R * 0.5 * v.scale * breath, coreR * 1.7)
  ctx.fillStyle = tokens.primaryStrong
  if (alpha > 0 && glowR > 0) {
    const glow = ctx.createRadialGradient(v.cx, v.cy, 0, v.cx, v.cy, glowR)
    glow.addColorStop(0, withAlpha(ctx, tokens.primaryStrong, 0.55))
    glow.addColorStop(0.3, withAlpha(ctx, tokens.primaryStrong, 0.2))
    glow.addColorStop(1, withAlpha(ctx, tokens.primaryStrong, 0))
    ctx.globalAlpha = alpha
    ctx.fillStyle = glow
    ctx.beginPath()
    ctx.arc(v.cx, v.cy, glowR, 0, Math.PI * 2)
    ctx.fill()
    ctx.fillStyle = tokens.primaryStrong
    ctx.beginPath()
    ctx.arc(v.cx, v.cy, coreR, 0, Math.PI * 2)
    ctx.fill()
  }
}

/** 一粒星尘；glint > 0 时按它的大小画星芒（启动动画展开时把星芒收掉） */
export function drawDust(ctx: CanvasRenderingContext2D, d: Dust, x: number, y: number, radius: number, v: StardustView, glint = 1): void {
  const tw = twinkle(d, v.time)
  if (d.glint && glint > 0 && tw > 0.6) {
    drawGlint(ctx, x, y, (radius * 2 + v.R * 0.1 * (tw - 0.6) * 2.5) * glint, radius * 0.45)
  }
  ctx.beginPath()
  ctx.arc(x, y, radius, 0, Math.PI * 2)
  ctx.fill()
}

/** 亮星：实心点 + 缓慢脉动的星芒 */
export function drawHead(ctx: CanvasRenderingContext2D, arm: number, x: number, y: number, v: StardustView, glint = 1): void {
  ctx.beginPath()
  ctx.arc(x, y, v.R * 0.075 * v.scale, 0, Math.PI * 2)
  ctx.fill()
  if (glint <= 0) return
  const pulse = 0.5 + 0.5 * Math.sin(v.time * 1.8 + arm * Math.PI)
  drawGlint(ctx, x, y, v.R * (0.14 + 0.08 * pulse) * v.scale * glint, v.R * 0.03 * v.scale)
}

/** 整幅星尘光球（待机动画用），alpha 为整体透明度 */
export function drawStardust(
  ctx: CanvasRenderingContext2D,
  tokens: MotionTokens,
  v: StardustView,
  alpha: number,
  options: StardustOptions = {},
): void {
  if (alpha <= 0) return
  drawCore(ctx, v, tokens, alpha, options)
  for (const d of DUST) {
    const pose = dustPose(d, v)
    const a = alpha * dustAlpha(d, pose, v.time)
    if (a <= 0.01) continue
    ctx.globalAlpha = a
    drawDust(ctx, d, pose.x, pose.y, dustRadius(d, pose, v), v)
  }
  for (let arm = 0; arm < ARMS; arm++) {
    const pose = headPose(arm, v)
    ctx.globalAlpha = alpha * (0.7 + 0.3 * pose.depth)
    drawHead(ctx, arm, pose.x, pose.y, v)
  }
  ctx.globalAlpha = 1
}
