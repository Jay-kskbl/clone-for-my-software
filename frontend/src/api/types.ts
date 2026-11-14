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
