// 盯着一个文档的任务（任务状态与重试 P2）：有没结束的任务就每隔几秒刷新一次，都结束了就停。
//
// 两条约定，避免文件列表里已有的两个毛病：
// - 换文档、主动刷新、停止时，旧请求取消，迟到的响应丢弃（不会用旧数据盖掉新数据）；
// - stop() 之后不再发请求、不再排下一次（离开页面后不会继续轮询）。
import type { Task } from '../../api/types'
import { hasActive } from './summary'

export const WATCH_INTERVAL_MS = 3000

export interface WatcherOptions {
  load: (documentId: string, signal: AbortSignal) => Promise<Task[]>
  onTasks: (tasks: Task[]) => void
  /** silent：自动刷新失败（页面上已经有旧数据） */
  onError: (error: unknown, silent: boolean) => void
  interval?: number
}

export class TaskWatcher {
  private documentId: string | null = null
  private generation = 0
  private controller: AbortController | null = null
  private timer: ReturnType<typeof setTimeout> | undefined
  private active = false
  private loaded = false

  constructor(private readonly options: WatcherOptions) {}

  /** 开始盯一个文档（换文档时直接再调一次）。 */
  start(documentId: string): Promise<void> {
    this.stop()
    this.documentId = documentId
    return this.run()
  }

  /** 立即刷新一次，例如点了重试之后。没有在盯任何文档时什么也不做。 */
  refresh(): Promise<void> {
    if (this.documentId === null) return Promise.resolve()
    return this.run()
  }

  stop(): void {
    this.cancel()
    this.documentId = null
    this.active = false
    this.loaded = false
  }

  private cancel(): void {
    this.generation += 1
    this.controller?.abort()
    this.controller = null
    clearTimeout(this.timer)
    this.timer = undefined
  }

  private async run(): Promise<void> {
    const documentId = this.documentId
    if (documentId === null) return
    this.cancel()
    const generation = this.generation
    const controller = new AbortController()
    this.controller = controller
    try {
      const tasks = await this.options.load(documentId, controller.signal)
      if (generation !== this.generation) return
      this.loaded = true
      this.active = hasActive(tasks)
      this.options.onTasks(tasks)
    } catch (error) {
      if (generation !== this.generation) return
      this.options.onError(error, this.loaded)
    }
    // 回调里可能已经 stop 或 refresh；自动刷新失败时，只要上次还有没结束的任务就接着试
    if (generation !== this.generation || !this.active) return
    this.timer = setTimeout(() => void this.run(), this.options.interval ?? WATCH_INTERVAL_MS)
  }
}
