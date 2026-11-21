// 扫描加载动画的状态机（指南 §6.1），纯函数，不碰 DOM，单元测试直接测它。
//
// idle ──start──▶ scanning ──(一轮结束 & 结果未到)──▶ scanning（下一轮）
//                    ├─(一轮结束 & 结果已到)──▶ summarizing ──▶ done
//                    ├─error──▶ error
//                    └─cancel──▶ idle
//
// 关键规则：结果到了也要等当前这一轮播完再切换（complete 只记下“结果已到”）。

export type ScanPhase = 'idle' | 'scanning' | 'summarizing' | 'done' | 'error'

export interface ScanState {
  phase: ScanPhase
  /** 第几轮扫描，从 1 开始；idle 时为 0 */
  round: number
  resultReady: boolean
}

export type ScanEvent =
  | { type: 'start' }
  | { type: 'complete' }
  | { type: 'roundEnd' }
  | { type: 'summarized' }
  | { type: 'error' }
  | { type: 'cancel' }

export const INITIAL_SCAN_STATE: ScanState = { phase: 'idle', round: 0, resultReady: false }

export function scanReducer(state: ScanState, event: ScanEvent): ScanState {
  switch (event.type) {
    case 'start':
      return { phase: 'scanning', round: 1, resultReady: false }
    case 'cancel':
      return INITIAL_SCAN_STATE
    case 'complete':
      return state.phase === 'scanning' ? { ...state, resultReady: true } : state
    case 'roundEnd':
      if (state.phase !== 'scanning') return state
      return state.resultReady ? { ...state, phase: 'summarizing' } : { ...state, round: state.round + 1 }
    case 'summarized':
      return state.phase === 'summarizing' ? { ...state, phase: 'done' } : state
    case 'error':
      return state.phase === 'scanning' ? { ...state, phase: 'error' } : state
  }
}
