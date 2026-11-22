<script setup lang="ts">
// 登录页：只负责布局和组装（T24w）。
// 品牌区、登录卡片在 features/login/；跳转规则在 redirect.ts，表单规则在 rules.ts，提交流程在 submit.ts。
import { useRoute, useRouter } from 'vue-router'

import LoginBrand from '../features/login/LoginBrand.vue'
import LoginForm from '../features/login/LoginForm.vue'
import { safeRedirect } from '../features/login/redirect'

const router = useRouter()
const route = useRoute()

/** 回到登录前要去的页面；只接受站内路径，避免被构造的链接带到别的网站 */
function goBack() {
  return router.push(safeRedirect(route.query.redirect))
}
</script>

<template>
  <div class="login">
    <LoginBrand />
    <LoginForm :after-sign-in="goBack" />
  </div>
</template>

<style scoped>
.login {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 24px;
  box-sizing: border-box;
  min-height: 100vh;
  padding: 72px 16px 24px;
}
</style>
