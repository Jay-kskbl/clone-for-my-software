// 系统配色（features/theme/theme.ts）：主色梯度算法与 Element Plus 一致、预设色对比度、保存读取、明暗判断。
import { describe, expect, it } from 'vitest'

import {
  contrast,
  contrastWarning,
  DEFAULT_THEME,
  loadTheme,
  paletteFor,
  resolveDark,
  saveTheme,
  THEME_PRESETS,
} from '../src/features/theme/theme'

describe('主色梯度', () => {
  it('默认海蓝在浅色下与 Element Plus 自带的值完全一致', () => {
    const vars = paletteFor('#409eff', false)
    expect(vars['--el-color-primary-light-3']).toBe('#79bbff')
    expect(vars['--el-color-primary-light-5']).toBe('#a0cfff')
    expect(vars['--el-color-primary-light-7']).toBe('#c6e2ff')
    expect(vars['--el-color-primary-light-8']).toBe('#d9ecff')
    expect(vars['--el-color-primary-light-9']).toBe('#ecf5ff')
    expect(vars['--el-color-primary-dark-2']).toBe('#337ecc')
    // 默认配色不改页面底色，和原来完全一样
    expect(vars['--app-bg']).toBeUndefined()
  })

  it('默认海蓝在暗色下与 Element Plus 暗色主题的值完全一致', () => {
    const vars = paletteFor('#409eff', true)
    expect(vars['--el-color-primary-light-3']).toBe('#3375b9')
    expect(vars['--el-color-primary-light-5']).toBe('#2a598a')
    expect(vars['--el-color-primary-light-7']).toBe('#213d5b')
    expect(vars['--el-color-primary-light-8']).toBe('#1d3043')
    expect(vars['--el-color-primary-light-9']).toBe('#18222c')
    expect(vars['--el-color-primary-dark-2']).toBe('#66b1ff')
    // 暗色下不改页面底色
    expect(vars['--app-bg']).toBeUndefined()
  })

  it('换了主色后，浅色下页面底色掺一点主色', () => {
    expect(paletteFor('#e0457b', false)['--app-bg']).not.toBe('#f5f7fa')
  })
})

describe('预设色对比度', () => {
  const base = paletteFor('#409eff', false)
  const baseOnPrimary = contrast('#ffffff', '#409eff')
  const baseStrong = contrast(base['--el-color-primary-dark-2'], '#ffffff')

  it.each(THEME_PRESETS.map((p) => [p.name, p.primary]))('%s 不比默认海蓝差，且没有提示', (_name, primary) => {
    expect(contrast('#ffffff', primary)).toBeGreaterThanOrEqual(baseOnPrimary - 0.01)
    expect(contrast(paletteFor(primary, false)['--el-color-primary-dark-2'], '#ffffff')).toBeGreaterThanOrEqual(3)
    expect(contrast(paletteFor(primary, true)['--el-color-primary-dark-2'], '#141414')).toBeGreaterThanOrEqual(3)
    expect(contrastWarning(primary, false)).toBeNull()
    expect(contrastWarning(primary, true)).toBeNull()
    expect(baseStrong).toBeGreaterThan(3)
  })

  it('太淡的自定义颜色给出提示', () => {
    expect(contrastWarning('#ffe680', false)).toMatch(/太淡|白字/)
    expect(contrastWarning('#1a1a40', true)).toMatch(/太淡/)
  })
})

describe('保存与读取', () => {
  function memory() {
    const data = new Map<string, string>()
    return { getItem: (k: string) => data.get(k) ?? null, setItem: (k: string, v: string) => void data.set(k, v) }
  }

  it('保存后能读回来', () => {
    const store = memory()
    saveTheme({ primary: '#0d9488', mode: 'dark' }, store)
    expect(loadTheme(store)).toEqual({ primary: '#0d9488', mode: 'dark' })
  })

  it('没有保存过、内容损坏、字段不合法、存储抛异常时都回到默认值', () => {
    expect(loadTheme(memory())).toEqual(DEFAULT_THEME)
    const bad = memory()
    bad.setItem('app-theme', '{oops')
    expect(loadTheme(bad)).toEqual(DEFAULT_THEME)
    const weird = memory()
    weird.setItem('app-theme', JSON.stringify({ primary: 'red; background:url(x)', mode: 'neon' }))
    expect(loadTheme(weird)).toEqual(DEFAULT_THEME)
    const broken = {
      getItem: () => {
        throw new Error('SecurityError')
      },
      setItem: () => {
        throw new Error('QuotaExceededError')
      },
    }
    expect(loadTheme(broken)).toEqual(DEFAULT_THEME)
    expect(() => saveTheme(DEFAULT_THEME, broken)).not.toThrow()
  })
})

describe('明暗判断', () => {
  it('浅色、深色固定；跟随系统时看系统设置', () => {
    expect(resolveDark('light', true)).toBe(false)
    expect(resolveDark('dark', false)).toBe(true)
    expect(resolveDark('system', true)).toBe(true)
    expect(resolveDark('system', false)).toBe(false)
  })
})
