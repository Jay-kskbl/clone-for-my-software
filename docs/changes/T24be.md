# 修改记录：T24be 搜索动效，检索可取消、30 秒超时（2026-11-25）

- 来源：克隆库 `feat/search-motion` 的搜索动效（`9ab00b7`–`f3e87ba`）、联测 V2（`eaff1df`）。Barry 于 2026-11-25 批准（“批准，用建议选项”），规范例外见 `decisions.md` D60
- 任务性质：不带 🔒；只改前端；没有改后端、接口、附录 A；没有新依赖
- 修改者：Claude（Opus 5.5）

## 1. 修改

| 文件 | 修改 |
|---|---|
| `src/features/search-motion/`（新增） | 扫描加载（`scan-loader/`）、启动（`launch/`）、待机（`idle-spinner/`）、登录页 logo（`logo/`）、公共层（`shared/`）、演示页（`lab/`） |
| `src/views/SearchView.vue` | 请求经 `searchSession` 发出：新的检索取消旧请求、丢弃旧返回，30 秒超时；去掉 `loading` 守卫和 `rerun`；“检索”按钮不再显示加载圈（加载中的按钮是禁用的，浏览器不提交表单，改词按回车没反应），完全相同的检索进行中时忽略重复提交；检索框改为胶囊形 |
| `src/views/LoginView.vue`、`login/LoginBrand.vue` | 标志用插槽传入星尘光球，不传时仍是原来 48 px 的静态标志 |
| `src/router.ts` | `/motion-lab` 只在 `import.meta.env.DEV` 时注册 |
| `src/api/search.ts`、`components/AppIcon.vue`、`i18n/messages.ts` | 传 `signal`；`file-text` 图标；动效文字 |
| `tests/search-motion/`（新增 5 个文件）、`i18n.test.ts` | 新增 40 项 |

## 2. 与克隆库的差别

- **结果一到就收拢，不等当前一轮播完**（D60）。状态机去掉 `resultReady`，`complete` 直接进入 `summarizing`；`scanLoader.complete` 停下扫描并收拢。测试先改，改之前 7 项失败。
- `/motion-lab` 只在开发模式有。
- 注释里的“指南”在克隆库，本仓库没有，`features/search-motion/README.md` 写明。

## 3. 行为变化（Windows 任务书要跟着改）

- 检索进行中改开关：原来等这次返回后再查，现在立即取消并按新开关重查。
- 没有结果、出错、有结果的区分不变（GLOBAL §12）；`/api/search` 的请求内容不变；后端耗时显示不变。
- 最短约 0.42 秒才显示结果（收拢动画）。

## 4. 待 Barry 定

检索时间较长时，扫描区的文字是“正在阅读第 n / 6 个文件”“正在整理答案…”。6 是卡片数，不是真实的文件数；系统也不生成答案。GLOBAL §8.1 不允许用假数据伪装真实功能，§13 不允许夸大。文字沿用克隆库里 Barry 定的写法，这次没有改。

## 5. 验证

见 DEVPLAN §5。**未测试（Not Tested）**：见 `docs/untested.md`“T24ba–T24be”。
