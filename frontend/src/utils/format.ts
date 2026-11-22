import type { Access, Status } from '../api/types'
import { m, translated } from '../i18n'

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

// 处理状态的说明与标签颜色（docs/api.md §5.1）；文字随界面语言（src/i18n）
export const STATUS_LABEL: Record<Status, { text: string; type: TagType }> = translated((msg) => ({
  pending: { text: msg.format.status.pending, type: 'info' },
  processing: { text: msg.format.status.processing, type: 'warning' },
  succeeded: { text: msg.format.status.succeeded, type: 'success' },
  failed: { text: msg.format.status.failed, type: 'danger' },
}))

export const ACCESS_LABEL: Record<Access, string> = translated((msg) => ({ ...msg.format.access }))

export function formatType(mimeType: string): string {
  const labels: Record<string, string> = {
    'application/pdf': 'PDF',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'Word',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'Excel',
    'image/png': m().format.typePng,
    'image/jpeg': m().format.typeJpeg,
  }
  return labels[mimeType] ?? mimeType
}

export type BadgeTone = 'danger' | 'primary' | 'success' | 'warning' | 'info'

// 文件类型色块上的短文字和颜色（components/FileTypeBadge.vue，T24s）
export function typeBadge(mimeType: string): { text: string; tone: BadgeTone } {
  const badges: Record<string, { text: string; tone: BadgeTone }> = {
    'application/pdf': { text: 'PDF', tone: 'danger' },
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': { text: 'DOC', tone: 'primary' },
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': { text: 'XLS', tone: 'success' },
    'image/png': { text: m().format.badgeImage, tone: 'warning' },
    'image/jpeg': { text: m().format.badgeImage, tone: 'warning' },
  }
  return badges[mimeType] ?? { text: m().format.badgeFile, tone: 'info' }
}

/** 还没有处理完的文档：列表需要继续刷新它们的状态。 */
export function isInProgress(status: Status): boolean {
  return status === 'pending' || status === 'processing'
}

// 浏览器能原样显示、后端也接受的图片类型（PNG、JPEG）
const IMAGE_TYPES = ['image/png', 'image/jpeg']

export function isImageType(mimeType: string): boolean {
  return IMAGE_TYPES.includes(mimeType)
}
