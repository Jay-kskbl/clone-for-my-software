<script setup lang="ts">
// 动效演示页（/motion-lab，只在克隆库里，不需要登录和后端）：用模拟的搜索请求走一遍
// 快速返回、慢速返回、报错、超时、连续搜索，供自测和设计走查。不是正式功能。
import 'element-plus/theme-chalk/dark/css-vars.css'

import { onBeforeUnmount, onMounted, ref } from 'vue'

import { controlsFrom, type ScanLoaderHandle } from '../scan-loader/handle'
import AppIcon from '../../../components/AppIcon.vue'
import { resetLaunchPlayed } from '../launch/playOnce'
import { useLaunchAnimation } from '../launch/useLaunchAnimation'
import IdleLabPanel from './IdleLabPanel.vue'
import ScanLoader from '../scan-loader/ScanLoader.vue'
import { createSearchSession, SearchTimeoutError } from '../scan-loader/searchSession'
import type { ScanPhase } from '../scan-loader/machine'
import { SEARCH_TEXT } from '../messages'
import { activeFrameCount } from '../shared/canvas'
import { prefersReducedMotion, setReducedMotionOverride } from '../shared/reducedMotion'

interface MockHit {
  title: string
  snippet: string
}

type Mode = 'fast' | 'slow' | 'error' | 'hang'

const MODE_DELAY: Record<Mode, number> = { fast: 300, slow: 5000, error: 1500, hang: Infinity }
// 演示用 8 秒超时，正式检索为 30 秒（DEFAULT_SEARCH_TIMEOUT_MS）
const LAB_TIMEOUT_MS = 8000

const mode = ref<Mode>('fast')
const query = ref('')
const PLACEHOLDER = '输入关键词，或描述想找的图片'
const input = ref<{ $el?: unknown } | null>(null)
useLaunchAnimation(input, {
  placeholder: PLACEHOLDER,
  hasValue: () => query.value !== '',
  onFinish: (reason) => note(`启动动画结束：${reason}`),
})
const results = ref<MockHit[] | null>(null)
const failure = ref<string | null>(null)
const phase = ref<ScanPhase>('idle')
const log = ref<string[]>([])
const frames = ref(0)
const reducedChoice = ref<'system' | 'on' | 'off'>('system')
const dark = ref(document.documentElement.classList.contains('dark'))

function note(text: string) {
  const time = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  log.value = [`${time} ${text}`, ...log.value].slice(0, 12)
}

function mockSearch(text: string, which: Mode, signal: AbortSignal): Promise<MockHit[]> {
  return new Promise((resolve, reject) => {
    const abort = () => {
      clearTimeout(timer)
      reject(new DOMException('aborted', 'AbortError'))
    }
    const timer =
      MODE_DELAY[which] === Infinity
        ? undefined
        : setTimeout(() => {
            signal.removeEventListener('abort', abort)
            if (which === 'error') reject(new Error('模拟的接口错误（HTTP 503）'))
            else
              resolve(
                Array.from({ length: 3 }, (_, i) => ({
                  title: `《${text}》示例文件 ${i + 1}.pdf`,
                  snippet: `模拟结果，返回耗时 ${MODE_DELAY[which]} 毫秒。`,
                })),
              )
          }, MODE_DELAY[which])
    signal.addEventListener('abort', abort, { once: true })
  })
}

const loader = ref<ScanLoaderHandle | null>(null)
const session = createSearchSession<MockHit[]>(
  controlsFrom(() => loader.value),
  {
    timeoutMs: LAB_TIMEOUT_MS,
    onError: (error) => {
      const message = error instanceof SearchTimeoutError ? SEARCH_TEXT.timeout(error.timeoutMs / 1000) : String(error)
      failure.value = message
      note(`失败：${message}`)
      return undefined
    },
  },
)

let seq = 0
function onSearch(which: Mode = mode.value) {
  const n = ++seq
  results.value = null
  failure.value = null
  note(`第 ${n} 次检索（${which}）开始`)
  void session.run((signal) => mockSearch(`${query.value || '示例'}#${n}`, which, signal))
}

function onRapid() {
  onSearch('slow')
  setTimeout(() => onSearch('fast'), 400)
}

function onDone(value: unknown) {
  const hits = value as MockHit[]
  results.value = hits
  note(`结果已显示：${hits[0]?.title ?? '空'}`)
}

function onPhase(value: ScanPhase) {
  phase.value = value
}

function setReduced(value: 'system' | 'on' | 'off') {
  reducedChoice.value = value
  setReducedMotionOverride(value === 'system' ? null : value === 'on')
}

function replayLaunch() {
  resetLaunchPlayed()
  location.reload()
}

