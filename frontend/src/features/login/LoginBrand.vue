<script setup lang="ts">
// 登录页顶部的品牌区：系统标志、系统名、一句话说明（T24w，从 LoginView.vue 拆出，外观不变）。
// 标志用插槽 logo 传入：登录页传星尘光球（T24be）；不传时显示原来的静态标志。
import AppIcon from '../../components/AppIcon.vue'
import { m } from '../../i18n'
</script>

<template>
  <div class="login-brand">
    <!-- 居中：插槽里的元素是块级（星尘光球），静态标志是行内块 -->
    <div class="login-logo-box">
      <slot name="logo">
        <span class="app-logo login-logo"><AppIcon name="docs" :size="26" /></span>
      </slot>
    </div>
    <h1 class="login-title">{{ m().app.title }}</h1>
    <p class="login-desc">{{ m().login.desc }}</p>
  </div>
</template>

<style scoped>
.login-brand {
  text-align: center;
}

.login-logo-box {
  display: flex;
  justify-content: center;
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
</style>
