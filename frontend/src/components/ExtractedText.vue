<script setup lang="ts">
// 系统抽取出的文本片段列表（GET /api/documents/{id}/text）：分页、跳到命中的片段、高亮检索词。
// Word、Excel 的预览直接用它；PDF、图片在“抽取文本”标签页里用它（T24f），能看到正文和 OCR
// 识别出的文字，顺序按页码穿插（T24e）。挂载时加载，放在懒加载的标签页里就是按需加载。
import { ElMessage } from 'element-plus'
import { nextTick, onMounted, ref } from 'vue'

import { errorMessage } from '../api/client'
import { getDocumentText } from '../api/documents'
import type { TextChunk } from '../api/types'
import { SOURCE_TYPE_LABEL, formatLocator } from '../utils/locator'
import { highlightText } from '../utils/snippet'

const TEXT_PAGE_SIZE = 50

const props = defineProps<{
  documentId: string
  // 要跳到并标出的片段（来自检索结果）；没有时从第 1 页开始
  targetChunk: string | null
  terms: string[]
  // 顶部的说明；不需要时传 null
  notice: string | null
  // 一个片段都没有时显示的文字
  emptyText: string
}>()

const chunks = ref<TextChunk[]>([])
const textTotal = ref(0)
const textPage = ref(1)
const textLoading = ref(false)

async function loadText(options: { page?: number; chunkId?: string | null } = {}) {
  textLoading.value = true
  try {
    const result = await getDocumentText(props.documentId, {
      page: options.page,
      page_size: TEXT_PAGE_SIZE,
      chunk_id: options.chunkId ?? undefined,
    })
    chunks.value = result.items
    textTotal.value = result.total
    textPage.value = result.page
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    textLoading.value = false
  }
}

async function scrollToTarget() {
  if (!props.targetChunk) return
  await nextTick()
  // 等浏览器完成一次布局再滚动。直接打开或刷新页面时，过早的滚动会被随后的布局变化
  // 和浏览器的滚动恢复冲掉；平滑滚动同样会被打断，所以用瞬时滚动
  await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))
  window.document.getElementById(`chunk-${props.targetChunk}`)?.scrollIntoView({ block: 'center' })
}

function onTextPageChange(page: number) {
  void loadText({ page })
}

// 重新加载当前这一页，不滚动：文件刚解析完、OCR 有新结果时由预览页调用
defineExpose({ reload: () => loadText({ page: textPage.value }) })

onMounted(async () => {
  await loadText({ chunkId: props.targetChunk })
  await scrollToTarget()
})
</script>

<template>
  <div v-loading="textLoading">
    <el-alert v-if="notice" type="info" :title="notice" show-icon :closable="false" class="notice" />
    <el-empty v-if="!textLoading && chunks.length === 0" :description="emptyText" />
    <div
      v-for="chunk in chunks"
      :id="`chunk-${chunk.chunk_id}`"
      :key="chunk.chunk_id"
      class="chunk"
      :class="{ target: chunk.chunk_id === targetChunk }"
    >
      <div class="chunk-meta">
        {{ formatLocator(chunk.locator) }}
        <template v-if="chunk.source_type !== 'body'">（{{ SOURCE_TYPE_LABEL[chunk.source_type] }}）</template>
      </div>
      <!-- highlightText 先转义全文，再只插入 <em>（utils/snippet.ts） -->
      <div class="chunk-text app-mark" v-html="highlightText(chunk.text, terms)" />
    </div>
    <el-pagination
      v-if="textTotal > TEXT_PAGE_SIZE"
      class="pagination"
      layout="total, prev, pager, next"
      :total="textTotal"
      :page-size="TEXT_PAGE_SIZE"
      :current-page="textPage"
      @current-change="onTextPageChange"
    />
  </div>
</template>

<style scoped>
.notice {
  margin-bottom: 12px;
}

.chunk {
  padding: 10px 12px;
  border-left: 3px solid transparent;
}

.chunk.target {
  background: var(--el-color-warning-light-9);
  border-left-color: var(--el-color-warning);
}

.chunk-meta {
  color: var(--app-text-secondary);
  font-size: 12px;
  margin-bottom: 4px;
}

/* 检索词高亮的样式在 styles.css 的 .app-mark（T24s） */
.chunk-text {
  white-space: pre-wrap;
  word-break: break-all;
  line-height: 1.7;
}

.pagination {
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
