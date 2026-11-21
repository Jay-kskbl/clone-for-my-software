import { describe, expect, it } from 'vitest'

import type { ChannelResult, ChannelStatus } from '../src/api/types'
import {
  DEFAULT_SELECTION,
  buildSearchRequest,
  cellText,
  channelCells,
  channelStatusText,
  formatScore,
  isEmptySelection,
  selectionFromQuery,
  selectionToQuery,
} from '../src/utils/channels'
import { typeBadge } from '../src/utils/format'

const ALL_ON = { meta: true, body: true, ocr: true, image: true }
const ALL_OFF = { meta: false, body: false, ocr: false, image: false }

function status(channel: ChannelStatus['channel'], state: ChannelStatus['status'], tookMs = 0): ChannelStatus {
  return { channel, status: state, took_ms: tookMs, detail: null }
}

describe('通道开关与地址栏（T24s）', () => {
  it('默认值与后端一致：图像关，其余开', () => {
    expect(DEFAULT_SELECTION).toEqual({ meta: true, body: true, ocr: true, image: false })
  })

  it('默认开关不写进地址栏', () => {
    expect(selectionToQuery({ ...DEFAULT_SELECTION })).toBeUndefined()
  })

  it('非默认开关写成 ch=…，读回来一致', () => {
    const selection = { meta: false, body: true, ocr: false, image: true }
    const ch = selectionToQuery(selection)
    expect(ch).toBe('body,image')
    expect(selectionFromQuery({ ch })).toEqual(selection)
  })

  it('没有 ch 时用默认值；兼容旧地址的 img=1', () => {
    expect(selectionFromQuery({})).toEqual(DEFAULT_SELECTION)
    expect(selectionFromQuery({ img: '1' })).toEqual({ ...DEFAULT_SELECTION, image: true })
  })

  it('ch 为空或全是无效值时退回默认值，不会得到四个都关的开关', () => {
    expect(selectionFromQuery({ ch: '' })).toEqual(DEFAULT_SELECTION)
    expect(selectionFromQuery({ ch: 'foo,bar' })).toEqual(DEFAULT_SELECTION)
  })

  it('isEmptySelection 只在四个都关时为真', () => {
    expect(isEmptySelection(ALL_OFF)).toBe(true)
    expect(isEmptySelection({ ...ALL_OFF, ocr: true })).toBe(false)
  })
})

describe('buildSearchRequest', () => {
  it('全开：三个通道都开，source_types 含正文和 OCR', () => {
    expect(buildSearchRequest('交换机', ALL_ON)).toEqual({
      query: '交换机',
      channels: { meta: true, text: true, image: true },
      source_types: ['body', 'ocr'],
    })
  })

  it('只开 OCR：文字通道开，source_types 只有 ocr', () => {
    const request = buildSearchRequest('q', { ...ALL_OFF, ocr: true })
    expect(request.channels).toEqual({ meta: false, text: true, image: false })
    expect(request.source_types).toEqual(['ocr'])
  })

  it('正文和 OCR 都关：文字通道关，且不传 source_types（传空列表后端会返回 422）', () => {
    const request = buildSearchRequest('q', { ...ALL_OFF, meta: true })
    expect(request.channels).toEqual({ meta: true, text: false, image: false })
    expect(request.source_types).toBeUndefined()
  })
})

describe('每条结果的通道名次', () => {
  const statuses = [status('meta', 'ok'), status('text', 'ok'), status('image', 'disabled')]

  it('按 文件名、文字、图像 的固定顺序给出三格', () => {
    const cells = channelCells([], statuses)
    expect(cells.map((c) => c.channel)).toEqual(['meta', 'text', 'image'])
  })

  it('命中的给名次；执行了没命中、没开、不可用分开标记', () => {
    const hitChannels: ChannelResult[] = [{ channel: 'text', rank: 3, score: 1.2 }]
    const cells = channelCells(hitChannels, [status('meta', 'ok'), status('text', 'ok'), status('image', 'unavailable')])
    expect(cells).toEqual([
      { channel: 'meta', state: 'miss', rank: null },
      { channel: 'text', state: 'hit', rank: 3 },
      { channel: 'image', state: 'unavailable', rank: null },
    ])
    expect(cells.map(cellText)).toEqual(['未命中', '第 3 名', '不可用'])
  })

  it('没开的通道显示“未开启”', () => {
    const image = channelCells([], statuses)[2]
    expect(image.state).toBe('disabled')
    expect(cellText(image)).toBe('未开启')
  })

  it('通道执行情况：执行了给耗时', () => {
    expect(channelStatusText(status('text', 'ok', 35))).toBe('35 毫秒')
    expect(channelStatusText(status('image', 'disabled'))).toBe('未开启')
    expect(channelStatusText(status('image', 'unavailable'))).toBe('不可用')
  })

  it('融合分保留 4 位小数', () => {
    // RRF，k = 60：第 1 名 + 第 1 名
    expect(formatScore(1 / 61 + 1 / 61)).toBe('0.0328')
  })
})

describe('typeBadge', () => {
  it.each([
    ['application/pdf', 'PDF'],
    ['application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'DOC'],
    ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'XLS'],
    ['image/png', '图片'],
    ['image/jpeg', '图片'],
    ['application/zip', '文件'],
  ])('%s → %s', (mime, text) => {
    expect(typeBadge(mime).text).toBe(text)
  })
})
