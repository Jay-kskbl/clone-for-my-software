// API 封装的测试：令牌、错误转换、401 处理、查询参数、上传。
// fetch 和 localStorage 用假的实现替换，不需要浏览器，也不需要后端。

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  ApiError,
  errorMessage,
  getToken,
  request,
  requestRaw,
  setToken,
  setUnauthenticatedHandler,
} from '../src/api/client'
import { listDocuments, uploadDocument } from '../src/api/documents'
import { listDocumentTasks, retryTask } from '../src/api/tasks'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

let fetchMock: ReturnType<typeof vi.fn>

function lastCall(): { url: string; init: RequestInit } {
  const [url, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit]
  return { url, init }
}

beforeEach(() => {
  const store = new Map<string, string>()
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => void store.set(key, value),
    removeItem: (key: string) => void store.delete(key),
  })
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
  setUnauthenticatedHandler(() => {})
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('令牌', () => {
  it('没有令牌时不带 Authorization 头', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, {}))

    await request('/api/auth/me')

    expect(new Headers(lastCall().init.headers).has('Authorization')).toBe(false)
  })

  it('有令牌时带上 Bearer 头', async () => {
    setToken('abc.def.ghi')
    fetchMock.mockResolvedValue(jsonResponse(200, {}))

    await request('/api/auth/me')

    expect(new Headers(lastCall().init.headers).get('Authorization')).toBe('Bearer abc.def.ghi')
  })

  it('setToken(null) 清除令牌', () => {
    setToken('abc')
    setToken(null)

    expect(getToken()).toBeNull()
  })
})

describe('请求体与查询参数', () => {
  it('普通对象按 JSON 发送', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, {}))

    await request('/api/auth/login', { method: 'POST', body: { username: 'a', password: 'b' } })

    const { init } = lastCall()
    expect(init.method).toBe('POST')
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
    expect(init.body).toBe('{"username":"a","password":"b"}')
  })

  it('空的查询参数被省略，中文被正确编码', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { items: [], total: 0, page: 1, page_size: 20 }))

    await listDocuments({ page: 2, page_size: 20, scope: undefined, tag: '财务' })

    expect(lastCall().url).toBe('/api/documents?page=2&page_size=20&tag=%E8%B4%A2%E5%8A%A1')
  })

  it('上传用 FormData，不手动设置 Content-Type', async () => {
    fetchMock.mockResolvedValue(jsonResponse(201, { id: 'x' }))
    const file = new File(['%PDF-1.4'], '年度报告.pdf')

    await uploadDocument(file, ['财务', '2026'])

    const { url, init } = lastCall()
    expect(url).toBe('/api/documents')
    expect(init.method).toBe('POST')
    // 浏览器要自己生成带分隔符的 multipart 头；手动设置会让后端解析失败
    expect(new Headers(init.headers).has('Content-Type')).toBe(false)
    const form = init.body as FormData
    expect((form.get('file') as File).name).toBe('年度报告.pdf')
    expect(form.getAll('tags')).toEqual(['财务', '2026'])
  })

  it('204 无内容时返回 undefined', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }))

    await expect(request('/api/documents/x', { method: 'DELETE' })).resolves.toBeUndefined()
  })
})

