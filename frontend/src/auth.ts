// 登录状态。整个前端只有这一处保存“当前用户是谁”。
//
// 令牌保存在 localStorage：刷新页面后不需要重新登录。代价是页面一旦被注入脚本，
// 令牌可能被读走；本项目不渲染用户提供的 HTML，令牌有效期也有限（默认 1 小时）。

import { reactive, readonly } from 'vue'

import * as authApi from './api/auth'
import { ApiError, getToken, setToken } from './api/client'
import type { User } from './api/types'

interface AuthState {
  user: User | null
  /** 已经向后端确认过登录状态（无论结果如何）。路由守卫等它确认完再放行。 */
  ready: boolean
  /**
   * 上一次确认登录状态时连不上服务器（登录页结构优化 L2）。这时本地令牌保留、ready 保持 false，
   * 下一次导航或在登录页点“重试”时再确认；登录页据此显示提示。
   */
  unreachable: boolean
}

const state = reactive<AuthState>({ user: null, ready: false, unreachable: false })

export const auth = readonly(state)

export async function login(username: string, password: string): Promise<void> {
  const token = await authApi.login(username, password)
  setToken(token.access_token)
  state.user = await authApi.fetchMe()
  state.ready = true
  state.unreachable = false
}

export function logout(): void {
  setToken(null)
  state.user = null
  state.ready = true
  state.unreachable = false
}

/**
 * 是否只是“暂时确认不了”：网络不通（status 0）或服务器 5xx（后端没启动时开发代理的 502、
 * 数据库不可用的 503 等）。这时令牌本身可能仍然有效，不能删。
 */
function cannotConfirm(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 0 || error.status >= 500)
}

/**
 * 路由守卫在每次导航前调用：本地有令牌就向后端确认它是否还有效，确认过一次之后直接返回。
 *
 * 只有后端明确说令牌无效（401）时才删除令牌。原来任何失败都删，后端重启或网络短暂断开时，
 * 用户一刷新页面就被退出了（问题 A1）。连不上时保留令牌，按“暂时未登录”处理，ready 不置位，
 * 下一次调用会重新确认。
 */
export async function restoreSession(): Promise<void> {
  if (state.ready) return
  if (!getToken()) {
    state.unreachable = false
    state.ready = true
    return
  }
  try {
    state.user = await authApi.fetchMe()
  } catch (error) {
    state.user = null
    if (cannotConfirm(error)) {
      state.unreachable = true
      return
    }
    // 401（令牌过期、账号被删）或其他意外错误：按未登录处理
    setToken(null)
  }
  state.unreachable = false
  state.ready = true
}
