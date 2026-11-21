// 定时器集中管理（指南 §3.5、§6.4）：cancel / destroy 时一次清空，不留残留。

export class TimerGroup {
  private readonly ids = new Set<ReturnType<typeof setTimeout>>()

  after(ms: number, fn: () => void): ReturnType<typeof setTimeout> {
    const id = setTimeout(() => {
      this.ids.delete(id)
      fn()
    }, ms)
    this.ids.add(id)
    return id
  }

  cancel(id: ReturnType<typeof setTimeout> | null | undefined): void {
    if (id == null) return
    clearTimeout(id)
    this.ids.delete(id)
  }

  clear(): void {
    for (const id of this.ids) clearTimeout(id)
    this.ids.clear()
  }

  get size(): number {
    return this.ids.size
  }
}
