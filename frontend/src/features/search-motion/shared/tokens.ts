// 动效颜色（指南 §3.1）：从项目的 CSS 变量读取（styles.css 的 --app-*、Element Plus 的 --el-*），
// 读不到再用 Element Plus 浅色主题的默认值。不在动效里写死色值。

export interface MotionTokens {
  primary: string
  /** 比 primary 深一档：小面积图形在白底上要 3:1，primary 只有约 2.8:1；暗色主题里 Element Plus 会把它换成更亮的蓝 */
  primaryStrong: string
  primarySoft: string
  text: string
  textSecondary: string
  placeholder: string
  border: string
  surface: string
}

const SOURCES: Record<keyof MotionTokens, [cssVar: string, fallback: string]> = {
  primary: ['--app-primary', '#409eff'],
  primaryStrong: ['--el-color-primary-dark-2', '#337ecc'],
  primarySoft: ['--app-primary-soft', '#ecf5ff'],
  text: ['--app-text', '#303133'],
  textSecondary: ['--app-text-secondary', '#909399'],
  placeholder: ['--el-text-color-placeholder', '#a8abb2'],
  border: ['--el-border-color', '#dcdfe6'],
  surface: ['--app-surface', '#ffffff'],
}

export function readTokens(): MotionTokens {
  const style = typeof document === 'undefined' ? null : getComputedStyle(document.documentElement)
  const tokens = {} as MotionTokens
  for (const key of Object.keys(SOURCES) as (keyof MotionTokens)[]) {
    const [cssVar, fallback] = SOURCES[key]
    tokens[key] = style?.getPropertyValue(cssVar).trim() || fallback
  }
  return tokens
}

// ---- 主题变化 ----
// 项目目前没有暗色模式；这里同时监听系统配色和 <html> 的 class / style / data-theme，
// 以后按 Element Plus 的方式（html.dark）加上暗色模式时，Canvas 不用改就能跟着重新读色。

type Listener = (tokens: MotionTokens) => void

const listeners = new Set<Listener>()
let scheme: MediaQueryList | null = null
let observer: MutationObserver | null = null

function notify(): void {
  const tokens = readTokens()
  for (const listener of [...listeners]) listener(tokens)
}

/** 订阅主题变化，回调拿到重新读取的颜色；返回取消订阅的函数。 */
export function onThemeChange(listener: Listener): () => void {
  if (listeners.size === 0 && typeof window !== 'undefined') {
    scheme = window.matchMedia?.('(prefers-color-scheme: dark)') ?? null
    scheme?.addEventListener('change', notify)
    observer = new MutationObserver(notify)
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'style', 'data-theme'] })
  }
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
    if (listeners.size > 0) return
    scheme?.removeEventListener('change', notify)
    observer?.disconnect()
    scheme = null
    observer = null
  }
}
