import { createApp } from 'vue'

import { setUnauthenticatedHandler } from './api/client'
import App from './App.vue'
import { auth, logout } from './auth'
import { installElementPlus } from './element'
import { afterUnauthenticated } from './features/login/redirect'
import { router } from './router'
// 放在 element.ts 之后引入：全局样式引用 Element Plus 的 CSS 变量（T24s）
import './styles.css'

// 任何请求发现令牌失效时：清掉登录状态；使用中过期的，带上当前地址回到登录页，
// 重新登录后回来（T24v，规则见 features/login/redirect.ts 的 afterUnauthenticated）
setUnauthenticatedHandler(() => {
  const target = afterUnauthenticated(auth.user !== null, router.currentRoute.value)
  logout()
  if (target) void router.push(target)
})

// Element Plus 按需注册（T24p，见 element.ts）
const app = createApp(App).use(router)
installElementPlus(app)
app.mount('#app')
