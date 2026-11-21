// 扫描加载动画状态机（指南 §6.1）。纯函数，不需要浏览器。
import { describe, expect, it } from 'vitest'

import { INITIAL_SCAN_STATE, scanReducer, type ScanEvent, type ScanState } from '../../src/features/search-motion/scan-loader/machine'

function run(...events: ScanEvent['type'][]): ScanState {
  return events.reduce<ScanState>((state, type) => scanReducer(state, { type } as ScanEvent), INITIAL_SCAN_STATE)
}

describe('扫描状态机', () => {
  it('start 进入第一轮扫描', () => {
    expect(run('start')).toEqual({ phase: 'scanning', round: 1, resultReady: false })
  })

  it('结果到了也要等这一轮播完才进入整理', () => {
    const state = run('start', 'complete')
    expect(state.phase).toBe('scanning')
    expect(state.resultReady).toBe(true)
    expect(run('start', 'complete', 'roundEnd').phase).toBe('summarizing')
    expect(run('start', 'complete', 'roundEnd', 'summarized').phase).toBe('done')
  })

  it('一轮结束结果未到：继续下一轮', () => {
    expect(run('start', 'roundEnd', 'roundEnd')).toEqual({ phase: 'scanning', round: 3, resultReady: false })
    expect(run('start', 'roundEnd', 'complete', 'roundEnd').phase).toBe('summarizing')
  })

  it('扫描中出错进入 error；整理中或完成后的 error 被忽略', () => {
    expect(run('start', 'error').phase).toBe('error')
    expect(run('start', 'complete', 'roundEnd', 'error').phase).toBe('summarizing')
    expect(run('start', 'complete', 'roundEnd', 'summarized', 'error').phase).toBe('done')
  })

  it('cancel 从任何状态回到 idle', () => {
    for (const events of [['start'], ['start', 'error'], ['start', 'complete', 'roundEnd']] as ScanEvent['type'][][]) {
      expect(run(...events, 'cancel')).toEqual(INITIAL_SCAN_STATE)
    }
  })

  it('error 之后的 complete 不会让它恢复', () => {
    expect(run('start', 'error', 'complete', 'roundEnd').phase).toBe('error')
  })

  it('重新 start 从第一轮开始，清掉上一次的结果标记', () => {
    expect(run('start', 'complete', 'start')).toEqual({ phase: 'scanning', round: 1, resultReady: false })
  })
})
