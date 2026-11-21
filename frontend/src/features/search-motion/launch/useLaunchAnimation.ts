// 启动动画的 Vue 适配层。
// - 在 setup 阶段（首帧渲染之前）就决定播不播：要播就先给 <html> 打标记，真实输入框从第一帧起隐藏；
//   不播（减少动效、本会话播过、输入框已有内容）就什么都不做，页面和原来完全一样。
// - 挂载后才懒加载动画脚本（不进首屏），加载失败直接显示输入框。
// - 输入框给 el-input 的实例 ref；el-input 上要加 class="sm-launch-target"。
import { onBeforeUnmount, onMounted, type Ref } from 'vue'

import { prefersReducedMotion } from '../shared/reducedMotion'
import type { LaunchEndReason, LaunchHandle } from './launchAnimation'
import { hasPlayedLaunch, markLaunchPlayed } from './playOnce'
import './launch.css'

export interface UseLaunchOptions {
  placeholder: string
  /** 输入框已经有内容（例如从地址栏恢复了检索词）时不播 */
  hasValue?: () => boolean
  onFinish?: (reason: LaunchEndReason) => void
}

const ATTR = 'smLaunch' // 与 launchAnimation.ts 的 LAUNCH_ATTR 相同；这里不 import，免得把动画脚本拉进首屏

function reveal(): void {
  delete document.documentElement.dataset[ATTR]
}

export function useLaunchAnimation(inputRef: Ref<{ $el?: unknown } | null>, options: UseLaunchOptions): void {
  const willPlay = !prefersReducedMotion() && !hasPlayedLaunch() && !(options.hasValue?.() ?? false)
  if (!willPlay) return

  document.documentElement.dataset[ATTR] = 'playing'
  let handle: LaunchHandle | null = null
  let disposed = false

  onMounted(async () => {
    const root = inputRef.value?.$el
    const wrapper = root instanceof HTMLElement ? root.querySelector<HTMLElement>('.el-input__wrapper') : null
    const input = root instanceof HTMLElement ? root.querySelector('input') : null
    if (!wrapper || !input) {
      reveal()
      return
    }
    markLaunchPlayed()
    try {
      const { playLaunch } = await import('./launchAnimation')
      if (disposed) return
      handle = playLaunch(
        { wrapper, input, icon: (root as HTMLElement).querySelector<SVGElement>('.el-input__prefix svg') },
        { placeholder: options.placeholder, onFinish: options.onFinish },
      )
    } catch {
      reveal()
    }
  })

  onBeforeUnmount(() => {
    disposed = true
    handle?.destroy()
    reveal()
  })
}
