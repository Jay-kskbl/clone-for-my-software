// 检索页的通道开关与每条结果的通道名次（T24s）。
//
// 后端有三个通道：meta（文件名/标签）、text（文字）、image（图像语义，CLIP）。
// 正文和 OCR 文字同属 text 通道，用 source_types 区分（docs/api.md §7.1），
// 所以页面上是四个开关、三个通道。这里只放纯函数，便于单元测试。
import type {
  Channel,
  ChannelResult,
  ChannelStatus,
  SearchRequest,
  SourceType,
} from '../api/types'

export interface ChannelSelection {
  meta: boolean
  body: boolean
  ocr: boolean
  image: boolean
}

type SelectionKey = keyof ChannelSelection

const SELECTION_KEYS: SelectionKey[] = ['meta', 'body', 'ocr', 'image']

/** 与后端的默认值一致：文件名、正文、OCR 开，图像关（docs/decisions.md D36）。 */
export const DEFAULT_SELECTION: Readonly<ChannelSelection> = {
  meta: true,
  body: true,
  ocr: true,
  image: false,
}

/** 四个开关全关：三个通道都没开，后端会返回 422，前端先拦下来。 */
export function isEmptySelection(selection: ChannelSelection): boolean {
  return SELECTION_KEYS.every((key) => !selection[key])
}

/**
 * 地址栏参数 ch：刷新页面或从预览页返回时开关保持不变。
 * 与默认值相同时不写；否则列出开着的开关，例如 ch=meta,body。
 */
export function selectionToQuery(selection: ChannelSelection): string | undefined {
  if (SELECTION_KEYS.every((key) => selection[key] === DEFAULT_SELECTION[key])) return undefined
  return SELECTION_KEYS.filter((key) => selection[key]).join(',')
}

export function selectionFromQuery(query: Record<string, unknown>): ChannelSelection {
  if (typeof query.ch === 'string') {
    const keys = new Set(query.ch.split(','))
    const selection = {
      meta: keys.has('meta'),
      body: keys.has('body'),
      ocr: keys.has('ocr'),
      image: keys.has('image'),
    }
    if (!isEmptySelection(selection)) return selection
  }
  // T24s 之前的地址只用 img=1 表示开启图像检索
  return { ...DEFAULT_SELECTION, image: query.img === '1' }
}

export function buildSearchRequest(query: string, selection: ChannelSelection): SearchRequest {
  const sourceTypes: SourceType[] = []
  if (selection.body) sourceTypes.push('body')
  if (selection.ocr) sourceTypes.push('ocr')
  const text = sourceTypes.length > 0
  return {
    query,
    channels: { meta: selection.meta, text, image: selection.image },
    // 文字通道关掉时不传 source_types：传空列表后端返回 422
    source_types: text ? sourceTypes : undefined,
  }
}

// ---- 每条结果在三个通道里的名次 ----

export const CELL_CHANNELS: Channel[] = ['meta', 'text', 'image']

/**
 * hit：命中，有名次；miss：通道执行了但没有命中这个文件；
 * disabled：这次没开这个通道；unavailable：开了但出了故障（例如 CLIP 服务没启动）。
 * 后三种要分开显示，否则看不出图像通道是“没找到”还是“根本没参与”（GLOBAL §12）。
 */
export type CellState = 'hit' | 'miss' | 'disabled' | 'unavailable'

export interface ChannelCell {
  channel: Channel
  state: CellState
  rank: number | null
}

export function channelCells(hitChannels: ChannelResult[], statuses: ChannelStatus[]): ChannelCell[] {
  return CELL_CHANNELS.map((channel) => {
    const result = hitChannels.find((c) => c.channel === channel)
    if (result) return { channel, state: 'hit', rank: result.rank }
    const status = statuses.find((s) => s.channel === channel)?.status
    if (status === 'disabled') return { channel, state: 'disabled', rank: null }
    if (status === 'unavailable') return { channel, state: 'unavailable', rank: null }
    return { channel, state: 'miss', rank: null }
  })
}

export function cellText(cell: ChannelCell): string {
  switch (cell.state) {
    case 'hit':
      return `第 ${cell.rank} 名`
    case 'miss':
      return '未命中'
    case 'disabled':
      return '未开启'
    case 'unavailable':
      return '不可用'
  }
}

/** 一个通道本次的执行情况：执行了显示耗时，否则说明没开或不可用。 */
export function channelStatusText(status: ChannelStatus): string {
  switch (status.status) {
    case 'ok':
      return `${status.took_ms} 毫秒`
    case 'disabled':
      return '未开启'
    case 'unavailable':
      return '不可用'
  }
}

/** RRF 融合分（Σ 1/(k+名次)）通常只有百分之几，保留 4 位小数才看得出差别。 */
export function formatScore(score: number): string {
  return score.toFixed(4)
}
