// 启动动画（动画 2）的时间轴（指南 §5.1），纯函数：给定时间，算出每一层的进度。
//
// 0 – 0.8 s    中心光标闪烁两次
// 0.8 – 1.7 s  约 60 个粒子从四周聚拢成半径 24 px 的旋转光环
// 2.1 – 2.9 s  光环展开，粒子排到胶囊形搜索框轮廓上
// 2.8 – 3.2 s  描边和放大镜图标淡入
// 3.1 s 起     逐字打出占位文字（每秒 10 字）
// 结束         切换到真实输入框并聚焦
import { easeInOutCubic, easeOutCubic, progress } from '../shared/easing'

export const LAUNCH_TIMING = {
  blinkEnd: 800,
  gatherStart: 800,
  gatherEnd: 1700,
  expandStart: 2100,
  expandEnd: 2900,
  strokeStart: 2800,
  strokeEnd: 3200,
  typeStart: 3100,
  msPerChar: 100,
  /** 打完字后停留一下再交给真实输入框 */
  hold: 250,
}

export const PARTICLE_COUNT = 60
export const RING_RADIUS = 24

export interface LaunchFrame {
  /** 光标透明度 0–1（只在 0–0.8 s） */
  cursor: number
  /** 聚拢进度（已缓出） */
  gather: number
  /** 展开进度（已缓出） */
  expand: number
  /** 描边、图标透明度 */
  stroke: number
  /** 已打出的字数 */
  chars: number
  finished: boolean
}

/** 整段动画的时长（毫秒），取决于要打的字数。 */
export function launchDuration(totalChars: number): number {
  const typed = LAUNCH_TIMING.typeStart + totalChars * LAUNCH_TIMING.msPerChar
  return Math.max(LAUNCH_TIMING.strokeEnd, typed) + LAUNCH_TIMING.hold
}

export function launchFrame(t: number, totalChars: number): LaunchFrame {
  const T = LAUNCH_TIMING
  // 两次闪烁：0.8 s 内两个起伏，用缓入缓出的余弦形状，不是生硬的亮灭
  const blink = t < T.blinkEnd ? easeInOutCubic(0.5 - 0.5 * Math.cos((t / T.blinkEnd) * Math.PI * 4)) : 0
  const chars = t < T.typeStart ? 0 : Math.min(totalChars, Math.floor((t - T.typeStart) / T.msPerChar) + 1)
  return {
    cursor: blink,
    gather: easeOutCubic(progress(t, T.gatherStart, T.gatherEnd)),
    expand: easeOutCubic(progress(t, T.expandStart, T.expandEnd)),
    stroke: easeOutCubic(progress(t, T.strokeStart, T.strokeEnd)),
    chars,
    finished: t >= launchDuration(totalChars),
  }
}

// ---- 胶囊（圆角矩形）轮廓上的点 ----

export interface Box {
  x: number
  y: number
  width: number
  height: number
  radius: number
}

/**
 * 轮廓上按周长比例 s ∈ [0, 1) 取点：从右侧中点出发顺时针（画布 y 轴向下）。
 * 粒子按角度排序后依次分配 s，展开时不会交叉，分布也均匀。
 */
export function pointOnOutline(box: Box, s: number): { x: number; y: number } {
  const r = Math.min(box.radius, box.height / 2, box.width / 2)
  const w = box.width
  const h = box.height
  const straightH = w - 2 * r
  const straightV = h - 2 * r
  const arc = (Math.PI * r) / 2
  const total = 2 * straightH + 2 * straightV + 4 * arc
  let d = (((s % 1) + 1) % 1) * total
  const left = box.x
  const top = box.y
  const right = left + w
  const bottom = top + h

  // 依次是：右边下半段、右下角、底边、左下角、左边、左上角、顶边、右上角、右边上半段
  const segments: [number, (u: number) => { x: number; y: number }][] = [
    [straightV / 2, (u) => ({ x: right, y: top + h / 2 + u })],
    [arc, (u) => corner(right - r, bottom - r, 0, u)],
    [straightH, (u) => ({ x: right - r - u, y: bottom })],
    [arc, (u) => corner(left + r, bottom - r, Math.PI / 2, u)],
    [straightV, (u) => ({ x: left, y: bottom - r - u })],
    [arc, (u) => corner(left + r, top + r, Math.PI, u)],
    [straightH, (u) => ({ x: left + r + u, y: top })],
    [arc, (u) => corner(right - r, top + r, (Math.PI * 3) / 2, u)],
    [straightV / 2, (u) => ({ x: right, y: top + r + u })],
  ]

  function corner(cx: number, cy: number, start: number, u: number) {
    const a = start + (r === 0 ? 0 : u / r)
    return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) }
  }

  for (const [length, at] of segments) {
    if (d <= length) return at(d)
    d -= length
  }
  return { x: right, y: top + h / 2 }
}
