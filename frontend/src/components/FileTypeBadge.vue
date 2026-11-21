<script setup lang="ts">
// 文件类型的小色块（T24s）：文件列表和检索结果里，不用读文字也能分出 PDF、Word、Excel、图片。
import { computed } from 'vue'

import { formatType, typeBadge } from '../utils/format'

const props = defineProps<{ mimeType: string; size?: 'small' | 'large' }>()
const badge = computed(() => typeBadge(props.mimeType))
</script>

<template>
  <span class="badge" :class="[badge.tone, size ?? 'small']" :title="formatType(mimeType)">{{ badge.text }}</span>
</template>

<style scoped>
.badge {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.small {
  width: 32px;
  height: 32px;
  font-size: 11px;
}

.large {
  width: 72px;
  height: 72px;
  border-radius: var(--app-radius);
  font-size: 16px;
}

.danger {
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}

.primary {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

.success {
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
}

.warning {
  background: var(--el-color-warning-light-9);
  color: var(--el-color-warning-dark-2);
}

.info {
  background: var(--el-fill-color);
  color: var(--app-text-secondary);
}
</style>
