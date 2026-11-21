// 搜索请求与扫描动画的对接层（指南 §6.3）：在请求封装这一层调用 start / complete / error / cancel，
// 保证四个时机一个不漏，而不是散在页面里。
// - 新请求发起时先取消旧请求（AbortController）和旧动画，旧请求晚到的返回直接丢弃（请求编号）。
// - 超过 timeoutMs（默认 30 秒）视为失败。

export interface ScanControls<T> {
  start(): void
  complete(result: T): void
  error(message?: string): void
  cancel(): void
}

export class SearchTimeoutError extends Error {
  readonly timeoutMs: number

  constructor(timeoutMs: number) {
    super(`search timed out after ${timeoutMs} ms`)
    this.name = 'SearchTimeoutError'
    this.timeoutMs = timeoutMs
  }
}

export interface SearchSessionOptions {
  timeoutMs?: number
  /** 当前（未被覆盖的）请求失败时调用：把错误转成提示文字，返回值显示在扫描动画里 */
  onError?: (error: unknown) => string | undefined
}

export interface SearchSession<T> {
  /** 发起一次搜索。task 必须把 signal 传给 fetch，取消和超时才能真正中断请求。 */
  run(task: (signal: AbortSignal) => Promise<T>): Promise<void>
  /** 取消进行中的请求和动画（用户离开页面、组件卸载时）；请求已返回、动画未播完时也会停下动画。 */
  cancel(): void
  readonly pending: boolean
}

export const DEFAULT_SEARCH_TIMEOUT_MS = 30_000

export function createSearchSession<T>(loader: ScanControls<T>, options: SearchSessionOptions = {}): SearchSession<T> {
  const timeoutMs = options.timeoutMs ?? DEFAULT_SEARCH_TIMEOUT_MS
  let current = 0
  let controller: AbortController | null = null
  let timer: ReturnType<typeof setTimeout> | null = null

  function release(): void {
    if (timer !== null) clearTimeout(timer)
    timer = null
    controller = null
  }

  /** 中断进行中的请求，并让它晚到的返回作废。 */
  function abortPending(): void {
    current++
    controller?.abort()
    release()
  }

  function cancel(): void {
    abortPending()
    // 请求已经返回、动画还在播完最后一轮时，也要停下动画（不能只看有没有进行中的请求）
    loader.cancel()
  }

  async function run(task: (signal: AbortSignal) => Promise<T>): Promise<void> {
    // 不调用 loader.cancel()：loader.start() 自己会把旧动画清掉，中间不出现一帧 idle
    abortPending()
    const id = ++current
    const own = new AbortController()
    controller = own
    let timedOut = false
    timer = setTimeout(() => {
      timedOut = true
      own.abort()
    }, timeoutMs)
    loader.start()
    try {
      const result = await task(own.signal)
      if (id !== current) return
      release()
      loader.complete(result)
    } catch (error) {
      if (id !== current) return
      release()
      const reason = timedOut ? new SearchTimeoutError(timeoutMs) : error
      loader.error(options.onError?.(reason))
    }
  }

  return {
    run,
    cancel,
    get pending() {
      return controller !== null
    },
  }
}
