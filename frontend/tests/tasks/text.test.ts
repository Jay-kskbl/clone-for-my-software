// 处理详情的文字（任务状态与重试 P3）
import { afterEach, describe, expect, it } from 'vitest'

import { ApiError } from '../../src/api/client'
import type { Task, TaskType } from '../../src/api/types'
import { summarizeTasks } from '../../src/features/tasks/summary'
import {
  formatDuration,
  hopelessNotice,
  retryLabel,
  retryMessage,
  stateTag,
  stepDetails,
  stepName,
} from '../../src/features/tasks/text'
import { locale } from '../../src/i18n'
import { task } from './fixtures'

afterEach(() => {
  locale.value = 'zh'
})

const step = (...tasks: Task[]) => summarizeTasks(tasks)[0]
const RAN = { started_at: '2026-11-23T08:00:00Z', finished_at: '2026-11-23T08:00:03Z' }

describe('说明', () => {
  it('单个任务成功：只写用时', () => {
    expect(stepDetails(step(task('parse', 'succeeded', RAN)))).toEqual(['用时 3 秒'])
  })

  it('单个任务失败：尝试次数和原因', () => {
    expect(stepDetails(step(task('embed', 'failed', { ...RAN, error: 'CLIP 服务连接失败（ConnectError）' })))).toEqual([
      '已尝试 3/3 次',
      '原因：CLIP 服务连接失败（ConnectError）',
    ])
  })

  it('失败但没有记录原因：照实说', () => {
    expect(stepDetails(step(task('parse', 'failed')))).toContain('原因：没有记录')
  })

  it('还没开始：没有说明', () => {
    expect(stepDetails(step(task('parse', 'pending')))).toEqual([])
  })

  it('等待重试：第几次失败和上次的原因', () => {
    expect(stepDetails(step(task('parse', 'pending', { attempts: 1, error: '处理超时（超过 60 秒），已终止' })))).toEqual([
      '第 1/3 次失败，等待再次处理',
      '原因：处理超时（超过 60 秒），已终止',
    ])
  })

  it('多个任务：计数，相同原因合并', () => {
    const lines = stepDetails(
      step(
        task('ocr', 'succeeded'),
        task('ocr', 'failed', { error: 'A' }),
        task('ocr', 'failed', { error: 'A' }),
        task('ocr', 'processing'),
      ),
    )
    expect(lines).toEqual(['共 4 项：成功 1，失败 2，未完成 1', '原因：A（2 项）'])
  })

  it('都结束了就不写“未完成”', () => {
    expect(stepDetails(step(task('ocr', 'succeeded'), task('ocr', 'succeeded')))).toEqual(['共 2 项：成功 2，失败 0'])
  })
})

describe('重试无用的提醒', () => {
  const hopeless = { attempts: 1, error: 'PDF 已加密' }
  it('没有这种任务时不提醒', () => {
    expect(hopelessNotice(step(task('ocr', 'failed'), task('ocr', 'succeeded')))).toBeNull()
  })
  it('全部都是', () => {
    expect(hopelessNotice(step(task('parse', 'failed', hopeless)))).toContain('建议检查原文件')
  })
  it('只有一部分：写明几项', () => {
    expect(hopelessNotice(step(task('ocr', 'failed', hopeless), task('ocr', 'failed')))).toContain('其中 1 项')
  })
})

describe('名称与按钮', () => {
  it('步骤名、状态', () => {
    expect(stepName('ocr')).toBe('OCR 识别')
    expect(stateTag('partial')).toEqual({ text: '部分失败', type: 'warning' })
  })
  it('不认识的类型直接显示类型', () => {
    expect(stepName('new-type' as TaskType)).toBe('new-type')
  })
  it('单个任务写“重试”，多个任务写失败了几项', () => {
    expect(retryLabel(step(task('parse', 'failed')))).toBe('重试')
    expect(retryLabel(step(task('ocr', 'failed'), task('ocr', 'succeeded')))).toBe('重试失败的 1 项')
  })
  it.each([
    [0, '不到 1 秒'],
    [999, '不到 1 秒'],
    [1000, '1 秒'],
    [59_400, '59 秒'],
    [59_600, '1 分 0 秒'],
    [125_000, '2 分 5 秒'],
  ])('%d 毫秒 → %s', (ms, expected) => {
    expect(formatDuration(ms)).toBe(expected)
  })
})

describe('重试结果', () => {
  const base = { queued: 0, skipped: 0, failed: 0, notSent: 0, error: null as unknown }
  const down = new ApiError(0, 'NETWORK', '无法连接服务器')

  it('全部成功', () => {
    expect(retryMessage({ ...base, queued: 3 })).toEqual({ type: 'success', text: '已放回队列 3 项，等待处理' })
  })
  it('全部跳过也不算失败', () => {
    expect(retryMessage({ ...base, skipped: 2 })).toEqual({ type: 'success', text: '2 项已不是失败状态，已跳过' })
  })
  it('部分失败：没发出去的也算进去', () => {
    expect(retryMessage({ ...base, queued: 1, failed: 1, notSent: 4, error: down })).toEqual({
      type: 'warning',
      text: '已放回队列 1 项，等待处理；5 项没有重试成功：无法连接服务器',
    })
  })
  it('一项都没成功', () => {
    expect(retryMessage({ ...base, failed: 1, error: down }).type).toBe('error')
  })
})

it('切到英文：说明跟着变，后端给的原因保持原文', () => {
  locale.value = 'en'
  expect(stepDetails(step(task('embed', 'failed', { error: 'CLIP 服务连接失败' })))).toEqual([
    '3 of 3 attempts used',
    'Reason: CLIP 服务连接失败',
  ])
})
