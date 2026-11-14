import { createRouter, createWebHistory } from 'vue-router'

import { auth, restoreSession } from './auth'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('./views/LoginView.vue') },
    {
      path: '/',
      name: 'documents',
      component: () => import('./views/DocumentsView.vue'),
      meta: { requiresAuth: true },
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

// 这里只决定“显示哪个页面”。真正的权限控制在后端：每个接口都校验令牌和权限，
// 即使有人绕过这段前端代码，也拿不到数据（GLOBAL §7.2）。
router.beforeEach(async (to) => {
  await restoreSession()
  if (to.meta.requiresAuth && !auth.user) {
    return { name: 'login', query: to.fullPath === '/' ? {} : { redirect: to.fullPath } }
  }
  if (to.name === 'login' && auth.user) {
    return { name: 'documents' }
  }
  return true
})
