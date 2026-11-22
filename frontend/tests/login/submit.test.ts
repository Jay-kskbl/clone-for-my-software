// 登录 / 注册的提交流程（登录页结构优化 L5）：先注册再登录、注册成功但登录失败、重复提交。
import { describe, expect, it, vi } from 'vitest'

import { singleFlight, submitCredentials, type SubmitDeps } from '../../src/features/login/submit'

const CREDS = { username: 'barry', password: 'password1' }
const TAKEN = new Error('用户名已存在')
const WRONG = new Error('用户名或密码错误')
const DOWN = new Error('数据库不可用，请稍后重试')

function deps(over: Partial<SubmitDeps> = {}) {
  const calls: string[] = []
  const d: SubmitDeps = {
    register: vi.fn(async (u: string) => {
      calls.push(`register:${u}`)
    }),
    login: vi.fn(async (u: string) => {
      calls.push(`login:${u}`)
    }),
    ...over,
  }
  return { d, calls }
}

describe('登录模式', () => {
  it('登录成功：只调登录', async () => {
    const { d, calls } = deps()
    expect(await submitCredentials('login', CREDS, d)).toEqual({ kind: 'signed-in', registered: false })
    expect(calls).toEqual(['login:barry'])
    expect(d.login).toHaveBeenCalledWith('barry', 'password1')
  })

  it('密码错误：失败，带上原始错误', async () => {
    const { d } = deps({ login: vi.fn().mockRejectedValue(WRONG) })
    expect(await submitCredentials('login', CREDS, d)).toEqual({ kind: 'failed', error: WRONG })
    expect(d.register).not.toHaveBeenCalled()
  })
})

describe('注册模式', () => {
  it('注册后登录成功：先注册再登录', async () => {
    const { d, calls } = deps()
    expect(await submitCredentials('register', CREDS, d)).toEqual({ kind: 'signed-in', registered: true })
    expect(calls).toEqual(['register:barry', 'login:barry'])
  })

  it('用户名已存在：失败，不再尝试登录', async () => {
    const { d } = deps({ register: vi.fn().mockRejectedValue(TAKEN) })
    expect(await submitCredentials('register', CREDS, d)).toEqual({ kind: 'failed', error: TAKEN })
    expect(d.login).not.toHaveBeenCalled()
  })

  it('注册成功但登录失败：单独返回，页面据此切回登录模式（问题 A3）', async () => {
    const { d } = deps({ login: vi.fn().mockRejectedValue(DOWN) })
    expect(await submitCredentials('register', CREDS, d)).toEqual({ kind: 'registered-not-signed-in', error: DOWN })
    expect(d.register).toHaveBeenCalledTimes(1)
  })
})

/** 一个可以手动结束的任务 */
function gate() {
  let open!: () => void
  let fail!: (e: unknown) => void
  const promise = new Promise<void>((resolve, reject) => {
    open = resolve
    fail = reject
  })
  return { promise, open, fail }
}

describe('singleFlight', () => {
  it('上一次没结束时再调用：直接返回 null，不重复执行', async () => {
    const g = gate()
    const task = vi.fn(async (x: number) => {
      await g.promise
      return x * 2
    })
    const run = singleFlight(task)

    const first = run(1)
    const second = run(2)
    expect(await second).toBeNull()
    g.open()
    expect(await first).toBe(2)
    expect(task).toHaveBeenCalledTimes(1)
  })

  it('结束后可以再次执行', async () => {
    const run = singleFlight(async (x: number) => x + 1)
    expect(await run(1)).toBe(2)
    expect(await run(2)).toBe(3)
  })

  it('上一次抛出异常后也能再次执行，异常原样抛给调用方', async () => {
    const g = gate()
    const task = vi.fn(async () => {
      await g.promise
      return 'ok'
    })
    const run = singleFlight(task)
    const first = run()
    g.fail(DOWN)
    await expect(first).rejects.toBe(DOWN)

    const again = gate()
    task.mockImplementationOnce(async () => {
      await again.promise
      return 'again'
    })
    const second = run()
    again.open()
    expect(await second).toBe('again')
    expect(task).toHaveBeenCalledTimes(2)
  })
})
