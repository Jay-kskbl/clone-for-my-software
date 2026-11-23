// 登录页打开时的服务状态检查（T24z）：只看后端是否连得上、数据库是否可用。
import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchHealth } from '../../src/api/health'
import type { ComponentStatus, HealthResponse } from '../../src/api/types'
import { ApiError } from '../../src/api/client'
import { checkLoginService } from '../../src/features/login/serviceStatus'

const OK: ComponentStatus = { status: 'ok', detail: null }
const DOWN: ComponentStatus = { status: 'unavailable', detail: 'ConnectError' }

function health(over: Partial<HealthResponse> = {}): HealthResponse {
  const merged = { database: OK, opensearch: OK, clip_service: OK, ...over }
  const allOk = [merged.database, merged.opensearch, merged.clip_service].every((c) => c.status === 'ok')
  return { status: allOk ? 'ok' : 'degraded', ...merged }
}

const resolve = (value: unknown) => () => Promise.resolve(value as HealthResponse)
const reject = (error: unknown) => () => Promise.reject(error)

describe('后端应答了', () => {
  it('全部正常：可以登录', async () => {
    expect(await checkLoginService(resolve(health()))).toBe('ok')
  })

  it('数据库不可用：提示数据库', async () => {
    expect(await checkLoginService(resolve(health({ database: { status: 'unavailable', detail: 'OperationalError' } })))).toBe(
      'database-down',
    )
  })

  it('只有 OpenSearch 或 CLIP 不可用：不影响登录，不提示', async () => {
    expect(await checkLoginService(resolve(health({ opensearch: DOWN })))).toBe('ok')
    expect(await checkLoginService(resolve(health({ clip_service: DOWN })))).toBe('ok')
    expect(await checkLoginService(resolve(health({ opensearch: DOWN, clip_service: DOWN })))).toBe('ok')
  })

  it.each([
    ['空对象', {}],
    ['null', null],
    ['database 的 status 不认识', { database: { status: 'maybe' } }],
  ])('应答格式不对（%s）：查不清楚，不提示', async (_name, body) => {
    expect(await checkLoginService(resolve(body))).toBe('unknown')
  })
})

describe('请求失败', () => {
  it('网络不通：后端连不上', async () => {
    expect(await checkLoginService(reject(new ApiError(0, 'NETWORK', '无法连接服务器')))).toBe('backend-down')
  })

  it.each([502, 503, 504])('开发代理返回 %i（后端没启动）：后端连不上', async (status) => {
    expect(await checkLoginService(reject(new ApiError(status, 'UNAVAILABLE', 'x')))).toBe('backend-down')
  })

  it.each([
    ['后端自己的 500', new ApiError(500, 'INTERNAL_ERROR', '服务器内部错误')],
    ['404（后端版本太旧，没有这个接口）', new ApiError(404, 'UNKNOWN', 'x')],
    ['不是 ApiError', new TypeError('x')],
  ])('%s：查不清楚，不提示', async (_name, error) => {
    expect(await checkLoginService(reject(error))).toBe('unknown')
  })
})

describe('与 fetchHealth 连起来（假 fetch）', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  function stubFetch(respond: () => Promise<Response>) {
    vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => {}, removeItem: () => {} })
    vi.stubGlobal('fetch', vi.fn(respond))
  }

  it('后端没启动，开发代理返回 502 错误页：后端连不上', async () => {
    stubFetch(() => Promise.resolve(new Response('Bad Gateway', { status: 502 })))
    expect(await checkLoginService(fetchHealth)).toBe('backend-down')
  })

  it('网络不通：后端连不上', async () => {
    stubFetch(() => Promise.reject(new TypeError('Failed to fetch')))
    expect(await checkLoginService(fetchHealth)).toBe('backend-down')
  })

  it('/health 报告数据库不可用：提示数据库', async () => {
    const body = health({ database: { status: 'unavailable', detail: 'OperationalError' } })
    stubFetch(() =>
      Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })),
    )
    expect(await checkLoginService(fetchHealth)).toBe('database-down')
  })
})
