// 扫描加载动画的状态机（指南 §6.1），纯函数，不碰 DOM，单元测试直接测它。
//
// idle ──start──▶ scanning ──(一轮结束)──▶ scanning（下一轮）
//                    ├─complete──▶ summarizing ──▶ done
//                    ├─error──▶ error
//                    └─cancel──▶ idle
//
// 关键规则：结果一到就收拢，不等当前这一轮播完。指南 §6.1 原来要求播完一轮，那样后端 50 毫秒返回也要
// 等约 4 秒才看到结果；Barry 于 2026-11-25 决定改成现在这样（decisions.md D60）。

export type ScanPhase = 'idle' | 'scanning' | 'summarizing' | 'done' | 'error'

export interface ScanState {
  phase: ScanPhase
  /** 第几轮扫描，从 1 开始；idle 时为 0 */
  round: number
}

export type ScanEvent =
  | { type: 'start' }
  | { type: 'complete' }
  | { type: 'roundEnd' }
  | { type: 'summarized' }
  | { type: 'error' }
  | { type: 'cancel' }

export const INITIAL_SCAN_STATE: ScanState = { phase: 'idle', round: 0 }

export function scanReducer(state: ScanState, event: ScanEvent): ScanState {
  switch (event.type) {
    case 'start':
      return { phase: 'scanning', round: 1 }
    case 'cancel':
      return INITIAL_SCAN_STATE
    case 'complete':
      return state.phase === 'scanning' ? { ...state, phase: 'summarizing' } : state
    case 'roundEnd':
      return state.phase === 'scanning' ? { ...state, round: state.round + 1 } : state
    case 'summarized':
      return state.phase === 'summarizing' ? { ...state, phase: 'done' } : state
    case 'error':
      return state.phase === 'scanning' ? { ...state, phase: 'error' } : state
  }
}
