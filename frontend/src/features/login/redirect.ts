// 登录后跳到哪里（登录页结构优化 L1，见 docs/登录页结构优化计划书.md）。
//
// redirect 参数来自地址栏，任何人都能构造一个带参数的链接发给别人，所以只接受本站内的路径，
// 其余一律回到首页。原来这段判断写在 LoginView.vue 里，只检查了“以 / 开头、不以 // 开头”。

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
