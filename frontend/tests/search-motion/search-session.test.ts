// 搜索请求与扫描动画的对接（指南 §6.3）：四个时机、连续搜索丢弃旧返回、超时。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  createSearchSession,
  SearchTimeoutError,
  type ScanControls,
} from '../../src/features/search-motion/scan-loader/searchSession'

function fakeLoader() {
  const calls: string[] = []
  const loader: ScanControls<string> = {
    start: () => calls.push('start'),
    complete: (r) => calls.push(`complete:${r}`),
    error: (m) => calls.push(`error:${m ?? ''}`),
    cancel: () => calls.push('cancel'),
  }
  return { loader, calls }
}

/** 一个可以手动 resolve / reject 的请求，并记录收到的 signal。 */
function deferred() {
  let resolve!: (v: string) => void
  let reject!: (e: unknown) => void
  let signal!: AbortSignal
  const task = (s: AbortSignal) => {
    signal = s
    return new Promise<string>((res, rej) => {
      resolve = res
      reject = rej
      s.addEventListener('abort', () => rej(new DOMException('aborted', 'AbortError')))
    })
  }
  return { task, resolve: (v: string) => resolve(v), reject: (e: unknown) => reject(e), signal: () => signal }
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('搜索会话', () => {
  it('成功：start → complete', async () => {
    const { loader, calls } = fakeLoader()
    const session = createSearchSession(loader)
    const req = deferred()
    const done = session.run(req.task)
    expect(session.pending).toBe(true)
    req.resolve('A')
    await done
    expect(calls).toEqual(['start', 'complete:A'])
    expect(session.pending).toBe(false)
  })

  it('失败：start → error，提示文字来自 onError', async () => {
    const { loader, calls } = fakeLoader()
    const session = createSearchSession(loader, { onError: (e) => `出错了：${(e as Error).message}` })
    const req = deferred()
    const done = session.run(req.task)
    req.reject(new Error('503'))
    await done
    expect(calls).toEqual(['start', 'error:出错了：503'])
  })

  it('连续搜索：中断旧请求，旧请求晚到的返回被丢弃；新动画直接 start（start 自己清掉旧动画）', async () => {
    const { loader, calls } = fakeLoader()
    const session = createSearchSession(loader)
    const first = deferred()
    const second = deferred()
    const p1 = session.run(first.task)
    const p2 = session.run(second.task)
    expect(first.signal().aborted).toBe(true)
    first.resolve('旧')
    second.resolve('新')
    await Promise.all([p1, p2])
    expect(calls).toEqual(['start', 'start', 'complete:新'])
  })

  it('超时：中断请求并以 SearchTimeoutError 进入 error', async () => {
    const { loader, calls } = fakeLoader()
    let reason: unknown
    const session = createSearchSession(loader, {
      timeoutMs: 30_000,
      onError: (e) => {
        reason = e
        return '超时'
      },
    })
    const req = deferred()
    const done = session.run(req.task)
    vi.advanceTimersByTime(29_999)
    expect(req.signal().aborted).toBe(false)
    vi.advanceTimersByTime(1)
    await done
    expect(req.signal().aborted).toBe(true)
    expect(reason).toBeInstanceOf(SearchTimeoutError)
    expect(calls).toEqual(['start', 'error:超时'])
  })

  it('cancel：中断请求、动画回到 idle，之后的返回不再处理', async () => {
    const { loader, calls } = fakeLoader()
    const session = createSearchSession(loader)
    const req = deferred()
    const done = session.run(req.task)
    session.cancel()
    await done
    expect(req.signal().aborted).toBe(true)
    expect(calls).toEqual(['start', 'cancel'])
    expect(session.pending).toBe(false)
  })

  it('请求已返回、动画还在播最后一轮时 cancel 也会停下动画', async () => {
    const { loader, calls } = fakeLoader()
    const session = createSearchSession(loader)
    const req = deferred()
    const done = session.run(req.task)
    req.resolve('A')
    await done
    session.cancel()
    expect(calls).toEqual(['start', 'complete:A', 'cancel'])
  })

  it('成功返回后不再触发超时', async () => {
    const { loader, calls } = fakeLoader()
    const session = createSearchSession(loader, { timeoutMs: 1000 })
    const req = deferred()
    const done = session.run(req.task)
    req.resolve('A')
    await done
    vi.advanceTimersByTime(5000)
    expect(calls).toEqual(['start', 'complete:A'])
    expect(vi.getTimerCount()).toBe(0)
  })
})
