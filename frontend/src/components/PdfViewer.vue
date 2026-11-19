<script setup lang="ts">
// PDF 预览（附录 A16）：用 pdf.js 把一页画到 canvas 上，可以翻页、缩放，打开时跳到指定页。
// 只显示画面，不提供文字选择层：毕设只需要“看到命中的那一页”。
import { GlobalWorkerOptions, RenderingCancelledException, getDocument } from 'pdfjs-dist'
import type { PDFDocumentLoadingTask, PDFDocumentProxy, RenderTask } from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'

// 解析 PDF 的工作在单独的 Web Worker 里进行，不卡住页面。worker 文件由 Vite 一起打包
GlobalWorkerOptions.workerSrc = workerUrl

// PDF.js 不把 CMap、标准字体、WASM 解码器打进主包；中文 CID 字体需要 CMap，
// 复杂图片和颜色空间也需要对应的静态资源。资源由 public/pdfjs 随前端一起发布。
const PDFJS_ASSET_BASE = `${import.meta.env.BASE_URL}pdfjs/`

const props = defineProps<{
  data: ArrayBuffer
  initialPage?: number
}>()

const MIN_SCALE = 0.5
const MAX_SCALE = 3
const SCALE_STEP = 0.25

const canvas = ref<HTMLCanvasElement>()
const page = ref(1)
const pageCount = ref(0)
const scale = ref(1.25)
const loading = ref(true)
const error = ref<string | null>(null)

// shallowRef：pdf.js 的对象不需要也不应该被 Vue 做深层响应式代理
const pdf = shallowRef<PDFDocumentProxy | null>(null)
let loadingTask: PDFDocumentLoadingTask | null = null
let renderTask: RenderTask | null = null

// 每次绘制一个序号：连续翻页、缩放时会有几次绘制同时在等待，只有最新的一次真正去画
let renderSeq = 0

async function render() {
  if (!pdf.value || !canvas.value) return
  // 页码输入框被清空时 page 不是整数：等用户输完再画
  if (!Number.isInteger(page.value) || page.value < 1 || page.value > pageCount.value) return
  const seq = ++renderSeq
  const previous = renderTask
  try {
    // 上一次绘制还没完成：取消它，并等它真正停下、放开 canvas。pdf.js 不允许两次绘制
    // 同时使用同一个 canvas，不等的话后一次会报错，页面上就会误报“这一页无法显示”
    if (previous) {
      previous.cancel()
      await previous.promise.catch(() => undefined)
    }
    const pdfPage = await pdf.value.getPage(page.value)
    // 等待期间又有了更新的绘制请求：这一次作废
    if (seq !== renderSeq) return
    const viewport = pdfPage.getViewport({ scale: scale.value })
    // 高清屏上按设备像素比放大画布，否则文字发虚；显示尺寸仍按 CSS 像素
    const ratio = window.devicePixelRatio || 1
    const target = canvas.value
    target.width = Math.floor(viewport.width * ratio)
    target.height = Math.floor(viewport.height * ratio)
    target.style.width = `${Math.floor(viewport.width)}px`
    target.style.height = `${Math.floor(viewport.height)}px`

    const task = pdfPage.render({
      canvas: target,
      viewport,
      transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0],
    })
    renderTask = task
    await task.promise
    if (seq === renderSeq) error.value = null
  } catch (e) {
    // 被更新的绘制取消或取代的，不算失败
    if (e instanceof RenderingCancelledException || seq !== renderSeq) return
    error.value = '这一页无法显示，可以下载原文件查看'
  }
}

async function open() {
  try {
    // pdf.js 会把传入的数据转交给 worker，原来的 ArrayBuffer 随之失效；传一份副本，
    // 父组件手里的数据之后仍然可以用
    loadingTask = getDocument({
      data: new Uint8Array(props.data.slice(0)),
      cMapUrl: `${PDFJS_ASSET_BASE}cmaps/`,
      cMapPacked: true,
      standardFontDataUrl: `${PDFJS_ASSET_BASE}standard_fonts/`,
      wasmUrl: `${PDFJS_ASSET_BASE}wasm/`,
      iccUrl: `${PDFJS_ASSET_BASE}iccs/`,
    })
    pdf.value = await loadingTask.promise
    pageCount.value = pdf.value.numPages
    // 地址里的页码可能超出范围（例如文档被重新上传过）：夹到有效范围内
    page.value = Math.min(Math.max(props.initialPage ?? 1, 1), pageCount.value)
  } catch {
    error.value = 'PDF 无法打开，可以下载原文件查看'
  } finally {
    loading.value = false
  }
  await render()
}

function zoom(delta: number) {
  scale.value = Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale.value + delta))
}

watch([page, scale], () => void render())

onMounted(() => void open())
onBeforeUnmount(() => {
  renderTask?.cancel()
  // 释放 worker 和它占用的内存
  void loadingTask?.destroy()
})
</script>

<template>
  <div class="pdf-viewer">
    <div class="toolbar">
      <el-button :disabled="page <= 1" @click="page -= 1">上一页</el-button>
      <span class="page-input">
        第
        <el-input-number
          v-model="page"
          :min="1"
          :max="Math.max(pageCount, 1)"
          :disabled="pageCount === 0"
          size="small"
          controls-position="right"
        />
        页，共 {{ pageCount }} 页
      </span>
      <el-button :disabled="page >= pageCount" @click="page += 1">下一页</el-button>
      <span class="zoom">
        <el-button size="small" :disabled="scale <= MIN_SCALE" @click="zoom(-SCALE_STEP)">缩小</el-button>
        {{ Math.round(scale * 100) }}%
        <el-button size="small" :disabled="scale >= MAX_SCALE" @click="zoom(SCALE_STEP)">放大</el-button>
      </span>
    </div>
    <el-alert v-if="error" type="warning" :title="error" show-icon :closable="false" />
    <div v-loading="loading" class="canvas-box">
      <canvas ref="canvas" />
    </div>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.page-input {
  display: flex;
  align-items: center;
  gap: 6px;
}

.zoom {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}

.canvas-box {
  min-height: 300px;
  overflow: auto;
  text-align: center;
  background: #f2f3f5;
  padding: 12px;
}

canvas {
  box-shadow: 0 1px 4px rgb(0 0 0 / 15%);
  background: #fff;
}
</style>
