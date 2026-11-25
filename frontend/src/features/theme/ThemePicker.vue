<script setup lang="ts">
// 配色面板（T24bc）：页面右下角一个圆形按钮，点开选主色（预设或自定义）和浅色 / 深色 / 跟随系统。
// 所有页面都有（App.vue 右下角，与语言切换放在一起），包括登录页。点面板外面或按 Esc 关闭。
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import AppIcon from '../../components/AppIcon.vue'
import { m } from '../../i18n'
import { theme } from './store'
import { contrastWarning, DEFAULT_THEME, resolveDark, THEME_PRESETS } from './theme'

const open = ref(false)
const root = ref<HTMLElement | null>(null)

const warning = computed(() => contrastWarning(theme.primary, resolveDark(theme.mode)))
const isPreset = computed(() => THEME_PRESETS.some((p) => p.primary === theme.primary))
const currentName = computed(() => {
  const preset = THEME_PRESETS.find((p) => p.primary === theme.primary)
  return preset ? m().theme.presets[preset.id] : m().theme.customName(theme.primary)
})

function reset() {
  theme.primary = DEFAULT_THEME.primary
  theme.mode = DEFAULT_THEME.mode
}

function onPointerDown(event: PointerEvent) {
  if (open.value && root.value && !root.value.contains(event.target as Node)) open.value = false
}

function onKey(event: KeyboardEvent) {
  if (event.key === 'Escape') open.value = false
}

onMounted(() => {
  document.addEventListener('pointerdown', onPointerDown)
  document.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onPointerDown)
  document.removeEventListener('keydown', onKey)
})
</script>

<template>
  <div ref="root" class="theme-picker">
    <div v-if="open" id="theme-panel" class="panel" role="dialog" :aria-label="m().theme.title">
      <p class="panel-title">{{ m().theme.title }}</p>

      <p class="label">{{ m().theme.primary }}</p>
      <div class="swatches">
        <button
          v-for="preset in THEME_PRESETS"
          :key="preset.id"
          type="button"
          class="swatch"
          :class="{ active: theme.primary === preset.primary }"
          :style="{ background: preset.primary }"
          :title="m().theme.presets[preset.id]"
          :aria-label="m().theme.presets[preset.id]"
          :aria-pressed="theme.primary === preset.primary"
          @click="theme.primary = preset.primary"
        />
        <label class="swatch custom" :class="{ active: !isPreset }" :title="m().theme.custom">
          <input v-model="theme.primary" type="color" :aria-label="m().theme.customAria" />
        </label>
      </div>
      <p class="names">
        {{ currentName }}
      </p>

      <p class="label">{{ m().theme.mode }}</p>
      <el-radio-group v-model="theme.mode" size="small">
        <el-radio-button value="light">{{ m().theme.light }}</el-radio-button>
        <el-radio-button value="dark">{{ m().theme.dark }}</el-radio-button>
        <el-radio-button value="system">{{ m().theme.system }}</el-radio-button>
      </el-radio-group>

      <p v-if="warning" class="warning">{{ warning }}</p>

      <div class="foot">
        <span class="hint">{{ m().theme.hint }}</span>
        <el-button link type="primary" size="small" @click="reset">{{ m().theme.reset }}</el-button>
      </div>
    </div>

    <button
      type="button"
      class="toggle"
      :aria-expanded="open"
      aria-controls="theme-panel"
      :title="m().theme.title"
      :aria-label="m().theme.title"
      @click="open = !open"
    >
      <AppIcon name="palette" :size="20" />
    </button>
  </div>
</template>

<style scoped>
.theme-picker {
  position: relative;
}

/* 面板在按钮上方、右对齐（按钮在 App.vue 右下角的 .floating-tools 里） */
.panel {
  position: absolute;
  right: 0;
  bottom: 54px;
}

.toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: var(--el-color-primary);
  color: var(--el-color-white);
  box-shadow: var(--el-box-shadow-light);
  cursor: pointer;
}

.toggle:focus-visible {
  outline: 2px solid var(--el-color-primary-dark-2);
  outline-offset: 2px;
}

.panel {
  box-sizing: border-box;
  width: 268px;
  padding: 14px 16px 10px;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
  background: var(--app-surface);
  color: var(--app-text);
  box-shadow: var(--el-box-shadow);
  font-size: 13px;
}

.panel p {
  margin: 0;
}

.panel-title {
  margin-bottom: 10px !important;
  font-size: 14px;
  font-weight: 600;
}

.label {
  margin: 10px 0 6px !important;
  color: var(--app-text-secondary);
  font-size: 12px;
}

.swatches {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.swatch {
  position: relative;
  box-sizing: border-box;
  width: 26px;
  height: 26px;
  padding: 0;
  border: 2px solid var(--app-surface);
  border-radius: 50%;
  box-shadow: 0 0 0 1px var(--el-border-color);
  cursor: pointer;
}

.swatch.active {
  box-shadow: 0 0 0 2px var(--app-text);
}

.swatch:focus-visible {
  outline: 2px solid var(--el-color-primary-dark-2);
  outline-offset: 2px;
}

/* 自定义：彩虹色圆点，里面盖一个透明的原生取色器 */
.custom {
  overflow: hidden;
  background: conic-gradient(#f56c6c, #e6a23c, #67c23a, #409eff, #9b59b6, #f56c6c);
}

.custom input {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  padding: 0;
  border: none;
  opacity: 0;
  cursor: pointer;
}

.names {
  margin-top: 6px !important;
  color: var(--app-text-regular);
}

.warning {
  margin-top: 10px !important;
  color: var(--el-color-danger);
  font-size: 12px;
  line-height: 1.5;
}

.foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 12px;
  padding-top: 8px;
  border-top: 1px solid var(--app-border);
}

.hint {
  color: var(--app-text-secondary);
  font-size: 12px;
}

</style>
