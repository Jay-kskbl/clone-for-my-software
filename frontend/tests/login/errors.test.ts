// 登录页的错误文字（T24y）：登录页会遇到的错误码给出具体说明，没列出的错误码显示后端原文。
import { describe, expect, it } from 'vitest'

import { ApiError } from '../../src/api/client'
import { LOGIN_ERROR_TEXT, loginErrorText } from '../../src/features/login/errors'

// 后端给出的原文（backend/app/api/errors.py、各模块的错误类）
const CASES: [code: string, status: number, backend: string][] = [
  ['INVALID_CREDENTIALS', 401, '用户名或密码错误'],
  ['USERNAME_TAKEN', 409, '用户名已存在'],
  ['VALIDATION_ERROR', 422, '请求参数不合法：body.username: String should have at least 3 characters'],
  ['DATABASE_UNAVAILABLE', 503, '数据库不可用，请稍后重试'],
  ['INTERNAL_ERROR', 500, '服务器内部错误'],
]

describe('后端错误码', () => {
  it.each(CASES)('%s：显示登录页自己的说明', (code, status, backend) => {
    const text = loginErrorText(new ApiError(status, code, backend))
    expect(text).toBe(LOGIN_ERROR_TEXT.get(code))
    expect(text).not.toBe('')
  })

  it('参数不合格：不显示后端的技术性原文', () => {
    const text = loginErrorText(new ApiError(422, 'VALIDATION_ERROR', '请求参数不合法：body.username: String should …'))
    expect(text).not.toContain('body.username')
    expect(text).toContain('3–32')
  })

  it('没列出的错误码：显示后端原文', () => {
    expect(loginErrorText(new ApiError(403, 'FORBIDDEN', '没有权限'))).toBe('没有权限')
  })

  it('错误码恰好是对象原型上的名字：仍显示后端原文', () => {
    expect(loginErrorText(new ApiError(400, 'constructor', '原文'))).toBe('原文')
  })
})

describe('前端生成的错误（api/client.ts）：原样显示', () => {
  it.each([
    ['网络不通', new ApiError(0, 'NETWORK', '无法连接服务器，请检查网络或确认后端已启动')],
    ['后端没启动（开发代理 502）', new ApiError(502, 'UNAVAILABLE', '服务暂时不可用（HTTP 502），请确认后端已启动')],
    ['无法识别的应答', new ApiError(418, 'UNKNOWN', '请求失败（HTTP 418）')],
  ])('%s', (_name, error) => {
    expect(loginErrorText(error)).toBe(error.message)
  })

  it('不是 ApiError（例如跳转时抛出的异常）：通用说明', () => {
    expect(loginErrorText(new TypeError('x'))).toBe('发生了未预期的错误')
    expect(loginErrorText(null)).toBe('发生了未预期的错误')
  })
})
