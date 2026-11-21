<script setup lang="ts">
// 页面里用到的几个线条图标（T24s）。项目没有图标库，这几个形状很简单，
// 直接画成 SVG，不为它们新增依赖。颜色跟随所在位置的文字颜色（currentColor）。
type IconName = 'docs' | 'folder' | 'search' | 'upload' | 'logout'

const PATHS: Record<IconName, string[]> = {
  docs: ['M8 3h7l5 5v11a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2', 'M15 3v5h5', 'M10 13h6', 'M10 17h4'],
  folder: ['M4 6a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z'],
  search: ['M11 4a7 7 0 1 0 0 14a7 7 0 1 0 0-14', 'M20 20l-4-4'],
  upload: ['M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2', 'M7 9l5-5l5 5', 'M12 4v12'],
  logout: [
    'M14 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2v-2',
    'M9 12h11',
    'M17 9l3 3l-3 3',
  ],
}

defineProps<{ name: IconName; size?: number }>()
</script>

<template>
  <svg
    class="app-icon"
    :width="size ?? 18"
    :height="size ?? 18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.8"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path v-for="d in PATHS[name]" :key="d" :d="d" />
  </svg>
</template>

<style scoped>
.app-icon {
  flex: none;
  vertical-align: middle;
}
</style>
