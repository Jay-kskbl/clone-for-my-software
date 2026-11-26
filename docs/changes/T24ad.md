# 修改记录：T24ad 失败的任务隔一段时间再重试（2026-11-25）

- 来源：`docs/changes/2026-11-23-代码复核建议.md` R2。原计划加一列 `available_at`（🔒）；Barry 追问“为什么这个方案更好”后，改为利用已有的 `started_at`、不改表结构，Barry 于 2026-11-25 选定（“No migration”）
- 任务性质：代码修改，不带 🔒；没有改表结构、索引、接口、附录 A，没有新依赖。新增一个配置项
- 决策：`docs/decisions.md` D55
- 修改者：Claude（Opus 5.5）

## 逐文件修改记录

| 文件 | 位置 | 修改 | 原因与影响 |
|---|---|---|---|
| `shared/tasks.py` | `_CLAIM_SQL`、`claim`、模块说明 | 领取条件加重试间隔；`claim` 新增参数 `retry_delays`（默认空，不等）；说明加约定 4 | 默认值保持原行为，直接调用 `claim` 的测试不受影响 |
| `shared/task_queue.py` | `parse_retry_delays`、`PgTaskQueue` | 解析配置（0–3600 秒，不接受空值、负数、nan）；构造参数 `retry_delays`，领取时传下去 | 两个 Worker 共用一份解析 |
| `backend/app/config.py`、`services/ocr_worker/ocr_worker/config.py` | 新字段 | `task_retry_delays_seconds`（默认 `30,120`）、属性 `retry_delays` | 不合法时启动即报错 |
| `backend/app/worker/__main__.py`、`services/ocr_worker/ocr_worker/__main__.py` | 建队列处 | 传入 `settings.retry_delays` | — |
| `.env.example` | Worker 一节末尾 | 新增 `TASK_RETRY_DELAYS_SECONDS=30,120` | 不写也可以，用默认值 |
| `shared/tests/test_task_queue.py` | 新增 15 项 | 解析的合法与不合法取值；间隔传到领取 SQL，且 SQL 用到的参数都传了 | 不需要数据库 |
| `backend/tests/unit/test_worker_loop.py`、`test_worker_main.py` | 新增 6 项 | 默认值、不合法值、Worker 把间隔传给队列 | 同上 |
| `services/ocr_worker/tests/test_config_and_models.py`、`test_main.py` | 新增 2 项 | 同上 | 同上 |
| `backend/tests/integration/test_task_queue.py` | 新增 8 项 | 按第几次失败等待、最后一个间隔重复用、等待的任务不挡别的任务、不等的几种情况（空间隔、0、租约过期、手动重试）、不可重试立即失败 | **需要 PostgreSQL，本机未运行** |
| `docs/decisions.md`、`docs/untested.md`、`docs/data-model.md`、`windows任务书.md`、`DEVPLAN.md` | — | D55；登记 8 项未运行的测试；`started_at` 说明；任务书第 17.2、17.15 节；任务与完成记录 | — |
| `docs/changes/2026-11-23-代码复核建议.md` | R2 | 标记 a 已做（不改表结构的做法）；**更正**“除了逐个点‘重试’”：前端没有重试按钮，只有接口 `POST /api/tasks/{id}/retry` | 原来写错了 |

## 验证

- 已运行（macOS，main 环境）：`shared/` 124 passed；`backend/` 732 passed、237 skipped（比上次多 8 项，就是新增的集成测试）；`services/ocr_worker/` 82 passed、4 skipped；三个目录 ruff check、format check 通过
- 已运行（macOS，ocr 环境）：真实识别 4 项通过；配置默认值在 ocr 环境里读出为 `(30.0, 120.0)`
- 反证：去掉三处“把间隔传下去”的代码，新增测试各有 1 项失败；恢复后通过
- **未测试（Not Tested）**：领取 SQL 在真实 PostgreSQL 上的行为（8 项集成测试）。代码复核：数组下标从 1 开始、空数组取 NULL 后按 0 处理、`cardinality` 对空数组返回 0；`started_at` 在失败放回时不清空（`_RELEASE_SET` 没有动它），手动重试与 `reocr` 会清空它并把 `attempts` 归零；租约过期的任务靠 `error` 识别

## 修改建议（后续）

1. R2 的 b（把失败的 embed、ocr 任务重新排队的命令）没有做，要等 Barry 批准。CLIP 长时间关闭时只有它能补救。
2. 在 Windows 上跑过之后，从 `docs/untested.md` 删去对应行；如果 30、120 秒不合适，改 `TASK_RETRY_DELAYS_SECONDS` 即可，不用改代码。
