import { request, requestRaw } from './client'
import type { DocumentItem, Page, Scope, Share, Status } from './types'

export interface ListParams {
  page: number
  page_size: number
  status?: Status
  scope?: Scope
  tag?: string
}

export function listDocuments(params: ListParams): Promise<Page<DocumentItem>> {
  return request<Page<DocumentItem>>('/api/documents', { query: { ...params } })
}

export function uploadDocument(file: File, tags: string[] = []): Promise<DocumentItem> {
  const form = new FormData()
  form.append('file', file)
  for (const tag of tags) form.append('tags', tag)
  return request<DocumentItem>('/api/documents', { method: 'POST', body: form })
}

export function deleteDocument(id: string): Promise<void> {
  return request<void>(`/api/documents/${id}`, { method: 'DELETE' })
}

/** 取回文件内容。下载接口需要登录令牌，不能用普通链接，所以先取成 Blob。 */
export async function downloadDocument(id: string): Promise<Blob> {
  const response = await requestRaw(`/api/documents/${id}/download`)
  return response.blob()
}

export async function listShares(documentId: string): Promise<Share[]> {
  const data = await request<{ items: Share[] }>(`/api/documents/${documentId}/shares`)
  return data.items
}

export function addShare(documentId: string, username: string): Promise<Share> {
  return request<Share>(`/api/documents/${documentId}/shares`, {
    method: 'POST',
    body: { username },
  })
}

export function removeShare(documentId: string, userId: string): Promise<void> {
  return request<void>(`/api/documents/${documentId}/shares/${userId}`, { method: 'DELETE' })
}
