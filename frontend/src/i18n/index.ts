// 界面语言切换（T24bc，Barry 2026-11-22 提出：一个中文、一个英文）。项目不引入 i18n 库，自己写一个最小实现：
// - locale 是一个 ref，m() 返回当前语言的文字表；模板和 computed 里调用 m() 时会自动跟着语言刷新。
// - 原来写成常量表的标签（如 STATUS_LABEL）用 translated() 包一层，取值时才按当前语言生成，调用方不用改。
// - 选择保存在本机浏览器（localStorage），读写失败就用中文，不报错。
// - 切换时同步 <html lang> 和页面标题；Element Plus 自带的文字（分页、确认框按钮等）由 element.ts 跟着切换。
import { ref, watch } from 'vue'

import { en, zh, type Messages } from './messages'

export type Locale = 'zh' | 'en'

const STORAGE_KEY = 'app-locale'

export function isLocale(value: unknown): value is Locale {
  return value === 'zh' || value === 'en'
}

type StorageLike = Pick<Storage, 'getItem' | 'setItem'>

function storage(): StorageLike | null {
  try {
    return window.localStorage
  } catch {
    return null
  }
}

export function loadLocale(store: StorageLike | null = storage()): Locale {
  try {
    const value = store?.getItem(STORAGE_KEY)
    return isLocale(value) ? value : 'zh'
  } catch {
    return 'zh'
  }
}

export function saveLocale(value: Locale, store: StorageLike | null = storage()): void {
  try {
    store?.setItem(STORAGE_KEY, value)
  } catch {
    // 存不进去就只在本次页面生效
  }
}

export const locale = ref<Locale>(loadLocale())

/** 当前语言的文字表 */
export function m(): Messages {
  return locale.value === 'en' ? en : zh
}

/** 取值时才按当前语言生成的对象：把原来的常量标签表换成它，调用方的写法（TABLE[key]）不用改。 */
export function translated<T extends object>(build: (messages: Messages) => T): T {
  return new Proxy({} as T, {
    get: (_target, key) => Reflect.get(build(m()), key),
    has: (_target, key) => Reflect.has(build(m()), key),
    ownKeys: () => Reflect.ownKeys(build(m())),
    getOwnPropertyDescriptor: (_target, key) => {
      const value = Reflect.get(build(m()), key)
      return value === undefined ? undefined : { enumerable: true, configurable: true, value }
    },
  })
}

function syncDocument(): void {
  if (typeof document === 'undefined') return
  document.documentElement.lang = locale.value === 'en' ? 'en' : 'zh-CN'
  document.title = m().app.title
}

let started = false

/** 在挂载应用之前调用一次：同步 <html lang> 和标题，之后语言一变就保存并同步。 */
export function initLocale(): void {
  if (started) return
  started = true
  syncDocument()
  watch(locale, (value) => {
    saveLocale(value)
    syncDocument()
  })
}
