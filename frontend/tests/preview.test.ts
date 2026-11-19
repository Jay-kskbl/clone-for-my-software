import { describe, expect, it } from 'vitest'

import { initialPreviewTab } from '../src/utils/preview'

describe('initialPreviewTab：预览页默认显示哪个标签页（T24f）', () => {
  it('直接打开 PDF 或图片：原文件', () => {
    expect(initialPreviewTab('pdf', {})).toBe('file')
    expect(initialPreviewTab('image', {})).toBe('file')
  })

  it('从检索结果打开图片：抽取文本（命中证据是 OCR 文字）', () => {
    expect(initialPreviewTab('image', { chunk: 'd:v:1000000000' })).toBe('text')
  })

  it('从检索结果打开 PDF：仍是原文件，由 pdf.js 跳到命中的页', () => {
    expect(initialPreviewTab('pdf', { page: '3', chunk: 'd:v:2' })).toBe('file')
  })

  it('地址栏里的 view 优先：刷新或复制链接时停在同一页', () => {
    expect(initialPreviewTab('pdf', { view: 'text' })).toBe('text')
    expect(initialPreviewTab('image', { view: 'file', chunk: 'd:v:1' })).toBe('file')
  })

  it('不认识的 view 或空的 chunk 按没有处理', () => {
    expect(initialPreviewTab('pdf', { view: 'other' })).toBe('file')
    expect(initialPreviewTab('image', { chunk: '' })).toBe('file')
    // 同名参数写了两次时 vue-router 给的是数组，不当作片段 ID
    expect(initialPreviewTab('image', { chunk: ['a', 'b'] })).toBe('file')
  })
})
