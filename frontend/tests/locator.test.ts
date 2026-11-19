import { describe, expect, it } from 'vitest'

import { degradedNotice, evidenceLabel, formatLocator, previewQuery } from '../src/utils/locator'

describe('formatLocator', () => {
  it('四种来源定位都有中文说明', () => {
    expect(formatLocator({ type: 'pdf_page', page: 12 })).toBe('第 12 页')
    // 数据里从 0 开始，给人看从 1 开始；Word 只到段落，不出现“页”
    expect(formatLocator({ type: 'docx_para', para_index: 0 })).toBe('第 1 段')
    expect(formatLocator({ type: 'xlsx_range', sheet: '成绩', range: 'B2:F3' })).toBe(
      '工作表“成绩” B2:F3',
    )
    expect(formatLocator({ type: 'image', image_id: 'x' })).toBe('图片')
  })
})

describe('previewQuery：从检索结果跳到预览页的参数', () => {
  it('PDF 带页码和片段', () => {
    expect(previewQuery({ type: 'pdf_page', page: 3 }, 'c1')).toEqual({ page: '3', chunk: 'c1' })
  })

  it('Word、Excel 只带片段', () => {
    expect(previewQuery({ type: 'docx_para', para_index: 4 }, 'c2')).toEqual({ chunk: 'c2' })
  })

  it('只被文件名命中时没有任何参数', () => {
    expect(previewQuery(null, null)).toEqual({})
  })
})

describe('evidenceLabel：命中依据', () => {
  it('没有证据时是文件名或标签匹配', () => {
    expect(evidenceLabel(null)).toBe('文件名或标签匹配')
  })

  it('片段证据显示位置和来源', () => {
    const evidence = {
      chunk_id: 'c',
      image_id: null,
      snippet: 's',
      source_type: 'ocr' as const,
      locator: { type: 'pdf_page' as const, page: 2 },
    }
    expect(evidenceLabel(evidence)).toBe('位置：第 2 页（OCR 文字）')
  })

  it('图片证据说明是 CLIP 图像语义匹配，不与 OCR 混为一谈', () => {
    const evidence = {
      chunk_id: null,
      image_id: 'd1',
      snippet: null,
      source_type: null,
      locator: { type: 'image' as const, image_id: 'd1' },
    }
    expect(evidenceLabel(evidence)).toBe('图像语义匹配（CLIP）')
  })
})

describe('degradedNotice：通道不可用的提示', () => {
  it('图像通道不可用时说明结果只来自文字检索', () => {
    const notice = degradedNotice({
      channel: 'image',
      status: 'unavailable',
      took_ms: 3,
      detail: 'CLIP 服务连接失败（ConnectError）',
    })
    expect(notice).toBe('图像检索暂时不可用，本次结果只来自文字检索（原因：CLIP 服务连接失败（ConnectError））')
  })

  it('没有原因时写“不可用”', () => {
    expect(degradedNotice({ channel: 'meta', status: 'unavailable', took_ms: 0, detail: null })).toBe(
      '文件名/标签通道未参与本次检索：不可用',
    )
  })
})
