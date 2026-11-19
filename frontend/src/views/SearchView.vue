<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, errorMessage } from '../api/client'
import { downloadDocument } from '../api/documents'
import { search } from '../api/search'
import type { ChannelStatus, SearchHit, SourceType } from '../api/types'
import { formatType, isImageType } from '../utils/format'
import {
  CHANNEL_LABEL,
  CHANNEL_TAG_TYPE,
  SOURCE_TYPE_LABEL,
  degradedNotice,
  evidenceLabel,
  previewQuery,
} from '../utils/locator'
import { sanitizeSnippet } from '../utils/snippet'
import { ThumbnailLoader, type ThumbnailState } from '../utils/thumbnails'

const route = useRoute()
const router = useRouter()

const query = ref(typeof route.query.q === 'string' ? route.query.q : '')
const sourceTypes = ref<SourceType[]>(['body', 'ocr'])
// 图像语义检索（CLIP）。默认关闭（与后端配置一致，D36）；开关放进地址栏，刷新后保持
const imageEnabled = ref(route.query.img === '1')
const loading = ref(false)
// 三种结果要分开显示：还没搜、搜到了（可能为空）、检索服务出错
const hits = ref<SearchHit[] | null>(null)
const channels = ref<ChannelStatus[]>([])
const tookMs = ref(0)
const failure = ref<{ unavailable: boolean; message: string } | null>(null)

/** 本应执行却失败的通道（例如 CLIP 服务没启动时的图像通道），如实告诉用户。 */
const degraded = computed(() => channels.value.filter((c) => c.status === 'unavailable'))

// 图片结果的缩略图：document_id → 状态
const thumbnails = reactive<Record<string, ThumbnailState>>({})
const loader = new ThumbnailLoader({
  download: downloadDocument,
  createUrl: (blob) => URL.createObjectURL(blob),
  revokeUrl: (url) => URL.revokeObjectURL(url),
  onChange: (id, state) => {
    thumbnails[id] = state
  },
})

function clearThumbnails() {
  loader.reset()
  for (const id of Object.keys(thumbnails)) delete thumbnails[id]
}

function thumbUrl(id: string): string | undefined {
  const state = thumbnails[id]
  return state?.status === 'ready' ? state.url : undefined
}

function loadThumbnails(results: SearchHit[]) {
  clearThumbnails()
  void loader.load(
    results
      .filter((hit) => isImageType(hit.document.mime_type))
      .map((hit) => ({ id: hit.document.id, sizeBytes: hit.document.size_bytes })),
  )
}

async function onSearch() {
  const text = query.value.trim()
  // 上一次检索还没返回时不再发新的（在输入框里连按回车）：两个应答谁后到谁显示，结果会错位
  if (!text || loading.value) return
  // 检索词放进地址栏：刷新页面或从预览页返回时结果还在
  const img = imageEnabled.value ? '1' : undefined
  if (route.query.q !== text || route.query.img !== img) {
    void router.replace({ query: { q: text, img } })
  }

  loading.value = true
  failure.value = null
  try {
    const response = await search({
      query: text,
      source_types: sourceTypes.value.length > 0 ? sourceTypes.value : undefined,
      channels: { image: imageEnabled.value },
    })
    hits.value = response.hits
    channels.value = response.channels
    tookMs.value = response.took_ms
    loadThumbnails(response.hits)
  } catch (error) {
    clearThumbnails()
    hits.value = null
    channels.value = []
    failure.value = {
      unavailable: error instanceof ApiError && error.code === 'SEARCH_UNAVAILABLE',
      message: errorMessage(error),
    }
  } finally {
    loading.value = false
  }
}

function open(hit: SearchHit) {
  void router.push({
    name: 'preview',
    params: { id: hit.document.id },
    query: {
      ...previewQuery(hit.evidence?.locator ?? null, hit.evidence?.chunk_id ?? null),
      q: query.value.trim(),
    },
  })
}

onMounted(() => {
  if (query.value) void onSearch()
})

onBeforeUnmount(clearThumbnails)
</script>

