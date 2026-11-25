import type { Task, TaskType, Status } from '../../src/api/types'

let next = 0

export function task(type: TaskType, status: Status, over: Partial<Task> = {}): Task {
  next += 1
  return {
    id: `t${next}`,
    document_id: 'd1',
    task_type: type,
    status,
    attempts: status === 'pending' ? 0 : status === 'failed' ? 3 : 1,
    max_attempts: 3,
    error: null,
    created_at: '2026-11-23T08:00:00Z',
    started_at: null,
    finished_at: null,
    ...over,
  }
}
