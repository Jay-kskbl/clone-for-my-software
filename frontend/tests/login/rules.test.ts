// 登录 / 注册表单的校验规则（T24w）：边界与后端一致（docs/api.md §4.2）。
import type { FormItemRule } from 'element-plus'
import { describe, expect, it } from 'vitest'

import {
  checkNewPassword,
  checkNewUsername,
  LOGIN_RULES,
  REGISTER_RULES,
  requirePassword,
  requireUsername,
  RULE_TEXT,
} from '../../src/features/login/rules'

describe('注册时的用户名', () => {
  it.each(['abc', 'a'.repeat(32), 'Barry_2026', 'a.b-c_d', '___'])('合格：%s', (value) => {
    expect(checkNewUsername(value)).toBeNull()
  })

  it('没填', () => {
    expect(checkNewUsername('')).toBe(RULE_TEXT.usernameRequired)
  })

  it.each([
    ['2 个字符', 'ab'],
    ['33 个字符', 'a'.repeat(33)],
    ['中文', '巴里巴里'],
    ['空格', 'bar ry'],
    ['@', 'barry@x'],
    ['斜杠', 'a/b'],
  ])('不合格：%s', (_name, value) => {
    expect(checkNewUsername(value)).toBe(RULE_TEXT.usernamePattern)
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
    expect(checkNewPassword('')).toBe(RULE_TEXT.passwordRequired)
  })

  it.each([
    ['7 个字符', 'x'.repeat(7)],
    ['129 个字符', 'x'.repeat(129)],
    ['7 个 emoji（UTF-16 长度 14，但只有 7 个字符）', '😀'.repeat(7)],
  ])('长度不合格：%s', (_name, value) => {
    expect(checkNewPassword(value)).toBe(RULE_TEXT.passwordLength)
  })
})

describe('登录时只检查填了没有', () => {
  it('格式不对也放行', () => {
    expect(requireUsername('a')).toBeNull()
    expect(requirePassword('1')).toBeNull()
  })

  it('没填时提示', () => {
    expect(requireUsername('')).toBe(RULE_TEXT.usernameRequired)
    expect(requirePassword('')).toBe(RULE_TEXT.passwordRequired)
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
    expect(run(LOGIN_RULES.username as FormItemRule[], '')).toBe(RULE_TEXT.usernameRequired)
    expect(run(LOGIN_RULES.password as FormItemRule[], '')).toBe(RULE_TEXT.passwordRequired)
  })

  it('注册规则：检查格式和长度；值不是字符串时按没填处理', () => {
    expect(run(REGISTER_RULES.username as FormItemRule[], 'ab')).toBe(RULE_TEXT.usernamePattern)
    expect(run(REGISTER_RULES.username as FormItemRule[], undefined)).toBe(RULE_TEXT.usernameRequired)
    expect(run(REGISTER_RULES.password as FormItemRule[], 'x'.repeat(7))).toBe(RULE_TEXT.passwordLength)
    expect(run(REGISTER_RULES.password as FormItemRule[], 'x'.repeat(8))).toBeNull()
  })

  it('提示文字与拆分前登录页上的相同', () => {
    expect(RULE_TEXT).toEqual({
      usernameRequired: '请输入用户名',
      usernamePattern: '3–32 个字符，只能包含英文字母、数字、下划线、点、连字符',
      passwordRequired: '请输入密码',
      passwordLength: '8–128 个字符',
    })
  })
})
