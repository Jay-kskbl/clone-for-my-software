// 批量重试（T24bd）：逐个调用现有的重试接口，限制同时进行的个数。
//
// 后端没有批量接口；扫描件可能有上百个失败的 OCR 任务，一次全发会同时占满连接。
import { ApiError } from '../../api/client'
import type { Task } from '../../api/types'

export const RETRY_CONCURRENCY = 4

export interface RetryResult {
  /** 已放回队列 */
  queued: number
  /** 任务已不是失败状态（别人先点了重试，或刚好处理完）：不算失败 */
  skipped: number
  failed: number
  /** 中途停下、没有发出请求的 */
  notSent: number
  /** 第一个失败的原因，用来显示 */
  error: unknown
}

/** 这些错误说明后面的请求也不会成功：停下来，不再一个个失败下去 */
function isFatal(error: unknown): boolean {
  if (!(error instanceof ApiError)) return true
  return error.status === 0 || error.status === 401 || error.status === 403 || error.status >= 500
}

export async function retryAll(
  tasks: readonly Task[],
  retry: (taskId: string) => Promise<unknown>,
  concurrency = RETRY_CONCURRENCY,
): Promise<RetryResult> {
  const queue = [...tasks]
  const result: RetryResult = { queued: 0, skipped: 0, failed: 0, notSent: 0, error: null }
  let stopped = false

  const worker = async () => {
    for (let task = queue.shift(); task; task = queue.shift()) {
      try {
        await retry(task.id)
        result.queued += 1
      } catch (error) {
        if (error instanceof ApiError && error.code === 'TASK_NOT_RETRYABLE') {
          result.skipped += 1
          continue
        }
        result.failed += 1
        result.error ??= error
        if (isFatal(error)) stopped = true
      }
      if (stopped) return
    }
  }

  await Promise.all(Array.from({ length: Math.min(concurrency, queue.length) }, worker))
  result.notSent = queue.length
  return result
}
