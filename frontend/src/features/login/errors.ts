// 登录页的错误文字（T24y）：登录页会遇到的后端错误码给出更具体的说明，其余显示后端原文。
//
// 后端的说明是通用的：用户名已存在时只说“用户名已存在”，参数不合格时给出 Pydantic 的原始描述
// （“请求参数不合法：body.username: String should …”），普通用户看不懂也不知道下一步怎么做。
// 前端自己生成的错误（连不上服务器、开发代理 502 等，见 api/client.ts）本来就是中文说明，原样显示。
import { ApiError, errorMessage } from '../../api/client'

/** 错误码 → 登录页上显示的说明。用 Map 而不是普通对象：未知错误码不会意外取到原型上的属性 */
export const LOGIN_ERROR_TEXT: ReadonlyMap<string, string> = new Map([
  ['INVALID_CREDENTIALS', '用户名或密码错误'],
  ['USERNAME_TAKEN', '这个用户名已被注册。换一个用户名，或切换到登录'],
  ['VALIDATION_ERROR', '用户名或密码不符合要求：用户名 3–32 个字符，密码 8–128 个字符'],
  ['DATABASE_UNAVAILABLE', '数据库暂时不可用，请稍后再试'],
  ['INTERNAL_ERROR', '服务器内部错误，请稍后再试'],
])

export function loginErrorText(error: unknown): string {
  if (error instanceof ApiError) return LOGIN_ERROR_TEXT.get(error.code) ?? error.message
  // 不是接口错误（例如登录后跳转时抛出的异常）：通用说明
  return errorMessage(error)
}
