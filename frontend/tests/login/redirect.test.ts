// 登录后的跳转地址（登录页结构优化 L1）：只接受站内路径，其余回到首页。
import { describe, expect, it } from 'vitest'

import { safeRedirect } from '../../src/features/login/redirect'

describe('safeRedirect', () => {
  it.each([
    ['/', '/'],
    ['/search', '/search'],
    ['/search?q=合同&channels=text', '/search?q=合同&channels=text'],
    ['/documents/3f2c?view=text#chunk-2', '/documents/3f2c?view=text#chunk-2'],
    // 以 /login 开头但不是登录页
    ['/loginhelp', '/loginhelp'],
  ])('站内路径原样保留：%s', (raw, expected) => {
    expect(safeRedirect(raw)).toBe(expected)
  })

  it.each([
    ['协议相对地址', '//evil.com'],
    ['协议相对地址带路径', '//evil.com/search'],
    ['反斜杠', '/\\evil.com'],
    ['反斜杠在后面', '/search\\x'],
    ['完整网址', 'https://evil.com/'],
    ['javascript 协议', 'javascript:alert(1)'],
    ['相对路径', 'search'],
    ['空字符串', ''],
    ['制表符', '/\t/evil.com'],
    ['换行', '/\n/evil.com'],
    ['DEL 字符', '/\u007f'],
    ['登录页本身', '/login'],
    ['登录页带参数', '/login?redirect=/search'],
    ['登录页带锚点', '/login#x'],
  ])('不合格时回到首页：%s', (_name, raw) => {
    expect(safeRedirect(raw)).toBe('/')
  })

  it.each([
    ['undefined', undefined],
    ['null（?redirect 没有值）', null],
    ['数组（同一个参数出现两次）', ['/search', '/documents']],
    ['数字', 42],
  ])('不是字符串时回到首页：%s', (_name, raw) => {
    expect(safeRedirect(raw)).toBe('/')
  })
})
