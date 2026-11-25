<script setup lang="ts">
// 检索页（T24s 重新排版）：检索框下面是检索通道开关；每条结果右侧显示它在三个通道里的名次
// 和 RRF 融合分，让“多通道检索 + 融合”在页面上看得见（GLOBAL §4.4）。
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, errorMessage } from '../api/client'
import { downloadDocument } from '../api/documents'
import { fetchHealth } from '../api/health'
import { search } from '../api/search'
import type { ChannelStatus, SearchHit } from '../api/types'
import FileTypeBadge from '../components/FileTypeBadge.vue'
import { m } from '../i18n'
import {
  buildSearchRequest,
  cellText,
  channelCells,
  channelStatusText,
  formatScore,
  isEmptySelection,
  selectionFromQuery,
  selectionToQuery,
} from '../utils/channels'
import { formatType, isImageType } from '../utils/format'
import {
  CHANNEL_LABEL,
  CHANNEL_SHORT_LABEL,
  degradedNotice,
  evidenceLabel,
  previewQuery,
} from '../utils/locator'
import { sanitizeSnippet } from '../utils/snippet'
import { ThumbnailLoader, type ThumbnailState } from '../utils/thumbnails'

const route = useRoute()
const router = useRouter()

const query = ref(typeof route.query.q === 'string' ? route.query.q : '')
// 四个开关、三个通道（utils/channels.ts）。图像通道默认关闭（与后端配置一致，D36）；
// 开关放进地址栏，刷新后保持
const selection = reactive(selectionFromQuery(route.query))
const noChannel = computed(() => isEmptySelection(selection))
const loading = ref(false)
// 三种结果要分开显示：还没搜、搜到了（可能为空）、检索服务出错
const hits = ref<SearchHit[] | null>(null)
const channels = ref<ChannelStatus[]>([])
const tookMs = ref(0)
const failure = ref<{ unavailable: boolean; message: string } | null>(null)

/** 本应执行却失败的通道（例如 CLIP 服务没启动时的图像通道），如实告诉用户。 */
const degraded = computed(() => channels.value.filter((c) => c.status === 'unavailable'))

// ---- CLIP 服务状态：进入页面时查一次 /health，图像通道检索成功时也说明它在线 ----

type ClipState = 'checking' | 'ok' | 'unavailable' | 'unknown'

const clip = ref<ClipState>('checking')

async function checkClip() {
  try {
    clip.value = (await fetchHealth()).clip_service.status
  } catch {
    clip.value = 'unknown'
  }
}

function updateClipFrom(statuses: ChannelStatus[]) {
  const image = statuses.find((c) => c.channel === 'image')
  if (image?.status === 'ok') clip.value = 'ok'
  // 图像通道不可用不一定是 CLIP 服务的问题（也可能是向量索引），重新查一次健康检查
  else if (image?.status === 'unavailable') void checkClip()
}

// ---- 图片结果的缩略图：document_id → 状态 ----

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

// ---- 检索 ----

// 检索进行中又改了开关：等这次返回后按新的开关再查一次
let rerun = false

async function onSearch() {
  const text = query.value.trim()
  // 上一次检索还没返回时不再发新的（在输入框里连按回车）：两个应答谁后到谁显示，结果会错位
  if (!text || noChannel.value || loading.value) return
  // 检索词和通道开关放进地址栏：刷新页面或从预览页返回时结果还在
  const ch = selectionToQuery(selection)
  if (route.query.q !== text || route.query.ch !== ch || route.query.img !== undefined) {
    void router.replace({ query: { q: text, ch } })
  }

  loading.value = true
  failure.value = null
  try {
    const response = await search(buildSearchRequest(text, selection))
    hits.value = response.hits
    channels.value = response.channels
    tookMs.value = response.took_ms
    updateClipFrom(response.channels)
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
    if (rerun) {
      rerun = false
      void onSearch()
    }
  }
}

// 改动开关后自动重新检索：同一个查询换一组通道马上能对照（便于演示消融对照）。
// 还没检索过时不自动发请求
watch(selection, () => {
  if (hits.value === null && failure.value === null) return
  if (loading.value) rerun = true
  else void onSearch()
})

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
  void checkClip()
  if (query.value) void onSearch()
})

onBeforeUnmount(clearThumbnails)
</script>

