import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// 后端地址。开发时由 Vite 把 /api 和 /health 转发过去，浏览器看到的始终是同一个来源，
// 所以后端不需要配置跨域（CORS）。
const BACKEND = 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': BACKEND,
      '/health': BACKEND,
    },
  },
})
