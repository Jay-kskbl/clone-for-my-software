// 登录页的错误文字（T24y，T24bc 起随界面语言）：按错误码给出当前语言的说明。
//
// 后端返回的错误说明只有中文（如“用户名或密码错误”），英文界面下原样显示会中英混杂。
// 登录页会遇到的错误码在这里翻译；没列出的错误码仍显示后端原文。
// 每次显示时才按当前语言生成：页面保存的是错误对象，切换语言后提示跟着变。
import { ApiError } from '../../api/client'
import { m } from '../../i18n'

export function loginErrorText(error: unknown): string {
  if (!(error instanceof ApiError)) return m().api.unexpected
  const text = m().login.errors
  switch (error.code) {
    case 'INVALID_CREDENTIALS':
      return text.invalidCredentials
    case 'USERNAME_TAKEN':
      return text.usernameTaken
    case 'VALIDATION_ERROR':
      return text.validation
    case 'DATABASE_UNAVAILABLE':
      return text.databaseUnavailable
    case 'INTERNAL_ERROR':
      return text.internal
    // 下面三种是前端自己生成的（api/client.ts），文字已经是生成时的语言；这里按当前语言重新生成
    case 'NETWORK':
      return m().api.network
    case 'UNAVAILABLE':
      return m().api.unavailable(error.status)
    case 'UNKNOWN':
      return m().api.failed(error.status)
    default:
      return error.message
  }
}
