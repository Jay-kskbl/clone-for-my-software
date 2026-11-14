// 登录状态。整个前端只有这一处保存“当前用户是谁”。
//
// 令牌保存在 localStorage：刷新页面后不需要重新登录。代价是页面一旦被注入脚本，
// 令牌可能被读走；本项目不渲染用户提供的 HTML，令牌有效期也有限（默认 1 小时）。

import { reactive, readonly } from 'vue'

import * as authApi from './api/auth'
import { getToken, setToken } from './api/client'
import type { User } from './api/types'

interface AuthState {
  user: User | null
  /** 已经向后端确认过登录状态（无论结果如何）。路由守卫等它确认完再放行。 */
  ready: boolean
}

const state = reactive<AuthState>({ user: null, ready: false })

export const auth = readonly(state)

export async function login(username: string, password: string): Promise<void> {
  const token = await authApi.login(username, password)
  setToken(token.access_token)
  state.user = await authApi.fetchMe()
  state.ready = true
}

export function logout(): void {
  setToken(null)
  state.user = null
  state.ready = true
}

/** 页面加载时调用一次：本地有令牌就向后端确认它是否还有效。 */
export async function restoreSession(): Promise<void> {
  if (state.ready) return
  if (getToken()) {
    try {
      state.user = await authApi.fetchMe()
    } catch {
      // 令牌过期、账号被删或后端不可用：都按未登录处理
      setToken(null)
      state.user = null
    }
  }
  state.ready = true
}
