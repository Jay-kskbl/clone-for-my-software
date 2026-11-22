<script setup lang="ts">
// 登录页：只负责布局和组装（T24w）。
// 品牌区、登录卡片在 features/login/；跳转规则在 redirect.ts，表单规则在 rules.ts，提交流程在 submit.ts。
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { auth, restoreSession } from '../auth'
import LoginBrand from '../features/login/LoginBrand.vue'
import LoginForm from '../features/login/LoginForm.vue'
import { safeRedirect } from '../features/login/redirect'

const router = useRouter()
const route = useRoute()

/** 回到登录前要去的页面；只接受站内路径，避免被构造的链接带到别的网站 */
function goBack() {
  return router.push(safeRedirect(route.query.redirect))
}

// 打开页面时连不上服务器（T24x）：本地令牌还在，服务恢复后点“重试”重新确认，成功就直接进入，不用再输密码
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
    <LoginBrand />
    <LoginForm :after-sign-in="goBack">
      <el-alert v-if="auth.unreachable" type="warning" :closable="false" show-icon class="login-status">
        <template #title>暂时连不上服务器，登录状态已保留。服务恢复后点“重试”即可继续。</template>
        <el-button size="small" :loading="retrying" class="login-status-action" @click="onRetry">重试</el-button>
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
  padding: 72px 16px 24px;
}

.login-status {
  margin-bottom: 16px;
}

.login-status-action {
  margin-top: 8px;
}
</style>
