// 动效用到的文案集中在这里（指南 §6.4 要求放进多语言文件；项目没有 i18n 库，
// 先集中成一个文件，以后接入 i18n 时只替换这里）。
// 扫描动画的文案：指南原文是“网页”，本系统检索的是文件，按 Barry 的决定改为“文件”。

export const SCAN_TEXT = {
  opening: '正在打开文件…',
  reading: (index: number, total: number) => `正在阅读第 ${index} / ${total} 个文件`,
  summarizing: '正在整理答案…',
  failed: '检索失败',
  retry: '重试',
}

export const SEARCH_TEXT = {
  timeout: (seconds: number) => `检索超时（${seconds} 秒内没有返回），请稍后重试`,
}
