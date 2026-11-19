/**
 * 检索结果里图片的缩略图（T23）。
 *
 * 下载接口要带登录令牌，<img> 不能直接用接口地址，所以先把文件取成 Blob，
 * 再生成一个 blob: 地址给 <img> 用。后端没有专门的缩略图接口，取回的是原图，
 * 由浏览器缩小显示；为了不拖慢页面：
 * - 只取图片类型的结果；
 * - 超过 maxBytes 的图片不取，显示占位；
 * - 同时最多 concurrency 个下载；
 * - 新的一次检索开始时，上一次还没开始的下载取消，已生成的地址全部释放（revoke）。
 */

export type ThumbnailState =
  | { status: 'loading' }
  | { status: 'ready'; url: string }
  | { status: 'skipped' }
  | { status: 'failed' }

export interface ThumbnailItem {
  id: string
  sizeBytes: number
}

export interface ThumbnailDeps {
  download: (id: string) => Promise<Blob>
  createUrl: (blob: Blob) => string
  revokeUrl: (url: string) => void
  /** 某张图片的状态变化时调用（视图用它刷新） */
  onChange: (id: string, state: ThumbnailState) => void
}

export const THUMBNAIL_MAX_BYTES = 5 * 1024 * 1024
export const THUMBNAIL_CONCURRENCY = 4

export class ThumbnailLoader {
  private generation = 0
  private urls: string[] = []

  constructor(
    private readonly deps: ThumbnailDeps,
    private readonly maxBytes = THUMBNAIL_MAX_BYTES,
    private readonly concurrency = THUMBNAIL_CONCURRENCY,
  ) {}

  /** 换成一批新的图片：释放上一批，再按顺序（结果名次）加载这一批。 */
  async load(items: ThumbnailItem[]): Promise<void> {
    this.reset()
    const generation = this.generation
    const queue: ThumbnailItem[] = []
    for (const item of items) {
      if (item.sizeBytes > this.maxBytes) {
        this.deps.onChange(item.id, { status: 'skipped' })
      } else {
        this.deps.onChange(item.id, { status: 'loading' })
        queue.push(item)
      }
    }
    const worker = async () => {
      for (let item = queue.shift(); item; item = queue.shift()) {
        if (generation !== this.generation) return
        await this.loadOne(item.id, generation)
      }
    }
    await Promise.all(Array.from({ length: Math.min(this.concurrency, queue.length) }, worker))
  }

  /** 释放全部地址，并让进行中的这一批作废（离开页面或开始新检索时调用）。 */
  reset(): void {
    this.generation += 1
    for (const url of this.urls) this.deps.revokeUrl(url)
    this.urls = []
  }

  private async loadOne(id: string, generation: number): Promise<void> {
    let blob: Blob
    try {
      blob = await this.deps.download(id)
    } catch {
      // 缩略图只是辅助显示：取不到时显示占位，不影响检索结果本身
      if (generation === this.generation) this.deps.onChange(id, { status: 'failed' })
      return
    }
    // 下载期间已经开始了新的一次检索：这张图不再需要，也不生成地址
    if (generation !== this.generation) return
    const url = this.deps.createUrl(blob)
    this.urls.push(url)
    this.deps.onChange(id, { status: 'ready', url })
  }
}
