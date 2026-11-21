import { createApp } from 'vue'

import { setUnauthenticatedHandler } from './api/client'
import App from './App.vue'
import { logout } from './auth'
import { installElementPlus } from './element'
import { router } from './router'
// 放在 element.ts 之后引入：全局样式引用 Element Plus 的 CSS 变量（T24s）
import './styles.css'

// 任何请求发现令牌失效时：清掉登录状态，回到登录页
setUnauthenticatedHandler(() => {
  logout()
  if (router.currentRoute.value.name !== 'login') void router.push({ name: 'login' })
})

// Element Plus 按需注册（T24p，见 element.ts）
const app = createApp(App).use(router)
installElementPlus(app)
app.mount('#app')
