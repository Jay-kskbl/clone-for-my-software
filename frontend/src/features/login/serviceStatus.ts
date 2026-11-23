// 登录页打开时检查一次服务状态（T24z）。
//
// 原来要填完表单、点了“登录”才知道后端没启动。现在打开登录页就调一次公开接口 GET /health，
// 登录用不了时提前说明。不轮询；用户点“重新检查”时再查一次。
// 登录只需要后端和数据库：OpenSearch、CLIP 服务不可用不影响登录，这里不看（检索页自己会提示）。
import { ApiError } from '../../api/client'
import type { HealthResponse } from '../../api/types'

export type ServiceStatus =
  /** 可以登录 */
  | 'ok'
  /** 连不上后端：网络不通，或后端没启动（开发代理返回 502–504） */
  | 'backend-down'
  /** 后端在，但数据库不可用 */
  | 'database-down'
  /** 查不清楚（例如应答格式不对）：不提示，免得说错，登录时出错再由表单内的提示说明 */
  | 'unknown'

/** load 一般传 api/health.ts 的 fetchHealth；测试时换成假的。本函数不抛异常。 */
export async function checkLoginService(load: () => Promise<HealthResponse>): Promise<ServiceStatus> {
  let health: HealthResponse
  try {
    health = await load()
  } catch (error) {
    if (error instanceof ApiError && (error.code === 'NETWORK' || error.code === 'UNAVAILABLE')) return 'backend-down'
    return 'unknown'
  }
  const database = health?.database?.status
  if (database === 'ok') return 'ok'
  if (database === 'unavailable') return 'database-down'
  return 'unknown'
}
