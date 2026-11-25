<script setup lang="ts">
// 登录页顶部的品牌区：系统标志、系统名、一句话说明（T24w，从 LoginView.vue 拆出，外观不变）。
import AppIcon from '../../components/AppIcon.vue'
</script>

<template>
  <div class="login-brand">
    <span class="app-logo login-logo"><AppIcon name="docs" :size="26" /></span>
    <h1 class="login-title">智能文档管理系统</h1>
    <p class="login-desc">多格式文档管理 · 全文检索 · OCR 文字检索 · 图文语义检索</p>
  </div>
</template>

<style scoped>
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
</style>
