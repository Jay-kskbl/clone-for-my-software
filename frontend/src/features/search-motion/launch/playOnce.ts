// 启动动画会话内只播一次（指南 §5.3）：用 sessionStorage 记标记。
// 隐私模式、禁用存储时读写 sessionStorage 会抛异常：一律 try/catch，读不到就当作“没播过”，
// 写不进去就当作“这次播了也记不住”——最坏情况是刷新后再播一次，不会报错。

const KEY = 'search-motion.launch-played'

type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

function session(): StorageLike | null {
  try {
    return window.sessionStorage
  } catch {
    return null
  }
}

export function hasPlayedLaunch(storage: StorageLike | null = session()): boolean {
  try {
    return storage?.getItem(KEY) === '1'
  } catch {
    return false
  }
}

export function markLaunchPlayed(storage: StorageLike | null = session()): void {
  try {
    storage?.setItem(KEY, '1')
  } catch {
    // 记不住就算了，见文件头说明
  }
}

/** 演示页 / 设计走查用：清掉标记，刷新后可以再看一次。 */
export function resetLaunchPlayed(storage: StorageLike | null = session()): void {
  try {
    storage?.removeItem(KEY)
  } catch {
    // 同上
  }
}
