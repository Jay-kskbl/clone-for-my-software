// 任务有了变化之后重新取文档（新功能联测 V1，修 P4 的遗漏）。
//
// 解析刚结束时轮询也停了，这时取文档如果恰好失败一次（网络断开、后端重启），没有人会再取，
// 页面就一直停在“解析中”。所以连不上（status 0）或 5xx 时隔一会儿再试，直到成功或离开页面；
// 4xx（文件已删除、共享被取消、登录过期）再试也没用，提示后停下。
// 同时有两次在进行时只认后一次，迟到的旧响应不会用旧状态盖掉新状态。
import { ApiError } from '../../api/client'
import { LatestRun } from '../../utils/latestRun'
import { WATCH_INTERVAL_MS } from './watcher'

export interface RefresherOptions<T> {
  load: () => Promise<T>
  onLoaded: (value: T) => void
  /** 一次 run() 只在第一次失败时调用一次，之后的自动重试不再打扰 */
  onError: (error: unknown) => void
  interval?: number
}

function mayRecover(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 0 || error.status >= 500)
}

export class Refresher<T> {
  private readonly runs = new LatestRun()
  private timer: ReturnType<typeof setTimeout> | undefined

  constructor(private readonly options: RefresherOptions<T>) {}

  run(): Promise<void> {
    return this.attempt(this.runs.begin(), true)
  }

  stop(): void {
    this.runs.stop()
    clearTimeout(this.timer)
  }

  private async attempt(run: number, first: boolean): Promise<void> {
    clearTimeout(this.timer)
    if (!this.runs.isCurrent(run)) return
    let value: T
    try {
      value = await this.options.load()
    } catch (error) {
      if (!this.runs.isCurrent(run)) return
      if (first) this.options.onError(error)
      if (mayRecover(error)) {
        this.timer = setTimeout(() => void this.attempt(run, false), this.options.interval ?? WATCH_INTERVAL_MS)
      }
      return
    }
    if (this.runs.isCurrent(run)) this.options.onLoaded(value)
  }
}
