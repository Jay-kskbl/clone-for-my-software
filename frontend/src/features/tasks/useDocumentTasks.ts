// 一个文档的处理任务：加载、自动刷新、重试（T24bd）。
// 文件列表的处理详情、预览页的提示条和详情共用，同一页面只有一份轮询。
import { ElMessage } from 'element-plus'
import { computed, onBeforeUnmount, reactive, ref, shallowRef } from 'vue'

import { listDocumentTasks, retryTask } from '../../api/tasks'
import type { Task } from '../../api/types'
import { singleFlight } from '../login/submit'
import { retryAll } from './retry'
import { hasActive, summarizeTasks } from './summary'
import { retryMessage } from './text'
import { TaskWatcher } from './watcher'

export interface DocumentTasksOptions {
  /** 每次拿到新的任务列表时调用（第一次时 previous 为 null） */
  onTasks?: (tasks: Task[], previous: Task[] | null) => void
  /** 有任务被放回队列（文档状态可能跟着变了） */
  onQueued?: () => void
}

export function useDocumentTasks(options: DocumentTasksOptions = {}) {
  // null：还没加载出来
  const tasks = shallowRef<Task[] | null>(null)
  const error = shallowRef<{ error: unknown; silent: boolean } | null>(null)
  const retrying = ref(false)
  const refreshing = ref(false)
  let disposed = false

  const watcher = new TaskWatcher({
    load: listDocumentTasks,
    onTasks: (next) => {
      const previous = tasks.value
      tasks.value = next
      error.value = null
      options.onTasks?.(next, previous)
    },
    onError: (cause, silent) => {
      error.value = { error: cause, silent }
    },
  })

  function start(documentId: string): Promise<void> {
    // 页面可能要先等别的请求返回才调用 start，那时用户也许已经离开：不再开始，否则没有人会停下它
    if (disposed) return Promise.resolve()
    tasks.value = null
    error.value = null
    return watcher.start(documentId)
  }

  function stop(): void {
    watcher.stop()
  }

  async function refresh(): Promise<void> {
    refreshing.value = true
    try {
      await watcher.refresh()
    } finally {
      refreshing.value = false
    }
  }

  // 同一时间只有一批重试：连点两下不会发两遍
  const retry = singleFlight(async (failed: Task[]) => {
    retrying.value = true
    try {
      const result = await retryAll(failed, retryTask)
      const { type, text } = retryMessage(result)
      if (text) ElMessage({ type, message: text })
      // 重试途中离开了页面：不再刷新，也不让页面去加载数据、排定时器
      if (disposed) return
      await watcher.refresh()
      if (result.queued > 0 && !disposed) options.onQueued?.()
    } finally {
      retrying.value = false
    }
  })

  onBeforeUnmount(() => {
    disposed = true
    stop()
  })

  return reactive({
    tasks,
    error,
    retrying,
    refreshing,
    steps: computed(() => summarizeTasks(tasks.value ?? [])),
    active: computed(() => hasActive(tasks.value ?? [])),
    start,
    stop,
    refresh,
    retry,
  })
}

export type DocumentTasks = ReturnType<typeof useDocumentTasks>
