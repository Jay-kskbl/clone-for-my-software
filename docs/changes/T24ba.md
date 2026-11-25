# 修改记录：T24ba 任务失败原因清理后再返回（2026-11-25）

- 来源：克隆库 `feat/search-motion` 的“任务状态与重试”P1（`5409181`）。Barry 于 2026-11-25 批准（“批准，用建议选项”），见 DEVPLAN“插入任务：克隆库前端整体放入”
- 任务性质：不带 🔒；接口字段不变，只是 `error` 的文字变了；没有改表结构、配置、附录 A；没有新依赖
- 修改者：Claude（Opus 5.5）

## 1. 问题

Worker 把异常原文存进 `processing_tasks.error`，任务接口原样返回，文档的 owner 和被共享者都能看到。2026-11-25 在 main（`536c882`）上实测，被共享者看到 `FileNotFoundError: [Errno 2] No such file or directory: '/srv/docmgr/storage/a.pdf'`。数据库连接失败的原文还会带主机名和端口。违反 GLOBAL §7.2。

## 2. 修改

| 文件 | 修改 |
|---|---|
| `backend/app/modules/documents/task_errors.py`（新增） | `public_task_error()`：只放行认得出来的写法，其余只给类型名。新增的异常漏登记，后果是说明不够详细，而不是泄露 |
| `backend/app/modules/documents/tasks.py` | `to_task_out(user, task)`：管理员看原文，其他人看清理过的 |
| `backend/app/api/tasks.py` | 三个任务接口都改用 `to_task_out` |
| `backend/tests/unit/test_task_errors.py`（新增 42 项）、`tests/integration/test_documents.py`（新增 1 项） | — |
| `docs/api.md` §5.1 | 说明 `error` 的规则 |

- 检索服务的错误只保留到 HTTP 状态码；OCR 模型加载失败只保留前半句。
- 数据库里的原文不变。`requeue-failed`（T24ae）、`reocr` 直接读数据库，看到的仍是原文，不受影响。
- `scripts/smoke/ocr_e2e.py` 用普通用户的令牌读失败原因，出错时打印的说明会变短，判断逻辑不变。
- 逐条看过放行类型的所有 `raise`：文字里只有数字、异常类型名、MIME、来源位置。T24aa–T24af 没有新增写法。

## 3. 验证

- `backend/` 802 passed、241 skipped；`ruff check`、`ruff format --check` 通过。
- 变异：`to_task_out` 总返回原文 → `test_ordinary_user_gets_the_cleaned_reason` 失败。
- 集成测试 3 个文件在 SQLite 替身上 82 通过、1 失败（`test_create_admin_command` 直连 PostgreSQL）。替身只替换引擎和列类型，业务代码原样，没有提交。
- **未测试（Not Tested）**：新增的集成测试在 PostgreSQL 上。
