// 登录前后的跳转（T24v）：登录后只回站内路径；去登录页时记住原地址；
// 令牌过期后回到原页面；页面加载时的 401 交给路由守卫。
import { describe, expect, it } from 'vitest'

import {
  afterUnauthenticated,
  guardTarget,
  loginRoute,
  safeRedirect,
  type GuardRoute,
} from '../../src/features/login/redirect'

describe('safeRedirect', () => {
  it.each([
    ['/', '/'],
    ['/search', '/search'],
    ['/search?q=合同&channels=text', '/search?q=合同&channels=text'],
    ['/documents/3f2c?view=text#chunk-2', '/documents/3f2c?view=text#chunk-2'],
    // 以 /login 开头但不是登录页
    ['/loginhelp', '/loginhelp'],
  ])('站内路径原样保留：%s', (raw, expected) => {
    expect(safeRedirect(raw)).toBe(expected)
  })

  it.each([
    ['协议相对地址', '//evil.com'],
    ['协议相对地址带路径', '//evil.com/search'],
    ['反斜杠', '/\\evil.com'],
    ['反斜杠在后面', '/search\\x'],
    ['完整网址', 'https://evil.com/'],
    ['javascript 协议', 'javascript:alert(1)'],
    ['相对路径', 'search'],
    ['空字符串', ''],
    ['制表符', '/\t/evil.com'],
    ['换行', '/\n/evil.com'],
    ['DEL 字符', '/\u007f'],
    ['登录页本身', '/login'],
    ['登录页带参数', '/login?redirect=/search'],
    ['登录页带锚点', '/login#x'],
  ])('不合格时回到首页：%s', (_name, raw) => {
    expect(safeRedirect(raw)).toBe('/')
  })

  it.each([
    ['undefined', undefined],
    ['null（?redirect 没有值）', null],
    ['数组（同一个参数出现两次）', ['/search', '/documents']],
    ['数字', 42],
  ])('不是字符串时回到首页：%s', (_name, raw) => {
    expect(safeRedirect(raw)).toBe('/')
  })
})

describe('loginRoute', () => {
  it('带上原地址', () => {
    expect(loginRoute('/search?q=合同')).toEqual({ name: 'login', query: { redirect: '/search?q=合同' } })
    expect(loginRoute('/documents/3f2c?view=text')).toEqual({
      name: 'login',
      query: { redirect: '/documents/3f2c?view=text' },
    })
  })

  it.each(['/', '/login', '/login?redirect=/search', '//evil.com'])('首页、登录页、不合格的地址不带：%s', (path) => {
    expect(loginRoute(path)).toEqual({ name: 'login', query: {} })
  })
})

function route(over: Partial<GuardRoute> & { fullPath: string }): GuardRoute {
  return { name: undefined, query: {}, meta: {}, ...over }
}

describe('guardTarget', () => {
  const search = route({ name: 'search', fullPath: '/search?q=1', query: { q: '1' }, meta: { requiresAuth: true } })
  const home = route({ name: 'documents', fullPath: '/', meta: { requiresAuth: true } })
  const login = route({ name: 'login', fullPath: '/login?redirect=/search', query: { redirect: '/search' } })
  // 没有 requiresAuth 的页面（现在只有登录页；守卫的规则对以后加的公开页面同样适用）
  const open = route({ name: 'public-page', fullPath: '/public-page' })

  it('未登录打开需要登录的页面：去登录页，带上原地址', () => {
    expect(guardTarget(search, false)).toEqual({ name: 'login', query: { redirect: '/search?q=1' } })
  })

  it('未登录打开首页：去登录页，不带 redirect（与原来相同）', () => {
    expect(guardTarget(home, false)).toEqual({ name: 'login', query: {} })
  })

  it('未登录打开登录页、不需要登录的页面：放行', () => {
    expect(guardTarget(login, false)).toBe(true)
    expect(guardTarget(open, false)).toBe(true)
  })

  it('已登录打开需要登录的页面：放行', () => {
    expect(guardTarget(search, true)).toBe(true)
  })

  it('已登录打开登录页：按 redirect 回去（原来一律去文件页）', () => {
    expect(guardTarget(login, true)).toBe('/search')
  })

  it('已登录打开登录页，redirect 缺失或不合格：去首页', () => {
    expect(guardTarget(route({ name: 'login', fullPath: '/login' }), true)).toBe('/')
    expect(
      guardTarget(route({ name: 'login', fullPath: '/login?redirect=//evil.com', query: { redirect: '//evil.com' } }), true),
    ).toBe('/')
  })
})

describe('afterUnauthenticated', () => {
  it('使用中令牌过期：去登录页并带上当前地址', () => {
    expect(afterUnauthenticated(true, { name: 'search', fullPath: '/search?q=合同' })).toEqual({
      name: 'login',
      query: { redirect: '/search?q=合同' },
    })
  })

  it('在首页过期：去登录页，不带 redirect', () => {
    expect(afterUnauthenticated(true, { name: 'documents', fullPath: '/' })).toEqual({ name: 'login', query: {} })
  })

  it('已经在登录页：不跳', () => {
    expect(afterUnauthenticated(true, { name: 'login', fullPath: '/login' })).toBeNull()
  })

  it('原来就没登录（页面加载时确认令牌收到 401）：不跳，交给路由守卫', () => {
    // 此时导航还没完成，当前路由是起始位置 `/`；路由守卫会带上要去的页面跳到登录页，这里再跳是多余的
    expect(afterUnauthenticated(false, { name: undefined, fullPath: '/' })).toBeNull()
  })
})
