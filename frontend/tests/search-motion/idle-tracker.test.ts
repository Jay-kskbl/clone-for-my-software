// 待机计时（指南 §4.1）：8 秒进入、任意操作退出、pointermove 节流、后台停止计时。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createIdleTracker } from '../../src/features/search-motion/idle-spinner/idleTracker'

class FakeVisibility extends EventTarget {
  hidden = false

  set(hidden: boolean) {
    this.hidden = hidden
    this.dispatchEvent(new Event('visibilitychange'))
  }
}

function setup(idleAfter = 8000) {
  const target = new EventTarget()
  const visibility = new FakeVisibility()
  const events: string[] = []
  const tracker = createIdleTracker({
    idleAfter,
    target,
    visibility,
    onIdle: () => events.push('idle'),
    onActive: () => events.push('active'),
  })
  const fire = (type: string) => target.dispatchEvent(new Event(type))
  return { tracker, visibility, events, fire }
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('待机计时', () => {
  it('8 秒无操作进入待机', () => {
    const { tracker, events } = setup()
    vi.advanceTimersByTime(7999)
    expect(events).toEqual([])
    vi.advanceTimersByTime(1)
    expect(events).toEqual(['idle'])
    expect(tracker.idle).toBe(true)
  })

  it('五种操作都会重新计时；待机中任意操作立即退出', () => {
    for (const type of ['pointermove', 'pointerdown', 'keydown', 'wheel', 'touchstart']) {
      const { events, fire, tracker } = setup()
      vi.advanceTimersByTime(7000)
      fire(type)
      vi.advanceTimersByTime(7000)
      expect(events).toEqual([])
      vi.advanceTimersByTime(1000)
      expect(events).toEqual(['idle'])
      fire(type)
      expect(events).toEqual(['idle', 'active'])
      expect(tracker.idle).toBe(false)
      tracker.destroy()
    }
  })

  it('退出待机后重新从 0 计时', () => {
    const { events, fire } = setup()
    vi.advanceTimersByTime(8000)
    fire('keydown')
    vi.advanceTimersByTime(7999)
    expect(events).toEqual(['idle', 'active'])
    vi.advanceTimersByTime(1)
    expect(events).toEqual(['idle', 'active', 'idle'])
  })

  it('200 ms 内的连续操作只重置一次计时', () => {
    const { events, fire } = setup()
    vi.advanceTimersByTime(1000)
    fire('pointermove') // t=1000 重置
    vi.advanceTimersByTime(100)
    fire('pointermove') // t=1100 在节流窗口内，忽略
    vi.advanceTimersByTime(7900) // t=9000 = 1000 + 8000
    expect(events).toEqual(['idle'])
  })

  it('切到后台停止计时（待机中直接退出），回到前台从 0 重新计时', () => {
    const { events, visibility } = setup()
    vi.advanceTimersByTime(5000)
    visibility.set(true)
    vi.advanceTimersByTime(60_000)
    expect(events).toEqual([])
    visibility.set(false)
    vi.advanceTimersByTime(7999)
    expect(events).toEqual([])
    vi.advanceTimersByTime(1)
    expect(events).toEqual(['idle'])
    visibility.set(true)
    expect(events).toEqual(['idle', 'active'])
  })

  it('destroy 后不再计时、不再响应操作', () => {
    const { tracker, events, fire, visibility } = setup()
    tracker.destroy()
    vi.advanceTimersByTime(60_000)
    fire('keydown')
    visibility.set(true)
    visibility.set(false)
    vi.advanceTimersByTime(60_000)
    expect(events).toEqual([])
    expect(vi.getTimerCount()).toBe(0)
  })

  it('poke：手动退出待机并重新计时', () => {
    const { tracker, events } = setup()
    vi.advanceTimersByTime(8000)
    tracker.poke()
    expect(events).toEqual(['idle', 'active'])
    vi.advanceTimersByTime(8000)
    expect(events).toEqual(['idle', 'active', 'idle'])
  })
})
