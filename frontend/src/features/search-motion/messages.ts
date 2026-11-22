// 动效用到的文案集中在这里（指南 §6.4 要求放进多语言文件；项目没有 i18n 库，
// 先集中成一个文件，以后接入 i18n 时只替换这里）。
// 扫描动画的文案：指南原文是“网页”，本系统检索的是文件，按 Barry 的决定改为“文件”。
// 加了语言切换后（src/i18n），文字本身放在 i18n/messages.ts 的 scan、search 两节，这里按当前语言取。
import { translated } from '../../i18n'

export const SCAN_TEXT = translated((msg) => msg.scan)

export const SEARCH_TEXT = translated((msg) => ({ timeout: msg.search.timeout }))
