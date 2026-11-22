// 登录 / 注册的提交流程（登录页结构优化 L5）。纯 TypeScript，请求函数由调用方传入，测试时换成假的。
//
// 注册是两步：先注册，再用同一组用户名密码登录。第二步失败时账号其实已经建好了，
// 原来页面停在“注册”模式，再点一次只会得到“用户名已存在”（问题 A3）。这里把这种情况单独返回，
// 由页面切回登录模式。

export type Mode = 'login' | 'register'

export interface Credentials {
  username: string
  password: string
}

export interface SubmitDeps {
  register: (username: string, password: string) => Promise<unknown>
  login: (username: string, password: string) => Promise<unknown>
}

export type SubmitResult =
  /** 已登录；registered 表示这次新注册了账号 */
  | { kind: 'signed-in'; registered: boolean }
  /** 登录失败，或注册本身失败（如用户名已存在） */
  | { kind: 'failed'; error: unknown }
  /** 注册成功，但随后自动登录失败：账号已经建好，应切回登录模式 */
  | { kind: 'registered-not-signed-in'; error: unknown }

export async function submitCredentials(mode: Mode, { username, password }: Credentials, deps: SubmitDeps): Promise<SubmitResult> {
  if (mode === 'register') {
    try {
      await deps.register(username, password)
    } catch (error) {
      return { kind: 'failed', error }
    }
    try {
      await deps.login(username, password)
    } catch (error) {
      return { kind: 'registered-not-signed-in', error }
    }
    return { kind: 'signed-in', registered: true }
  }
  try {
    await deps.login(username, password)
  } catch (error) {
    return { kind: 'failed', error }
  }
  return { kind: 'signed-in', registered: false }
}

/**
 * 同一时间只运行一次：上一次还没结束时再调用，直接返回 null，不再执行。
 *
 * 表单校验是异步的，“登录”按钮要等校验结束才变成加载中（加载中的按钮不响应回车）。
 * 实测在这之前连续提交两次会发出两次登录请求；注册模式下第二次会得到“用户名已存在”。
 */
export function singleFlight<A extends unknown[], R>(task: (...args: A) => Promise<R>): (...args: A) => Promise<R | null> {
  let running = false
  return async (...args: A) => {
    if (running) return null
    running = true
    try {
      return await task(...args)
    } finally {
      running = false
    }
  }
}
