import type { Channel, ChannelStatus, Evidence, Locator, SourceType } from '../api/types'

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

export const CHANNEL_LABEL: Record<Channel, string> = {
  meta: '文件名/标签',
  text: '正文',
  image: '图像',
}

// 命中通道标记的颜色：一眼能看出结果来自文字检索还是图像语义检索
export const CHANNEL_TAG_TYPE: Record<Channel, 'info' | 'primary' | 'success'> = {
  meta: 'info',
  text: 'primary',
  image: 'success',
}

/**
 * 一条结果的命中依据。图片证据来自 CLIP 图像语义检索（不是 OCR 文字），
 * 要与 OCR 命中分开说明（GLOBAL §4.1、§13）。
 */
export function evidenceLabel(evidence: Evidence | null): string {
  if (!evidence) return '文件名或标签匹配'
  if (evidence.image_id) return '图像语义匹配（CLIP）'
  const where = `位置：${formatLocator(evidence.locator)}`
  return evidence.source_type ? `${where}（${SOURCE_TYPE_LABEL[evidence.source_type]}）` : where
}

/** 本应执行却没有执行成功的通道的提示。图像通道不可用时，结果只来自文字检索。 */
export function degradedNotice(status: ChannelStatus): string {
  const reason = status.detail ?? '不可用'
  if (status.channel === 'image') {
    return `图像检索暂时不可用，本次结果只来自文字检索（原因：${reason}）`
  }
  return `${CHANNEL_LABEL[status.channel]}通道未参与本次检索：${reason}`
}

/** 预览页的地址：PDF 带上页码，其他类型带上命中片段的 ID，用来跳到命中的位置。 */
export function previewQuery(locator: Locator | null, chunkId: string | null): Record<string, string> {
  const query: Record<string, string> = {}
  if (locator?.type === 'pdf_page') query.page = String(locator.page)
  if (chunkId) query.chunk = chunkId
  return query
}
