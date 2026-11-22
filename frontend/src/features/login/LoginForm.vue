<script setup lang="ts">
// 登录 / 注册卡片（T24w，从 LoginView.vue 拆出）：表单、模式切换、提交。
// 不管登录后去哪里：登录成功后调用 afterSignIn，由页面决定跳转（等它完成才结束“提交中”，避免按钮闪一下又能点）。
// 默认插槽放在表单上方，页面用它显示“连不上服务器”之类的提示（T24x）。
// 提交流程（先注册再登录、注册成功但登录失败）在 submit.ts，表单规则在 rules.ts，都有单元测试。
import type { FormInstance } from 'element-plus'
import { ElMessage } from 'element-plus'
import { reactive, ref } from 'vue'

import * as authApi from '../../api/auth'
import { errorMessage } from '../../api/client'
import { login } from '../../auth'
import { LOGIN_RULES, REGISTER_RULES } from './rules'
import { singleFlight, submitCredentials, type Mode } from './submit'

const props = defineProps<{
  /** 登录成功之后做什么（通常是跳回原页面） */
  afterSignIn: () => Promise<unknown>
}>()

const mode = ref<Mode>('login')
const submitting = ref(false)
const formRef = ref<FormInstance>()
const form = reactive({ username: '', password: '' })

function setMode(value: Mode) {
  mode.value = value
  formRef.value?.clearValidate()
}

function switchMode() {
  setMode(mode.value === 'login' ? 'register' : 'login')
}

// singleFlight：校验结束前（“登录”按钮还没变成加载中）连按两次回车，原来会发两次请求
const onSubmit = singleFlight(async () => {
  if (!(await formRef.value?.validate().catch(() => false))) return
  submitting.value = true
  try {
    const result = await submitCredentials(mode.value, form, { register: authApi.register, login })
    if (result.kind === 'failed') {
      ElMessage.error(errorMessage(result.error))
      return
    }
    if (result.kind === 'registered-not-signed-in') {
      // 账号已经建好：切回登录模式，用户名和密码都保留，再点一次“登录”即可。
      // 原来停在注册模式，再点一次只会得到“用户名已存在”
      setMode('login')
      ElMessage.warning(`账号已创建，但自动登录没有成功（${errorMessage(result.error)}）。已切换到登录，请再点一次“登录”。`)
      return
    }
    // 原来在注册成功、还没登录时就提示“已自动登录”，随后登录失败时提示是错的；现在登录成功后才提示
    if (result.registered) ElMessage.success('注册成功，已自动登录')
    await props.afterSignIn()
  } catch (error) {
    // afterSignIn（跳转）失败等意外情况
    ElMessage.error(errorMessage(error))
  } finally {
    submitting.value = false
  }
})
</script>

<template>
  <el-card class="login-card" shadow="never">
    <!-- 用 h2：读屏软件按标题跳转时能找到表单；样式与原来的卡片标题相同 -->
    <template #header>
      <h2 class="login-card-title">{{ mode === 'login' ? '登录' : '注册新用户' }}</h2>
    </template>
    <!-- 表单上方的提示，由页面传入（“连不上服务器，登录状态已保留”等） -->
    <slot />
    <!--
      切换登录 / 注册时 rules 会换一套。Element Plus 默认在 rules 变化后把整个表单校验一遍，
      空表单一切到“注册”就冒出两行红字（原来就有这个问题），所以关掉；各字段仍在失去焦点和提交时校验
    -->
    <el-form
      ref="formRef"
      :model="form"
      :rules="mode === 'login' ? LOGIN_RULES : REGISTER_RULES"
      :validate-on-rule-change="false"
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
