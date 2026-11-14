import { request } from './client'
import type { TokenResponse, User } from './types'

export function register(username: string, password: string): Promise<User> {
  return request<User>('/api/auth/register', { method: 'POST', body: { username, password } })
}

export function login(username: string, password: string): Promise<TokenResponse> {
  return request<TokenResponse>('/api/auth/login', {
    method: 'POST',
    body: { username, password },
  })
}

export function fetchMe(): Promise<User> {
  return request<User>('/api/auth/me')
}
