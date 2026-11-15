import { describe, expect, it } from 'vitest'

import { formatLocator, previewQuery } from '../src/utils/locator'

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
