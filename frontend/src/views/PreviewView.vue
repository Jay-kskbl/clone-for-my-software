<script setup lang="ts">
// 文档预览（附录 A16）：PDF 用 pdf.js 显示并跳到命中的页；图片原样显示；
// Word、Excel 显示系统抽取出的文本，并跳到命中的段落或单元格范围。
import { ElMessage } from 'element-plus'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { errorMessage } from '../api/client'
import { downloadDocument, getDocument, getDocumentText } from '../api/documents'
import type { DocumentItem, TextChunk } from '../api/types'
import PdfViewer from '../components/PdfViewer.vue'
import { STATUS_LABEL, formatType } from '../utils/format'
import { SOURCE_TYPE_LABEL, formatLocator } from '../utils/locator'
import { highlightText } from '../utils/snippet'

const PDF = 'application/pdf'
const IMAGE_TYPES = ['image/png', 'image/jpeg']
const TEXT_PAGE_SIZE = 50

const route = useRoute()
const id = computed(() => String(route.params.id))
const initialPage = computed(() => {
  const page = Number(route.query.page)
  return Number.isInteger(page) && page >= 1 ? page : 1
})
const targetChunk = computed(() => (typeof route.query.chunk === 'string' ? route.query.chunk : null))
const terms = computed(() =>
  typeof route.query.q === 'string' ? route.query.q.split(/\s+/).filter(Boolean) : [],
)

const document = ref<DocumentItem | null>(null)
const loadError = ref<string | null>(null)
const fileData = ref<ArrayBuffer | null>(null)
const imageUrl = ref<string | null>(null)

const chunks = ref<TextChunk[]>([])
const textTotal = ref(0)
const textPage = ref(1)
const textLoading = ref(false)

const kind = computed<'pdf' | 'image' | 'text' | null>(() => {
  if (!document.value) return null
  if (document.value.mime_type === PDF) return 'pdf'
  if (IMAGE_TYPES.includes(document.value.mime_type)) return 'image'
  return 'text'
})

async function loadText(options: { page?: number; chunkId?: string | null } = {}) {
  textLoading.value = true
  try {
    const result = await getDocumentText(id.value, {
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
  if (!targetChunk.value) return
  await nextTick()
  // 等浏览器完成一次布局再滚动。直接打开或刷新页面时，过早的滚动会被随后的布局变化
  // 和浏览器的滚动恢复冲掉；平滑滚动同样会被打断，所以用瞬时滚动
  await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))
  window.document.getElementById(`chunk-${targetChunk.value}`)?.scrollIntoView({ block: 'center' })
}

async function load() {
  try {
    document.value = await getDocument(id.value)
  } catch (error) {
    loadError.value = errorMessage(error)
    return
  }
  try {
    if (kind.value === 'text') {
      await loadText({ chunkId: targetChunk.value })
      await scrollToTarget()
    } else {
      // 下载接口需要登录令牌，不能直接把地址交给 <img> 或 pdf.js，先取成字节
      const blob = await downloadDocument(id.value)
      if (kind.value === 'pdf') fileData.value = await blob.arrayBuffer()
      else imageUrl.value = URL.createObjectURL(blob)
    }
  } catch (error) {
    loadError.value = errorMessage(error)
  }
}

function onTextPageChange(page: number) {
  void loadText({ page })
}

async function onDownload() {
  if (!document.value) return
  try {
    const blob = await downloadDocument(document.value.id)
    const url = URL.createObjectURL(blob)
    const link = window.document.createElement('a')
    link.href = url
    link.download = document.value.filename
    link.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

onMounted(() => void load())
onBeforeUnmount(() => {
  if (imageUrl.value) URL.revokeObjectURL(imageUrl.value)
})
</script>

<template>
  <el-card>
    <div class="head">
      <el-button link @click="$router.back()">← 返回</el-button>
      <template v-if="document">
        <span class="title">{{ document.filename }}</span>
        <span class="type">{{ formatType(document.mime_type) }}</span>
        <el-tag :type="STATUS_LABEL[document.status].type" size="small">{{ STATUS_LABEL[document.status].text }}</el-tag>
        <el-button class="download" @click="onDownload">下载原文件</el-button>
      </template>
    </div>

    <el-alert v-if="loadError" type="error" :title="loadError" show-icon :closable="false" />

    <PdfViewer v-else-if="kind === 'pdf' && fileData" :data="fileData" :initial-page="initialPage" />

    <div v-else-if="kind === 'image' && imageUrl" class="image-box">
      <img :src="imageUrl" :alt="document?.filename" class="image" />
    </div>

    <div v-else-if="kind === 'text'" v-loading="textLoading">
      <el-alert
        type="info"
        title="Word 和 Excel 只显示系统抽取出的文本，看不到原始格式、图表和公式；需要原样查看请下载原文件。"
        show-icon
        :closable="false"
        class="notice"
      />
      <el-empty
        v-if="!textLoading && chunks.length === 0"
        :description="document?.status === 'succeeded' ? '这个文件里没有抽取到文字' : '文件还没有处理完成，暂时没有抽取文本'"
      />
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
        <div class="chunk-text" v-html="highlightText(chunk.text, terms)" />
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

    <div v-else-if="!document" v-loading="true" class="placeholder" />
  </el-card>
</template>

<style scoped>
.head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.title {
  font-size: 16px;
  font-weight: 600;
}

.type {
  color: #909399;
  font-size: 13px;
}

.download {
  margin-left: auto;
}

.notice {
  margin-bottom: 12px;
}

.image-box {
  text-align: center;
}

.image {
  max-width: 100%;
}

.chunk {
  padding: 10px 12px;
  border-left: 3px solid transparent;
}

.chunk.target {
  background: #fdf6ec;
  border-left-color: #e6a23c;
}

.chunk-meta {
  color: #909399;
  font-size: 12px;
  margin-bottom: 4px;
}

.chunk-text {
  white-space: pre-wrap;
  word-break: break-all;
  line-height: 1.7;
}

.chunk-text :deep(em) {
  color: #f56c6c;
  font-style: normal;
}

.pagination {
  justify-content: flex-end;
  margin-top: 16px;
}

.placeholder {
  min-height: 200px;
}
</style>
