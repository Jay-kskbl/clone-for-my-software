# 前端（M14）

Vue 3 + TypeScript + Element Plus。只依赖 `docs/api.md` 中的接口契约。

## 准备

需要 Node.js 的 LTS 版本（22.12 以上，实际使用的是 26.13.1）。本项目把 Node.js 装在了项目内的 `.tools/node/`（见 `docs/decisions.md` D23），
它不在系统 `PATH` 里，每个新开的终端先执行一次：

```bash
export PATH="$(git rev-parse --show-toplevel)/.tools/node/bin:$PATH"
```

然后在本目录安装依赖：

```bash
npm install
```

## 常用命令

| 命令 | 作用 |
|---|---|
| `npm run dev` | 开发服务器，访问 `http://127.0.0.1:5173`。`/api`、`/health` 会被转发到 `http://127.0.0.1:8000`，所以要先启动后端 |
| `npm run typecheck` | 类型检查（包括 `.vue` 文件） |
| `npm test` | 单元测试 |
| `npm run build` | 类型检查 + 生产构建，产物在 `dist/` |
| `npm run sync:pdfjs` | 把 `node_modules/pdfjs-dist` 的 `cmaps`、`standard_fonts`、`wasm`、`iccs` 复制到 `public/pdfjs/`。**升级 pdfjs-dist 之后必须运行**，否则 `npm test` 里的一致性检查会失败（T24m） |

## 目录

```
src/
├── api/          接口封装：client.ts（令牌、错误转换）、auth.ts、documents.ts、tasks.ts（任务与重试）、search.ts、health.ts（GET /health，T24s）、types.ts（与 api.md 对应的类型）
├── auth.ts       登录状态（当前用户）
├── router.ts     路由与登录跳转
├── App.vue       页面骨架：登录后左侧导航栏 + 内容区（最宽 1200px）；≤768px 时导航栏收成顶部一行（T24s）
├── styles.css    全局样式：--app-* 公共取值（全部引用 Element Plus 的 CSS 变量）、标题区、检索词高亮 .app-mark（T24s）
├── views/        页面：LoginView（登录/注册）、DocumentsView（文件列表、拖拽上传与逐个文件的上传记录、下载、删除）、
│                 SearchView（检索：检索通道面板与 CLIP 服务状态、结果卡片、三个通道的名次与 RRF 融合分、图片缩略图、降级提示）、
│                 PreviewView（预览；PDF、图片分“原文件 / 抽取文本”两个标签页，T24f）
├── i18n/         界面语言（T24bc）：index.ts（locale、m()、translated()）、messages.ts（中英文两套文字）
├── features/theme/  系统配色与语言按钮（T24bc）：theme.ts（颜色计算、保存）、store.ts、ThemePicker、LocaleSwitch
├── features/tasks/  处理任务（T24bd）：TaskDialog（处理详情）、useDocumentTasks（加载、自动刷新、重试）；summary / retry / watcher / refresher / text / changes 是有单元测试的纯逻辑
├── components/   ShareDialog（共享）、PdfViewer（PDF 显示）、ExtractedText（抽取文本列表）、AppIcon（线条图标）、FileTypeBadge（文件类型色块）
└── utils/        格式化、来源定位与通道说明、摘要清洗、缩略图加载（thumbnails.ts）、预览默认标签页（preview.ts）、检索通道开关与名次（channels.ts）、保存下载文件（download.ts）、只认最后一次（latestRun.ts）
tests/            单元测试（接口封装、格式化、来源定位、摘要、缩略图、预览标签页、检索通道、pdf.js 资源一致性、Element Plus 注册）
scripts/          pdfjs-assets.mjs（资源比较）、sync-pdfjs.mjs（复制资源）
public/pdfjs/     pdf.js 的 CMap、标准字体、WASM 解码器、ICC 配置，PdfViewer 运行时按需加载（中文 PDF 需要 CMap）
```

## 说明

- 页面上的登录判断和按钮显隐只决定“显示什么”，不是权限控制；权限由后端每个接口校验。
- Element Plus 按需引入（T24p）：新页面用到新的 `<el-xxx>` 组件时，在 `src/element.ts` 加它的样式，在 `src/element-components.ts` 加 import 和清单项；漏了的话 `npm test` 会失败。
- 上传时选择文件的类型过滤只是方便用户，真正的类型检查在后端按文件内容进行。
- 样式（T24s）：颜色不要在组件里写死十六进制值，引用 Element Plus 的 `--el-*` 变量或 `src/styles.css` 里的 `--app-*`；检索词高亮统一用 `.app-mark` 类（浅黄底）。
