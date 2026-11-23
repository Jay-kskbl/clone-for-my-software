<script setup lang="ts">
// 登录页：只负责布局和组装（T24w）。
// 品牌区、登录卡片在 features/login/；跳转规则在 redirect.ts，表单规则在 rules.ts，提交流程在 submit.ts。
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { fetchHealth } from '../api/health'
import { auth, restoreSession } from '../auth'
import LoginBrand from '../features/login/LoginBrand.vue'
import LoginForm from '../features/login/LoginForm.vue'
import { safeRedirect } from '../features/login/redirect'
import { checkLoginService, type ServiceStatus } from '../features/login/serviceStatus'
import { singleFlight } from '../features/login/submit'

const router = useRouter()
const route = useRoute()

/** 回到登录前要去的页面；只接受站内路径，避免被构造的链接带到别的网站 */
function goBack() {
  return router.push(safeRedirect(route.query.redirect))
}

// 服务状态（T24z）：打开页面时查一次 GET /health，后端连不上或数据库不可用时提前说明；不轮询。
// 查完之前按“正常”处理，不显示任何提示，避免页面一打开就闪一下
const service = ref<ServiceStatus>('ok')
const checkService = singleFlight(async () => {
  service.value = await checkLoginService(fetchHealth)
})
const serviceNotice = computed(() => {
  if (service.value === 'backend-down') return '连不上后端服务，现在无法登录。请确认后端已启动，再点“重新检查”。'
  if (service.value === 'database-down') return '后端已启动，但数据库不可用，现在无法登录。请确认数据库已启动，再点“重新检查”。'
  return ''
})
const rechecking = ref(false)

async function onRecheck() {
  rechecking.value = true
  try {
    await checkService()
  } finally {
    rechecking.value = false
  }
}

onMounted(() => void checkService())

// 打开页面时连不上服务器（T24x）：本地令牌还在，服务恢复后点“重试”重新确认，成功就直接进入，不用再输密码
const retrying = ref(false)

async function onRetry() {
  retrying.value = true
  try {
    await restoreSession()
    if (auth.user) {
      await goBack()
      return
    }
    // 没进去（令牌已失效，或仍然连不上）：顺便更新服务状态，下面的提示才不会停在旧结果
    await checkService()
  } finally {
    retrying.value = false
  }
}
</script>

<template>
  <div class="login">
    <LoginBrand />
    <LoginForm :after-sign-in="goBack">
      <!-- 两条提示只显示一条：本地有令牌但连不上（T24x）时，“登录状态已保留”更要紧，它的“重试”也会更新服务状态 -->
      <el-alert v-if="auth.unreachable" type="warning" :closable="false" show-icon class="login-status">
        <template #title>暂时连不上服务器，登录状态已保留。服务恢复后点“重试”即可继续。</template>
        <el-button size="small" :loading="retrying" class="login-status-action" @click="onRetry">重试</el-button>
      </el-alert>
      <el-alert v-else-if="serviceNotice" type="warning" :closable="false" show-icon class="login-status">
        <template #title>{{ serviceNotice }}</template>
        <el-button size="small" :loading="rechecking" class="login-status-action" @click="onRecheck">重新检查</el-button>
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
