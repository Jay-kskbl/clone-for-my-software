<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, errorMessage } from '../api/client'
import { search } from '../api/search'
import type { ChannelStatus, SearchHit, SourceType } from '../api/types'
import { formatType } from '../utils/format'
import { CHANNEL_LABEL, SOURCE_TYPE_LABEL, formatLocator, previewQuery } from '../utils/locator'
import { sanitizeSnippet } from '../utils/snippet'

const route = useRoute()
const router = useRouter()

const query = ref(typeof route.query.q === 'string' ? route.query.q : '')
const sourceTypes = ref<SourceType[]>(['body', 'ocr'])
const loading = ref(false)
// 三种结果要分开显示：还没搜、搜到了（可能为空）、检索服务出错
const hits = ref<SearchHit[] | null>(null)
const channels = ref<ChannelStatus[]>([])
const tookMs = ref(0)
const failure = ref<{ unavailable: boolean; message: string } | null>(null)

/** 本应执行却失败的通道。图像通道尚未实现时也在这里，如实告诉用户。 */
const degraded = computed(() => channels.value.filter((c) => c.status === 'unavailable'))

async function onSearch() {
  const text = query.value.trim()
  if (!text) return
  // 检索词放进地址栏：刷新页面或从预览页返回时结果还在
  if (route.query.q !== text) void router.replace({ query: { q: text } })

  loading.value = true
  failure.value = null
  try {
    const response = await search({
      query: text,
      source_types: sourceTypes.value.length > 0 ? sourceTypes.value : undefined,
    })
    hits.value = response.hits
    channels.value = response.channels
    tookMs.value = response.took_ms
  } catch (error) {
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
</script>

<template>
  <el-card>
    <form class="search-bar" @submit.prevent="onSearch">
      <el-input
        v-model="query"
        size="large"
        clearable
        placeholder="输入关键词，检索文件名、标签、正文和图片中识别出的文字"
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
      type="info"
      :title="`${CHANNEL_LABEL[channel.channel]}通道未参与本次检索：${channel.detail ?? '不可用'}`"
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
              <span v-if="hit.evidence">
                位置：{{ formatLocator(hit.evidence.locator) }}
                <template v-if="hit.evidence.source_type">（{{ SOURCE_TYPE_LABEL[hit.evidence.source_type] }}）</template>
              </span>
              <span v-else>文件名或标签匹配</span>
              <span class="hit-channels">
                命中：
                <el-tag v-for="c in hit.channels" :key="c.channel" size="small" effect="plain" class="hit-tag">
                  {{ CHANNEL_LABEL[c.channel] }} 第 {{ c.rank }} 名
                </el-tag>
              </span>
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
  padding: 14px 0;
  border-bottom: 1px solid #ebeef5;
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
