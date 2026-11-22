<script setup lang="ts">
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import * as authApi from '../api/auth'
import { errorMessage } from '../api/client'
import { login } from '../auth'
import StardustLogo from '../features/search-motion/logo/StardustLogo.vue'
import { m } from '../i18n'

const router = useRouter()
const route = useRoute()

const mode = ref<'login' | 'register'>('login')
const submitting = ref(false)
const formRef = ref<FormInstance>()
const form = reactive({ username: '', password: '' })

// 注册时的规则与后端一致（docs/api.md §4.2）。这里只是为了尽早提示，后端仍会再校验一次。
// 登录时不检查格式：不对就是登录失败。
// 提示文字随界面语言，所以写成 computed
const registerRules = computed<FormRules>(() => ({
  username: [
    { required: true, message: m().login.usernameRequired, trigger: 'blur' },
    {
      pattern: /^[A-Za-z0-9_.-]{3,32}$/,
      message: m().login.usernamePattern,
      trigger: 'blur',
    },
  ],
  password: [
    { required: true, message: m().login.passwordRequired, trigger: 'blur' },
    { min: 8, max: 128, message: m().login.passwordLength, trigger: 'blur' },
  ],
}))
const loginRules = computed<FormRules>(() => ({
  username: [{ required: true, message: m().login.usernameRequired, trigger: 'blur' }],
  password: [{ required: true, message: m().login.passwordRequired, trigger: 'blur' }],
}))

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
      ElMessage.success(m().login.registered)
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
      <!-- logo：星尘光球中间放文档图标（search-motion），一直转动 -->
      <StardustLogo class="login-logo" />
      <h1 class="login-title">{{ m().app.title }}</h1>
      <p class="login-desc">{{ m().login.desc }}</p>
    </div>
    <el-card class="login-card" shadow="never">
      <template #header>{{ mode === 'login' ? m().login.loginTitle : m().login.registerTitle }}</template>
      <el-form
        ref="formRef"
        :model="form"
        :rules="mode === 'login' ? loginRules : registerRules"
        :validate-on-rule-change="false"
        label-position="top"
        @submit.prevent="onSubmit"
      >
        <el-form-item :label="m().login.username" prop="username">
          <el-input v-model.trim="form.username" autocomplete="username" />
        </el-form-item>
        <el-form-item :label="m().login.password" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
          />
        </el-form-item>
        <el-button type="primary" native-type="submit" :loading="submitting" class="login-submit">
          {{ mode === 'login' ? m().login.submitLogin : m().login.submitRegister }}
        </el-button>
      </el-form>
      <div class="login-switch">
        <el-button link type="primary" @click="switchMode">
          {{ mode === 'login' ? m().login.toRegister : m().login.toLogin }}
        </el-button>
      </div>
    </el-card>
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

.login-brand {
  text-align: center;
}

.login-logo {
  margin: 0 auto;
}

.login-title {
  margin: 4px 0 4px;
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