<template>
  <div class="page-head">
    <div>
      <h1 class="page-title">{{ m().search.title }}</h1>
      <p class="page-desc">{{ m().search.desc }}</p>
    </div>
  </div>

  <el-card shadow="never" class="search-card">
    <form class="search-bar" @submit.prevent="onSearch">
      <el-input
        v-model="query"
        size="large"
        clearable
        :placeholder="m().search.placeholder"
        maxlength="256"
      />
      <el-button type="primary" size="large" native-type="submit" :loading="loading">{{ m().search.submit }}</el-button>
    </form>

    <div class="channels" role="group" :aria-label="m().search.channelsAria">
      <div class="channel-group">
        <span class="group-label">{{ m().search.groupMeta }}</span>
        <div class="group-items">
          <el-checkbox v-model="selection.meta" border>{{ m().search.optMeta }}</el-checkbox>
        </div>
      </div>
      <div class="channel-group">
        <span class="group-label">{{ m().search.groupText }}</span>
        <div class="group-items">
          <el-checkbox v-model="selection.body" border>{{ m().search.optBody }}</el-checkbox>
          <el-checkbox v-model="selection.ocr" border>{{ m().search.optOcr }}</el-checkbox>
        </div>
      </div>
      <div class="channel-group">
        <span class="group-label">{{ m().search.groupImage }}</span>
        <div class="group-items">
          <el-checkbox v-model="selection.image" border>{{ m().search.optImage }}</el-checkbox>
          <span class="clip-state" :class="`clip-${clip}`">{{ m().search.clip[clip] }}</span>
        </div>
      </div>
    </div>
    <p v-if="noChannel" class="channels-error">{{ m().search.noChannel }}</p>
    <p v-else class="channels-hint">{{ m().search.channelsHint }}</p>
  </el-card>

  <el-alert
    v-if="failure"
    :type="failure.unavailable ? 'error' : 'warning'"
    :title="failure.unavailable ? m().search.unavailableTitle : m().search.failedTitle"
    :description="failure.unavailable ? m().search.unavailableDesc : failure.message"
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

  <div v-loading="loading" class="results">
    <div v-if="hits === null && failure === null && !loading" class="guide">
      <p class="guide-title">{{ m().search.guideTitle }}</p>
      <ul class="guide-list">
        <li v-for="line in m().search.guide" :key="line">{{ line }}</li>
      </ul>
      <p class="guide-foot">{{ m().search.guideFoot }}</p>
    </div>

    <template v-else-if="hits !== null">
      <p class="summary">
        <span>{{ m().search.summary(hits.length, tookMs) }}</span>
        <span v-for="c in channels" :key="c.channel">{{ CHANNEL_LABEL[c.channel] }}：{{ channelStatusText(c) }}</span>
      </p>
      <el-empty v-if="hits.length === 0" :description="m().search.empty" />
      <ul v-else class="hits">
        <li v-for="(hit, index) in hits" :key="hit.document.id" class="hit">
          <span class="hit-rank">{{ index + 1 }}</span>
          <div
            v-if="thumbnails[hit.document.id]"
            class="hit-thumb"
            :title="m().search.open(hit.document.filename)"
            @click="open(hit)"
          >
            <img v-if="thumbUrl(hit.document.id)" :src="thumbUrl(hit.document.id)" :alt="hit.document.filename" />
            <span v-else-if="thumbnails[hit.document.id].status === 'loading'" class="thumb-note">{{ m().search.thumbLoading }}</span>
            <span v-else-if="thumbnails[hit.document.id].status === 'skipped'" class="thumb-note">{{ m().search.thumbLarge1 }}<br />{{ m().search.thumbLarge2 }}</span>
            <span v-else class="thumb-note">{{ m().search.thumbError }}</span>
          </div>
          <FileTypeBadge v-else :mime-type="hit.document.mime_type" size="large" class="hit-badge" @click="open(hit)" />

          <div class="hit-body">
            <div class="hit-head">
              <el-link type="primary" class="hit-title" @click="open(hit)">{{ hit.document.filename }}</el-link>
              <span class="hit-type">{{ formatType(hit.document.mime_type) }}</span>
              <el-tag v-for="tag in hit.document.tags" :key="tag" size="small">{{ tag }}</el-tag>
            </div>
            <!-- 摘要经过白名单清洗，只保留 <em>（utils/snippet.ts）；高亮样式见 styles.css 的 .app-mark -->
            <p
              v-if="hit.evidence?.snippet"
              class="hit-snippet app-mark"
              v-html="sanitizeSnippet(hit.evidence.snippet)"
            />
            <div class="hit-meta">{{ evidenceLabel(hit.evidence) }}</div>
          </div>

          <div class="hit-fusion">
            <div class="cells">
              <div
                v-for="cell in channelCells(hit.channels, channels)"
                :key="cell.channel"
                class="cell"
                :class="`cell-${cell.state}`"
              >
                <span class="cell-label">{{ CHANNEL_SHORT_LABEL[cell.channel] }}</span>
                <span class="cell-value">{{ cellText(cell) }}</span>
              </div>
            </div>
            <div class="fused" :title="m().search.fusedTitle">
              {{ m().search.fused }}<strong>{{ formatScore(hit.score) }}</strong>
            </div>
          </div>
        </li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
