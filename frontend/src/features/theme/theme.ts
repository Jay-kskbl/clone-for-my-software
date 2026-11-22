// 系统整体配色（Barry 2026-11-22：不止蓝白，可以调节，演示用）。
//
// 做法：全站颜色本来就都从 Element Plus 的 CSS 变量来（styles.css 的 --app-* 也引用 --el-*），
// 所以换主题 = 在 <html> 上改写主色那一组变量（--el-color-primary 及其 light-3/5/7/8/9、dark-2），
// 再用 html.dark 切换 Element Plus 自带的暗色变量（main.ts 全局引入 dark/css-vars.css）。
// 动效的 Canvas 通过 tokens.ts 的 MutationObserver 监听 <html> 的 class / style，换主题后自动重新读色。
//
// 选择保存在本机浏览器（localStorage，读写失败就用默认值，不报错），只影响这个浏览器。

export type ThemeMode = 'light' | 'dark' | 'system'

export interface ThemeSettings {
  /** 主色，#rrggbb */
  primary: string
  mode: ThemeMode
}

export interface ThemePreset {
  id: string
  name: string
  primary: string
}

/** 预设主色。都比默认的海蓝对比度更高（白字在主色上、主色深一档在白底上都 ≥ 默认值），见 contrast() */
export const THEME_PRESETS: readonly ThemePreset[] = [
  { id: 'blue', name: '海蓝', primary: '#409eff' },
  { id: 'teal', name: '青碧', primary: '#0d9488' },
  { id: 'violet', name: '靛紫', primary: '#7c5cff' },
  { id: 'orange', name: '琥珀橙', primary: '#e8711c' },
  { id: 'rose', name: '玫红', primary: '#e0457b' },
  { id: 'green', name: '森绿', primary: '#3d9a50' },
]

export const DEFAULT_THEME: ThemeSettings = { primary: '#409eff', mode: 'light' }

const STORAGE_KEY = 'app-theme'
const WHITE = '#ffffff'
const BLACK = '#000000'
/** Element Plus 暗色主题的页面底色，它的暗色主色梯度就是和这个颜色混出来的 */
const DARK_BG = '#141414'
/** Element Plus 浅色主题的 --el-fill-color-light，页面底色在它上面掺一点主色 */
const LIGHT_FILL = '#f5f7fa'

// ---- 颜色计算 ----

export function isHexColor(value: unknown): value is string {
  return typeof value === 'string' && /^#[0-9a-f]{6}$/i.test(value)
}

function rgb(hex: string): [number, number, number] {
  return [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)) as [number, number, number]
}

function toHex(c: number[]): string {
  // 先去掉浮点误差（如 43.4999999 应为 43.5），再四舍五入，结果才与 Sass 的 mix() 一致
  const round = (v: number) => Math.round(Math.round(v * 1e6) / 1e6)
  return `#${c.map((v) => round(Math.min(255, Math.max(0, v))).toString(16).padStart(2, '0')).join('')}`
}

/** 与 Element Plus 的 SCSS mix($a, $b, $weight) 相同：weight 为 a 的比例 */
export function mix(a: string, b: string, weight: number): string {
  const ca = rgb(a)
  const cb = rgb(b)
  return toHex(ca.map((v, i) => v * weight + cb[i] * (1 - weight)))
}

function luminance(hex: string): number {
  const [r, g, b] = rgb(hex).map((v) => {
    const c = v / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

/** WCAG 对比度 */
export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

/**
 * 主色一组变量，算法与 Element Plus 的主题一致：
 * 浅色：light-i = 白色占 i×10% 与主色混合，dark-2 = 黑色占 20%；
 * 暗色：light-i 与暗色底色混合，dark-2 = 白色占 20%（暗色下“深一档”其实是更亮）。
 * 另外给页面底色 --app-bg 掺一点主色（只在浅色下），让配色不只体现在按钮上；
 * 默认海蓝不掺，保持系统原来的样子。
 */
export function paletteFor(primary: string, dark: boolean): Record<string, string> {
  const base = dark ? DARK_BG : WHITE
  const vars: Record<string, string> = { '--el-color-primary': primary }
  for (const i of [3, 5, 7, 8, 9]) vars[`--el-color-primary-light-${i}`] = mix(base, primary, i / 10)
  vars['--el-color-primary-dark-2'] = mix(dark ? WHITE : BLACK, primary, 0.2)
  if (!dark && primary.toLowerCase() !== DEFAULT_THEME.primary) vars['--app-bg'] = mix(primary, LIGHT_FILL, 0.05)
  return vars
}

/** 自定义颜色的提示：常驻图形（动效、高亮）用“深一档”的主色，对页面底色要 ≥ 3:1 */
export function contrastWarning(primary: string, dark: boolean): string | null {
  const vars = paletteFor(primary, dark)
  const strong = contrast(vars['--el-color-primary-dark-2'], dark ? DARK_BG : WHITE)
  if (strong < 3) return `这个颜色在${dark ? '深色' : '浅色'}底上太淡（对比度 ${strong.toFixed(1)}:1，低于 3:1），图形可能看不清`
  const onPrimary = contrast(WHITE, primary)
  if (onPrimary < 2.5) return `按钮上的白字看不清（对比度 ${onPrimary.toFixed(1)}:1），建议选深一点的颜色`
  return null
}

// ---- 保存与应用 ----

type StorageLike = Pick<Storage, 'getItem' | 'setItem'>

function storage(): StorageLike | null {
  try {
    return window.localStorage
  } catch {
    return null
  }
}

export function loadTheme(store: StorageLike | null = storage()): ThemeSettings {
  try {
    const raw = store?.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULT_THEME }
    const value = JSON.parse(raw) as Partial<ThemeSettings>
    return {
      primary: isHexColor(value.primary) ? value.primary.toLowerCase() : DEFAULT_THEME.primary,
      mode: value.mode === 'dark' || value.mode === 'system' || value.mode === 'light' ? value.mode : DEFAULT_THEME.mode,
    }
  } catch {
    return { ...DEFAULT_THEME }
  }
}

export function saveTheme(settings: ThemeSettings, store: StorageLike | null = storage()): void {
  try {
    store?.setItem(STORAGE_KEY, JSON.stringify(settings))
  } catch {
    // 存不进去（隐私模式等）就只在本次页面生效
  }
}

function systemDark(): boolean {
  return typeof window !== 'undefined' && (window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false)
}

export function resolveDark(mode: ThemeMode, prefersDark: boolean = systemDark()): boolean {
  return mode === 'dark' || (mode === 'system' && prefersDark)
}

/** 写到 <html> 上：主色一组变量 + dark 类 + color-scheme（让滚动条、表单控件也跟着变） */
export function applyTheme(settings: ThemeSettings, root: HTMLElement = document.documentElement): void {
  const dark = resolveDark(settings.mode)
  root.classList.toggle('dark', dark)
  root.style.colorScheme = dark ? 'dark' : 'light'
  // 先清掉上一次写的 --app-bg（暗色下不写，要回到 styles.css 的值）
  root.style.removeProperty('--app-bg')
  for (const [name, value] of Object.entries(paletteFor(settings.primary, dark))) root.style.setProperty(name, value)
}
