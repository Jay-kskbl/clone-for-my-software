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
import { STATUS_LABEL, formatType, isImageType } from '../utils/format'
import { type PreviewTab, initialPreviewTab } from '../utils/preview'

const PDF = 'application/pdf'
const OFFICE_NOTICE =
  'Word 和 Excel 只显示系统抽取出的文本，看不到原始格式、图表和公式；需要原样查看请下载原文件。'
const EXTRACTED_NOTICE =
  '这里是系统从文件中抽取的文字：PDF 有文字层的页直接取出文字，扫描页和图片是 OCR 识别的结果，可能有错字。'

const route = useRoute()
const router = useRouter()
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

// PDF、图片当前的标签页；两个标签页都是懒加载，第一次切过去时才加载
const tab = ref<PreviewTab>('file')

const kind = computed<'pdf' | 'image' | 'text' | null>(() => {
  if (!document.value) return null
  if (document.value.mime_type === PDF) return 'pdf'
  if (isImageType(document.value.mime_type)) return 'image'
  return 'text'
})

const emptyText = computed(() => {
  if (document.value?.status !== 'succeeded') return '文件还没有处理完成，暂时没有抽取文本'
  // PDF、图片解析成功后 OCR 仍在后台进行（文档状态只跟随解析，D27）
  return kind.value === 'text' ? '这个文件里没有抽取到文字' : '没有抽取到文字（扫描页和图片的 OCR 可能还在处理中）'
})

async function load() {
  try {
    document.value = await getDocument(id.value)
  } catch (error) {
    loadError.value = errorMessage(error)
    return
  }
  // Word、Excel 的抽取文本由 ExtractedText 自己加载
  if (kind.value !== 'pdf' && kind.value !== 'image') return
  tab.value = initialPreviewTab(kind.value, route.query)
  try {
    // 下载接口需要登录令牌，不能直接把地址交给 <img> 或 pdf.js，先取成字节
    const blob = await downloadDocument(id.value)
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

    <!-- 两个标签页都懒加载：PdfViewer 不在隐藏的标签页里先渲染（那时量不到容器宽度），
         抽取文本也只在第一次切过去时才请求 -->
    <el-tabs v-else-if="kind === 'pdf' || kind === 'image'" v-model="tab" @tab-change="onTabChange">
      <el-tab-pane label="原文件" name="file" lazy>
        <PdfViewer v-if="kind === 'pdf' && fileData" :data="fileData" :initial-page="initialPage" />
        <div v-else-if="kind === 'image' && imageUrl" class="image-box">
          <img :src="imageUrl" :alt="document?.filename" class="image" />
        </div>
        <div v-else v-loading="true" class="placeholder" />
      </el-tab-pane>
      <el-tab-pane label="抽取文本" name="text" lazy>
        <ExtractedText
          :document-id="id"
          :target-chunk="targetChunk"
          :terms="terms"
          :notice="EXTRACTED_NOTICE"
          :empty-text="emptyText"
        />
      </el-tab-pane>
    </el-tabs>

    <ExtractedText
      v-else-if="kind === 'text'"
      :document-id="id"
      :target-chunk="targetChunk"
      :terms="terms"
      :notice="OFFICE_NOTICE"
      :empty-text="emptyText"
    />

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