.search-card {
  border-radius: var(--app-radius-lg);
}

.search-bar {
  display: flex;
  gap: 12px;
}

.channels {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 28px;
  margin-top: 16px;
}

.channel-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.group-label {
  color: var(--app-text-secondary);
  font-size: 12px;
}

.group-items {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

/* Element Plus 给相邻的带边框复选框加了外边距，这里统一用 gap 排开 */
.group-items .el-checkbox {
  margin: 0;
}

.clip-state {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--app-text-secondary);
  font-size: 12px;
}

.clip-state::before {
  content: '';
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--el-text-color-placeholder);
}

.clip-ok::before {
  background: var(--el-color-success);
}

.clip-unavailable {
  color: var(--el-color-danger);
}

.clip-unavailable::before {
  background: var(--el-color-danger);
}

.channels-hint,
.channels-error {
  margin: 12px 0 0;
  font-size: 12px;
}

.channels-hint {
  color: var(--app-text-secondary);
}

.channels-error {
  color: var(--el-color-danger);
}

.notice {
  margin-top: 12px;
}

.results {
  min-height: 120px;
  margin-top: 16px;
}

.guide {
  padding: 18px 24px;
  border: 1px dashed var(--el-border-color);
  border-radius: var(--app-radius-lg);
  background: var(--app-surface);
  color: var(--app-text-regular);
  font-size: 14px;
  line-height: 1.9;
}

.guide-title {
  margin: 0 0 4px;
  color: var(--app-text);
  font-size: 15px;
  font-weight: 600;
}

.guide-list {
  margin: 0;
  padding-left: 18px;
}

.guide-foot {
  margin: 6px 0 0;
  color: var(--app-text-secondary);
  font-size: 13px;
}

.summary {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 18px;
  margin: 0 0 12px;
  color: var(--app-text-secondary);
  font-size: 13px;
}

.hits {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.hit {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 14px 16px;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
  background: var(--app-surface);
}

.hit:hover {
  border-color: var(--el-border-color);
}

.hit-rank {
  flex: none;
  width: 20px;
  padding-top: 2px;
  color: var(--app-text-secondary);
  font-weight: 600;
  text-align: center;
}

/* 缩略图：原图由浏览器缩小显示，保持比例 */
.hit-thumb {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 72px;
  height: 72px;
  overflow: hidden;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius);
  background: var(--el-fill-color-light);
  cursor: pointer;
}

.hit-thumb img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.thumb-note {
  color: var(--app-text-secondary);
  font-size: 12px;
  text-align: center;
}

.hit-badge {
  cursor: pointer;
}

.hit-body {
  flex: 1;
  min-width: 0;
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
  color: var(--app-text-secondary);
  font-size: 13px;
}

.hit-snippet {
  margin: 6px 0;
  color: var(--app-text);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}

.hit-meta {
  margin-top: 4px;
  color: var(--app-text-secondary);
  font-size: 13px;
}

.hit-fusion {
  display: flex;
  flex: none;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
}

.cells {
  display: flex;
  gap: 6px;
}

.cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  width: 64px;
  padding: 5px 0;
  border-radius: 6px;
  background: var(--el-fill-color-light);
  color: var(--app-text-secondary);
  font-size: 12px;
}

.cell-label {
  font-size: 11px;
}

.cell-hit {
  background: var(--app-primary-soft);
  color: var(--app-primary);
}

.cell-hit .cell-value {
  font-weight: 600;
}

.cell-disabled {
  color: var(--el-text-color-placeholder);
}

.cell-unavailable {
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}

.fused {
  display: flex;
  align-items: baseline;
  gap: 6px;
  color: var(--app-text-secondary);
  font-size: 12px;
}

.fused strong {
  color: var(--app-text);
  font-size: 15px;
  font-variant-numeric: tabular-nums;
}

/* 窄屏：名次和融合分换到结果下面一行 */
@media (max-width: 900px) {
  .hit {
    flex-wrap: wrap;
  }

  .hit-fusion {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    padding-top: 10px;
    border-top: 1px solid var(--app-border);
  }
}

@media (max-width: 600px) {
  .search-bar {
    flex-direction: column;
  }
}
</style>