<template>
  <el-card>
    <form class="search-bar" @submit.prevent="onSearch">
      <el-input
        v-model="query"
        size="large"
        clearable
        placeholder="输入关键词，检索文件名、标签、正文和图片中识别出的文字；开启图像语义检索后也可以描述图片内容"
        maxlength="256"
      />
      <el-button type="primary" size="large" native-type="submit" :loading="loading">检索</el-button>
    </form>
    <div class="search-options">
      <span class="option-label">正文范围</span>
      <el-checkbox-group v-model="sourceTypes">
        <el-checkbox value="body">{{ SOURCE_TYPE_LABEL.body }}</el-checkbox>
        <el-checkbox value="ocr">{{ SOURCE_TYPE_LABEL.ocr }}</el-checkbox>
      </el-checkbox-group>
      <el-checkbox v-model="imageEnabled" class="image-switch">图像语义检索（CLIP）</el-checkbox>
    </div>

    <el-alert
      v-if="failure"
      :type="failure.unavailable ? 'error' : 'warning'"
      :title="failure.unavailable ? '检索服务暂时不可用' : '检索失败'"
      :description="failure.unavailable ? '这不是“没有搜到”：检索服务出了故障，请稍后重试。' : failure.message"
      show-icon
      :closable="false"
      class="notice"
    />

    <el-alert
      v-for="channel in degraded"
      :key="channel.channel"
      type="warning"
      :title="degradedNotice(channel)"
      show-icon
      :closable="false"
      class="notice"
    />

    <div v-loading="loading">
      <template v-if="hits !== null">
        <p class="summary">共 {{ hits.length }} 个文件，用时 {{ tookMs }} 毫秒</p>
        <el-empty v-if="hits.length === 0" description="没有找到匹配的文件" />
        <ul class="hits">
          <li v-for="hit in hits" :key="hit.document.id" class="hit">
            <div
              v-if="thumbnails[hit.document.id]"
              class="hit-thumb"
              :title="`打开 ${hit.document.filename}`"
              @click="open(hit)"
            >
              <img v-if="thumbUrl(hit.document.id)" :src="thumbUrl(hit.document.id)" :alt="hit.document.filename" />
              <span v-else-if="thumbnails[hit.document.id].status === 'loading'" class="thumb-note">加载中</span>
              <span v-else-if="thumbnails[hit.document.id].status === 'skipped'" class="thumb-note">图片较大<br />点击查看</span>
              <span v-else class="thumb-note">无法显示</span>
            </div>
            <div class="hit-body">
              <div class="hit-head">
                <el-link type="primary" class="hit-title" @click="open(hit)">{{ hit.document.filename }}</el-link>
                <span class="hit-type">{{ formatType(hit.document.mime_type) }}</span>
                <el-tag v-for="tag in hit.document.tags" :key="tag" size="small" class="hit-tag">{{ tag }}</el-tag>
              </div>
              <!-- 摘要经过白名单清洗，只保留 <em>（utils/snippet.ts） -->
              <p
                v-if="hit.evidence?.snippet"
                class="hit-snippet"
                v-html="sanitizeSnippet(hit.evidence.snippet)"
              />
              <div class="hit-meta">
                <span>{{ evidenceLabel(hit.evidence) }}</span>
                <span class="hit-channels">
                  命中：
                  <el-tag
                    v-for="c in hit.channels"
                    :key="c.channel"
                    size="small"
                    effect="plain"
                    :type="CHANNEL_TAG_TYPE[c.channel]"
                    class="hit-tag"
                  >
                    {{ CHANNEL_LABEL[c.channel] }} 第 {{ c.rank }} 名
                  </el-tag>
                </span>
              </div>
            </div>
          </li>
        </ul>
      </template>
    </div>
  </el-card>
</template>

<style scoped>
.search-bar {
  display: flex;
  gap: 12px;
}

.search-options {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 12px 0 4px;
}

.option-label {
  color: #606266;
  font-size: 14px;
}

.notice {
  margin-top: 12px;
}

.summary {
  color: #909399;
  font-size: 13px;
}

.hits {
  list-style: none;
  margin: 0;
  padding: 0;
}

.hit {
  display: flex;
  gap: 14px;
  padding: 14px 0;
  border-bottom: 1px solid #ebeef5;
}

.hit-body {
  flex: 1;
  min-width: 0;
}

.image-switch {
  margin-left: 12px;
}

/* 缩略图：原图由浏览器缩小显示，保持比例 */
.hit-thumb {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 96px;
  height: 96px;
  overflow: hidden;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  background: #f5f7fa;
  cursor: pointer;
}

.hit-thumb img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.thumb-note {
  color: #909399;
  font-size: 12px;
  text-align: center;
}

.hit-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.hit-title {
  font-size: 16px;
}

.hit-type {
  color: #909399;
  font-size: 13px;
}

.hit-snippet {
  margin: 8px 0;
  color: #303133;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}

.hit-snippet :deep(em) {
  color: #f56c6c;
  font-style: normal;
}

.hit-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  color: #909399;
  font-size: 13px;
}

.hit-tag {
  margin-left: 4px;
}
</style>
