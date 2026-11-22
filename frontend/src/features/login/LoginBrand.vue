<script setup lang="ts">
// 登录页顶部的品牌区：logo、系统名、一句话说明（登录页结构优化 L4，从 LoginView.vue 拆出）。
// logo 用插槽传入：克隆库里登录页传星尘光球（search-motion 动效，P4）；不传时显示侧栏同款的静态图标，
// 以后把登录页合回主仓库时，去掉 LoginView.vue 里的那一行插槽就不再依赖动效代码（问题 B3）。
import AppIcon from '../../components/AppIcon.vue'
import { m } from '../../i18n'
</script>

<template>
  <div class="login-brand">
    <div class="login-brand-logo">
      <slot name="logo">
        <span class="app-logo"><AppIcon name="docs" :size="20" /></span>
      </slot>
    </div>
    <h1 class="login-brand-title">{{ m().app.title }}</h1>
    <p class="login-brand-desc">{{ m().login.desc }}</p>
  </div>
</template>

<style scoped>
.login-brand {
  text-align: center;
}

/* logo 居中：插槽里的元素可能是块级（星尘光球）也可能是行内块（静态图标） */
.login-brand-logo {
  display: flex;
  justify-content: center;
}

.login-brand-title {
  margin: 4px 0 4px;
  font-size: 22px;
  font-weight: 600;
}

.login-brand-desc {
  margin: 0;
  color: var(--app-text-secondary);
  font-size: 13px;
}
</style>
