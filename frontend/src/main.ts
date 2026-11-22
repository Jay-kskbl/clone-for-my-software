import { createApp } from 'vue'

import { setUnauthenticatedHandler } from './api/client'
import App from './App.vue'
import { logout } from './auth'
import { installElementPlus } from './element'
import { initTheme } from './features/theme/store'
import { initLocale } from './i18n'
import { router } from './router'
// Element Plus 的暗色变量（只在 html.dark 时生效），系统配色的“深色”用它
import 'element-plus/theme-chalk/dark/css-vars.css'
// 放在 element.ts 之后引入：全局样式引用 Element Plus 的 CSS 变量（T24s）
import './styles.css'

// 任何请求发现令牌失效时：清掉登录状态，回到登录页
setUnauthenticatedHandler(() => {
  logout()
  if (router.currentRoute.value.name !== 'login') void router.push({ name: 'login' })
})

// 系统配色：挂载前先写到 <html> 上，首屏就是保存过的配色
initTheme()
// 界面语言：同步 <html lang> 和页面标题，之后切换时保存
initLocale()

// Element Plus 按需注册（T24p，见 element.ts）
const app = createApp(App).use(router)
installElementPlus(app)
app.mount('#app')
