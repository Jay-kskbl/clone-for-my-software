import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../src/api/client'
import { getDocumentText } from '../src/api/documents'
import { search } from '../src/api/search'

function stubFetch(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

beforeEach(() => {
  // 测试在 node 环境里运行，没有浏览器的 localStorage；client.ts 读令牌时要用到它
  const store = new Map<string, string>()
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => void store.set(key, value),
    removeItem: (key: string) => void store.delete(key),
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('检索接口', () => {
  it('以 JSON POST 到 /api/search', async () => {
    const fetchMock = stubFetch(200, { hits: [], channels: [], took_ms: 3 })

    const result = await search({ query: '报销', source_types: ['body'] })

    expect(result.hits).toEqual([])
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/search')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ query: '报销', source_types: ['body'] })
  })

  it('检索服务故障是 SEARCH_UNAVAILABLE 错误，不是空结果', async () => {
    stubFetch(503, { error: { code: 'SEARCH_UNAVAILABLE', message: '检索服务暂时不可用，请稍后重试' } })

    const error = await search({ query: '报销' }).catch((e) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect(error.code).toBe('SEARCH_UNAVAILABLE')
  })
})

describe('抽取文本接口', () => {
  it('带上分页和片段参数', async () => {
    const fetchMock = stubFetch(200, { items: [], total: 0, page: 1, page_size: 50 })

    await getDocumentText('doc-1', { page_size: 50, chunk_id: 'doc-1:v:3' })

    expect(fetchMock.mock.calls[0][0]).toBe('/api/documents/doc-1/text?page_size=50&chunk_id=doc-1%3Av%3A3')
  })
})
