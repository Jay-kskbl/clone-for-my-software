# 修改记录：T24bd 任务面板：处理详情、重试、预览页自动刷新（2026-11-25）

- 来源：克隆库 `feat/search-motion` 的任务状态与重试 P2–P4（`9519053`、`b2c5905`、`6af9c44`）、联测 V1（`8f8aee6`）。Barry 于 2026-11-25 批准（“批准，用建议选项”）
- 任务性质：不带 🔒；只改前端；没有改后端、接口、附录 A；没有新依赖。前提是 T24ba（否则会把服务器路径显示出来）
- 修改者：Claude（Opus 5.5）

## 1. 为什么

后端有任务查看、重试接口，前端没有界面；D8 写“用户要在任务列表里查看”，但列表不存在。对应 GLOBAL §3.3（失败原因、重试）和 §6 第 3 条（上传成功但解析失败是合法状态，允许重试）。

## 2. 修改

| 文件 | 修改 |
|---|---|
| `src/api/tasks.ts`（新增）、`types.ts`、`client.ts` | 两个任务接口；请求可以用 `signal` 取消，主动取消不算网络故障 |
| `src/features/tasks/`（新增 8 个文件） | `summary`（按类型汇总）、`retry`（批量重试，网络不通、401、403、5xx 停下）、`watcher`（有没结束的任务每 3 秒刷新，迟到的丢弃）、`refresher`（取文档失败自己再试）、`changes`、`text`、`useDocumentTasks`、`TaskDialog.vue` |
| `src/views/DocumentsView.vue` | 状态标签改成按钮，点开处理详情；解析失败的多一行“查看原因” |
| `src/views/PreviewView.vue`、`components/ExtractedText.vue` | 失败提示条、进度、“有新的识别结果，点此刷新”；解析完自动更新 |
| `src/i18n/messages.ts` | `tasks.*`；列名“处理状态”改“解析状态”，“处理成功 / 失败”改“已解析 / 解析失败” |
| `tests/tasks/`（新增 8 个文件，含公共数据）、`client.test.ts`、`format.test.ts`、`i18n.test.ts` | 新增 108 项；其中取消请求 2 项是移植时补的（克隆库没有，撤掉实现不会失败） |

要点：同一时间只有一批重试；离开页面后不再请求、不排定时器；被共享者能看不能重试；T24ad 的重试间隔期间任务是 `pending`、`attempts` 大于 0，显示“第 n/3 次失败，等待再次处理”。命令行 `requeue-failed`（T24ae）放回队列时，已经停止刷新的对话框要点“刷新”才会更新。

## 3. 验证

见 DEVPLAN §5。**未测试（Not Tested）**：见 `docs/untested.md`“T24ba–T24be”。
