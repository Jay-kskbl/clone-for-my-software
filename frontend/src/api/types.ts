// 接口的数据结构，与 docs/api.md 一一对应。前端只依赖这份契约。

export type Role = 'user' | 'admin'
export type Status = 'pending' | 'processing' | 'succeeded' | 'failed'
export type Access = 'owner' | 'shared' | 'admin'
export type Scope = 'mine' | 'shared'

export interface User {
  id: string
  username: string
  role: Role
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
}

export interface UserRef {
  id: string
  username: string
}

export interface DocumentItem {
  id: string
  filename: string
  mime_type: string
  size_bytes: number
  status: Status
  tags: string[]
  owner: UserRef
  access: Access
  created_at: string
  updated_at: string
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface Share {
  user: UserRef
  created_at: string
}

// ---- 来源定位（shared/contracts/locators.py）----

export type SourceType = 'body' | 'ocr'

export type Locator =
  | { type: 'pdf_page'; page: number }
  | { type: 'docx_para'; para_index: number }
  | { type: 'xlsx_range'; sheet: string; range: string }
  | { type: 'image'; image_id: string }

// ---- 检索（docs/api.md §7.1）----

export type Channel = 'meta' | 'text' | 'image'
export type ChannelState = 'ok' | 'disabled' | 'unavailable'

export interface SearchRequest {
  query: string
  top_k?: number
  channels?: Partial<Record<Channel, boolean>>
  source_types?: SourceType[]
}

export interface ChannelResult {
  channel: Channel
  rank: number
  score: number
}

export interface Evidence {
  chunk_id: string | null
  image_id: string | null
  /** 已由后端做过 HTML 转义，只含 <em> 标记；显示前仍要经过 utils/snippet.ts 清洗 */
  snippet: string | null
  source_type: SourceType | null
  locator: Locator
}

export interface SearchHit {
  document: DocumentItem
  score: number
  channels: ChannelResult[]
  evidence: Evidence | null
}

export interface ChannelStatus {
  channel: Channel
  status: ChannelState
  took_ms: number
  detail: string | null
}

export interface SearchResponse {
  hits: SearchHit[]
  channels: ChannelStatus[]
  took_ms: number
}

// ---- 抽取文本（docs/api.md §5.6）----

export interface TextChunk {
  chunk_id: string
  seq: number
  source_type: SourceType
  text: string
  locator: Locator
}
