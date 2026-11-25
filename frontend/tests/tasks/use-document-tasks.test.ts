// useDocumentTasks 与页面生命周期的配合：离开页面之后不再请求、不再轮询（T24bd）。
// 项目没有组件测试工具，用 Vue 自带的 createRenderer 配一套什么都不画的节点操作来挂载、卸载组件。
import { createRenderer, defineComponent, h } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Task } from '../../src/api/types'
import { task } from './fixtures'

const api = vi.hoisted(() => ({ listDocumentTasks: vi.fn(), retryTask: vi.fn() }))
vi.mock('../../src/api/tasks', () => api)
vi.mock('element-plus', () => ({ ElMessage: vi.fn() }))

import { useDocumentTasks, type DocumentTasks, type DocumentTasksOptions } from '../../src/features/tasks/useDocumentTasks'

interface Node {
  children: Node[]
}
const { createApp } = createRenderer<Node, Node>({
  createElement: () => ({ children: [] }),
  createText: () => ({ children: [] }),
  createComment: () => ({ children: [] }),
  insert: () => {},
  remove: () => {},
  setText: () => {},
  setElementText: () => {},
  patchProp: () => {},
  parentNode: () => null,
  nextSibling: () => null,
})

function mount(options: DocumentTasksOptions = {}): { tasks: DocumentTasks; unmount: () => void } {
  let tasks!: DocumentTasks
  const app = createApp(
    defineComponent({
      setup() {
        tasks = useDocumentTasks(options)
        return () => h('div')
      },
    }),
  )
  app.mount({ children: [] })
  return { tasks, unmount: () => app.unmount() }
}

const ACTIVE: Task[] = [task('ocr', 'processing')]
const FAILED: Task[] = [task('parse', 'failed')]
const PENDING: Task[] = [task('parse', 'pending')]

beforeEach(() => {
  vi.useFakeTimers()
  api.listDocumentTasks.mockReset()
  api.retryTask.mockReset()
})
afterEach(() => void vi.useRealTimers())

describe('离开页面', () => {
  it('离开之后停止轮询', async () => {
    api.listDocumentTasks.mockResolvedValue(ACTIVE)
    const { tasks, unmount } = mount()
    await tasks.start('d1')
    await vi.advanceTimersByTimeAsync(3000)
    expect(api.listDocumentTasks).toHaveBeenCalledTimes(2)

    unmount()
    await vi.advanceTimersByTimeAsync(60_000)

    expect(api.listDocumentTasks).toHaveBeenCalledTimes(2)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('离开之后才调用 start（页面在等文档返回时用户走了）：不请求、不轮询', async () => {
    api.listDocumentTasks.mockResolvedValue(ACTIVE)
    const { tasks, unmount } = mount()
    unmount()

    await tasks.start('d1')
    await vi.advanceTimersByTimeAsync(60_000)

    expect(api.listDocumentTasks).not.toHaveBeenCalled()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('重试途中离开：不再刷新，也不通知页面', async () => {
    api.listDocumentTasks.mockResolvedValue(FAILED)
    let finish!: () => void
    api.retryTask.mockImplementation(() => new Promise<void>((resolve) => (finish = resolve)))
    const onQueued = vi.fn()
    const { tasks, unmount } = mount({ onQueued })
    await tasks.start('d1')
    const retrying = tasks.retry(FAILED)

    unmount()
    finish()
    await retrying
    await vi.advanceTimersByTimeAsync(60_000)

    expect(api.listDocumentTasks).toHaveBeenCalledTimes(1)
    expect(onQueued).not.toHaveBeenCalled()
  })
})

describe('重试', () => {
  it('连点两下只发一批；完成后刷新一次并通知页面一次', async () => {
    api.listDocumentTasks.mockResolvedValueOnce(FAILED).mockResolvedValue(PENDING)
    api.retryTask.mockResolvedValue(undefined)
    const onQueued = vi.fn()
    const onTasks = vi.fn()
    const { tasks, unmount } = mount({ onQueued, onTasks })
    await tasks.start('d1')

    await Promise.all([tasks.retry(FAILED), tasks.retry(FAILED)])

    expect(api.retryTask).toHaveBeenCalledTimes(1)
    expect(onQueued).toHaveBeenCalledTimes(1)
    expect(onTasks).toHaveBeenLastCalledWith(PENDING, FAILED)
    expect(tasks.retrying).toBe(false)
    unmount()
  })
})
