<script setup lang="ts">
// 文档预览（附录 A16）：PDF 用 pdf.js 显示并跳到命中的页；图片原样显示；
// Word、Excel 显示系统抽取出的文本，并跳到命中的段落或单元格范围。
// PDF、图片另有“抽取文本”标签页，显示正文和 OCR 识别出的文字（T24f，decisions.md D45）。
import { ElMessage } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { errorMessage } from '../api/client'
import { downloadDocument, getDocument } from '../api/documents'
import type { DocumentItem } from '../api/types'
import ExtractedText from '../components/ExtractedText.vue'
import PdfViewer from '../components/PdfViewer.vue'
import { documentOutdated, hasNewOcr } from '../features/tasks/changes'
import { Refresher } from '../features/tasks/refresher'
import { failedTasks } from '../features/tasks/summary'
import TaskDialog from '../features/tasks/TaskDialog.vue'
import { failureNotices, progressText } from '../features/tasks/text'
import { useDocumentTasks } from '../features/tasks/useDocumentTasks'
import { saveBlob } from '../utils/download'
import { m } from '../i18n'
import { STATUS_LABEL, formatType, isImageType } from '../utils/format'
import { type PreviewTab, initialPreviewTab } from '../utils/preview'

const PDF = 'application/pdf'

const route = useRoute()
const router = useRouter()
// 进入页面时就定下来，不跟着 route 变：请求返回时用户可能已经去了别的页面，那时 route.params 是别的页面的。
// 换一个文件时 App.vue 会重新创建本组件（router-view 的 key）
const id = String(route.params.id)
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

// PDF、图片当前的标签页；两个标签页都是懒加载，第一次切过去时才加载
const tab = ref<PreviewTab>('file')

const kind = computed<'pdf' | 'image' | 'text' | null>(() => {
  if (!document.value) return null
  if (document.value.mime_type === PDF) return 'pdf'
  if (isImageType(document.value.mime_type)) return 'image'
  return 'text'
})

const emptyText = computed(() => {
  if (document.value?.status === 'failed') return m().preview.parseFailed
  if (document.value?.status !== 'succeeded') return m().preview.notReady
  // PDF、图片解析成功后 OCR 仍在后台进行（文档状态只跟随解析，D27）
  return kind.value === 'text' ? m().preview.noText : m().preview.noTextScan
})

// ---- 处理任务：失败提示、重试、处理完自动刷新（任务状态与重试 P4）----

const showTasks = ref(false)
// 抽取文本组件（两处用法同一时间只会有一个）；没打开过“抽取文本”标签页时为 null
const extracted = ref<{ reload: () => Promise<void> } | null>(null)
const newText = ref(false)

const tasks = useDocumentTasks({
  onTasks: (next, previous) => {
    if (!document.value) return
    if (documentOutdated(document.value.status, previous, next)) void refresher.run()
    // 正文可能正在读，不打断，只提示；还没打开过抽取文本的，打开时自然是最新的
    if (extracted.value && hasNewOcr(previous, next)) newText.value = true
  },
})
const notices = computed(() => failureNotices(tasks.steps))
const progress = computed(() => progressText(tasks.steps))
const canRetry = computed(() => document.value !== null && document.value.access !== 'shared')

// 失败会自己再试，离开页面即停（refresher.ts）
const refresher = new Refresher<DocumentItem>({
  load: () => getDocument(id),
  onLoaded: (next) => {
    const before = document.value?.status
    document.value = next
    // 刚解析完：原来是空的，直接换成新内容
    if (before !== 'succeeded' && next.status === 'succeeded') void extracted.value?.reload()
  },
  onError: (error) => ElMessage.error(errorMessage(error)),
})

async function loadNewText() {
  newText.value = false
  await extracted.value?.reload()
}

let disposed = false

async function load() {
  try {
    document.value = await getDocument(id)
    // 文件还没取回来用户就离开了：不再请求任务、下载原文件
    if (disposed) return
    void tasks.start(id)
  } catch (error) {
    loadError.value = errorMessage(error)
    return
  }
  // Word、Excel 的抽取文本由 ExtractedText 自己加载
  if (kind.value !== 'pdf' && kind.value !== 'image') return
  tab.value = initialPreviewTab(kind.value, route.query)
  try {
    // 下载接口需要登录令牌，不能直接把地址交给 <img> 或 pdf.js，先取成字节
    const blob = await downloadDocument(id)
    if (disposed) return
    if (kind.value === 'pdf') fileData.value = await blob.arrayBuffer()
    else imageUrl.value = URL.createObjectURL(blob)
  } catch (error) {
    loadError.value = errorMessage(error)
  }
}

function onTabChange(name: string | number) {
  // 写进地址栏：刷新或复制链接时停在同一个标签页；用 replace，不往浏览器历史里加记录
  void router.replace({ query: { ...route.query, view: String(name) } })
}

