# 修改记录：T24bh 检索动效的文字只说真实发生的事（2026-11-25）

- 来源：T24be 的待定项。Barry 于 2026-11-25 批准（“改”）
- 任务性质：不带 🔒；只改前端文字；没有改后端、接口、附录 A；没有新依赖
- 修改者：Claude（Opus 5.5）

## 1. 问题

检索时间较长时，扫描区依次显示“正在打开文件…”“正在阅读第 1 / 6 个文件”……“正在整理答案…”。6 是装饰卡片的张数，与文件数无关；系统此时没有打开或阅读文件，也不生成答案。GLOBAL §8.1 不允许用假数据伪装真实功能，§13 不允许夸大系统能力；论文截图和答辩演示会拍到。

## 2. 修改

| 文件 | 修改 |
|---|---|
| `src/i18n/messages.ts` | `scan.opening`、`scan.reading` 合并为 `searching`（“正在检索…” / “Searching…”）；`summarizing` 改为“正在整理结果…” / “Preparing results…” |
| `src/features/search-motion/scan-loader/scanLoader.ts` | 每轮开头写一次 `searching`，不再跟着卡片变；卡片动画不变 |
| `src/features/search-motion/messages.ts` | 注释 |
| `tests/i18n.test.ts` | 新增 2 项：中英文里没有数字，没有“阅读、打开、答案、read、open、answer”，以后改文字时会拦住 |
| `windows任务书.md` | 第 17.1、17.2 节的提交核对和前端项数（378），第 17.18 节第 10 步的预期 |

Barry 同意的是“正在阅读……”“正在整理答案…”两句；“正在打开文件…”性质相同，留着就会先后出现两种说法，一并改了。

## 3. 验证

见 DEVPLAN §5。克隆库里的文字没有改。