function toggleDark() {
  dark.value = !dark.value
  document.documentElement.classList.toggle('dark', dark.value)
}

let poll: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  poll = setInterval(() => (frames.value = activeFrameCount()), 300)
})
onBeforeUnmount(() => {
  clearInterval(poll)
  session.cancel()
  setReducedMotionOverride(null)
})
</script>

<template>
  <div class="lab">
    <header class="lab-head">
      <h1 class="page-title">搜索动效演示</h1>
      <p class="page-desc">克隆库专用自测页：模拟请求，不连后端。</p>
      <div class="lab-tools">
        <el-button size="small" data-test="replay" @click="replayLaunch">重播启动动画（刷新）</el-button>
        <el-button size="small" @click="toggleDark">{{ dark ? '切到浅色' : '切到暗色' }}</el-button>
        <el-radio-group :model-value="reducedChoice" size="small" @change="(v: unknown) => setReduced(v as 'system' | 'on' | 'off')">
          <el-radio-button value="system">减少动效：跟随系统（{{ prefersReducedMotion() ? '开' : '关' }}）</el-radio-button>
          <el-radio-button value="on">强制开</el-radio-button>
          <el-radio-button value="off">强制关</el-radio-button>
        </el-radio-group>
        <span class="lab-stat" data-test="frames">rAF 登记数：{{ frames }}</span>
        <span class="lab-stat" data-test="phase">扫描状态：{{ phase }}</span>
      </div>
    </header>

    <el-card shadow="never" class="lab-card">
      <form class="lab-bar" @submit.prevent="onSearch()">
        <el-input ref="input" v-model="query" size="large" class="sm-launch-target lab-input" :placeholder="PLACEHOLDER">
          <template #prefix><AppIcon name="search" /></template>
        </el-input>
        <el-button type="primary" size="large" round native-type="submit">检索</el-button>
      </form>
      <div class="lab-modes">
        <el-radio-group v-model="mode" size="small">
          <el-radio-button value="fast">快速返回 0.3 s</el-radio-button>
          <el-radio-button value="slow">慢速返回 5 s</el-radio-button>
          <el-radio-button value="error">报错 1.5 s</el-radio-button>
          <el-radio-button value="hang">不返回（{{ LAB_TIMEOUT_MS / 1000 }} s 超时）</el-radio-button>
        </el-radio-group>
        <el-button size="small" data-test="rapid" @click="onRapid">连续搜索（慢 → 0.4 s 后快）</el-button>
        <el-button size="small" @click="session.cancel()">取消</el-button>
      </div>
    </el-card>

    <section class="lab-results">
      <ScanLoader ref="loader" retryable @done="onDone" @phase="onPhase" @retry="onSearch()" />
      <el-alert v-if="failure" type="warning" :title="failure" :closable="false" show-icon class="lab-alert" />
      <ul v-if="results && phase === 'done'" class="lab-hits">
        <li v-for="hit in results" :key="hit.title" class="lab-hit">
          <strong>{{ hit.title }}</strong>
          <span>{{ hit.snippet }}</span>
        </li>
      </ul>
    </section>

    <IdleLabPanel @log="note" />

    <section class="lab-log">
      <h2>事件</h2>
      <ol>
        <li v-for="line in log" :key="line">{{ line }}</li>
      </ol>
    </section>
  </div>
</template>

<style scoped>
.lab {
  box-sizing: border-box;
  max-width: 1000px;
  min-height: 100vh;
  margin: 0 auto;
  padding: 24px 16px 48px;
}

.lab-tools,
.lab-modes {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  margin-top: 12px;
}

.lab-stat {
  color: var(--app-text-regular);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.lab-card {
  margin-top: 16px;
  border-radius: var(--app-radius-lg);
}

.lab-bar {
  display: flex;
  gap: 12px;
}

.lab-input :deep(.el-input__wrapper) {
  border-radius: 999px;
}

.lab-results {
  min-height: 140px;
  margin-top: 16px;
}

.lab-alert {
  margin-top: 12px;
}

.lab-hits {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
  animation: lab-in 0.3s cubic-bezier(0.33, 1, 0.68, 1);
}

.lab-hit {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
  background: var(--app-surface);
  color: var(--app-text);
}

.lab-hit span {
  color: var(--app-text-regular);
  font-size: 13px;
}

.lab-log {
  margin-top: 24px;
  color: var(--app-text-regular);
  font-size: 12px;
}

.lab-log h2 {
  margin: 0 0 6px;
  font-size: 14px;
}

@keyframes lab-in {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
}

@media (prefers-reduced-motion: reduce) {
  .lab-hits {
    animation: none;
  }
}
</style>
