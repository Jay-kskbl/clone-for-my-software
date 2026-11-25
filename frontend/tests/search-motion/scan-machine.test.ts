// 扫描加载动画状态机（指南 §6.1；结果一到就收拢是 Barry 2026-11-25 的决定，D60）。纯函数，不需要浏览器。
import { describe, expect, it } from 'vitest'

import { INITIAL_SCAN_STATE, scanReducer, type ScanEvent, type ScanState } from '../../src/features/search-motion/scan-loader/machine'

function run(...events: ScanEvent['type'][]): ScanState {
  return events.reduce<ScanState>((state, type) => scanReducer(state, { type } as ScanEvent), INITIAL_SCAN_STATE)
}

describe('扫描状态机', () => {
  it('start 进入第一轮扫描', () => {
    expect(run('start')).toEqual({ phase: 'scanning', round: 1 })
  })

  it('结果一到就进入整理，不等这一轮播完', () => {
    expect(run('start', 'complete').phase).toBe('summarizing')
    expect(run('start', 'complete', 'summarized').phase).toBe('done')
  })

  it('迟到的 roundEnd 不影响已经开始的整理', () => {
    expect(run('start', 'complete', 'roundEnd')).toEqual({ phase: 'summarizing', round: 1 })
  })

  it('整理中再来一次 complete：不重来', () => {
    expect(run('start', 'complete', 'complete')).toEqual({ phase: 'summarizing', round: 1 })
  })

  it('一轮结束结果未到：继续下一轮', () => {
    expect(run('start', 'roundEnd', 'roundEnd')).toEqual({ phase: 'scanning', round: 3 })
    expect(run('start', 'roundEnd', 'complete').phase).toBe('summarizing')
  })

  it('扫描中出错进入 error；整理中或完成后的 error 被忽略', () => {
    expect(run('start', 'error').phase).toBe('error')
    expect(run('start', 'complete', 'error').phase).toBe('summarizing')
    expect(run('start', 'complete', 'summarized', 'error').phase).toBe('done')
  })

  it('cancel 从任何状态回到 idle', () => {
    for (const events of [['start'], ['start', 'error'], ['start', 'complete']] as ScanEvent['type'][][]) {
      expect(run(...events, 'cancel')).toEqual(INITIAL_SCAN_STATE)
    }
  })

  it('error 之后的 complete 不会让它恢复', () => {
    expect(run('start', 'error', 'complete').phase).toBe('error')
  })

  it('整理中重新 start：从第一轮开始', () => {
    expect(run('start', 'roundEnd', 'complete', 'start')).toEqual({ phase: 'scanning', round: 1 })
  })
})
