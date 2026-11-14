<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { ref, watch } from 'vue'

import { errorMessage } from '../api/client'
import { addShare, listShares, removeShare } from '../api/documents'
import type { DocumentItem, Share } from '../api/types'
import { formatTime } from '../utils/format'

const props = defineProps<{ document: DocumentItem | null }>()
const emit = defineEmits<{ close: [] }>()

const shares = ref<Share[]>([])
const loading = ref(false)
const username = ref('')
const adding = ref(false)

async function load(documentId: string) {
  loading.value = true
  try {
    shares.value = await listShares(documentId)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    loading.value = false
  }
}

// 每次换一个文档打开对话框，都重新读取它的共享名单
watch(
  () => props.document,
  (document) => {
    shares.value = []
    username.value = ''
    if (document) void load(document.id)
  },
  { immediate: true },
)

async function onAdd() {
  const name = username.value.trim()
  if (!props.document || !name) return
  adding.value = true
  try {
    await addShare(props.document.id, name)
    username.value = ''
    ElMessage.success(`已共享给 ${name}`)
    await load(props.document.id)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    adding.value = false
  }
}

async function onRemove(share: Share) {
  if (!props.document) return
  try {
    await removeShare(props.document.id, share.user.id)
    ElMessage.success(`已取消对 ${share.user.username} 的共享`)
    await load(props.document.id)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}
</script>

<template>
  <el-dialog
    :model-value="document !== null"
    :title="document ? `共享：${document.filename}` : ''"
    width="520px"
    @close="emit('close')"
  >
    <p class="share-hint">被共享的用户可以查看、下载和检索这个文件，不能删除或再共享给别人。</p>
    <el-form class="share-add" @submit.prevent="onAdd">
      <el-input v-model="username" placeholder="输入对方的用户名" />
      <el-button type="primary" native-type="submit" :loading="adding" :disabled="!username.trim()">
        共享
      </el-button>
    </el-form>
    <el-table v-loading="loading" :data="shares" empty-text="还没有共享给任何人">
      <el-table-column label="用户" prop="user.username" />
      <el-table-column label="共享时间">
        <template #default="{ row }: { row: Share }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="100">
        <template #default="{ row }: { row: Share }">
          <el-button link type="danger" @click="onRemove(row)">取消共享</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-dialog>
</template>

<style scoped>
.share-hint {
  margin: 0 0 12px;
  color: #606266;
  font-size: 13px;
}

.share-add {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
</style>
