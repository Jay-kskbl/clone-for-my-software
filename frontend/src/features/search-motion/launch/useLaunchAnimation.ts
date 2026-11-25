// 启动动画的 Vue 适配层。
// - 检索框没有输入时循环播放，输入后停止（Barry 2026-11-22 决定，取代指南 §5.3 的“会话内只播一次”）；
//   循环规则见 loop.ts。
// - 在 setup 阶段（首帧渲染之前）就决定第一轮播不播：要播就先给 <html> 打标记，真实输入框从第一帧起隐藏；
//   不播（减少动效、输入框已有内容）就什么都不做，页面和原来完全一样。
// - 挂载后才懒加载动画脚本（不进首屏），加载失败直接显示输入框。
// - 输入框给 el-input 的实例 ref；el-input 上要加 class="sm-launch-target"。
import { onBeforeUnmount, onMounted, type Ref } from 'vue'

import { onReducedMotionChange, prefersReducedMotion } from '../shared/reducedMotion'
import type { LaunchEndReason } from './launchAnimation'
import { createLaunchLoop, type LaunchLoop } from './loop'
import './launch.css'

export interface UseLaunchOptions {
  /** 逐字打出的占位文字；传函数时每一轮开播前取一次（界面语言切换后下一轮就用新语言） */
  placeholder: string | (() => string)
  /** 输入框有内容（用户输入了，或从地址栏恢复了检索词）时不播 */
  hasValue?: () => boolean
  onFinish?: (reason: LaunchEndReason) => void
}

const ATTR = 'smLaunch' // 与 launchAnimation.ts 的 LAUNCH_ATTR 相同；这里不 import，免得把动画脚本拉进首屏

function reveal(): void {
  delete document.documentElement.dataset[ATTR]
}

export function useLaunchAnimation(inputRef: Ref<{ $el?: unknown } | null>, options: UseLaunchOptions): void {
  const empty = () => !(options.hasValue?.() ?? false)
  // 第一轮不播时也照样挂载：之后输入框清空、失焦，仍会开始循环
  if (!prefersReducedMotion() && empty()) document.documentElement.dataset[ATTR] = 'playing'

  let loop: LaunchLoop | null = null
  let disposed = false
  const cleanups: (() => void)[] = []

  onMounted(async () => {
    const root = inputRef.value?.$el
    const wrapper = root instanceof HTMLElement ? root.querySelector<HTMLElement>('.el-input__wrapper') : null
    const input = root instanceof HTMLElement ? root.querySelector('input') : null
    if (!wrapper || !input) {
      reveal()
      return
    }
    try {
      const { playLaunch } = await import('./launchAnimation')
      if (disposed) return
      const target = { wrapper, input, icon: (root as HTMLElement).querySelector<SVGElement>('.el-input__prefix svg') }
      const current = createLaunchLoop({
        play: (onEnd) =>
          playLaunch(target, {
            placeholder: typeof options.placeholder === 'function' ? options.placeholder() : options.placeholder,
            onFinish: (reason) => {
              onEnd(reason)
              options.onFinish?.(reason)
            },
          }),
        canPlay: () => !prefersReducedMotion() && empty() && document.activeElement !== input,
      })
      loop = current
      // 输入框失焦（可能已清空）、减少动效关闭：重新排下一轮
      const wake = () => current.wake()
      input.addEventListener('blur', wake)
      cleanups.push(() => input.removeEventListener('blur', wake))
      cleanups.push(onReducedMotionChange((reduced) => !reduced && wake()))
      if (!current.start()) {
        reveal()
        current.wake()
      }
    } catch {
      reveal()
    }
  })

  onBeforeUnmount(() => {
    disposed = true
    for (const cleanup of cleanups) cleanup()
    loop?.destroy()
    reveal()
  })
}
