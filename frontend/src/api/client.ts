// 所有请求的统一出口：带上登录令牌，把后端的错误结构转换成 ApiError。

const TOKEN_KEY = 'docmgr.token'

/** 后端返回的错误：{"error": {"code", "message"}}（docs/api.md §1.2）。 */
export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null): void {
  if (token === null) {
    localStorage.removeItem(TOKEN_KEY)
  } else {
    localStorage.setItem(TOKEN_KEY, token)
  }
}

// 令牌失效（401）时要做的事，由 main.ts 注册：清掉登录状态并回到登录页。
// 用回调而不是在这里直接引用路由，避免 api 层依赖页面层。
let onUnauthenticated: (() => void) | null = null

export function setUnauthenticatedHandler(handler: () => void): void {
  onUnauthenticated = handler
}

type Query = Record<string, string | number | undefined | null>

export interface RequestOptions {
  method?: string
  query?: Query
  /** 普通对象按 JSON 发送；FormData 原样发送（上传文件用）。 */
  body?: unknown
}

function buildUrl(path: string, query?: Query): string {
  if (!query) return path
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value))
  }
  const text = params.toString()
  return text ? `${path}?${text}` : path
}

async function toApiError(response: Response): Promise<ApiError> {
  try {
    const data = (await response.json()) as { error?: { code?: string; message?: string } }
    if (data.error?.code && data.error.message) {
      return new ApiError(response.status, data.error.code, data.error.message)
    }
  } catch {
    // 响应不是 JSON（例如后端没启动时开发代理返回的错误页），走下面的兜底
  }
  // 502/503/504 且不是后端自己的错误结构：请求没有到达后端（后端没启动，或中间的代理连不上它）
  if (response.status >= 502 && response.status <= 504) {
    return new ApiError(response.status, 'UNAVAILABLE', `服务暂时不可用（HTTP ${response.status}），请确认后端已启动`)
  }
  return new ApiError(response.status, 'UNKNOWN', `请求失败（HTTP ${response.status}）`)
}

/** 发请求并返回原始响应；非 2xx 时抛 ApiError，网络不通时抛 code 为 NETWORK 的 ApiError。 */
export async function requestRaw(path: string, options: RequestOptions = {}): Promise<Response> {
  const headers = new Headers()
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  let body: BodyInit | undefined
  if (options.body instanceof FormData) {
    // 不手动设置 Content-Type：浏览器会自己加上带分隔符的 multipart/form-data
    body = options.body
  } else if (options.body !== undefined) {
    headers.set('Content-Type', 'application/json')
    body = JSON.stringify(options.body)
  }

  let response: Response
  try {
    response = await fetch(buildUrl(path, options.query), {
      method: options.method ?? 'GET',
      headers,
      body,
    })
  } catch {
    throw new ApiError(0, 'NETWORK', '无法连接服务器，请检查网络或确认后端已启动')
  }

  if (response.ok) return response

  const error = await toApiError(response)
  // 登录接口自己的 401（密码错误）不算“登录状态失效”。等待期间令牌已经换了（重新登录了）也不算：
  // 那是旧令牌的 401，与现在的登录状态无关（T24bb）
  if (error.status === 401 && error.code === 'UNAUTHENTICATED' && getToken() === token) onUnauthenticated?.()
  throw error
}

/** 发请求并把响应按 JSON 解析；204 无内容时返回 undefined。 */
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await requestRaw(path, options)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

/** 把任意异常变成可以直接显示给用户的一句话。 */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  return '发生了未预期的错误'
}
