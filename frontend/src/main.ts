import 'element-plus/dist/index.css'

import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { createApp } from 'vue'

import { setUnauthenticatedHandler } from './api/client'
import App from './App.vue'
import { logout } from './auth'
import { router } from './router'

// 任何请求发现令牌失效时：清掉登录状态，回到登录页
setUnauthenticatedHandler(() => {
  logout()
  if (router.currentRoute.value.name !== 'login') void router.push({ name: 'login' })
})

createApp(App).use(router).use(ElementPlus, { locale: zhCn }).mount('#app')
