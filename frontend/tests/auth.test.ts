// 登录状态（src/auth.ts）：恢复会话时只有 401 才删除令牌，连不上服务器时保留（登录页结构优化 L2）。
// fetch 和 localStorage 用假的实现替换，不需要浏览器，也不需要后端。
// auth.ts 的状态是模块级的单例，每个测试重新导入一份。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

type AuthModule = typeof import('../src/auth')
type ClientModule = typeof import('../src/api/client')

const USER = { id: 'u1', username: 'barry', role: 'user', created_at: '2026-11-22T00:00:00Z' }

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

let store: Map<string, string>
let fetchMock: ReturnType<typeof vi.fn>
let authModule: AuthModule
let client: ClientModule

beforeEach(async () => {
  store = new Map()
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => void store.set(key, value),
    removeItem: (key: string) => void store.delete(key),
  })
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
  vi.resetModules()
  client = await import('../src/api/client')
  authModule = await import('../src/auth')
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('restoreSession', () => {
  it('本地没有令牌：不发请求，直接按未登录处理', async () => {
    await authModule.restoreSession()

    expect(fetchMock).not.toHaveBeenCalled()
    expect(authModule.auth).toMatchObject({ user: null, ready: true, unreachable: false })
  })

  it('令牌有效：读到当前用户', async () => {
    client.setToken('t1')
    fetchMock.mockResolvedValue(jsonResponse(200, USER))

    await authModule.restoreSession()

    expect(authModule.auth.user?.username).toBe('barry')
    expect(authModule.auth).toMatchObject({ ready: true, unreachable: false })
    expect(client.getToken()).toBe('t1')
  })

  it('确认过一次后不再发请求', async () => {
    client.setToken('t1')
    fetchMock.mockResolvedValue(jsonResponse(200, USER))

    await authModule.restoreSession()
    await authModule.restoreSession()

    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('401：令牌无效，删除令牌', async () => {
    client.setToken('expired')
    fetchMock.mockResolvedValue(jsonResponse(401, { error: { code: 'UNAUTHENTICATED', message: '令牌无效或已过期' } }))

    await authModule.restoreSession()

    expect(client.getToken()).toBeNull()
    expect(authModule.auth).toMatchObject({ user: null, ready: true, unreachable: false })
  })

  it.each([
    ['网络不通', () => Promise.reject(new TypeError('Failed to fetch'))],
    ['后端没启动，开发代理返回 502', () => Promise.resolve(new Response('Bad Gateway', { status: 502 }))],
    ['数据库不可用 503', () => Promise.resolve(jsonResponse(503, { error: { code: 'DATABASE_UNAVAILABLE', message: '数据库不可用，请稍后重试' } }))],
    ['服务器内部错误 500', () => Promise.resolve(jsonResponse(500, { error: { code: 'INTERNAL_ERROR', message: '服务器内部错误' } }))],
  ])('%s：保留令牌，标记连不上，下次再确认', async (_name, respond) => {
    client.setToken('t1')
    fetchMock.mockImplementation(respond)

    await authModule.restoreSession()

    expect(client.getToken()).toBe('t1')
    expect(authModule.auth).toMatchObject({ user: null, ready: false, unreachable: true })
  })

  it('连不上之后服务恢复：再次确认即登录，不用重新输入密码', async () => {
    client.setToken('t1')
    fetchMock.mockResolvedValueOnce(new Response('Bad Gateway', { status: 502 }))
    await authModule.restoreSession()
    expect(authModule.auth.unreachable).toBe(true)

    fetchMock.mockResolvedValueOnce(jsonResponse(200, USER))
    await authModule.restoreSession()

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(authModule.auth.user?.username).toBe('barry')
    expect(authModule.auth).toMatchObject({ ready: true, unreachable: false })
  })

  it('连不上之后服务恢复但令牌已过期：删除令牌', async () => {
    client.setToken('t1')
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    await authModule.restoreSession()

    fetchMock.mockResolvedValueOnce(jsonResponse(401, { error: { code: 'UNAUTHENTICATED', message: '令牌无效或已过期' } }))
    await authModule.restoreSession()

    expect(client.getToken()).toBeNull()
    expect(authModule.auth).toMatchObject({ user: null, ready: true, unreachable: false })
  })
})

describe('login / logout', () => {
  it('连不上之后登录成功：清掉连不上的标记', async () => {
    client.setToken('old')
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    await authModule.restoreSession()

    fetchMock
      .mockResolvedValueOnce(jsonResponse(200, { access_token: 'new', token_type: 'bearer', expires_in: 3600 }))
      .mockResolvedValueOnce(jsonResponse(200, USER))
    await authModule.login('barry', 'password1')

    expect(client.getToken()).toBe('new')
    expect(authModule.auth).toMatchObject({ ready: true, unreachable: false })
    expect(authModule.auth.user?.username).toBe('barry')
  })

  it('退出登录：删除令牌并清掉连不上的标记', async () => {
    client.setToken('t1')
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    await authModule.restoreSession()

    authModule.logout()

    expect(client.getToken()).toBeNull()
    expect(authModule.auth).toMatchObject({ user: null, ready: true, unreachable: false })
  })
})

describe('点了“重试”还没返回时又登录（新功能联测 V4）', () => {
  function pendingMe() {
    let respond!: (response: Response) => void
    fetchMock.mockImplementationOnce(() => new Promise<Response>((resolve) => (respond = resolve)))
    return (response: Response) => respond(response)
  }

  async function loginWhileRestoring() {
    const respond = pendingMe()
    const restoring = authModule.restoreSession()
    fetchMock
      .mockResolvedValueOnce(jsonResponse(200, { access_token: 'new', token_type: 'bearer', expires_in: 3600 }))
      .mockResolvedValueOnce(jsonResponse(200, USER))
    await authModule.login('barry', 'password1')
    return async (response: Response) => {
      respond(response)
      await restoring
    }
  }

  beforeEach(async () => {
    client.setToken('old')
    client.setUnauthenticatedHandler(authModule.logout)
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    await authModule.restoreSession()
  })

  it('旧令牌的 401 后到：不把刚登录的人退出', async () => {
    const finish = await loginWhileRestoring()
    await finish(jsonResponse(401, { error: { code: 'UNAUTHENTICATED', message: '令牌无效或已过期' } }))

    expect(client.getToken()).toBe('new')
    expect(authModule.auth.user?.username).toBe('barry')
  })

  it('旧令牌的用户信息后到：不盖掉刚登录的用户', async () => {
    const finish = await loginWhileRestoring()
    await finish(jsonResponse(200, { ...USER, id: 'u0', username: 'someone-else' }))

    expect(authModule.auth.user?.username).toBe('barry')
  })

  it('旧请求连不上：不标记连不上', async () => {
    const finish = await loginWhileRestoring()
    await finish(jsonResponse(503, { error: { code: 'DATABASE_UNAVAILABLE', message: '数据库不可用' } }))

    expect(client.getToken()).toBe('new')
    expect(authModule.auth).toMatchObject({ ready: true, unreachable: false })
  })
})
