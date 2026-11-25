// 缓动（指南 §3.4）：聚拢、展开、淡入、卡片入场用缓出；样式切换、扫描线用缓入缓出。
// 除旋转（匀速）外不做线性位移。

export function clamp01(value: number): number {
  return value < 0 ? 0 : value > 1 ? 1 : value
}

export function lerp(from: number, to: number, t: number): number {
  return from + (to - from) * t
}

/** 把时间 t 映射成 [start, end] 区间内的进度 0–1。 */
export function progress(t: number, start: number, end: number): number {
  return clamp01((t - start) / (end - start))
}

/** 缓出（先快后慢，cubic）。 */
export function easeOutCubic(t: number): number {
  const u = 1 - clamp01(t)
  return 1 - u * u * u
}

/** 缓入缓出（先加速后减速，cubic）。 */
export function easeInOutCubic(t: number): number {
  const x = clamp01(t)
  return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2
}

/** 与 easeOutCubic、easeInOutCubic 对应的 CSS 写法，DOM 动画用。 */
export const CSS_EASE_OUT = 'cubic-bezier(0.33, 1, 0.68, 1)'
export const CSS_EASE_IN_OUT = 'cubic-bezier(0.65, 0, 0.35, 1)'
