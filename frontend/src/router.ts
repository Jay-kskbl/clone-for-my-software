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
    {
      path: '/search',
      name: 'search',
      component: () => import('./views/SearchView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/documents/:id',
      name: 'preview',
      component: () => import('./views/PreviewView.vue'),
      meta: { requiresAuth: true },
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
  // 提供 scrollBehavior 后，由 vue-router 接管滚动位置（它会把浏览器的自动滚动恢复关掉）：
  // 后退时回到原来的位置，进入新页面时从顶部开始。预览页自己负责滚到命中的片段
  scrollBehavior(_to, _from, savedPosition) {
    return savedPosition ?? { top: 0 }
  },
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
