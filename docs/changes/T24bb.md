# 修改记录：T24bb 登录竞态、文件列表、预览页的缺陷（2026-11-25）

- 来源：克隆库 `feat/search-motion` 的新功能联测 V1（一部分，`8f8aee6`）、V4（`3c9fe75`）。三处缺陷 2026-11-25 都在 main（`536c882`）上复现过
- 任务性质：不带 🔒；只改前端；没有改后端、接口、附录 A；没有新依赖
- 修改者：Claude（Opus 5.5）

## 1. 问题与修改

| 问题（在 main 上的复现） | 原因 | 修改 |
|---|---|---|
| 连不上时点“重试”，没返回又用表单登录：新用户被踢回登录页、令牌被删；旧令牌仍有效时显示成旧令牌的用户 | `restoreSession` 和 401 回调不看令牌是否已经换了 | `auth.ts`：等待期间令牌换了，就不采用这个结果；`api/client.ts`：旧令牌的 401 不触发退出 |
| 快速切换筛选：选着“我上传的”，显示的是共享来的文件。列表没返回就离开：之后一直每 5 秒请求 | 乱序返回没有丢弃；离开后返回的那次仍会排定时器 | 新增 `utils/latestRun.ts`（`LatestRun`：只认最后一次，停止后全部作废），`DocumentsView.vue` 使用 |
| 后退两步从一个预览跳到另一个：地址变了、内容没变。没加载完就离开：请求 `/documents/undefined/download`，或把另一个文件重复下载一次 | vue-router 复用组件；`id` 是跟着路由变的 computed | `App.vue` 的 `router-view` 加 `:key="route.path"`（只改 query 不会重建）；`PreviewView.vue` 的 `id` 进入时定下来，返回后先看是否已离开 |

`api/client.ts`、`auth.ts`、`latestRun.ts` 和测试与克隆库相同，只改注释编号；三个 `.vue` 人工移植（克隆库的版本带任务面板和中英文）。

## 2. 验证

- 类型检查通过；前端 17 个文件 210 项通过（原 205 项，新增 `auth.test.ts` 3 项、`latest-run.test.ts` 2 项）；生产构建通过。
- 撤掉 `auth.ts`、`client.ts` 的修改，`auth.test.ts` 3 项失败。
- 浏览器 + 真实 FastAPI + SQLite 替身：离开列表后 0 次请求，留在列表时轮询照常；切换筛选显示正确；后退两步标题与地址一致；登录竞态后新用户仍在、令牌仍在。
- **未测试（Not Tested）**：见 `docs/untested.md`“T24ba–T24be”。
