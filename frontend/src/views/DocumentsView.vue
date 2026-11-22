<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'

import { errorMessage } from '../api/client'
import {
  deleteDocument,
  downloadDocument,
  listDocuments,
  uploadDocument,
} from '../api/documents'
import type { DocumentItem, Scope } from '../api/types'
import AppIcon from '../components/AppIcon.vue'
import FileTypeBadge from '../components/FileTypeBadge.vue'
import ShareDialog from '../components/ShareDialog.vue'
import { m, translated } from '../i18n'
import { saveBlob } from '../utils/download'
import {
  ACCESS_LABEL,
  STATUS_LABEL,
  formatSize,
  formatTime,
  formatType,
  isInProgress,
} from '../utils/format'

// 有文档还在处理时，每隔这么久刷新一次列表，让状态自己变成“处理成功”或“处理失败”
const REFRESH_INTERVAL_MS = 5000
// 与后端允许的类型一致（docs/api.md §1.2）。只是帮用户在选择文件时过滤一下，
// 真正的类型检查在后端按文件内容进行（拖进来的文件不经过这个过滤，由后端拒绝）。
const ACCEPT = '.pdf,.docx,.xlsx,.png,.jpg,.jpeg'

const documents = ref<DocumentItem[]>([])
const total = ref(0)
const loading = ref(false)
// 列表没加载出来时在页面里显示原因（T24s：页面数据加载失败统一用页内提示，
// 删除、下载这类操作的结果仍用弹出消息）。自动刷新失败也要说出来，不能让列表悄悄停在旧状态
const loadError = ref<{ silent: boolean; message: string } | null>(null)
const query = reactive<{ page: number; page_size: number; scope: Scope | '' }>({
  page: 1,
  page_size: 20,
  scope: '',
})
const sharing = ref<DocumentItem | null>(null)
const fileInput = ref<HTMLInputElement>()
const dragActive = ref(false)

const inProgressCount = computed(() => documents.value.filter((d) => isInProgress(d.status)).length)

let refreshTimer: ReturnType<typeof setTimeout> | undefined

async function load(options: { silent?: boolean } = {}) {
  clearTimeout(refreshTimer)
  if (!options.silent) loading.value = true
  try {
    const page = await listDocuments({
      page: query.page,
      page_size: query.page_size,
      scope: query.scope || undefined,
    })
    documents.value = page.items
    total.value = page.total
    loadError.value = null
    // 删掉本页最后一条后，这一页可能空了：退回上一页
    if (page.items.length === 0 && page.total > 0 && query.page > 1) {
      query.page -= 1
      await load(options)
      return
    }
  } catch (error) {
    loadError.value = { silent: options.silent === true, message: errorMessage(error) }
  } finally {
    loading.value = false
  }
  if (documents.value.some((d) => isInProgress(d.status))) {
    refreshTimer = setTimeout(() => void load({ silent: true }), REFRESH_INTERVAL_MS)
  }
}

function onFilterChange() {
  query.page = 1
  void load()
}

// ---- 上传：选择或拖进来的文件排成一队，逐个上传，每个文件的结果留在页面上 ----

type UploadState = 'waiting' | 'uploading' | 'done' | 'failed'

interface UploadItem {
  id: number
  file: File
  state: UploadState
  message: string
}

const UPLOAD_STATE: Record<UploadState, { text: string; type: 'info' | 'primary' | 'success' | 'danger' }> = translated(
  (msg) => ({
    waiting: { text: msg.documents.uploadState.waiting, type: 'info' },
    uploading: { text: msg.documents.uploadState.uploading, type: 'primary' },
    done: { text: msg.documents.uploadState.done, type: 'success' },
    failed: { text: msg.documents.uploadState.failed, type: 'danger' },
  }),
)

const uploads = ref<UploadItem[]>([])
const uploading = computed(() => uploads.value.some((u) => u.state === 'waiting' || u.state === 'uploading'))
const hasFinishedUploads = computed(() => uploads.value.some((u) => u.state === 'done' || u.state === 'failed'))
let nextUploadId = 0
let processing = false

function enqueue(files: File[]) {
  for (const file of files) uploads.value.push({ id: nextUploadId++, file, state: 'waiting', message: '' })
  void processQueue()
}

// 一次只传一个：保持上传顺序，也不让很多大文件同时占满带宽。
// 正在上传时又加进来的文件排在队尾，由同一个循环接着处理
async function processQueue() {
  if (processing) return
  processing = true
  let succeeded = 0
  try {
    for (;;) {
      const item = uploads.value.find((u) => u.state === 'waiting')
      if (!item) break
      item.state = 'uploading'
      try {
        await uploadDocument(item.file)
        item.state = 'done'
        succeeded += 1
      } catch (error) {
        item.state = 'failed'
        item.message = errorMessage(error)
      }
    }
  } finally {
    processing = false
  }
  if (succeeded > 0) {
    query.page = 1
    await load()
  }
}

