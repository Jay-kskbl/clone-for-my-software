import type { Access, Status } from '../api/types'

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes / 1024
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`
}

export function formatTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}`
  )
}

type TagType = 'info' | 'warning' | 'success' | 'danger'

// 处理状态的中文说明与标签颜色（docs/api.md §5.1）
export const STATUS_LABEL: Record<Status, { text: string; type: TagType }> = {
  pending: { text: '等待处理', type: 'info' },
  processing: { text: '处理中', type: 'warning' },
  succeeded: { text: '处理成功', type: 'success' },
  failed: { text: '处理失败', type: 'danger' },
}

export const ACCESS_LABEL: Record<Access, string> = {
  owner: '我上传的',
  shared: '共享给我的',
  admin: '管理员可见',
}

const TYPE_LABEL: Record<string, string> = {
  'application/pdf': 'PDF',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'Word',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'Excel',
  'image/png': '图片（PNG）',
  'image/jpeg': '图片（JPEG）',
}

export function formatType(mimeType: string): string {
  return TYPE_LABEL[mimeType] ?? mimeType
}

/** 还没有处理完的文档：列表需要继续刷新它们的状态。 */
export function isInProgress(status: Status): boolean {
  return status === 'pending' || status === 'processing'
}
