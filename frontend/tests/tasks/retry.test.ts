// 批量重试（任务状态与重试 P2）
import { describe, expect, it, vi } from 'vitest'

import { ApiError } from '../../src/api/client'
import { retryAll } from '../../src/features/tasks/retry'
import { task } from './fixtures'

const many = (n: number) => Array.from({ length: n }, () => task('ocr', 'failed'))

describe('批量重试', () => {
  it('全部放回队列，每个任务只发一次', async () => {
    const tasks = many(10)
    const retry = vi.fn().mockResolvedValue(undefined)
    expect(await retryAll(tasks, retry)).toEqual({ queued: 10, skipped: 0, failed: 0, notSent: 0, error: null })
    expect(retry.mock.calls.map((c) => c[0]).sort()).toEqual(tasks.map((t) => t.id).sort())
  })

  it('没有任务时不发请求', async () => {
    const retry = vi.fn()
    expect((await retryAll([], retry)).queued).toBe(0)
    expect(retry).not.toHaveBeenCalled()
  })

  it('同时进行的不超过上限', async () => {
    let running = 0
    let peak = 0
    const retry = async () => {
      running += 1
      peak = Math.max(peak, running)
      await new Promise((r) => setTimeout(r, 2))
      running -= 1
    }
    expect((await retryAll(many(12), retry, 4)).queued).toBe(12)
    expect(peak).toBe(4)
  })

  it('409（已不是失败状态）算跳过，继续处理后面的', async () => {
    const retry = vi.fn().mockResolvedValue(undefined)
    retry.mockRejectedValueOnce(new ApiError(409, 'TASK_NOT_RETRYABLE', '只有失败的任务可以重试'))
    expect(await retryAll(many(3), retry, 1)).toMatchObject({ queued: 2, skipped: 1, failed: 0, error: null })
  })

  it('其他 409 不当作跳过', async () => {
    const retry = vi.fn().mockRejectedValue(new ApiError(409, 'USERNAME_TAKEN', 'x'))
    expect(await retryAll(many(1), retry)).toMatchObject({ skipped: 0, failed: 1 })
  })

  it('单个任务 404：记一次失败，继续后面的', async () => {
    const gone = new ApiError(404, 'NOT_FOUND', '任务不存在')
    const retry = vi.fn().mockResolvedValue(undefined)
    retry.mockRejectedValueOnce(gone)
    expect(await retryAll(many(3), retry, 1)).toEqual({ queued: 2, skipped: 0, failed: 1, notSent: 0, error: gone })
  })

  it.each([
    ['网络不通', new ApiError(0, 'NETWORK', 'x')],
    ['令牌失效', new ApiError(401, 'UNAUTHENTICATED', 'x')],
    ['无权限', new ApiError(403, 'FORBIDDEN', 'x')],
    ['服务器故障', new ApiError(503, 'DATABASE_UNAVAILABLE', 'x')],
    ['意外的异常', new Error('x')],
  ])('%s：停下来，剩下的不再发', async (_name, error) => {
    const retry = vi.fn().mockRejectedValue(error)
    const result = await retryAll(many(20), retry, 1)
    expect(retry).toHaveBeenCalledTimes(1)
    expect(result).toEqual({ queued: 0, skipped: 0, failed: 1, notSent: 19, error })
  })

  it('并发时停下来：已发出的等它结束，计数对得上总数', async () => {
    const retry = vi.fn().mockRejectedValue(new ApiError(0, 'NETWORK', 'x'))
    const r = await retryAll(many(20), retry, 4)
    expect(retry).toHaveBeenCalledTimes(4)
    expect(r.queued + r.skipped + r.failed + r.notSent).toBe(20)
  })
})
