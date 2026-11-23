// 任务汇总（任务状态与重试 P2）
import { describe, expect, it } from 'vitest'

import type { TaskType } from '../../src/api/types'
import {
  durationMs,
  failedTasks,
  hasActive,
  isHopeless,
  parseStatus,
  summarizeTasks,
} from '../../src/features/tasks/summary'
import { task } from './fixtures'

describe('步骤', () => {
  it('没有任务时没有步骤', () => {
    expect(summarizeTasks([])).toEqual([])
  })

  it('按处理顺序排，与接口返回的先后无关', () => {
    const steps = summarizeTasks([task('embed', 'pending'), task('ocr', 'pending'), task('parse', 'succeeded')])
    expect(steps.map((s) => s.type)).toEqual(['parse', 'ocr', 'embed'])
  })

  it('不认识的类型排在最后，不丢掉', () => {
    const steps = summarizeTasks([task('new-type' as TaskType, 'failed'), task('cleanup', 'pending')])
    expect(steps.map((s) => s.type)).toEqual(['cleanup', 'new-type'])
  })

  it('同类任务合成一步并计数', () => {
    const [ocr] = summarizeTasks([
      task('ocr', 'succeeded'),
      task('ocr', 'succeeded'),
      task('ocr', 'failed'),
      task('ocr', 'processing'),
    ])
    expect(ocr).toMatchObject({ total: 4, succeeded: 2, active: 1, single: null })
    expect(ocr.failed).toHaveLength(1)
  })

  it('只有一个任务时给出它', () => {
    const only = task('parse', 'succeeded')
    expect(summarizeTasks([only])[0].single).toBe(only)
  })
})

describe('状态', () => {
  const state = (...tasks: ReturnType<typeof task>[]) => summarizeTasks(tasks)[0].state

  it('都没开始：等待', () => {
    expect(state(task('ocr', 'pending'), task('ocr', 'pending'))).toBe('waiting')
  })
  it('有一项在处理：进行中', () => {
    expect(state(task('ocr', 'pending'), task('ocr', 'processing'))).toBe('running')
  })
  it('有一项已经有结果、其余在等：进行中', () => {
    expect(state(task('ocr', 'pending'), task('ocr', 'succeeded'))).toBe('running')
  })
  it('失败过、等待重试：进行中，不是“等待”', () => {
    expect(state(task('parse', 'pending', { attempts: 1, error: 'x' }))).toBe('running')
  })
  it('有失败但还有没结束的：仍是进行中', () => {
    expect(state(task('ocr', 'failed'), task('ocr', 'processing'))).toBe('running')
  })
  it('全部成功', () => {
    expect(state(task('ocr', 'succeeded'), task('ocr', 'succeeded'))).toBe('succeeded')
  })
  it('一部分失败', () => {
    expect(state(task('ocr', 'succeeded'), task('ocr', 'failed'))).toBe('partial')
  })
  it('全部失败', () => {
    expect(state(task('ocr', 'failed'), task('ocr', 'failed'))).toBe('failed')
  })
})

describe('失败原因', () => {
  it('相同的合并计数，多的在前；没有原因的归为 null', () => {
    const [step] = summarizeTasks([
      task('ocr', 'failed', { error: 'A' }),
      task('ocr', 'failed', { error: 'B' }),
      task('ocr', 'failed', { error: 'B' }),
      task('ocr', 'failed', { error: null }),
      task('ocr', 'failed', { error: '' }),
      task('ocr', 'failed', { error: 'B' }),
    ])
    expect(step.reasons).toEqual([
      { text: 'B', count: 3 },
      { text: null, count: 2 },
      { text: 'A', count: 1 },
    ])
  })

  it('成功的、等待重试的任务带着旧原因，不算失败原因', () => {
    const [step] = summarizeTasks([task('ocr', 'pending', { attempts: 1, error: '上次的' }), task('ocr', 'succeeded')])
    expect(step.reasons).toEqual([])
    expect(step.waitingRetry?.error).toBe('上次的')
  })
})

describe('判断', () => {
  it('次数没用完就失败：重试大概率无用', () => {
    expect(isHopeless(task('parse', 'failed', { attempts: 1 }))).toBe(true)
    expect(isHopeless(task('parse', 'failed', { attempts: 3 }))).toBe(false)
    expect(isHopeless(task('parse', 'pending', { attempts: 1 }))).toBe(false)
  })

  it('还有没结束的任务', () => {
    expect(hasActive([])).toBe(false)
    expect(hasActive([task('parse', 'succeeded'), task('ocr', 'failed')])).toBe(false)
    expect(hasActive([task('parse', 'succeeded'), task('ocr', 'pending')])).toBe(true)
  })

  it('解析状态', () => {
    expect(parseStatus([task('ocr', 'failed'), task('parse', 'succeeded')])).toBe('succeeded')
    expect(parseStatus([task('cleanup', 'pending')])).toBeNull()
  })

  it('失败的任务', () => {
    const failed = task('ocr', 'failed')
    expect(failedTasks([task('parse', 'succeeded'), failed])).toEqual([failed])
  })

  it('用时：没开始、没结束、时间颠倒、格式不对都是 null', () => {
    const at = (started_at: string | null, finished_at: string | null) =>
      durationMs(task('parse', 'succeeded', { started_at, finished_at }))
    expect(at('2026-11-23T08:00:00Z', '2026-11-23T08:00:03.5Z')).toBe(3500)
    expect(at(null, '2026-11-23T08:00:03Z')).toBeNull()
    expect(at('2026-11-23T08:00:00Z', null)).toBeNull()
    expect(at('2026-11-23T08:00:03Z', '2026-11-23T08:00:00Z')).toBeNull()
    expect(at('bad', 'bad')).toBeNull()
  })
})
