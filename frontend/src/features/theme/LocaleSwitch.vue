<script setup lang="ts">
// 界面语言切换（Barry 2026-11-22，演示用）：右下角、配色按钮左边的“中 | EN”胶囊，点一下立即切换，
// 选择保存在本机浏览器（src/i18n）。
import { locale, m, type Locale } from '../../i18n'

const OPTIONS: { value: Locale; short: string }[] = [
  { value: 'zh', short: '中' },
  { value: 'en', short: 'EN' },
]
</script>

<template>
  <div class="locale-switch" role="group" :aria-label="m().locale.label">
    <button
      v-for="option in OPTIONS"
      :key="option.value"
      type="button"
      class="option"
      :class="{ active: locale === option.value }"
      :aria-pressed="locale === option.value"
      :title="m().locale[option.value]"
      :lang="option.value === 'en' ? 'en' : 'zh-CN'"
      @click="locale = option.value"
    >
      {{ option.short }}
    </button>
  </div>
</template>

<style scoped>
.locale-switch {
  display: flex;
  box-sizing: border-box;
  height: 44px;
  padding: 4px;
  border: 1px solid var(--app-border);
  border-radius: 22px;
  background: var(--app-surface);
  box-shadow: var(--el-box-shadow-light);
}

.option {
  min-width: 40px;
  padding: 0 10px;
  border: none;
  border-radius: 18px;
  background: transparent;
  color: var(--app-text-regular);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.option.active {
  background: var(--el-color-primary);
  color: var(--el-color-white);
}

.option:focus-visible {
  outline: 2px solid var(--el-color-primary-dark-2);
  outline-offset: 1px;
}
</style>
