<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { ref, watch } from 'vue'

import { errorMessage } from '../api/client'
import { addShare, listShares, removeShare } from '../api/documents'
import type { DocumentItem, Share } from '../api/types'
import { m } from '../i18n'
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
    ElMessage.success(m().share.added(name))
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
    ElMessage.success(m().share.removed(share.user.username))
    await load(props.document.id)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}
</script>

<template>
  <el-dialog
    :model-value="document !== null"
    :title="document ? m().share.title(document.filename) : ''"
    width="min(520px, 92vw)"
    @close="emit('close')"
  >
    <p class="share-hint">{{ m().share.hint }}</p>
    <el-form class="share-add" @submit.prevent="onAdd">
      <el-input v-model="username" :placeholder="m().share.placeholder" />
      <el-button type="primary" native-type="submit" :loading="adding" :disabled="!username.trim()">
        {{ m().share.submit }}
      </el-button>
    </el-form>
    <el-table v-loading="loading" :data="shares" :empty-text="m().share.empty">
      <el-table-column :label="m().share.colUser" prop="user.username" />
      <el-table-column :label="m().share.colTime">
        <template #default="{ row }: { row: Share }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column :label="m().share.colActions" width="100">
        <template #default="{ row }: { row: Share }">
          <el-button link type="danger" @click="onRemove(row)">{{ m().share.remove }}</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-dialog>
</template>

<style scoped>
.share-hint {
  margin: 0 0 12px;
  color: var(--app-text-regular);
  font-size: 13px;
}

.share-add {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
</style>
