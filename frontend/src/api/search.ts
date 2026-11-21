import { request } from './client'
import type { SearchRequest, SearchResponse } from './types'

/**
 * 检索。检索服务故障时抛出 code 为 SEARCH_UNAVAILABLE 的 ApiError（503），
 * 没有结果时正常返回、hits 为空列表——两者必须区分开（GLOBAL §12）。
 * signal 用于取消（新的检索覆盖旧的、超时），见 features/search-motion/scan-loader/searchSession.ts。
 */
export function search(body: SearchRequest, signal?: AbortSignal): Promise<SearchResponse> {
  return request<SearchResponse>('/api/search', { method: 'POST', body, signal })
}
