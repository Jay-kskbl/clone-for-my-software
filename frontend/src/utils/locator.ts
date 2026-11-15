import type { Locator, SourceType } from '../api/types'

/**
 * 来源位置的中文说明。Word 只到段落（附录 A9），不显示页码。
 * 段落序号在数据里从 0 开始，给人看时从 1 开始。
 */
export function formatLocator(locator: Locator): string {
  switch (locator.type) {
    case 'pdf_page':
      return `第 ${locator.page} 页`
    case 'docx_para':
      return `第 ${locator.para_index + 1} 段`
    case 'xlsx_range':
      return `工作表“${locator.sheet}” ${locator.range}`
    case 'image':
      return '图片'
  }
}

export const SOURCE_TYPE_LABEL: Record<SourceType, string> = {
  body: '正文',
  ocr: 'OCR 文字',
}

export const CHANNEL_LABEL: Record<'meta' | 'text' | 'image', string> = {
  meta: '文件名/标签',
  text: '正文',
  image: '图像',
}

/** 预览页的地址：PDF 带上页码，其他类型带上命中片段的 ID，用来跳到命中的位置。 */
export function previewQuery(locator: Locator | null, chunkId: string | null): Record<string, string> {
  const query: Record<string, string> = {}
  if (locator?.type === 'pdf_page') query.page = String(locator.page)
  if (chunkId) query.chunk = chunkId
  return query
}
