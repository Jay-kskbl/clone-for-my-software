// 预览页跟随任务变化（T24bd）
import { describe, expect, it } from 'vitest'

import { documentOutdated, hasNewOcr } from '../../src/features/tasks/changes'
import { task } from './fixtures'

const parse = (status: Parameters<typeof task>[1], over = {}) => [task('parse', status, over)]

describe('文档状态过时', () => {
  it('解析任务状态变了', () => {
    expect(documentOutdated('processing', parse('processing'), parse('succeeded'))).toBe(true)
    expect(documentOutdated('failed', parse('failed'), parse('pending'))).toBe(true)
  })

  it('没变就不取', () => {
    expect(documentOutdated('processing', parse('processing'), parse('processing'))).toBe(false)
  })

  it('解析等待重试：任务 pending、文档 processing 本来就不同，不会每次轮询都取', () => {
    const waiting = parse('pending', { attempts: 1 })
    expect(documentOutdated('processing', null, waiting)).toBe(false)
    expect(documentOutdated('processing', waiting, waiting)).toBe(false)
  })

  it('第一次拿到任务：取文档和取任务之间刚好解析完', () => {
    expect(documentOutdated('processing', null, parse('succeeded'))).toBe(true)
    expect(documentOutdated('pending', null, parse('failed'))).toBe(true)
    expect(documentOutdated('succeeded', null, parse('succeeded'))).toBe(false)
  })

  it('只有 OCR 在变：文档状态不跟随它（D27）', () => {
    const done = task('parse', 'succeeded')
    expect(documentOutdated('succeeded', [done, task('ocr', 'pending')], [done, task('ocr', 'failed')])).toBe(false)
  })

  it('没有解析任务', () => {
    expect(documentOutdated('succeeded', null, [])).toBe(false)
  })
})

describe('新的 OCR 结果', () => {
  const a = task('ocr', 'processing')
  it('有一项刚成功', () => {
    expect(hasNewOcr([a], [{ ...a, status: 'succeeded' }])).toBe(true)
  })
  it('解析完新建的 OCR 任务直接就成功了', () => {
    expect(hasNewOcr(parse('processing'), [task('ocr', 'succeeded')])).toBe(true)
  })
  it('原来就成功的、失败的、别的类型的都不算', () => {
    const done = task('ocr', 'succeeded')
    const b = task('embed', 'processing')
    expect(hasNewOcr([done, a, b], [done, { ...a, status: 'failed' }, { ...b, status: 'succeeded' }])).toBe(false)
  })
  it('重试后再次成功算新结果', () => {
    expect(hasNewOcr([{ ...a, status: 'pending' }], [{ ...a, status: 'succeeded' }])).toBe(true)
  })
  it('第一次拿到任务不提示', () => {
    expect(hasNewOcr(null, [task('ocr', 'succeeded')])).toBe(false)
  })
})
