// 处理详情里的文字（任务状态与重试 P3）：步骤名、状态、说明、重试结果。
// 每次显示时按当前语言生成。失败原因来自后端，切到英文时仍是中文（与其他后端文字相同）。
import { errorMessage } from '../../api/client'
import type { TaskType } from '../../api/types'
import { m } from '../../i18n'
import type { RetryResult } from './retry'
import { durationMs, isHopeless, type StepState, type TaskStep } from './summary'

type TagType = 'info' | 'primary' | 'success' | 'warning' | 'danger'

const STATE_TAG: Record<StepState, TagType> = {
  waiting: 'info',
  running: 'primary',
  succeeded: 'success',
  partial: 'warning',
  failed: 'danger',
}

export function stateTag(state: StepState): { text: string; type: TagType } {
  return { text: m().tasks.state[state], type: STATE_TAG[state] }
}

export function stepName(type: TaskType): string {
  // 后端以后新增的类型这里没有名字，直接显示类型，不留空
  return m().tasks.step[type] ?? type
}

export function formatDuration(ms: number): string {
  const text = m().tasks
  if (ms < 1000) return text.underSecond
  const seconds = Math.round(ms / 1000)
  if (seconds < 60) return text.seconds(seconds)
  return text.minutes(Math.floor(seconds / 60), seconds % 60)
}

/** 一个步骤的说明，一句一行：计数、用时、尝试次数、原因 */
export function stepDetails(step: TaskStep): string[] {
  const text = m().tasks
  const lines: string[] = []
  if (step.single) {
    const took = durationMs(step.single)
    if (step.single.status === 'succeeded' && took !== null) lines.push(text.took(formatDuration(took)))
    if (step.single.status === 'failed') lines.push(text.attempts(step.single.attempts, step.single.max_attempts))
  } else {
    lines.push(text.counts(step.total, step.succeeded, step.failed.length, step.active))
  }
  if (step.waitingRetry) {
    lines.push(text.waitingRetry(step.waitingRetry.attempts, step.waitingRetry.max_attempts))
    if (step.waitingRetry.error) lines.push(text.reason(step.waitingRetry.error))
  }
  for (const reason of step.reasons) {
    const what = reason.text ?? text.unknownReason
    lines.push(step.total === 1 ? text.reason(what) : text.reasonCount(what, reason.count))
  }
  return lines
}

/** 重试大概率无用时的提醒；不需要提醒时为 null */
export function hopelessNotice(step: TaskStep): string | null {
  const hopeless = step.failed.filter(isHopeless).length
  if (hopeless === 0) return null
  return hopeless === step.failed.length ? m().tasks.hopelessAll : m().tasks.hopelessSome(hopeless)
}

export function retryLabel(step: TaskStep): string {
  return step.total === 1 ? m().tasks.retry : m().tasks.retryMany(step.failed.length)
}

/** 重试之后的提示 */
export function retryMessage(result: RetryResult): { type: 'success' | 'warning' | 'error'; text: string } {
  const text = m().tasks
  const parts: string[] = []
  const unsuccessful = result.failed + result.notSent
  if (result.queued > 0) parts.push(text.retried(result.queued))
  if (result.skipped > 0) parts.push(text.retrySkipped(result.skipped))
  if (unsuccessful > 0) parts.push(text.retryFailed(unsuccessful, errorMessage(result.error)))
  const type = unsuccessful === 0 ? 'success' : result.queued > 0 ? 'warning' : 'error'
  return { type, text: parts.join(text.join) }
}
