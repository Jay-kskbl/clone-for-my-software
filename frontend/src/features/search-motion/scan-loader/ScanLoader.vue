<script setup lang="ts">
// 扫描加载动画的 Vue 适配层：只负责挂载 / 卸载，把核心对象的方法暴露给父组件。
// 父组件用 ref 拿到 ScanLoaderHandle，交给 createSearchSession（见 searchSession.ts）。
import { onBeforeUnmount, onMounted, ref } from 'vue'

import type { ScanPhase } from './machine'
import { createScanLoader, type ScanLoader } from './scanLoader'
import type { ScanLoaderHandle } from './handle'

const props = defineProps<{ pageCount?: number; retryable?: boolean }>()
const emit = defineEmits<{ done: [result: unknown]; retry: []; phase: [phase: ScanPhase] }>()

const host = ref<HTMLElement | null>(null)
const phase = ref<ScanPhase>('idle')
let loader: ScanLoader<unknown> | null = null

onMounted(() => {
  loader = createScanLoader<unknown>(host.value!, {
    pageCount: props.pageCount,
    onDone: (result) => emit('done', result),
    onPhaseChange: (value) => {
      phase.value = value
      emit('phase', value)
    },
    onRetry: props.retryable ? () => emit('retry') : undefined,
  })
})

onBeforeUnmount(() => {
  loader?.destroy()
  loader = null
})

const handle: ScanLoaderHandle = {
  start: (pageCount) => loader?.start(pageCount ?? props.pageCount),
  complete: (result) => loader?.complete(result),
  error: (message) => loader?.error(message),
  cancel: () => loader?.cancel(),
}
defineExpose(handle)
</script>

<template>
  <!-- idle / done 时不占位：结果区显示引导或结果 -->
  <div v-show="phase === 'scanning' || phase === 'summarizing' || phase === 'error'" ref="host" />
</template>
