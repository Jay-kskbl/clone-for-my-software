<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'

import { errorMessage } from '../api/client'
import {
  deleteDocument,
  downloadDocument,
  listDocuments,
  uploadDocument,
} from '../api/documents'
import type { DocumentItem, Scope } from '../api/types'
import ShareDialog from '../components/ShareDialog.vue'
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
// 真正的类型检查在后端按文件内容进行。
const ACCEPT = '.pdf,.docx,.xlsx,.png,.jpg,.jpeg'

const documents = ref<DocumentItem[]>([])
const total = ref(0)
const loading = ref(false)
const uploading = ref(false)
const query = reactive<{ page: number; page_size: number; scope: Scope | '' }>({
  page: 1,
  page_size: 20,
  scope: '',
})
const sharing = ref<DocumentItem | null>(null)
const fileInput = ref<HTMLInputElement>()

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
    // 删掉本页最后一条后，这一页可能空了：退回上一页
    if (page.items.length === 0 && page.total > 0 && query.page > 1) {
      query.page -= 1
      await load(options)
      return
    }
  } catch (error) {
    // 自动刷新失败时不打扰用户，下次手动操作时自然会看到错误
    if (!options.silent) ElMessage.error(errorMessage(error))
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

async function onFilesChosen(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  // 清空选择：否则再选同一个文件不会触发 change 事件
  input.value = ''
  if (files.length === 0) return

  uploading.value = true
  let succeeded = 0
  for (const file of files) {
    try {
      await uploadDocument(file)
      succeeded += 1
    } catch (error) {
      ElMessage.error(`${file.name}：${errorMessage(error)}`)
    }
  }
  uploading.value = false
  if (succeeded > 0) {
    ElMessage.success(`已上传 ${succeeded} 个文件，正在后台处理`)
    query.page = 1
    await load()
  }
}

async function onDownload(document: DocumentItem) {
  try {
    const blob = await downloadDocument(document.id)
    const url = URL.createObjectURL(blob)
    const link = window.document.createElement('a')
    link.href = url
    link.download = document.filename
    link.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function onDelete(document: DocumentItem) {
  try {
    await ElMessageBox.confirm(`确定删除“${document.filename}”吗？删除后无法恢复。`, '删除文件', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return // 用户点了取消
  }
  try {
    await deleteDocument(document.id)
    ElMessage.success('已删除')
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
  <el-card>
    <div class="toolbar">
      <div class="toolbar-left">
        <el-button type="primary" :loading="uploading" @click="fileInput?.click()">
          上传文件
        </el-button>
        <input
          ref="fileInput"
          type="file"
          multiple
          hidden
          :accept="ACCEPT"
          @change="onFilesChosen"
        />
        <span class="toolbar-hint">支持 PDF、Word（docx）、Excel（xlsx）、PNG、JPEG</span>
      </div>
      <div class="toolbar-right">
        <el-radio-group v-model="query.scope" @change="onFilterChange">
          <el-radio-button value="">全部</el-radio-button>
          <el-radio-button value="mine">我上传的</el-radio-button>
          <el-radio-button value="shared">共享给我的</el-radio-button>
        </el-radio-group>
        <el-button @click="load()">刷新</el-button>
      </div>
    </div>

    <el-table v-loading="loading" :data="documents" empty-text="还没有文件">
      <el-table-column label="文件名" min-width="220" show-overflow-tooltip>
        <template #default="{ row }: { row: DocumentItem }">
          {{ row.filename }}
          <el-tag v-for="tag in row.tags" :key="tag" size="small" class="doc-tag">{{ tag }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="120">
        <template #default="{ row }: { row: DocumentItem }">{{ formatType(row.mime_type) }}</template>
      </el-table-column>
      <el-table-column label="大小" width="100">
        <template #default="{ row }: { row: DocumentItem }">{{ formatSize(row.size_bytes) }}</template>
      </el-table-column>
      <el-table-column label="处理状态" width="110">
        <template #default="{ row }: { row: DocumentItem }">
          <el-tag :type="STATUS_LABEL[row.status].type">{{ STATUS_LABEL[row.status].text }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="上传者" width="120" prop="owner.username" show-overflow-tooltip />
      <el-table-column label="来源" width="110">
        <template #default="{ row }: { row: DocumentItem }">{{ ACCESS_LABEL[row.access] }}</template>
      </el-table-column>
      <el-table-column label="上传时间" width="150">
        <template #default="{ row }: { row: DocumentItem }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }: { row: DocumentItem }">
          <el-button link type="primary" @click="$router.push({ name: 'preview', params: { id: row.id } })">查看</el-button>
          <el-button link type="primary" @click="onDownload(row)">下载</el-button>
          <template v-if="canManage(row)">
            <el-button link type="primary" @click="sharing = row">共享</el-button>
            <el-button link type="danger" @click="onDelete(row)">删除</el-button>
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
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.toolbar-hint {
  color: #909399;
  font-size: 13px;
}

.doc-tag {
  margin-left: 6px;
}

.pagination {
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
