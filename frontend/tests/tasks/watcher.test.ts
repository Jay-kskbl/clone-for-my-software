// 任务刷新（任务状态与重试 P2）：轮询、停止、丢弃迟到的响应
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Task } from '../../src/api/types'
import { TaskWatcher } from '../../src/features/tasks/watcher'
import { task } from './fixtures'

const ACTIVE = [task('parse', 'processing')]
const DONE = [task('parse', 'succeeded')]

function setup(load: (id: string, signal: AbortSignal) => Promise<Task[]>) {
  const onTasks = vi.fn()
  const onError = vi.fn()
  const spy = vi.fn(load)
  return { watcher: new TaskWatcher({ load: spy, onTasks, onError, interval: 1000 }), load: spy, onTasks, onError }
}

/** 手动控制什么时候返回的请求 */
function deferred() {
  let resolve!: (tasks: Task[]) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<Task[]>((a, b) => {
    resolve = a
    reject = b
  })
  return { promise, resolve, reject }
}

beforeEach(() => void vi.useFakeTimers())
afterEach(() => void vi.useRealTimers())

describe('轮询', () => {
  it('还有没结束的任务就接着刷新，都结束了就停', async () => {
    const answers = [ACTIVE, ACTIVE, DONE]
    const { watcher, load, onTasks } = setup(async () => answers.shift() ?? DONE)
    await watcher.start('d1')
    expect(load).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1000)
    await vi.advanceTimersByTimeAsync(1000)
    expect(load).toHaveBeenCalledTimes(3)
    await vi.advanceTimersByTimeAsync(10_000)
    expect(load).toHaveBeenCalledTimes(3)
    expect(onTasks).toHaveBeenLastCalledWith(DONE)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('一开始就都结束了：只请求一次', async () => {
    const { watcher, load } = setup(async () => DONE)
    await watcher.start('d1')
    await vi.advanceTimersByTimeAsync(10_000)
    expect(load).toHaveBeenCalledTimes(1)
  })

  it('refresh 后又有了没结束的任务（点了重试）：重新开始轮询', async () => {
    const answers = [DONE, ACTIVE, DONE]
    const { watcher, load } = setup(async () => answers.shift() ?? DONE)
    await watcher.start('d1')
    await watcher.refresh()
    await vi.advanceTimersByTimeAsync(1000)
    expect(load).toHaveBeenCalledTimes(3)
  })

  it('refresh 会取消已排好的下一次，不会变成两条轮询', async () => {
    const { watcher, load } = setup(async () => ACTIVE)
    await watcher.start('d1')
    await watcher.refresh()
    expect(load).toHaveBeenCalledTimes(2)
    expect(vi.getTimerCount()).toBe(1)
    await vi.advanceTimersByTimeAsync(1000)
    expect(load).toHaveBeenCalledTimes(3)
  })
})

describe('停止', () => {
  it('stop 之后不再请求，也不留定时器', async () => {
    const { watcher, load } = setup(async () => ACTIVE)
    await watcher.start('d1')
    watcher.stop()
    expect(vi.getTimerCount()).toBe(0)
    await vi.advanceTimersByTimeAsync(10_000)
    expect(load).toHaveBeenCalledTimes(1)
  })

  it('请求还没返回就 stop（离开页面）：取消请求，迟到的响应不回调、不排下一次', async () => {
    const pending = deferred()
    let signal: AbortSignal | undefined
    const { watcher, onTasks, onError } = setup((_id, s) => {
      signal = s
      return pending.promise
    })
    const started = watcher.start('d1')
    watcher.stop()
    expect(signal?.aborted).toBe(true)
    pending.resolve(ACTIVE)
    await started
    expect(onTasks).not.toHaveBeenCalled()
    expect(onError).not.toHaveBeenCalled()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('取消引起的异常不当作错误', async () => {
    const pending = deferred()
    const { watcher, onError } = setup(() => pending.promise)
    const started = watcher.start('d1')
    watcher.stop()
    pending.reject(new DOMException('aborted', 'AbortError'))
    await started
    expect(onError).not.toHaveBeenCalled()
  })

  it('没有 start 时 refresh 什么也不做', async () => {
    const { watcher, load } = setup(async () => DONE)
    await watcher.refresh()
    expect(load).not.toHaveBeenCalled()
  })

  it('在 onTasks 里 stop（关掉对话框）：不再排下一次', async () => {
    const onError = vi.fn()
    const watcher: TaskWatcher = new TaskWatcher({
      load: async () => ACTIVE,
      onTasks: () => watcher.stop(),
      onError,
      interval: 1000,
    })
    await watcher.start('d1')
    expect(vi.getTimerCount()).toBe(0)
  })
})

describe('换文档', () => {
  it('旧文档的响应后到：丢弃，不覆盖新文档的', async () => {
    const first = deferred()
    const second = deferred()
    const { watcher, onTasks } = setup((id) => (id === 'd1' ? first.promise : second.promise))
    const a = watcher.start('d1')
    const b = watcher.start('d2')
    second.resolve(DONE)
    await b
    first.resolve(ACTIVE)
    await a
    expect(onTasks).toHaveBeenCalledTimes(1)
    expect(onTasks).toHaveBeenCalledWith(DONE)
    expect(vi.getTimerCount()).toBe(0)
  })
})

describe('出错', () => {
  it('第一次就失败：不是静默的，也不再自动重试', async () => {
    const error = new Error('x')
    const { watcher, load, onError } = setup(async () => Promise.reject(error))
    await watcher.start('d1')
    expect(onError).toHaveBeenCalledWith(error, false)
    await vi.advanceTimersByTimeAsync(10_000)
    expect(load).toHaveBeenCalledTimes(1)
  })

  it('自动刷新失败：静默的，接着试，恢复后照常', async () => {
    const error = new Error('x')
    let n = 0
    const { watcher, load, onError, onTasks } = setup(async () => {
      n += 1
      if (n === 2) throw error
      return n === 1 ? ACTIVE : DONE
    })
    await watcher.start('d1')
    await vi.advanceTimersByTimeAsync(1000)
    expect(onError).toHaveBeenCalledWith(error, true)
    await vi.advanceTimersByTimeAsync(1000)
    expect(load).toHaveBeenCalledTimes(3)
    expect(onTasks).toHaveBeenLastCalledWith(DONE)
  })
})
