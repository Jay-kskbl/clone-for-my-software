<script setup lang="ts">
// 登录页：只负责布局和组装（登录页结构优化 L4）。
// 品牌区、登录卡片在 features/login/，跳转规则在 features/login/redirect.ts，表单规则在 rules.ts。
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { auth, restoreSession } from '../auth'
import LoginBrand from '../features/login/LoginBrand.vue'
import LoginForm from '../features/login/LoginForm.vue'
import { safeRedirect } from '../features/login/redirect'
import StardustLogo from '../features/search-motion/logo/StardustLogo.vue'
import { m } from '../i18n'

const router = useRouter()
const route = useRoute()

/** 回到登录前要去的页面；只接受站内路径，避免被构造的链接带到别的网站 */
function goBack() {
  return router.push(safeRedirect(route.query.redirect))
}

// 打开页面时连不上服务器（L2）：本地令牌还在，服务恢复后点“重试”重新确认，成功就直接进入，不用再输密码
const retrying = ref(false)

async function onRetry() {
  retrying.value = true
  try {
    await restoreSession()
    if (auth.user) await goBack()
  } finally {
    retrying.value = false
  }
}
</script>

<template>
  <div class="login">
    <LoginBrand>
      <!-- 克隆库专用：星尘光球中间放文档图标（search-motion），一直转动。去掉这一段就显示静态图标 -->
      <template #logo><StardustLogo /></template>
    </LoginBrand>
    <LoginForm :after-sign-in="goBack">
      <el-alert v-if="auth.unreachable" type="warning" :closable="false" show-icon class="login-unreachable">
        <template #title>{{ m().login.unreachable }}</template>
        <el-button size="small" :loading="retrying" class="login-retry" @click="onRetry">{{ m().login.retry }}</el-button>
      </el-alert>
    </LoginForm>
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
  padding: 24px 16px 24px;
}

.login-unreachable {
  margin-bottom: 16px;
}

.login-retry {
  margin-top: 8px;
}
</style>
