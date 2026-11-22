<script setup lang="ts">
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import * as authApi from '../api/auth'
import { errorMessage } from '../api/client'
import { login } from '../auth'
import AppIcon from '../components/AppIcon.vue'
import IdleSpinner from '../features/search-motion/idle-spinner/IdleSpinner.vue'

const router = useRouter()
const route = useRoute()

const mode = ref<'login' | 'register'>('login')
const submitting = ref(false)
const formRef = ref<FormInstance>()
const form = reactive({ username: '', password: '' })

// 注册时的规则与后端一致（docs/api.md §4.2）。这里只是为了尽早提示，后端仍会再校验一次。
// 登录时不检查格式：不对就是登录失败。
const registerRules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    {
      pattern: /^[A-Za-z0-9_.-]{3,32}$/,
      message: '3–32 个字符，只能包含英文字母、数字、下划线、点、连字符',
      trigger: 'blur',
    },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 8, max: 128, message: '8–128 个字符', trigger: 'blur' },
  ],
}
const loginRules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

function switchMode() {
  mode.value = mode.value === 'login' ? 'register' : 'login'
  formRef.value?.clearValidate()
}

async function onSubmit() {
  if (!(await formRef.value?.validate().catch(() => false))) return
  submitting.value = true
  try {
    if (mode.value === 'register') {
      await authApi.register(form.username, form.password)
      ElMessage.success('注册成功，已自动登录')
    }
    await login(form.username, form.password)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    // 只接受站内路径，避免被构造的链接带到别的网站
    await router.push(redirect.startsWith('/') && !redirect.startsWith('//') ? redirect : '/')
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="login">
    <div class="login-brand">
      <span class="app-logo login-logo"><AppIcon name="docs" :size="26" /></span>
      <h1 class="login-title">智能文档管理系统</h1>
      <p class="login-desc">多格式文档管理 · 全文检索 · OCR 文字检索 · 图文语义检索</p>
    </div>
    <el-card class="login-card" shadow="never">
      <template #header>{{ mode === 'login' ? '登录' : '注册新用户' }}</template>
      <el-form
        ref="formRef"
        :model="form"
        :rules="mode === 'login' ? loginRules : registerRules"
        label-position="top"
        @submit.prevent="onSubmit"
      >
        <el-form-item label="用户名" prop="username">
          <el-input v-model.trim="form.username" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
          />
        </el-form-item>
        <el-button type="primary" native-type="submit" :loading="submitting" class="login-submit">
          {{ mode === 'login' ? '登录' : '注册并登录' }}
        </el-button>
      </el-form>
      <div class="login-switch">
        <el-button link type="primary" @click="switchMode">
          {{ mode === 'login' ? '没有账号？注册' : '已有账号？登录' }}
        </el-button>
      </div>
    </el-card>
    <!-- 待机动画（search-motion，与检索页同一个星尘光球）：8 秒无操作时出现在登录框下方，任意操作淡出。
         画布始终占位，出现、消失时页面不跳动 -->
    <IdleSpinner class="login-idle" />
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

.login-brand {
  text-align: center;
}

.login-logo {
  width: 48px;
  height: 48px;
  border-radius: var(--app-radius-lg);
}

.login-title {
  margin: 12px 0 4px;
  font-size: 22px;
  font-weight: 600;
}

.login-desc {
  margin: 0;
  color: var(--app-text-secondary);
  font-size: 13px;
}

/* 窄屏时不超出屏幕宽度 */
.login-card {
  width: 100%;
  max-width: 380px;
  border-radius: var(--app-radius-lg);
}

.login-submit {
  width: 100%;
}

.login-switch {
  margin-top: 12px;
  text-align: center;
}
</style>
