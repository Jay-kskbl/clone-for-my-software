import type { Channel, ChannelStatus, Evidence, Locator, SourceType } from '../api/types'
import { m, translated } from '../i18n'

/**
 * 来源位置的说明（文字随界面语言）。Word 只到段落（附录 A9），不显示页码。
 * 段落序号在数据里从 0 开始，给人看时从 1 开始。
 */
export function formatLocator(locator: Locator): string {
  switch (locator.type) {
    case 'pdf_page':
      return m().locator.page(locator.page)
    case 'docx_para':
      return m().locator.para(locator.para_index + 1)
    case 'xlsx_range':
      return m().locator.sheet(locator.sheet, locator.range)
    case 'image':
      return m().locator.image
  }
}

export const SOURCE_TYPE_LABEL: Record<SourceType, string> = translated((msg) => ({ ...msg.locator.source }))

// text 通道同时检索正文和 OCR 文字（用 source_types 区分），所以叫“文字”而不是“正文”（T24s）
export const CHANNEL_LABEL: Record<Channel, string> = translated((msg) => ({ ...msg.locator.channel }))

// 检索结果右侧名次格子里用的短名称
export const CHANNEL_SHORT_LABEL: Record<Channel, string> = translated((msg) => ({ ...msg.locator.channelShort }))

/**
 * 一条结果的命中依据。图片证据来自 CLIP 图像语义检索（不是 OCR 文字），
 * 要与 OCR 命中分开说明（GLOBAL §4.1、§13）。
 */
export function evidenceLabel(evidence: Evidence | null): string {
  const msg = m().locator
  if (!evidence) return msg.evidenceMeta
  if (evidence.image_id) return msg.evidenceImage
  const where = msg.where(formatLocator(evidence.locator))
  return evidence.source_type ? msg.withSource(where, SOURCE_TYPE_LABEL[evidence.source_type]) : where
}

/** 本应执行却没有执行成功的通道的提示。图像通道不可用时，结果只来自文字检索。 */
export function degradedNotice(status: ChannelStatus): string {
  const msg = m().locator
  const reason = status.detail ?? msg.unavailable
  if (status.channel === 'image') return msg.imageDegraded(reason)
  return msg.channelDegraded(CHANNEL_LABEL[status.channel], reason)
}

/** 预览页的地址：PDF 带上页码，其他类型带上命中片段的 ID，用来跳到命中的位置。 */
export function previewQuery(locator: Locator | null, chunkId: string | null): Record<string, string> {
  const query: Record<string, string> = {}
  if (locator?.type === 'pdf_page') query.page = String(locator.page)
  if (chunkId) query.chunk = chunkId
  return query
}
