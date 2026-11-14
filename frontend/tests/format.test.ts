import { describe, expect, it } from 'vitest'

import {
  ACCESS_LABEL,
  STATUS_LABEL,
  formatSize,
  formatTime,
  formatType,
  isInProgress,
} from '../src/utils/format'

describe('formatSize', () => {
  it.each([
    [0, '0 B'],
    [1023, '1023 B'],
    [1024, '1.0 KB'],
    [1536, '1.5 KB'],
    [10 * 1024, '10 KB'],
    [1048576, '1.0 MB'],
    [50 * 1024 * 1024, '50 MB'],
    [3 * 1024 ** 3, '3.0 GB'],
  ])('%d 字节 → %s', (bytes, expected) => {
    expect(formatSize(bytes)).toBe(expected)
  })
})

describe('formatTime', () => {
  it('按本地时区显示到分钟', () => {
    const local = new Date(2026, 10, 13, 9, 5)

    expect(formatTime(local.toISOString())).toBe('2026-11-13 09:05')
  })

  it('无法解析的时间原样返回，而不是显示 Invalid Date', () => {
    expect(formatTime('not-a-date')).toBe('not-a-date')
  })
})

describe('状态与类型', () => {
  it('四种处理状态都有中文说明', () => {
    expect(Object.keys(STATUS_LABEL).sort()).toEqual(
      ['failed', 'pending', 'processing', 'succeeded'].sort(),
    )
    expect(STATUS_LABEL.failed).toEqual({ text: '处理失败', type: 'danger' })
  })

  it('三种访问关系都有中文说明', () => {
    expect(Object.keys(ACCESS_LABEL).sort()).toEqual(['admin', 'owner', 'shared'])
  })

  it('只有等待处理和处理中需要继续刷新', () => {
    expect(isInProgress('pending')).toBe(true)
    expect(isInProgress('processing')).toBe(true)
    expect(isInProgress('succeeded')).toBe(false)
    expect(isInProgress('failed')).toBe(false)
  })

  it('已知类型显示中文名，未知类型原样显示', () => {
    expect(formatType('application/pdf')).toBe('PDF')
    expect(formatType('image/jpeg')).toBe('图片（JPEG）')
    expect(formatType('application/x-unknown')).toBe('application/x-unknown')
  })
})