async function onDownload() {
  if (!document.value) return
  try {
    saveBlob(await downloadDocument(document.value.id), document.value.filename)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

// 从列表或检索结果点进来时回到原来的页面；直接打开链接时没有上一页，回到文件列表，
// 不让“返回”把人带出本系统（vue-router 把上一页记在 history.state.back 里）
function goBack() {
  if (window.history.state?.back) router.back()
  else void router.push({ name: 'documents' })
}

onMounted(() => void load())
onBeforeUnmount(() => {
  disposed = true
  refresher.stop()
  if (imageUrl.value) URL.revokeObjectURL(imageUrl.value)
})
</script>

<template>
  <el-button link class="back" @click="goBack">{{ m().preview.back }}</el-button>
  <div class="page-head">
    <div class="head-main">
      <h1 class="page-title">{{ document?.filename ?? m().preview.fallbackTitle }}</h1>
      <p v-if="document" class="page-desc">
        <span>{{ formatType(document.mime_type) }}</span>
        <el-tag :type="STATUS_LABEL[document.status].type" size="small">{{ STATUS_LABEL[document.status].text }}</el-tag>
        <!-- 一直在 DOM 里，内容变化时读屏软件才会读出来 -->
        <span role="status" aria-live="polite">{{ progress }}</span>
        <span v-if="tasks.error && !tasks.error.silent" class="tasks-error">{{ m().tasks.loadError }}</span>
      </p>
    </div>
    <div v-if="document" class="head-actions">
      <el-button @click="showTasks = true">{{ m().tasks.open }}</el-button>
      <el-button @click="onDownload">{{ m().preview.downloadOriginal }}</el-button>
    </div>
  </div>

  <el-alert v-if="notices.length > 0" type="warning" show-icon :closable="false" class="failures">
    <template #title>
      <div v-for="line in notices" :key="line">{{ line }}</div>
    </template>
    <div class="failure-actions">
      <el-button
        v-if="canRetry"
        size="small"
        type="primary"
        :loading="tasks.retrying"
        @click="tasks.retry(failedTasks(tasks.tasks ?? []))"
      >
        {{ m().tasks.retryAllFailed }}
      </el-button>
      <el-button size="small" @click="showTasks = true">{{ m().tasks.viewDetails }}</el-button>
    </div>
  </el-alert>

  <div v-if="newText" class="new-text" role="status">
    {{ m().tasks.newText }}
    <el-button link type="primary" @click="loadNewText">{{ m().tasks.loadNewText }}</el-button>
  </div>

  <el-card shadow="never" class="preview-card">
    <el-alert v-if="loadError" type="error" :title="loadError" show-icon :closable="false" />

    <!-- 两个标签页都懒加载：PdfViewer 不在隐藏的标签页里先渲染（那时量不到容器宽度），
         抽取文本也只在第一次切过去时才请求 -->
    <el-tabs v-else-if="kind === 'pdf' || kind === 'image'" v-model="tab" @tab-change="onTabChange">
      <el-tab-pane :label="m().preview.tabFile" name="file" lazy>
        <PdfViewer v-if="kind === 'pdf' && fileData" :data="fileData" :initial-page="initialPage" />
        <div v-else-if="kind === 'image' && imageUrl" class="image-box">
          <img :src="imageUrl" :alt="document?.filename" class="image" />
        </div>
        <div v-else v-loading="true" class="placeholder" />
      </el-tab-pane>
      <el-tab-pane :label="m().preview.tabText" name="text" lazy>
        <ExtractedText
          ref="extracted"
          :document-id="id"
          :target-chunk="targetChunk"
          :terms="terms"
          :notice="m().preview.extractedNotice"
          :empty-text="emptyText"
        />
      </el-tab-pane>
    </el-tabs>

    <ExtractedText
      v-else-if="kind === 'text'"
      ref="extracted"
      :document-id="id"
      :target-chunk="targetChunk"
      :terms="terms"
      :notice="m().preview.officeNotice"
      :empty-text="emptyText"
    />

    <div v-else-if="!document" v-loading="true" class="placeholder" />
  </el-card>

  <TaskDialog :document="showTasks ? document : null" :source="tasks" @close="showTasks = false" />
</template>

<style scoped>
.back {
  margin-bottom: 8px;
  color: var(--app-text-secondary);
}

.head-main {
  min-width: 0;
}

.head-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

/* Element Plus 给相邻按钮加了外边距，这里统一用 gap 排开 */
.head-actions .el-button + .el-button,
.failure-actions .el-button + .el-button {
  margin-left: 0;
}

.tasks-error {
  color: var(--el-color-danger-dark-2);
}

.failures {
  margin-bottom: 12px;
}

/* Element Plus 的警告标题是橙字配浅橙底，对比度不够；颜色由图标和底色表示，文字用正文色 */
.failures :deep(.el-alert__title) {
  color: var(--app-text);
  line-height: 1.6;
}

.failure-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 6px;
}

.new-text {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 8px 12px;
  border-radius: var(--app-radius);
  background: var(--app-primary-soft);
  color: var(--app-text);
  font-size: 13px;
}

.preview-card {
  border-radius: var(--app-radius-lg);
}

.image-box {
  text-align: center;
}

.image {
  max-width: 100%;
}

.placeholder {
  min-height: 200px;
}
</style>
