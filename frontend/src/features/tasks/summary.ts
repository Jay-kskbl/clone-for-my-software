// 把一个文档的任务列表汇总成几个处理步骤（任务状态与重试 P2）。纯函数，不碰 DOM 和网络。
//
// 文档状态只跟随 parse 任务（decisions.md D27），OCR、向量任务失败时文档仍是“成功”，
// 所以要看任务本身。扫描件一页一个 OCR 任务，可能上百条，按类型汇总后再显示。
import type { Status, Task, TaskType } from '../../api/types'

export const STEP_ORDER: readonly TaskType[] = ['parse', 'ocr', 'embed', 'cleanup']

/** waiting 还没开始；running 正在进行；partial 都结束了但有一部分失败 */
export type StepState = 'waiting' | 'running' | 'succeeded' | 'partial' | 'failed'

export interface TaskStep {
  type: TaskType
  state: StepState
  total: number
  succeeded: number
  /** 还没结束的（等待 + 处理中） */
  active: number
  failed: Task[]
  /** 失败的原因及各有几项，多的在前；没有记录原因的归到 null */
  reasons: { text: string | null; count: number }[]
  /** 等待重试的任务里最近的一个：已经失败过，还会再处理 */
  waitingRetry: Task | null
  /** 只有一个任务时给出它，用来显示用时、尝试次数 */
  single: Task | null
}

export function isActive(task: Task): boolean {
  return task.status === 'pending' || task.status === 'processing'
}

/**
 * 次数没用完就标为失败：后端判定重试也不会成功（文件损坏、加密等，retryable=False）。
 * 次数恰好用完时分不出来，按“可以再试”处理，只影响要不要多一句提示。
 */
export function isHopeless(task: Task): boolean {
  return task.status === 'failed' && task.attempts < task.max_attempts
}

function stateOf(tasks: Task[]): StepState {
  const active = tasks.filter(isActive).length
  const failed = tasks.filter((t) => t.status === 'failed').length
  if (active > 0) {
    // 有一项开始过（在处理，或已经有结果），就算进行中
    const untouched = tasks.every((t) => t.status === 'pending' && t.attempts === 0)
    return untouched ? 'waiting' : 'running'
  }
  if (failed === 0) return 'succeeded'
  return failed === tasks.length ? 'failed' : 'partial'
}

function reasonsOf(failed: Task[]): TaskStep['reasons'] {
  const counts = new Map<string | null, number>()
  for (const task of failed) counts.set(task.error || null, (counts.get(task.error || null) ?? 0) + 1)
  return [...counts].map(([text, count]) => ({ text, count })).sort((a, b) => b.count - a.count)
}

export function summarizeTasks(tasks: Task[]): TaskStep[] {
  const byType = new Map<TaskType, Task[]>()
  for (const task of tasks) byType.set(task.task_type, [...(byType.get(task.task_type) ?? []), task])

  // 认识的步骤按处理顺序排，以后新增的类型排在最后，不丢掉
  const known = STEP_ORDER.filter((type) => byType.has(type))
  const unknown = [...byType.keys()].filter((type) => !STEP_ORDER.includes(type))
  return [...known, ...unknown].map((type) => {
    const items = byType.get(type) ?? []
    const failed = items.filter((t) => t.status === 'failed')
    const waiting = items.filter((t) => t.status === 'pending' && t.attempts > 0)
    return {
      type,
      state: stateOf(items),
      total: items.length,
      succeeded: items.filter((t) => t.status === 'succeeded').length,
      active: items.filter(isActive).length,
      failed,
      reasons: reasonsOf(failed),
      waitingRetry: waiting[0] ?? null,
      single: items.length === 1 ? items[0] : null,
    }
  })
}

/** 还有没结束的任务：需要继续刷新 */
export function hasActive(tasks: Task[]): boolean {
  return tasks.some(isActive)
}

/** 解析任务的状态，文档状态跟随它（D27）。一个文档只有一个 parse 任务；没有时为 null */
export function parseStatus(tasks: Task[]): Status | null {
  return tasks.find((t) => t.task_type === 'parse')?.status ?? null
}

export function failedTasks(tasks: Task[]): Task[] {
  return tasks.filter((t) => t.status === 'failed')
}

/** 一个任务的处理用时（毫秒）；没开始、没结束或时间不合理时为 null */
export function durationMs(task: Task): number | null {
  if (!task.started_at || !task.finished_at) return null
  const ms = new Date(task.finished_at).getTime() - new Date(task.started_at).getTime()
  return Number.isFinite(ms) && ms >= 0 ? ms : null
}
