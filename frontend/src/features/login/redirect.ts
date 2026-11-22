// 登录前后的跳转（登录页结构优化 L1、L3，见 docs/登录页结构优化计划书.md）。
//
// - safeRedirect：登录后跳到哪里。redirect 参数来自地址栏，任何人都能构造一个带参数的链接发给别人，
//   所以只接受本站内的路径，其余一律回到首页。原来这段判断写在 LoginView.vue 里，只检查了
//   “以 / 开头、不以 // 开头”。
// - loginRoute / guardTarget / afterUnauthenticated：什么时候去登录页、带不带原地址。
//   原来分散在 router.ts 和 main.ts，令牌过期后跳登录页不带原地址（问题 A2）。
// 都是纯函数，router.ts、main.ts 只负责调用。
import type { RouteLocationRaw } from 'vue-router'

const HOME = '/'

/** 地址栏的 redirect 参数 → 可以放心跳转的站内路径；不合格时返回首页 `/`。 */
export function safeRedirect(raw: unknown): string {
  // vue-router 的 query 值可能是 null 或数组（?redirect=a&redirect=b）
  if (typeof raw !== 'string') return HOME
  // 必须以一个 / 开头：// 开头是“协议相对地址”，浏览器会当成别的网站
  if (!raw.startsWith('/') || raw.startsWith('//')) return HOME
  // 浏览器把反斜杠当斜杠（/\evil.com 等同于 //evil.com）；换行、制表符等控制字符会被浏览器先删掉再解析，
  // 删完可能又变成 //。两类都不接受
  if (/[\\\u0000-\u001f\u007f]/.test(raw)) return HOME
  // 跳回登录页没有意义（路由守卫又会把已登录的人送走）
  if (raw === '/login' || raw.startsWith('/login?') || raw.startsWith('/login#')) return HOME
  return raw
}

/** 去登录页，并记住登录后要回到的地址；回首页、回登录页或地址不合格时不带 redirect。 */
export function loginRoute(fullPath: string): RouteLocationRaw {
  const back = safeRedirect(fullPath)
  return { name: 'login', query: back === HOME ? {} : { redirect: back } }
}

/** 路由守卫需要的那部分路由信息（vue-router 的 RouteLocationNormalized 满足它） */
export interface GuardRoute {
  name?: unknown
  fullPath: string
  query: Record<string, unknown>
  meta: Record<PropertyKey, unknown>
}

/**
 * 路由守卫的决定：放行（true）或改去哪里。只决定“显示哪个页面”，真正的权限控制在后端（GLOBAL §7.2）。
 * 已登录时打开登录页，按 redirect 回去（原来一律去文件页，问题 A4）。
 */
export function guardTarget(to: GuardRoute, signedIn: boolean): true | RouteLocationRaw {
  if (to.meta.requiresAuth && !signedIn) return loginRoute(to.fullPath)
  if (to.name === 'login' && signedIn) return safeRedirect(to.query.redirect)
  return true
}

/**
 * 请求收到 401 UNAUTHENTICATED（令牌过期或账号被删）之后去哪里；null 表示不跳转。
 *
 * - 原来是登录状态（使用中令牌过期）：去登录页并带上当前地址，重新登录后回来（问题 A2）。
 * - 原来就不是登录状态：这是页面加载时确认令牌（restoreSession）收到的 401。此时导航还没完成，
 *   当前路由是起始位置 `/`，不知道要去哪里；路由守卫马上会把人送到登录页并带上 redirect。
 *   原来这里也跳一次（不带 redirect），实测最后仍停在守卫给的地址（守卫的跳转后开始），
 *   但那是多余的一次导航，结果还取决于两次导航的先后，所以不再跳。
 * - 已经在登录页：不跳。
 */
export function afterUnauthenticated(
  wasSignedIn: boolean,
  current: { name?: unknown; fullPath: string },
): RouteLocationRaw | null {
  if (!wasSignedIn || current.name === 'login') return null
  return loginRoute(current.fullPath)
}
