<script setup lang="ts">
// 登录页的 logo：星尘光球（与待机、启动动画同一个图形，shared/stardust.ts）中间放文档图标
// （Barry 2026-11-22 决定，取代原来蓝色方块里的文档图标）。
// 一直转动，不等待机；全页共用一个 rAF 循环，页面切到后台时自动暂停；减少动效时只画一帧静止画面。
// 实心核（半径约 23 px）中间用 HTML 盖一个文档图标（约 24 px），颜色取页面底色，在主色实心核上保持清晰。
// 光圈（星尘轨道）以 10 秒为一个周期，先变大再变小：从 45% 平滑放大到原大，再缩回 45%（Barry 2026-11-22，
// 第二次要求加大幅度）。只缩轨道，核心和图标大小不变。
// 放大的同时，轨道沿长轴（左右方向）再拉长到 1.9 倍，缩小时回到 1 倍：左右的变化比上下明显得多
// （Barry 第三次要求：缩放程度不变，左右比变化加大，左右不要太空）。
// 画布 240 × 160：最大时最外侧的星芒离左右边缘约 3 px、离上下边缘约 10 px，不会被裁掉，左右也不空。
import { onBeforeUnmount, onMounted, ref } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'
import { addFrame, createCanvasSurface } from '../shared/canvas'
import { onReducedMotionChange, prefersReducedMotion } from '../shared/reducedMotion'
import { drawStardust } from '../shared/stardust'
import { onThemeChange, readTokens } from '../shared/tokens'

const props = withDefaults(defineProps<{ width?: number; height?: number }>(), { width: 240, height: 160 })

const TURNS_PER_SECOND = 0.35
const PULSE_MS = 10_000
const ORBIT_MIN = 0.45
const STRETCH_MAX = 1.9

/** 缩放进度 0～1：t = 0 时 0（最小），5 秒时 1（最大），10 秒回到 0（余弦曲线，两端和顶点都是平滑的） */
function pulse(clockMs: number): number {
  const phase = (clockMs % PULSE_MS) / PULSE_MS
  return 0.5 - 0.5 * Math.cos(phase * Math.PI * 2)
}
const CORE = 0.145
const ICON = 0.15

const canvas = ref<HTMLCanvasElement | null>(null)
const cleanups: (() => void)[] = []

onMounted(() => {
  const el = canvas.value!
  let tokens = readTokens()
  let clock = 0
  let rotation = 0
  let offFrame: (() => void) | null = null
  let reduced = false

  const surface = createCanvasSurface(el, { observe: el.parentElement ?? el, onResize: () => paint() })

  function paint(): void {
    surface.clear()
    const size = Math.min(surface.width, surface.height)
    if (size <= 0) return
    // 减少动效时停在最大
    const k = reduced ? 1 : pulse(clock)
    const view = {
      cx: surface.width / 2,
      cy: surface.height / 2,
      R: size * 0.4,
      rotation,
      time: clock / 1000,
      scale: 1,
      orbitScale: ORBIT_MIN + (1 - ORBIT_MIN) * k,
      orbitStretch: 1 + (STRETCH_MAX - 1) * k,
    }
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

  function apply(value: boolean): void {
    reduced = value
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
  <div class="sm-logo" :style="{ width: `${props.width}px`, height: `${props.height}px` }" aria-hidden="true">
    <canvas ref="canvas" />
    <AppIcon name="file-text" :size="Math.round(Math.min(props.width, props.height) * ICON)" class="sm-logo-icon" />
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
