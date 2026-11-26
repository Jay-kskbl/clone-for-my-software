// 登录 / 注册表单的校验规则（T24w，从 LoginView.vue 移出）。
//
// 注册时的要求与后端一致（docs/api.md §4.2）。这里只是为了尽早提示，后端仍会再校验一次。
// 登录时只检查“填了没有”：格式不对就是登录失败，不提前说明用户名该长什么样。
//
// 检查本身写成返回错误文字的纯函数，规则只是把它包成 Element Plus 的 validator，
// 所以测试测到的就是页面实际用的判断。提示文字在校验时才按当前语言取（m()），规则本身不用随语言重建。
import type { FormItemRule, FormRules } from 'element-plus'

import { m } from '../../i18n'

/** 用户名：3–32 个字符，只允许英文字母、数字、下划线、点、连字符（与后端相同，区分大小写） */
export const USERNAME_PATTERN = /^[A-Za-z0-9_.-]{3,32}$/
export const PASSWORD_MIN = 8
export const PASSWORD_MAX = 128

/** 返回 null 表示没有问题，否则是要显示的提示 */
export type Check = (value: string) => string | null

export const requireUsername: Check = (value) => (value === '' ? m().login.usernameRequired : null)
export const requirePassword: Check = (value) => (value === '' ? m().login.passwordRequired : null)

export const checkNewUsername: Check = (value) =>
  requireUsername(value) ?? (USERNAME_PATTERN.test(value) ? null : m().login.usernamePattern)

export const checkNewPassword: Check = (value) => {
  const missing = requirePassword(value)
  if (missing) return missing
  // 按字符数而不是 UTF-16 长度算，和后端（Python 的 len）一致：一个 emoji 算 1 个字符
  const length = [...value].length
  return length < PASSWORD_MIN || length > PASSWORD_MAX ? m().login.passwordLength : null
}

function rule(check: Check): FormItemRule {
  return {
    // required 只用来让 Element Plus 在标签前显示红色星号；真正的判断全在 validator 里
    required: true,
    trigger: 'blur',
    validator: (_rule, value, callback) => {
      const problem = check(typeof value === 'string' ? value : '')
      callback(problem === null ? undefined : new Error(problem))
    },
  }
}

export const LOGIN_RULES: FormRules = {
  username: [rule(requireUsername)],
  password: [rule(requirePassword)],
}

export const REGISTER_RULES: FormRules = {
  username: [rule(checkNewUsername)],
  password: [rule(checkNewPassword)],
}
