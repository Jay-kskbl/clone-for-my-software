# 修改记录：T24al 图像通道把查询编码和向量检索分开计时（2026-11-26）

- 来源：`docs/changes/2026-11-26-后端优化分析.md`（六项优化分析）。Barry 于 2026-11-26 要求“按照计划书来进行优化，还是先在克隆库中修改”
- 工作位置：克隆库 `BARRY zou-search-motion`，分支 `feat/search-motion`。没有改主仓库，没有同步
- 编号：主仓库 `main` 已用到 T24ak（T24ah–T24ak 是克隆库对齐之后主仓库新加的），所以从 T24al 起编，避免同步时撞号
- 任务性质：小改动，不带 🔒；没有改表结构（`search_logs.channels` 本来就是 jsonb）、索引、接口应答、配置、附录 A，没有新依赖
- 修改者：Claude（Opus 5.5）

## 计划书六项的处理

计划书对六项的建议都是 A（不改代码）。按计划书执行，结果如下：

| # | 优化点 | 计划书的建议 | 这次做了什么 |
|---|---|---|---|
| 1 | CLIP 服务一次只算一个请求 | A 不改，T27 补测“一边处理一边检索” | 没有改 CLIP 服务。补测写进 DEVPLAN T27；T24al 的 `encode_ms` 让补测时能看出降级或变慢是不是出在编码（排队）这一段 |
| 2 | 可访问文档 ID 全部放进检索请求 | A 不改，写进论文“局限与改进” | 没有改代码。仓库里还没有论文稿，这一条留在 DEVPLAN §4，由 T28 写进局限 |
| 3 | 每个任务新开一个子进程 | A 不改 | 没有改。Windows 上的开销写进 DEVPLAN T27 |
| 4 | 两个文本通道依次执行 | A 不改；T27 前再决定要不要把图像通道的编码和向量检索分开计时 | 两个文本通道仍然依次执行。**分开计时这次做了（T24al，见下文）** |
| 5 | 每次写索引都立即刷新 | A 不改 | 没有改 |
| 6 | 每个任务开头检查索引 | A 保持 | 没有改 |

计划书里的 B、C、D 做法都没有做：它们要改附录 A3、A12 或 D26、D33 的决定，按 CLAUDE.md 要先由 Barry 批准。

## 为什么要分开计时

W3 里 clip-only 的 P50 是 96 ms，而 T00 在本机测的查询文本编码只要 20 ms。剩下的时间花在 Windows 上的编码、HTTP 往返还是向量精确检索，原来的日志分不出来：`search_logs.channels` 只记每个通道的总耗时 `took_ms`。计划书第 1 项的补测也需要知道：边处理边检索时，图像通道变慢或降级是不是因为查询在 CLIP 服务里排在 embed 后面。

## 逐文件修改记录

| 文件 | 位置 | 修改前 | 修改后 | 原因与影响 |
|---|---|---|---|---|
| `backend/app/modules/search/channels.py` | 新增 `ImageTimings`、`_elapsed_ms`；`search_image` 加可选参数 `timings` | 只返回结果，不分阶段计时 | 编码（`clip.encode_text`）和向量检索（`search_vectors`）各自计时，用 `finally` 写进调用方传入的 `ImageTimings`，所以阶段中途失败时（例如 CLIP 超时）已经花掉的时间也记得下来；没走到的阶段为 `None` | 计时只调用 `time.perf_counter()`，不改变检索流程和降级规则 |
| `backend/app/modules/search/service.py` | `ChannelReport` 加 `stages`；新增 `_channels_log`；`_run_image` | 检索日志 `channels` 每个通道 `{status, took_ms, detail, hits}` | 图像通道开启时，日志里 `image` 多两项 `encode_ms`、`vector_ms`（没走到的为 `null`）；其余通道和图像通道关闭时，结构与以前相同。成功、降级、意外错误、没有配置 CLIP 客户端四种情况都记 | `_write_log` 改为调用 `_channels_log`，生成的内容与以前相同（只多出图像通道的两项）。接口应答 `ChannelStatusOut` 是逐个字段构造的，没有变化 |
| `backend/tests/unit/test_search_service.py` | 假 OpenSearch 加 `delays`、假 CLIP 加 `delay`；新增 10 项 | — | 两个阶段分开计时（用等待时间模拟）；CLIP 超时只有编码时间；维度不一致不进入向量检索；向量索引出错和意外错误两个阶段都有；没有 CLIP 客户端时都是 `None`；日志只给图像通道加字段；图像通道关闭时日志结构不变；文本通道失败、没有等图像通道时不写这两项；接口应答没有这两项 | — |
| `backend/tests/integration/test_search_db.py` | `test_clip_service_down_degrades_to_text_search` 加 2 条断言 | — | 真实数据库里 `channels.image.encode_ms` 是整数、`vector_ms` 为 `null` | 需要 PostgreSQL，本机没有，**未运行** |
| `docs/data-model.md` | `search_logs.channels` | — | 写明图像通道的两项 | — |
| `docs/decisions.md` | D36“记录” | — | 补一段 T24al | — |
| `docs/untested.md`、`DEVPLAN.md`、`docs/changes/2026-11-26-后端优化分析.md` | — | — | 登记、任务与完成记录、T27 的测量项、计划书第 4 项的后续 | — |

