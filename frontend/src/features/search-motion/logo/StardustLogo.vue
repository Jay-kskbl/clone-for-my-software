<script setup lang="ts">
// 登录页的 logo：星尘光球（与待机、启动动画同一个图形，shared/stardust.ts）中间放文档图标
// （Barry 2026-11-22 决定，取代原来蓝色方块里的文档图标）。
// 一直转动，不等待机；全页共用一个 rAF 循环，页面切到后台时自动暂停；减少动效时只画一帧静止画面。
// 实心核放大到画布的 19%，图标用 HTML 盖在中间，颜色取页面底色，在主色实心核上保持清晰。
import { onBeforeUnmount, onMounted, ref } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'
import { addFrame, createCanvasSurface } from '../shared/canvas'
import { onReducedMotionChange, prefersReducedMotion } from '../shared/reducedMotion'
import { drawStardust } from '../shared/stardust'
import { onThemeChange, readTokens } from '../shared/tokens'

const props = withDefaults(defineProps<{ size?: number }>(), { size: 120 })

const TURNS_PER_SECOND = 0.35
const CORE = 0.19
const ICON = 0.2

const canvas = ref<HTMLCanvasElement | null>(null)
const cleanups: (() => void)[] = []

onMounted(() => {
  const el = canvas.value!
  let tokens = readTokens()
  let clock = 0
  let rotation = 0
  let offFrame: (() => void) | null = null

  const surface = createCanvasSurface(el, { observe: el.parentElement ?? el, onResize: () => paint() })

  function paint(): void {
    surface.clear()
    const size = Math.min(surface.width, surface.height)
    if (size <= 0) return
    const view = { cx: size / 2, cy: size / 2, R: size * 0.4, rotation, time: clock / 1000, scale: 1 }
    drawStardust(surface.ctx, tokens, view, 1, { coreRadius: size * CORE })
  }

  function start(): void {
    if (offFrame) return
    offFrame = addFrame((_now, dt) => {
      clock += dt
      rotation += (dt / 1000) * TURNS_PER_SECOND * Math.PI * 2
      paint()
    })
  }

  function stop(): void {
    offFrame?.()
    offFrame = null
  }

  function apply(reduced: boolean): void {
    if (!reduced) return start()
    stop()
    rotation = -Math.PI / 4
    clock = 0
    paint()
  }

  apply(prefersReducedMotion())
  cleanups.push(
    onReducedMotionChange(apply),
    onThemeChange((value) => {
      tokens = value
      paint()
    }),
    stop,
    () => surface.destroy(),
  )
})

onBeforeUnmount(() => {
  for (const cleanup of cleanups.splice(0)) cleanup()
})
</script>

<template>
  <div class="sm-logo" :style="{ width: `${props.size}px`, height: `${props.size}px` }" aria-hidden="true">
    <canvas ref="canvas" />
    <AppIcon name="file-text" :size="Math.round(props.size * ICON)" class="sm-logo-icon" />
  </div>
</template>

<style scoped>
.sm-logo {
  position: relative;
  pointer-events: none;
}

.sm-logo canvas {
  display: block;
}

.sm-logo-icon {
  position: absolute;
  top: 50%;
  left: 50%;
  color: var(--app-surface);
  transform: translate(-50%, -50%);
}
</style>
