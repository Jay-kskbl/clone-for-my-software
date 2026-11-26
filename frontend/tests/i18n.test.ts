// 界面语言切换（src/i18n）：中英两套文字结构一致、切换后标签跟着变、保存读取。
import { afterEach, describe, expect, it } from 'vitest'

import { isLocale, loadLocale, locale, m, saveLocale, translated } from '../src/i18n'
import { en, zh } from '../src/i18n/messages'
import { formatLocator, evidenceLabel } from '../src/utils/locator'
import { STATUS_LABEL, typeBadge } from '../src/utils/format'
import { cellText } from '../src/utils/channels'
import { SCAN_TEXT } from '../src/features/search-motion/messages'

afterEach(() => {
  locale.value = 'zh'
})

/** 把文字表展开成“路径 → 类型”，用来比较两套的结构 */
function shape(value: unknown, path = ''): string[] {
  if (Array.isArray(value)) return [`${path}:array(${value.length})`]
  if (value && typeof value === 'object') {
    return Object.entries(value).flatMap(([key, child]) => shape(child, path ? `${path}.${key}` : key))
  }
  return [`${path}:${typeof value}`]
}

describe('文字表', () => {
  it('中英两套的键、类型、数组长度完全一致', () => {
    expect(shape(en)).toEqual(shape(zh))
  })

  it('英文里没有漏掉的中文（语言名“中文”除外）', () => {
    const texts = shape(en).length
    expect(texts).toBeGreaterThan(100)
    const strings: string[] = []
    const collect = (value: unknown) => {
      if (typeof value === 'string') strings.push(value)
      else if (typeof value === 'function') strings.push(String((value as (...a: unknown[]) => unknown)(1, 'x', 'y')))
      else if (value && typeof value === 'object') Object.values(value).forEach(collect)
    }
    collect({ ...en, locale: { ...en.locale, zh: '' } })
    expect(strings.filter((s) => /[一-龥]/.test(s))).toEqual([])
  })
})

describe('切换', () => {
  it('m() 和 translated() 按当前语言取值', () => {
    const table = translated((msg) => ({ a: msg.app.title }))
    expect(m().app.title).toBe('智能文档管理系统')
    expect(table.a).toBe('智能文档管理系统')
    locale.value = 'en'
    expect(m().app.title).toBe('Smart Document Manager')
    expect(table.a).toBe('Smart Document Manager')
    expect(Object.keys(table)).toEqual(['a'])
  })

  it('页面用到的标签和文案跟着切换', () => {
    expect(STATUS_LABEL.processing.text).toBe('解析中')
    expect(formatLocator({ type: 'pdf_page', page: 3 })).toBe('第 3 页')
    expect(cellText({ channel: 'text', state: 'hit', rank: 2 })).toBe('第 2 名')
    expect(SCAN_TEXT.searching).toBe('正在检索…')
    locale.value = 'en'
    expect(STATUS_LABEL.processing.text).toBe('Parsing')
    expect(STATUS_LABEL.processing.type).toBe('warning')
    expect(formatLocator({ type: 'pdf_page', page: 3 })).toBe('Page 3')
    expect(formatLocator({ type: 'docx_para', para_index: 0 })).toBe('Paragraph 1')
    expect(evidenceLabel(null)).toBe('Matched file name or tags')
    expect(typeBadge('image/png').text).toBe('IMG')
    expect(cellText({ channel: 'text', state: 'hit', rank: 2 })).toBe('#2')
    expect(SCAN_TEXT.searching).toBe('Searching…')
  })
})

describe('保存与读取', () => {
  function memory() {
    const data = new Map<string, string>()
    return { getItem: (k: string) => data.get(k) ?? null, setItem: (k: string, v: string) => void data.set(k, v) }
  }

  it('保存后能读回；没有、不合法或存储抛异常时为中文', () => {
    const store = memory()
    expect(loadLocale(store)).toBe('zh')
    saveLocale('en', store)
    expect(loadLocale(store)).toBe('en')
    store.setItem('app-locale', 'fr')
    expect(loadLocale(store)).toBe('zh')
    const broken = {
      getItem: () => {
        throw new Error('SecurityError')
      },
      setItem: () => {
        throw new Error('QuotaExceededError')
      },
    }
    expect(loadLocale(broken)).toBe('zh')
    expect(() => saveLocale('en', broken)).not.toThrow()
    expect(isLocale('en')).toBe(true)
    expect(isLocale('EN')).toBe(false)
  })
})

describe('检索动效的文字只说真实发生的事（T24bh）', () => {
  it.each([
    ['中文', zh.scan],
    ['英文', en.scan],
  ])('%s：不出现文件计数，不说“阅读”“答案”', (_name, scan) => {
    for (const text of Object.values(scan)) {
      // 卡片数不是文件数；系统不打开文件，也不生成答案（GLOBAL §8.1、§13）
      expect(typeof text).toBe('string')
      expect(text).not.toMatch(/阅读|打开|答案|\d|read|open|answer/i)
    }
  })
})
