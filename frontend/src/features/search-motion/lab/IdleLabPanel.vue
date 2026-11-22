<script setup lang="ts">
// 演示页的待机动画面板：默认参数（8 s 进入待机）与快速走查参数（2 s）可切换，
// 也可以手动 show / hide（指南 §4.2 的调试接口）。
import { computed, ref } from 'vue'

import IdleSpinner from '../idle-spinner/IdleSpinner.vue'

const emit = defineEmits<{ log: [text: string] }>()

const fast = ref(false)
const idleAfter = computed(() => (fast.value ? 2000 : 8000))
const spinner = ref<{ show(): void; hide(): void } | null>(null)
</script>

<template>
  <section class="idle-lab">
    <div class="idle-tools">
      <el-checkbox v-model="fast" size="small" border>快速走查（{{ idleAfter / 1000 }} s 进入待机）</el-checkbox>
      <el-button size="small" @click="spinner?.show()">show()</el-button>
      <el-button size="small" @click="spinner?.hide()">hide()</el-button>
    </div>
    <div class="idle-guide">
      <div class="idle-text">
        <p class="idle-title">输入关键词开始检索</p>
        <p>{{ idleAfter / 1000 }} 秒不操作，右侧出现待机动画；移动鼠标、按键、滚动或触摸后 0.4 秒内淡出。</p>
      </div>
      <IdleSpinner
        ref="spinner"
        :idle-after="idleAfter"
        data-test="idle"
        @idle="emit('log', '待机：进入')"
        @active="emit('log', '待机：退出')"
      />
    </div>
  </section>
</template>

<style scoped>
.idle-lab {
  margin-top: 24px;
}

.idle-tools {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
}

.idle-tools .el-checkbox {
  margin: 0;
}

.idle-guide {
  display: flex;
  align-items: center;
  gap: 24px;
  margin-top: 12px;
  padding: 18px 24px;
  border: 1px dashed var(--el-border-color);
  border-radius: var(--app-radius-lg);
  background: var(--app-surface);
  color: var(--app-text-regular);
  font-size: 14px;
}

.idle-text {
  flex: 1;
  min-width: 0;
}

.idle-text p {
  margin: 0;
}

.idle-title {
  margin-bottom: 4px !important;
  color: var(--app-text);
  font-weight: 600;
}
</style>
