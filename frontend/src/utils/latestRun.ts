// 只认最后一次（T24bb）：同一件事可能同时有几次在进行（自动刷新、重试后的刷新、用户翻页），
// 只有最后开始的那次算数——它的结果才显示，也只有它能排下一次定时器；停止（离开页面）之后全部不算。
export class LatestRun {
  private current = 0
  private ended = false

  get stopped(): boolean {
    return this.ended
  }

  /** 开始一次，返回编号；之前的全部作废。 */
  begin(): number {
    this.current += 1
    return this.current
  }

  isCurrent(run: number): boolean {
    return !this.ended && run === this.current
  }

  stop(): void {
    this.ended = true
  }
}
