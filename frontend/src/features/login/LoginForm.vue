<script setup lang="ts">
// 登录 / 注册卡片（登录页结构优化 L4，从 LoginView.vue 拆出）：表单、模式切换、提交。
// 不管登录后去哪里：登录成功后调用 afterSignIn，由页面决定跳转（等它完成才结束“提交中”，避免按钮闪一下又能点）。
// 默认插槽放在表单上方，页面用它显示“连不上服务器”之类的提示。
import type { FormInstance } from 'element-plus'
import { ElMessage } from 'element-plus'
import { reactive, ref } from 'vue'

import * as authApi from '../../api/auth'
import { errorMessage } from '../../api/client'
import { login } from '../../auth'
import { m } from '../../i18n'
import { LOGIN_RULES, REGISTER_RULES } from './rules'

const props = defineProps<{
  /** 登录成功之后做什么（通常是跳回原页面） */
  afterSignIn: () => Promise<unknown>
}>()

const mode = ref<'login' | 'register'>('login')
const submitting = ref(false)
const formRef = ref<FormInstance>()
const form = reactive({ username: '', password: '' })

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
    await props.afterSignIn()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <el-card class="login-card" shadow="never">
    <!-- 用 h2：读屏软件按标题跳转时能找到表单（问题 C4）；样式与原来的卡片标题相同 -->
    <template #header>
      <h2 class="login-card-title">{{ mode === 'login' ? m().login.loginTitle : m().login.registerTitle }}</h2>
    </template>
    <slot />
    <el-form
      ref="formRef"
      :model="form"
      :rules="mode === 'login' ? LOGIN_RULES : REGISTER_RULES"
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
</template>

<style scoped>
/* 窄屏时不超出屏幕宽度 */
.login-card {
  width: 100%;
  max-width: 380px;
  border-radius: var(--app-radius-lg);
}

.login-card-title {
  margin: 0;
  font: inherit;
}

.login-submit {
  width: 100%;
}

.login-switch {
  margin-top: 12px;
  text-align: center;
}
</style>
