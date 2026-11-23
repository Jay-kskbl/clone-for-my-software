# 修改记录：任务状态与重试（2026-11-23）

- 来源：2026-11-23 前端评估。后端有任务查看、重试接口，前端没有界面；`decisions.md` D8 写“用户要在任务列表里查看”，但列表不存在
- 分支：`feat/search-motion`（克隆库）。Barry 于 2026-11-23 批准 P1–P4，决定在克隆库做，不进主仓库的 DEVPLAN，也不同步到主仓库
- 每个任务一个提交；提交编号补在本文件，单独提交
- 没有新依赖，没有改表结构、索引、配置

| 编号 | 内容 | 状态 | 提交 |
|---|---|---|---|
| P1 | 后端清理任务失败原因，原文只给管理员看 | 完成 | `5409181` |
| P2 | 前端任务逻辑（汇总、重试、轮询）与单元测试 | 未开始 | — |
| P3 | 处理详情对话框，接入文件列表 | 未开始 | — |
| P4 | 预览页提示条与自动刷新 | 未开始 | — |
| P5（未批准） | 任务接口增加 `locator`，显示具体失败页码 | — | — |
| P6（未批准） | 管理员任务页 | — | — |

------------------------------------------------------------------------

## P1 后端清理任务失败原因

### 为什么

Worker 把异常原文存进 `processing_tasks.error`，任务接口原样返回，文档的 owner 和被共享者都能看到。没有预料到的异常会带出内部信息，按 Worker 的拼法实测：

- `FileNotFoundError: [Errno 2] No such file or directory: '/srv/docmgr/storage/…'`（服务器路径）
- `OperationalError: … connection to server at "127.0.0.1", port 1 failed`（数据库地址）

加界面之前接口已经是这样；加了界面会直接显示出来，所以先改后端。只在前端隐藏不算修好。

### 修改的文件

| 文件 | 改了什么 |
|---|---|
| `backend/app/modules/documents/task_errors.py`（新增） | `public_task_error()`：只放行认得出来的写法，其余只给类型名 |
| `backend/app/modules/documents/tasks.py` | `to_task_out(user, task)`：管理员看原文，其他人看清理过的 |
| `backend/app/api/tasks.py` | 三个任务接口都改用 `to_task_out` |
| `backend/tests/unit/test_task_errors.py`（新增） | 42 项 |
| `backend/tests/integration/test_documents.py` | 新增 1 项（owner、被共享者、管理员分别看到什么），**未运行** |
| `docs/api.md` §5.1 | 说明 `error` 的规则 |

### 关键设计

- 默认不放行：新增的异常没登记，后果是说明不够详细，而不是泄露。
- 检索服务的错误只保留到 HTTP 状态码。OpenSearch 的原因文字可能带节点名和内网地址（`[node-1][172.18.0.2:9300]`）。
- OCR 模型加载失败只保留前半句，后半句是内部异常，可能带模型目录。
- 数据库里的原文不变，排查问题不受影响。接口字段不变，只是 `error` 的文字变了。

### 验证

- 后端全量：763 通过、230 跳过（改之前 721 通过、229 跳过）。用主仓库的 `.venv-main` 运行克隆库的代码，没有写主仓库
- 变异检查：把 `to_task_out` 改成总是返回原文，`test_ordinary_user_gets_the_cleaned_reason` 失败
- `ruff check`、`ruff format --check` 通过
- **未测试（Not Tested）：** 新增的集成测试，本机没有 PostgreSQL