function clearFinishedUploads() {
  uploads.value = uploads.value.filter((u) => u.state === 'waiting' || u.state === 'uploading')
}

function onFilesChosen(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  // 清空选择：否则再选同一个文件不会触发 change 事件
  input.value = ''
  if (files.length > 0) enqueue(files)
}

function onDragLeave(event: DragEvent) {
  // 移到拖放区里的子元素上也会触发 dragleave，只有真正离开拖放区才取消高亮
  const zone = event.currentTarget as HTMLElement
  if (!zone.contains(event.relatedTarget as Node | null)) dragActive.value = false
}

function onDrop(event: DragEvent) {
  dragActive.value = false
  const files = Array.from(event.dataTransfer?.files ?? [])
  if (files.length > 0) enqueue(files)
}

// ---- 单个文件的操作 ----

async function onDownload(document: DocumentItem) {
  try {
    saveBlob(await downloadDocument(document.id), document.filename)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function onDelete(document: DocumentItem) {
  try {
    await ElMessageBox.confirm(m().documents.confirmDelete(document.filename), m().documents.confirmDeleteTitle, {
      type: 'warning',
      confirmButtonText: m().documents.delete,
      cancelButtonText: m().documents.cancel,
    })
  } catch {
    return // 用户点了取消
  }
  try {
    await deleteDocument(document.id)
    ElMessage.success(m().documents.deleted)
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

/** 删除和共享只有 owner 和管理员能做（docs/api.md §1.1）；后端也会校验。 */
function canManage(document: DocumentItem): boolean {
  return document.access !== 'shared'
}

onMounted(() => void load())
onBeforeUnmount(() => clearTimeout(refreshTimer))
</script>

<template>
  <div class="page-head">
    <div>
      <h1 class="page-title">{{ m().documents.title }}</h1>
      <p class="page-desc">
        {{ m().documents.total(total) }}<template v-if="inProgressCount > 0">{{ m().documents.inProgress(inProgressCount) }}</template>
      </p>
    </div>
  </div>

  <div
    class="dropzone"
    :class="{ active: dragActive }"
    role="button"
    tabindex="0"
    @click="fileInput?.click()"
    @keydown.enter.prevent="fileInput?.click()"
    @keydown.space.prevent="fileInput?.click()"
    @dragenter.prevent="dragActive = true"
    @dragover.prevent="dragActive = true"
    @dragleave="onDragLeave"
    @drop.prevent="onDrop"
  >
    <AppIcon name="upload" :size="28" class="dropzone-icon" />
    <div class="dropzone-text">{{ m().documents.dropText }}<span class="dropzone-link">{{ m().documents.dropLink }}</span></div>
    <div class="dropzone-hint">{{ m().documents.dropHint }}</div>
  </div>
  <input ref="fileInput" type="file" multiple hidden :accept="ACCEPT" @change="onFilesChosen" />

  <div v-if="uploads.length > 0" class="uploads">
    <div class="uploads-head">
      <span>{{ m().documents.uploads }}<template v-if="uploading">{{ m().documents.uploadingNow }}</template></span>
      <el-button v-if="hasFinishedUploads" link type="primary" @click="clearFinishedUploads">{{ m().documents.clearFinished }}</el-button>
    </div>
    <div v-for="item in uploads" :key="item.id" class="upload-row">
      <span class="upload-name" :title="item.file.name">{{ item.file.name }}</span>
      <span class="upload-size">{{ formatSize(item.file.size) }}</span>
      <el-tag size="small" :type="UPLOAD_STATE[item.state].type">{{ UPLOAD_STATE[item.state].text }}</el-tag>
      <span v-if="item.message" class="upload-error">{{ item.message }}</span>
    </div>
  </div>

  <el-card shadow="never" class="list-card">
    <div class="toolbar">
      <el-radio-group v-model="query.scope" @change="onFilterChange">
        <el-radio-button value="">{{ m().documents.scope.all }}</el-radio-button>
        <el-radio-button value="mine">{{ m().documents.scope.mine }}</el-radio-button>
        <el-radio-button value="shared">{{ m().documents.scope.shared }}</el-radio-button>
      </el-radio-group>
      <el-button @click="load()">{{ m().documents.refresh }}</el-button>
    </div>

    <el-alert
      v-if="loadError"
      type="error"
      :title="loadError.silent ? m().documents.loadErrorSilent : m().documents.loadErrorTitle"
      :description="m().documents.loadErrorDesc(loadError.message)"
      show-icon
      :closable="false"
      class="notice"
    />

    <el-table v-loading="loading" :data="documents">
      <template #empty>
        <div class="table-empty">
          <template v-if="loadError">{{ m().documents.emptyError }}</template>
          <template v-else-if="query.scope === 'shared'">{{ m().documents.emptyShared }}</template>
          <template v-else>{{ m().documents.empty }}</template>
        </div>
      </template>
      <!-- 不用 show-overflow-tooltip：它把整格压成一行，标签会和文件名一起被省略号截掉（T24n）。
           文件名自己省略、悬停看全名；标签放不下时换到下一行。
           类型、上传者、来源合并成文件名下面的一行小字（T24s），表格从 8 列减到 5 列 -->
      <el-table-column :label="m().documents.col.name" min-width="300">
        <template #default="{ row }: { row: DocumentItem }">
          <div class="doc-cell">
            <FileTypeBadge :mime-type="row.mime_type" />
            <div class="doc-main">
              <div class="doc-name">
                <span class="doc-filename" :title="row.filename">{{ row.filename }}</span>
                <el-tag v-for="tag in row.tags" :key="tag" size="small" class="doc-tag" :title="tag">{{ tag }}</el-tag>
              </div>
              <div class="doc-sub">
                {{ formatType(row.mime_type) }} · {{ m().documents.uploader(row.owner.username) }} · {{ ACCESS_LABEL[row.access] }}
              </div>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column :label="m().documents.col.status" width="110">
        <template #default="{ row }: { row: DocumentItem }">
          <el-tag :type="STATUS_LABEL[row.status].type">{{ STATUS_LABEL[row.status].text }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column :label="m().documents.col.size" width="100">
        <template #default="{ row }: { row: DocumentItem }">{{ formatSize(row.size_bytes) }}</template>
      </el-table-column>
      <el-table-column :label="m().documents.col.created" width="150">
        <template #default="{ row }: { row: DocumentItem }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column :label="m().documents.col.actions" width="210" fixed="right">
        <template #default="{ row }: { row: DocumentItem }">
          <el-button link type="primary" @click="$router.push({ name: 'preview', params: { id: row.id } })">{{ m().documents.view }}</el-button>
          <el-button link type="primary" @click="onDownload(row)">{{ m().documents.download }}</el-button>
          <template v-if="canManage(row)">
            <el-button link type="primary" @click="sharing = row">{{ m().documents.share }}</el-button>
            <el-button link type="danger" @click="onDelete(row)">{{ m().documents.delete }}</el-button>
          </template>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-model:current-page="query.page"
      v-model:page-size="query.page_size"
      class="pagination"
      layout="total, sizes, prev, pager, next"
      :total="total"
      :page-sizes="[10, 20, 50, 100]"
      @current-change="load()"
      @size-change="onFilterChange"
    />
  </el-card>

  <ShareDialog :document="sharing" @close="sharing = null" />
</template>

<style scoped>
.dropzone {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 22px 16px;
  border: 1px dashed var(--el-border-color);
  border-radius: var(--app-radius-lg);
  background: var(--app-surface);
  color: var(--app-text-regular);
  text-align: center;
  cursor: pointer;
  transition: border-color 0.15s, background-color 0.15s;
}

.dropzone:hover,
.dropzone:focus-visible,
.dropzone.active {
  border-color: var(--app-primary);
  background: var(--app-primary-soft);
  outline: none;
}

.dropzone-icon {
  color: var(--app-primary);
}

.dropzone-link {
  color: var(--app-primary);
}

.dropzone-hint {
  color: var(--app-text-secondary);
  font-size: 12px;
}

.uploads {
  margin-top: 12px;
  padding: 8px 14px;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius);
  background: var(--app-surface);
  font-size: 13px;
}

.uploads-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 28px;
  color: var(--app-text-secondary);
}

.upload-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 12px;
  padding: 6px 0;
  border-top: 1px solid var(--app-border);
}

.upload-name {
  flex: 1;
  min-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.upload-size {
  color: var(--app-text-secondary);
}

.upload-error {
  flex-basis: 100%;
  color: var(--el-color-danger);
  font-size: 12px;
}

.list-card {
  margin-top: 16px;
  border-radius: var(--app-radius-lg);
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.notice {
  margin-bottom: 12px;
}

.table-empty {
  padding: 24px 0;
  color: var(--app-text-secondary);
  line-height: 1.6;
}

.doc-cell {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.doc-main {
  min-width: 0;
}

.doc-name {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 6px;
  min-width: 0;
}

.doc-filename {
  max-width: 100%;
  overflow: hidden;
  color: var(--app-text);
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 很长的标签也不撑破单元格 */
.doc-tag {
  max-width: 100%;
}

.doc-tag :deep(.el-tag__content) {
  overflow: hidden;
  text-overflow: ellipsis;
}

.doc-sub {
  margin-top: 2px;
  color: var(--app-text-secondary);
  font-size: 12px;
}

.pagination {
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
