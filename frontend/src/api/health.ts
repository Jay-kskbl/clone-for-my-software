import { request } from './client'
import type { HealthResponse } from './types'

/**
 * 各依赖服务的状态。公开接口，不需要登录；依赖不可用时也返回 200，
 * 由各项的 status 说明（backend/app/api/health.py）。检索页用它显示 CLIP 服务是否在线（T24s）。
 */
export function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health')
}
