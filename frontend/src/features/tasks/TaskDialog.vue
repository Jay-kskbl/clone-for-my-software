<script setup lang="ts">
// 处理详情（任务状态与重试 P3）：一个文档处理到哪一步、为什么失败、重试。
// 数据和轮询由使用它的页面提供（useDocumentTasks），这里只负责显示。
import { computed } from 'vue'

import { errorMessage } from '../../api/client'
import type { DocumentItem } from '../../api/types'
import { m } from '../../i18n'
import { hopelessNotice, retryLabel, stateTag, stepDetails, stepName } from './text'
import type { DocumentTasks } from './useDocumentTasks'

const props = defineProps<{ document: DocumentItem | null; source: DocumentTasks }>()
const emit = defineEmits<{ close: [] }>()

// 被共享者只能看（docs/api.md §6.2）；后端也会校验
const canRetry = computed(() => props.document !== null && props.document.access !== 'shared')
const loading = computed(() => props.source.tasks === null && props.source.error === null)
const errorTitle = computed(() => (props.source.error?.silent ? m().tasks.staleError : m().tasks.loadError))
</script>

<template>
  <el-dialog
    :model-value="document !== null"
    :title="document ? m().tasks.title(document.filename) : ''"
    width="min(620px, 92vw)"
    @close="emit('close')"
  >
    <p class="hint">{{ m().tasks.hint }}<template v-if="!canRetry">{{ m().tasks.readonly }}</template></p>

    <el-alert
      v-if="source.error"
      :type="source.error.silent ? 'warning' : 'error'"
      :title="errorTitle"
      :description="errorMessage(source.error.error)"
      show-icon
      :closable="false"
      class="notice"
    />

    <div v-loading="loading" class="body">
      <p v-if="source.tasks !== null && source.steps.length === 0" class="empty">{{ m().tasks.empty }}</p>
      <ul v-else class="steps">
        <li v-for="step in source.steps" :key="step.type" class="step">
          <div class="step-main">
            <div class="step-head">
              <span class="step-name">{{ stepName(step.type) }}</span>
              <el-tag size="small" :type="stateTag(step.state).type" disable-transitions>{{ stateTag(step.state).text }}</el-tag>
            </div>
            <p v-for="(line, index) in stepDetails(step)" :key="index" class="line">{{ line }}</p>
            <p v-if="canRetry && hopelessNotice(step)" class="line warn">{{ hopelessNotice(step) }}</p>
          </div>
          <el-button
            v-if="canRetry && step.failed.length > 0"
            size="small"
            type="primary"
            plain
            :loading="source.retrying"
            @click="source.retry(step.failed)"
          >
            {{ retryLabel(step) }}
          </el-button>
        </li>
      </ul>
    </div>

    <div class="foot">
      <!-- 一直在 DOM 里，内容变化时读屏软件才会读出来 -->
      <span role="status" aria-live="polite">{{ source.active ? m().tasks.autoRefresh : '' }}</span>
      <el-button size="small" :loading="source.refreshing" @click="source.refresh()">{{ m().tasks.refresh }}</el-button>
    </div>
  </el-dialog>
</template>

<style scoped>
.hint {
  margin: 0 0 12px;
  color: var(--app-text-regular);
  font-size: 13px;
  line-height: 1.6;
}

.notice {
  margin-bottom: 12px;
}

.body {
  min-height: 72px;
}

.empty {
  margin: 0;
  padding: 20px 0;
  color: var(--app-text-regular);
  text-align: center;
}

.steps {
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0;
  list-style: none;
}

.step {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px 16px;
  padding: 12px 0;
  border-top: 1px solid var(--app-border);
}

/* 说明放得下时与按钮同一行，放不下时按钮换到下一行 */
.step-main {
  flex: 1 1 220px;
  min-width: 0;
}

.step-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.step-name {
  color: var(--app-text);
  font-weight: 600;
}

.line {
  margin: 4px 0 0;
  color: var(--app-text-regular);
  font-size: 13px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.warn {
  color: var(--app-text);
}

.foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--app-border);
  color: var(--app-text-regular);
  font-size: 12px;
}
</style>
