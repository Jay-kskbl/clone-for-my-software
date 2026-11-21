/**
 * 把取回的文件交给浏览器保存。下载接口需要登录令牌，不能用普通链接，
 * 所以先取成 Blob 再保存（文件列表和预览页共用，T24s 前两处各写了一份）。
 */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
