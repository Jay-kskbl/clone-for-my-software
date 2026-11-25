import type { ScanControls } from './searchSession'

/** ScanLoader.vue 通过 ref 暴露的方法。 */
export interface ScanLoaderHandle {
  start(pageCount?: number): void
  complete(result: unknown): void
  error(message?: string): void
  cancel(): void
}

/** 把组件 ref 包装成 createSearchSession 需要的控制对象（ref 还没挂载时调用会被忽略）。 */
export function controlsFrom<T>(get: () => ScanLoaderHandle | null): ScanControls<T> {
  return {
    start: () => get()?.start(),
    complete: (result) => get()?.complete(result),
    error: (message) => get()?.error(message),
    cancel: () => get()?.cancel(),
  }
}
