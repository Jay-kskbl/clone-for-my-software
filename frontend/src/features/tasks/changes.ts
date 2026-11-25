// 预览页要不要跟着任务的变化刷新（T24bd）。纯函数。
import type { Status, Task } from '../../api/types'
import { parseStatus } from './summary'

/**
 * 页面上的文档状态过时了，要重新取文档。
 *
 * 不能简单地比较“文档状态 ≠ 解析任务状态”：解析失败等待重试时，任务是 pending、文档是
 * processing（D27），两者本来就不同，那样每次轮询都会去取一次文档。
 */
export function documentOutdated(shown: Status, previous: Task[] | null, next: Task[]): boolean {
  const now = parseStatus(next)
  if (now === null) return false
  if (previous !== null) return parseStatus(previous) !== now
  // 第一次拿到任务：文档是先取的，中间可能刚好解析完
  return (now === 'succeeded' || now === 'failed') && now !== shown
}

/** 又有 OCR 任务成功了，可能有新的识别文字 */
export function hasNewOcr(previous: Task[] | null, next: Task[]): boolean {
  if (previous === null) return false
  const done = new Set(previous.filter(isDoneOcr).map((t) => t.id))
  return next.some((t) => isDoneOcr(t) && !done.has(t.id))
}

function isDoneOcr(task: Task): boolean {
  return task.task_type === 'ocr' && task.status === 'succeeded'
}
