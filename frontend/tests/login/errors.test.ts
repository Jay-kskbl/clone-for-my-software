// 登录页的错误文字（T24y，T24bc 起随界面语言）：按错误码给出当前语言的说明，没列出的错误码显示后端原文。
import { afterEach, describe, expect, it } from 'vitest'

import { ApiError } from '../../src/api/client'
import { loginErrorText } from '../../src/features/login/errors'
import { locale } from '../../src/i18n'
import { en, zh } from '../../src/i18n/messages'

afterEach(() => {
  locale.value = 'zh'
})

// 后端的说明只有中文（backend/app/modules/auth/service.py 等）
const CASES: [code: string, status: number, backend: string, pick: (t: typeof zh) => string][] = [
  ['INVALID_CREDENTIALS', 401, '用户名或密码错误', (t) => t.login.errors.invalidCredentials],
  ['USERNAME_TAKEN', 409, '用户名已存在', (t) => t.login.errors.usernameTaken],
  ['VALIDATION_ERROR', 422, '请求参数不合法：body.username: String should have at least 3 characters', (t) => t.login.errors.validation],
  ['DATABASE_UNAVAILABLE', 503, '数据库不可用，请稍后重试', (t) => t.login.errors.databaseUnavailable],
  ['INTERNAL_ERROR', 500, '服务器内部错误', (t) => t.login.errors.internal],
]

describe('后端错误码', () => {
  it.each(CASES)('%s：中文、英文界面各给出对应文字', (code, status, backend, pick) => {
    const error = new ApiError(status, code, backend)
    expect(loginErrorText(error)).toBe(pick(zh))
    locale.value = 'en'
    expect(loginErrorText(error)).toBe(pick(en))
    expect(loginErrorText(error)).not.toMatch(/[一-龥]/)
  })

  it('没列出的错误码：显示后端原文', () => {
    const error = new ApiError(403, 'FORBIDDEN', '没有权限')
    expect(loginErrorText(error)).toBe('没有权限')
    locale.value = 'en'
    expect(loginErrorText(error)).toBe('没有权限')
  })
})

describe('前端生成的错误（api/client.ts）', () => {
  it('网络不通：按当前语言重新生成，不用生成时的语言', () => {
    // 模拟出错时界面是中文，之后切到英文
    const error = new ApiError(0, 'NETWORK', zh.api.network)
    expect(loginErrorText(error)).toBe(zh.api.network)
    locale.value = 'en'
    expect(loginErrorText(error)).toBe(en.api.network)
  })

  it('后端没启动（开发代理 502）：带上状态码', () => {
    const error = new ApiError(502, 'UNAVAILABLE', zh.api.unavailable(502))
    locale.value = 'en'
    expect(loginErrorText(error)).toBe(en.api.unavailable(502))
    expect(loginErrorText(error)).toContain('502')
  })

  it('其他无法识别的应答：带上状态码', () => {
    const error = new ApiError(418, 'UNKNOWN', zh.api.failed(418))
    expect(loginErrorText(error)).toBe(zh.api.failed(418))
    locale.value = 'en'
    expect(loginErrorText(error)).toBe(en.api.failed(418))
  })

  it('不是 ApiError（例如跳转时抛出的异常）：通用说明', () => {
    expect(loginErrorText(new TypeError('x'))).toBe(zh.api.unexpected)
    expect(loginErrorText('oops')).toBe(zh.api.unexpected)
    locale.value = 'en'
    expect(loginErrorText(null)).toBe(en.api.unexpected)
  })
})