describe('错误处理', () => {
  it('后端的错误结构被转换成 ApiError', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(415, { error: { code: 'UNSUPPORTED_FILE_TYPE', message: '不支持的文件类型' } }),
    )

    const error = await request('/api/documents', { method: 'POST' }).catch((e: unknown) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      status: 415,
      code: 'UNSUPPORTED_FILE_TYPE',
      message: '不支持的文件类型',
    })
    expect(errorMessage(error)).toBe('不支持的文件类型')
  })

  it('后端不可达（代理返回 502）时提示服务不可用', async () => {
    fetchMock.mockResolvedValue(new Response('<html>Bad Gateway</html>', { status: 502 }))

    const error = await request('/api/documents').catch((e: unknown) => e)

    // 后端没启动时，开发代理返回的就是这种响应
    expect(error).toMatchObject({ status: 502, code: 'UNAVAILABLE' })
    expect(errorMessage(error)).toContain('后端')
  })

  it('其他非 JSON 的错误响应给出带状态码的兜底信息', async () => {
    fetchMock.mockResolvedValue(new Response('oops', { status: 500 }))

    const error = await request('/api/documents').catch((e: unknown) => e)

    expect(error).toMatchObject({ status: 500, code: 'UNKNOWN' })
    expect(errorMessage(error)).toContain('500')
  })

  it('连不上服务器时抛出 NETWORK 错误，而不是原始的 TypeError', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))

    const error = await request('/api/documents').catch((e: unknown) => e)

    expect(error).toMatchObject({ status: 0, code: 'NETWORK' })
  })

  it('检索服务故障与“没有结果”可以区分：503 是错误，不是空列表', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(503, { error: { code: 'DATABASE_UNAVAILABLE', message: '数据库不可用' } }),
    )

    await expect(listDocuments({ page: 1, page_size: 20 })).rejects.toMatchObject({ status: 503 })
  })

  it('非 ApiError 的异常显示通用提示，不暴露内部信息', () => {
    expect(errorMessage(new Error('secret stack detail'))).toBe('发生了未预期的错误')
  })
})

describe('登录状态失效', () => {
  it('401 UNAUTHENTICATED 触发回调', async () => {
    const handler = vi.fn()
    setUnauthenticatedHandler(handler)
    fetchMock.mockResolvedValue(
      jsonResponse(401, { error: { code: 'UNAUTHENTICATED', message: '令牌无效或已过期' } }),
    )

    await expect(requestRaw('/api/documents')).rejects.toMatchObject({ status: 401 })

    expect(handler).toHaveBeenCalledOnce()
  })

  it('登录时密码错误（401 INVALID_CREDENTIALS）不触发回调', async () => {
    const handler = vi.fn()
    setUnauthenticatedHandler(handler)
    fetchMock.mockResolvedValue(
      jsonResponse(401, { error: { code: 'INVALID_CREDENTIALS', message: '用户名或密码错误' } }),
    )

    await expect(request('/api/auth/login', { method: 'POST', body: {} })).rejects.toMatchObject({
      code: 'INVALID_CREDENTIALS',
    })

    expect(handler).not.toHaveBeenCalled()
  })

  it('403 不触发回调：无权限不等于未登录', async () => {
    const handler = vi.fn()
    setUnauthenticatedHandler(handler)
    fetchMock.mockResolvedValue(
      jsonResponse(403, { error: { code: 'FORBIDDEN', message: '无权访问该文档' } }),
    )

    await expect(request('/api/documents/x')).rejects.toMatchObject({ status: 403 })

    expect(handler).not.toHaveBeenCalled()
  })
})

describe('任务接口（任务状态与重试 P2）', () => {
  it('列出文档的任务：取出 items', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { items: [{ id: 't1' }] }))
    const controller = new AbortController()
    expect(await listDocumentTasks('d1', controller.signal)).toEqual([{ id: 't1' }])
    expect(lastCall().url).toBe('/api/documents/d1/tasks')
    expect(lastCall().init.signal).toBe(controller.signal)
  })

  it('重试：POST，没有请求体', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { id: 't1', status: 'pending' }))
    await retryTask('t1')
    expect(lastCall().url).toBe('/api/tasks/t1/retry')
    expect(lastCall().init.method).toBe('POST')
    expect(lastCall().init.body).toBeUndefined()
  })

  it('409 的错误码原样带出来，批量重试靠它区分“跳过”', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(409, { error: { code: 'TASK_NOT_RETRYABLE', message: '只有失败的任务可以重试' } }),
    )
    await expect(retryTask('t1')).rejects.toMatchObject({ status: 409, code: 'TASK_NOT_RETRYABLE' })
  })
})
