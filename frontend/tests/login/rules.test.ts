// 登录 / 注册表单的校验规则（T24w）：边界与后端一致（docs/api.md §4.2），提示随界面语言。
import type { FormItemRule } from 'element-plus'
import { afterEach, describe, expect, it } from 'vitest'

import {
  checkNewPassword,
  checkNewUsername,
  LOGIN_RULES,
  REGISTER_RULES,
  requirePassword,
  requireUsername,
} from '../../src/features/login/rules'
import { locale } from '../../src/i18n'
import { en, zh } from '../../src/i18n/messages'

afterEach(() => {
  locale.value = 'zh'
})

describe('注册时的用户名', () => {
  it.each(['abc', 'a'.repeat(32), 'Barry_2026', 'a.b-c_d', '___'])('合格：%s', (value) => {
    expect(checkNewUsername(value)).toBeNull()
  })

  it('没填', () => {
    expect(checkNewUsername('')).toBe(zh.login.usernameRequired)
  })

  it.each([
    ['2 个字符', 'ab'],
    ['33 个字符', 'a'.repeat(33)],
    ['中文', '巴里巴里'],
    ['空格', 'bar ry'],
    ['@', 'barry@x'],
    ['斜杠', 'a/b'],
  ])('不合格：%s', (_name, value) => {
    expect(checkNewUsername(value)).toBe(zh.login.usernamePattern)
  })
})

describe('注册时的密码', () => {
  it.each([
    ['8 个字符', 'x'.repeat(8)],
    ['128 个字符', 'x'.repeat(128)],
    ['中文和空格也算字符', '我的密码 很长哦'],
    // 后端按 Python 的 len 计数：一个 emoji 是 1 个字符。127 个 x + 1 个 emoji = 128
    ['emoji 按 1 个字符算', `${'x'.repeat(127)}😀`],
  ])('合格：%s', (_name, value) => {
    expect(checkNewPassword(value)).toBeNull()
  })

  it('没填', () => {
    expect(checkNewPassword('')).toBe(zh.login.passwordRequired)
  })

  it.each([
    ['7 个字符', 'x'.repeat(7)],
    ['129 个字符', 'x'.repeat(129)],
    ['7 个 emoji（UTF-16 长度 14，但只有 7 个字符）', '😀'.repeat(7)],
  ])('长度不合格：%s', (_name, value) => {
    expect(checkNewPassword(value)).toBe(zh.login.passwordLength)
  })
})

describe('登录时只检查填了没有', () => {
  it('格式不对也放行', () => {
    expect(requireUsername('a')).toBeNull()
    expect(requirePassword('1')).toBeNull()
  })

  it('没填时提示', () => {
    expect(requireUsername('')).toBe(zh.login.usernameRequired)
    expect(requirePassword('')).toBe(zh.login.passwordRequired)
  })
})

/** 像 Element Plus 那样调用规则里的 validator，返回错误文字（没有错误时为 null） */
function run(rules: FormItemRule[] | undefined, value: unknown): string | null {
  const rule = rules?.[0]
  if (!rule?.validator) throw new Error('规则缺少 validator')
  let result: string | null = 'not called'
  rule.validator(rule, value, (error?: string | Error) => {
    result = error ? (error instanceof Error ? error.message : error) : null
  }, {}, {})
  return result
}

describe('表单规则', () => {
  it('四条规则都标为必填（标签前的红色星号），失去焦点时检查', () => {
    for (const rules of [LOGIN_RULES, REGISTER_RULES]) {
      for (const field of ['username', 'password'] as const) {
        const list = rules[field] as FormItemRule[]
        expect(list).toHaveLength(1)
        expect(list[0].required).toBe(true)
        expect(list[0].trigger).toBe('blur')
      }
    }
  })

  it('登录规则：只检查填了没有', () => {
    expect(run(LOGIN_RULES.username as FormItemRule[], 'a')).toBeNull()
    expect(run(LOGIN_RULES.username as FormItemRule[], '')).toBe(zh.login.usernameRequired)
    expect(run(LOGIN_RULES.password as FormItemRule[], '')).toBe(zh.login.passwordRequired)
  })

  it('注册规则：检查格式和长度；值不是字符串时按没填处理', () => {
    expect(run(REGISTER_RULES.username as FormItemRule[], 'ab')).toBe(zh.login.usernamePattern)
    expect(run(REGISTER_RULES.username as FormItemRule[], undefined)).toBe(zh.login.usernameRequired)
    expect(run(REGISTER_RULES.password as FormItemRule[], 'x'.repeat(7))).toBe(zh.login.passwordLength)
    expect(run(REGISTER_RULES.password as FormItemRule[], 'x'.repeat(8))).toBeNull()
  })

  it('提示文字在校验时按当前语言取，切换语言后不用重建规则', () => {
    locale.value = 'en'
    expect(run(REGISTER_RULES.username as FormItemRule[], 'ab')).toBe(en.login.usernamePattern)
    expect(run(LOGIN_RULES.password as FormItemRule[], '')).toBe(en.login.passwordRequired)
  })
})
