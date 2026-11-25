// 动效用到的文案集中在这里（指南 §6.4 要求放进多语言文件；项目没有 i18n 库，
// 先集中成一个文件，以后接入 i18n 时只替换这里）。
// 扫描动画的文案只说真实发生的事：“正在检索”“正在整理结果”。指南原文是“正在阅读第 n / 6 个网页”“正在整理答案”，
// 但 6 是卡片数，系统也不打开文件、不生成答案（Barry 2026-11-25 决定，T24bh）。
// 加了语言切换后（src/i18n），文字本身放在 i18n/messages.ts 的 scan、search 两节，这里按当前语言取。
import { translated } from '../../i18n'

export const SCAN_TEXT = translated((msg) => msg.scan)

export const SEARCH_TEXT = translated((msg) => ({ timeout: msg.search.timeout }))
