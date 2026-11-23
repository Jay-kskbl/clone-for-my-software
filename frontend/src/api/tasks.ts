import { request } from './client'
import type { Task } from './types'

/** 一个文档的全部处理任务，按创建时间从新到旧。扫描件每页一个 OCR 任务，可能有上百条。 */
export async function listDocumentTasks(documentId: string, signal?: AbortSignal): Promise<Task[]> {
  const data = await request<{ items: Task[] }>(`/api/documents/${documentId}/tasks`, { signal })
  return data.items
}

/** 把一个失败的任务放回队列。任务已不是失败状态时抛 409 TASK_NOT_RETRYABLE。 */
export function retryTask(taskId: string): Promise<Task> {
  return request<Task>(`/api/tasks/${taskId}/retry`, { method: 'POST' })
}
