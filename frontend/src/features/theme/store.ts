// 当前配色的全局状态：配色面板改它，改了就写到 <html> 上并保存（theme.ts）。
// 模式为“跟随系统”时，系统切换深浅色也会马上跟着变。
import { reactive, watch } from 'vue'

import { applyTheme, loadTheme, saveTheme, type ThemeSettings } from './theme'

export const theme = reactive<ThemeSettings>(loadTheme())

let started = false

/** 在挂载应用之前调用一次：首屏就是保存过的配色，不会先闪一下默认的蓝白 */
export function initTheme(): void {
  if (started) return
  started = true
  applyTheme(theme)
  watch(theme, () => {
    applyTheme(theme)
    saveTheme({ ...theme })
  })
  window.matchMedia?.('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (theme.mode === 'system') applyTheme(theme)
  })
}
