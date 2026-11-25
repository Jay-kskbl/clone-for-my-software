// 重新取文档（新功能联测 V1）：失败后自己再试、迟到的旧响应丢弃、离开后停止。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../../src/api/client'
import { Refresher } from '../../src/features/tasks/refresher'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((a, b) => {
    resolve = a
    reject = b
  })
  return { promise, resolve, reject }
}

function setup(load: () => Promise<string>) {
  const spy = vi.fn(load)
  const onLoaded = vi.fn()
  const onError = vi.fn()
  return { refresher: new Refresher({ load: spy, onLoaded, onError, interval: 1000 }), load: spy, onLoaded, onError }
}

const DOWN = new ApiError(503, 'DATABASE_UNAVAILABLE', '数据库不可用')

beforeEach(() => void vi.useFakeTimers())
afterEach(() => void vi.useRealTimers())

it('成功：交出结果，不再请求', async () => {
  const { refresher, load, onLoaded, onError } = setup(async () => 'a')
  await refresher.run()
  await vi.advanceTimersByTimeAsync(60_000)
  expect(onLoaded).toHaveBeenCalledExactlyOnceWith('a')
  expect(onError).not.toHaveBeenCalled()
  expect(load).toHaveBeenCalledTimes(1)
  expect(vi.getTimerCount()).toBe(0)
})

describe('失败', () => {
  it.each([
    ['网络不通', new ApiError(0, 'NETWORK', '')],
    ['数据库不可用', DOWN],
    ['代理 502', new ApiError(502, 'UNAVAILABLE', '')],
  ])('%s：只提示一次，隔一会儿再试，直到成功', async (_name, error) => {
    let left = 3
    const { refresher, load, onLoaded, onError } = setup(async () => {
      if (left-- > 0) throw error
      return 'ok'
    })
    await refresher.run()
    await vi.advanceTimersByTimeAsync(2000)
    expect(onLoaded).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1000)
    expect(load).toHaveBeenCalledTimes(4)
    expect(onLoaded).toHaveBeenCalledExactlyOnceWith('ok')
    expect(onError).toHaveBeenCalledExactlyOnceWith(error)
    expect(vi.getTimerCount()).toBe(0)
  })

  it.each([
    ['文件已删除 404', new ApiError(404, 'NOT_FOUND', '')],
    ['共享被取消 403', new ApiError(403, 'FORBIDDEN', '')],
    ['登录过期 401', new ApiError(401, 'UNAUTHENTICATED', '')],
    ['不是接口错误', new TypeError('x')],
  ])('%s：提示后不再试', async (_name, error) => {
    const { refresher, load, onError } = setup(() => Promise.reject(error))
    await refresher.run()
    await vi.advanceTimersByTimeAsync(60_000)
    expect(load).toHaveBeenCalledTimes(1)
    expect(onError).toHaveBeenCalledTimes(1)
    expect(vi.getTimerCount()).toBe(0)
  })
})

it('先发的后到：丢弃，不会用旧状态盖掉新状态', async () => {
  const first = deferred<string>()
  const second = deferred<string>()
  const answers = [first, second]
  const { refresher, onLoaded } = setup(() => answers.shift()!.promise)
  const a = refresher.run()
  const b = refresher.run()
  second.resolve('已解析')
  first.resolve('解析中')
  await Promise.all([a, b])
  expect(onLoaded).toHaveBeenCalledExactlyOnceWith('已解析')
})

it('等着再试时又有新的一次：旧的定时器取消', async () => {
  const errors: unknown[] = [DOWN]
  const { refresher, load, onLoaded } = setup(async () => {
    const error = errors.shift()
    if (error) throw error
    return 'ok'
  })
  await refresher.run()
  await refresher.run()
  await vi.advanceTimersByTimeAsync(60_000)
  expect(load).toHaveBeenCalledTimes(2)
  expect(onLoaded).toHaveBeenCalledTimes(1)
})

describe('停止之后', () => {
  it('正在等的响应丢弃', async () => {
    const pending = deferred<string>()
    const { refresher, onLoaded } = setup(() => pending.promise)
    const run = refresher.run()
    refresher.stop()
    pending.resolve('x')
    await run
    expect(onLoaded).not.toHaveBeenCalled()
  })

  it('失败也不提示、不再试', async () => {
    const pending = deferred<string>()
    const { refresher, onError } = setup(() => pending.promise)
    const run = refresher.run()
    refresher.stop()
    pending.reject(DOWN)
    await run
    expect(onError).not.toHaveBeenCalled()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('不再接受新的请求', async () => {
    const { refresher, load } = setup(async () => 'x')
    refresher.stop()
    await refresher.run()
    expect(load).not.toHaveBeenCalled()
  })
})
