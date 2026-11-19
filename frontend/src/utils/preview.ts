/** 预览页的标签页（T24f，decisions.md D45）。只有 PDF 和图片分“原文件 / 抽取文本”两页。 */

export type PreviewTab = 'file' | 'text'

/**
 * 打开预览页时默认显示哪个标签页。
 *
 * - 地址栏里有 view=file / view=text：照它（刷新、复制链接时停在同一页）。
 * - 从检索结果打开图片（带命中片段 chunk）：显示抽取文本并跳到那个片段。图片的命中证据
 *   就是 OCR 文字，原图上没法高亮。
 * - 其余情况（包括从检索结果打开 PDF）：原文件。PDF 由 pdf.js 跳到命中的页。
 */
export function initialPreviewTab(kind: 'pdf' | 'image', query: Record<string, unknown>): PreviewTab {
  if (query.view === 'file' || query.view === 'text') return query.view
  if (kind === 'image' && typeof query.chunk === 'string' && query.chunk !== '') return 'text'
  return 'file'
}