## 两个阶段各包括什么

- `encode_ms`：调 CLIP 服务 `POST /encode/text` 的往返时间，包括 HTTP、在 CLIP 服务里等锁（排在 embed 的前向计算后面）和前向计算本身。CLIP 超时时约等于超时时间（默认 3 s）
- `vector_ms`：调 `search_vectors` 的往返时间，包括 HTTP 和 OpenSearch 的精确检索（`script_score`）；向量索引不存在时也包括建索引
- `took_ms` 减去两者：维度检查、整理证据、线程启动等，正常应当只有一两毫秒

T27 可以这样读（PostgreSQL）：`channels->'image'->>'encode_ms'`、`channels->'image'->>'vector_ms'`，按 `config` 里的实验配置分组。

## 验证

- 已运行（macOS，main 环境 Python 加 `PYTHONPATH` 指向克隆库，确认 `app`、`shared` 都从克隆库导入）：`backend/` pytest 821 passed、241 skipped（对齐后是 811 passed、241 skipped，新增 10 项都是单元测试）；`test_search_service.py` 70 项通过；ruff check、ruff format --check 通过。shared、OCR Worker、CLIP 服务、前端没有改动，没有重跑
- 反证：在临时 worktree 里用修改前的代码跑新的测试文件，新增 10 项中 9 项失败；没失败的一项是“接口应答没有这两项”，它检查的是不该变的东西，修改前本来就成立
- **未测试（Not Tested）**：`test_search_db.py::test_clip_service_down_degrades_to_text_search` 新增的 2 条断言（需要 PostgreSQL）；真实 CLIP 服务和 OpenSearch 上两个阶段的实际数字（只用假的网络层和等待时间测过）。已登记 `docs/untested.md`

## 代码复核（未运行部分）

- 集成测试：CLIP 端口上没有服务，`encode_text` 抛 `ClipError`（连接失败），`finally` 先写 `encode_ms` 再由 `except` 转成 `ImageChannelUnavailable`；`search_vectors` 没有调用，`vector_ms` 保持 `None`；`_channels_log` 把两项原样放进 dict，JSONB 里整数仍是整数、`None` 是 `null`。断言与单元测试 `test_clip_timeout_keeps_the_encoding_time_and_has_no_vector_time` 走的是同一条路径
- 兼容性：`search_image` 的新参数有默认值，其他调用方不用改（全仓库只有 `_run_image` 调用它）；实验运行器只读 `outcome.channels` 的 `status`，`results.jsonl` 的格式不变；前端只读接口应答，不受影响

## 修改建议（后续）

- 实验运行器的 `results.jsonl` 每条查询只记总耗时 `took_ms` 和各通道状态，不记各通道耗时。T27 要按通道统计 P50/P95 时，现在要从 `search_logs` 读；如果想直接从 `results.jsonl` 算，需要另开任务让运行器把各通道的 `took_ms` 和图像通道的两个阶段也写进去。由 Barry 决定，记在 DEVPLAN §4
