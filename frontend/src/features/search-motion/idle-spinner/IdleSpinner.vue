<script setup lang="ts">
// 待机动画（星尘光球）的 Vue 适配层。参数变化时重建核心对象；卸载时 destroy（停帧、清定时器、移除监听）。
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { createIdleSpinner, type IdleSpinner } from './idleSpinner'

const props = withDefaults(defineProps<{ idleAfter?: number; size?: number }>(), {
  idleAfter: 8000,
  // 120 px：星尘光球的细节（闪烁、星芒、拖尾）在 72 px 下看不清（Barry 2026-11-22 决定放大）
  size: 120,
})
const emit = defineEmits<{ idle: []; active: [] }>()

const canvas = ref<HTMLCanvasElement | null>(null)
let spinner: IdleSpinner | null = null

function create() {
  spinner?.destroy()
  spinner = createIdleSpinner(canvas.value!, {
    idleAfter: props.idleAfter,
    onIdle: () => emit('idle'),
    onActive: () => emit('active'),
  })
}

onMounted(create)
watch(() => props.idleAfter, create)
onBeforeUnmount(() => {
  spinner?.destroy()
  spinner = null
})

defineExpose({
  show: () => spinner?.show(),
  hide: () => spinner?.hide(),
})
</script>

<template>
  <div class="sm-idle" :style="{ width: `${size}px`, height: `${size}px` }">
    <canvas ref="canvas" aria-hidden="true" />
  </div>
</template>

<style scoped>
.sm-idle {
  flex: none;
  pointer-events: none;
}

.sm-idle canvas {
  display: block;
}
</style>
