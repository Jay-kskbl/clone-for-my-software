import { describe, expect, it, vi } from 'vitest'

import { ThumbnailLoader, type ThumbnailState } from '../src/utils/thumbnails'

function setup(download: (id: string) => Promise<Blob>, maxBytes = 100, concurrency = 2) {
  const states: Record<string, ThumbnailState> = {}
  const revoked: string[] = []
  let n = 0
  const loader = new ThumbnailLoader(
    {
      download,
      createUrl: () => `blob:${++n}`,
      revokeUrl: (url) => void revoked.push(url),
      onChange: (id, state) => {
        states[id] = state
      },
    },
    maxBytes,
    concurrency,
  )
  return { loader, states, revoked }
}

describe('ThumbnailLoader：检索结果的图片缩略图', () => {
  it('逐个下载并生成地址；过大的图片不下载', async () => {
    const download = vi.fn(async (_id: string) => new Blob(['x']))
    const { loader, states } = setup(download)

    await loader.load([
      { id: 'a', sizeBytes: 10 },
      { id: 'big', sizeBytes: 101 },
      { id: 'b', sizeBytes: 100 },
    ])

    expect(states).toEqual({
      a: { status: 'ready', url: 'blob:1' },
      big: { status: 'skipped' },
      b: { status: 'ready', url: 'blob:2' },
    })
    expect(download.mock.calls.map((c) => c[0])).toEqual(['a', 'b'])
  })

  it('下载失败只把这一张标为失败，其他照常', async () => {
    const { loader, states } = setup(async (id) => {
      if (id === 'a') throw new Error('403')
      return new Blob(['x'])
    })

    await loader.load([
      { id: 'a', sizeBytes: 1 },
      { id: 'b', sizeBytes: 1 },
    ])

    expect(states.a).toEqual({ status: 'failed' })
    expect(states.b.status).toBe('ready')
  })

  it('同时下载的数目不超过上限', async () => {
    let running = 0
    let peak = 0
    const { loader } = setup(async () => {
      running += 1
      peak = Math.max(peak, running)
      await new Promise((resolve) => setTimeout(resolve, 1))
      running -= 1
      return new Blob(['x'])
    })

    await loader.load(Array.from({ length: 6 }, (_, i) => ({ id: String(i), sizeBytes: 1 })))

    expect(peak).toBe(2)
  })

  it('新一批开始时释放上一批的地址；上一批迟到的下载不再生成地址', async () => {
    let release: (blob: Blob) => void = () => {}
    const slow = new Promise<Blob>((resolve) => (release = resolve))
    const download = vi.fn((id: string) => (id === 'slow' ? slow : Promise.resolve(new Blob(['x']))))
    const { loader, states, revoked } = setup(download, 100, 1)

    await loader.load([{ id: 'a', sizeBytes: 1 }])
    const first = loader.load([{ id: 'slow', sizeBytes: 1 }])
    expect(revoked).toEqual(['blob:1'])

    await loader.load([{ id: 'c', sizeBytes: 1 }])
    release(new Blob(['x']))
    await first

    expect(states.slow).toEqual({ status: 'loading' })
    expect(states.c).toEqual({ status: 'ready', url: 'blob:2' })
  })

  it('reset 释放全部地址', async () => {
    const { loader, revoked } = setup(async () => new Blob(['x']))
    await loader.load([
      { id: 'a', sizeBytes: 1 },
      { id: 'b', sizeBytes: 1 },
    ])

    loader.reset()

    expect(revoked.sort()).toEqual(['blob:1', 'blob:2'])
  })
})
