<script setup lang="ts">
// 页面里用到的几个线条图标（T24s）。项目没有图标库，这几个形状很简单，
// 直接画成 SVG，不为它们新增依赖。颜色跟随所在位置的文字颜色（currentColor）。
type IconName = 'docs' | 'file-text' | 'folder' | 'search' | 'upload' | 'logout'

const PATHS: Record<IconName, string[]> = {
  docs: ['M8 3h7l5 5v11a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2', 'M15 3v5h5', 'M10 13h6', 'M10 17h4'],
  // 登录页星尘光球 logo 中间的文档图标：取自 Lucide 图标库的 file-text（lucide-static v1.77.0，
  // https://lucide.dev/icons/file-text），ISC 许可，Copyright (c) 2026 Lucide Icons and Contributors。
  // 只抄了路径数据，没有安装任何包；登记见 docs/downloads.md §2.8（Barry 2026-11-22 批准）
  'file-text': [
    'M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z',
    'M14 2v5a1 1 0 0 0 1 1h5',
    'M10 9H8',
    'M16 13H8',
    'M16 17H8',
  ],
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
