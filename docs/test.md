# test：T00–T19 待测试、待联调、未完成事项总表

整理日期：2026-11-15（T19 完成后，最新提交 `d2de104`）
整理依据：`DEVPLAN.md` §3–§5、`docs/untested.md`、`docs/decisions.md` D16–D32、`env_check/未测试/清单.md`。
本次整理**没有重新运行任何测试**，下面的数字全部取自上述记录。

> 本文件是汇总视图，便于 T19 之后统一安排正式测试。逐项测试名、补测命令和判断标准仍以 `docs/untested.md` 为准；某项跑通后，按 CLAUDE.md 的规则从 `untested.md` 删除，再回来勾掉本文件对应行。

------------------------------------------------------------------------

## 当前状态（2026-11-21 修正，最新提交 `e3a3278`，T24n 之后）

**下面 §0–§6 是 2026-11-15 的快照，其中很多项已经过时，以本节和 `docs/untested.md` 为准。** 本次修正只根据 DEVPLAN §5 和 `docs/untested.md` 的记录更新，**没有运行任何测试**，也没有新的原始测试数据（JUnit XML）。

| 项目 | 2026-11-15 的记录 | 现在 | 依据 |
|---|---|---|---|
| §2 未运行的自动化测试 | 188 项 | **3 项**（T24g 1 项、T24i 2 项，都需要 PostgreSQL）。原 188 项在 2026-11-16 Windows 补测中通过；T20–T24f 新增的 38 项在 2026-11-19 Windows 第二轮通过（只有汇总数字） | untested.md 开头两段、§1 |
| §3 🧪 没有运行结果的 | 17 条 | **0 条** | untested.md §2 |
| §4 联调 | 一次都没做过 | **部分完成**：2026-11-19 Windows 第二轮用真实 PostgreSQL、OpenSearch、OCR Worker、CLIP 服务走通注册登录、上传处理、OCR 检索、删除、共享与取消共享、CLIP 检索与降级、中文 PDF 预览。记录里没有按 §4 的 J1–J14 逐项对照，哪些 J 项算通过要等有逐项记录再定；J8 的 50 MB PDF、J11 崩溃恢复联调、J12 一致性检查、J13 实验流程、J14 管理员视角都没有记录；macOS 本机仍没有联调过 | untested.md §4“后端连上真实数据库后的整体运行” |
| 本机测试（记录值） | backend 540、shared 105、ocr_worker 63 + 4、frontend 48 | backend 718 通过、229 跳过（T24l）；shared 108（T24k）；ocr_worker 71 通过、4 跳过（T24l，main 环境）；frontend 70（T24n） | DEVPLAN §5 T24k–T24n |
| Windows 上运行 | 从未跑过 | 跑到 `50b244b`（T24f 之后）：8 项符号链接测试因 WinError 1314 失败，其余通过；T24g 之后的代码（含 T24k–T24n）没有在 Windows 上跑过 | untested.md §7 |
| 未完成的任务 | T00（部分）、T20–T32 | T00（部分）、T25–T32；T20–T24、T24a–T24i、T24k–T24n 已完成 | DEVPLAN §3 |
| 里程碑 | 基础系统、MVP-0、MVP-1 未达成 | 基础系统、MVP-0、MVP-1、MVP-2 都**没有打 tag**：DEVPLAN 里 MVP-0 剩余“前后端浏览器联调”，Windows 第二轮的联调能否算作 MVP-0 验收由 Barry 决定；MVP-1、MVP-2 还差评测数据集和标注 | DEVPLAN §3 里程碑行 |

> **T24s 补充（2026-11-21，前端界面优化）：** 上表的其余数字没有随之重核，只补前端：本机 frontend 93 项通过（10 个文件，新增 `channels.test.ts` 20 项），类型检查、生产构建通过；T24o–T24s 也已完成。T24s 改了全部页面的布局（侧栏、拖拽上传、检索通道面板、三格名次与 RRF 融合分），只对着临时模拟后端在 Chrome 内核的内置浏览器里截图核对过。新增 3 项未验证性质，已登记到 `docs/untested.md` 第 4 节“T24s 前端界面优化”：与真实后端联调（`/health` 和检索响应的真实字段、各通道状态的显示）、鼠标从文件管理器真实拖入文件、Chrome 以外的浏览器。§4 的联调路径里 J2（管理员标记现在在侧栏）、J3（上传改为拖拽区和逐个文件的上传记录）、J6（结果改为卡片，右侧三格名次和融合分）、J7、J14 要按新界面核对；Windows 第二轮的界面截图是 T24s 之前的样子。

仍未验证、写论文和测试报告时要照实说明的主要项目：Docker 与 compose、Linux `RLIMIT_AS`、并发与长时间运行、极端真实文件、正式检索评测（B0–B3 没有正式指标）、T24g 之后的代码在 Windows 和真实数据库上的运行。逐项见 `docs/untested.md` §4、§7。

------------------------------------------------------------------------

## 0. 一页结论

| 类别 | 数量 / 状态 | 阻塞原因 |
|---|---|---|
| 已写好但从未运行的自动化测试 | **188 项**（数据库集成 172 项 + OpenSearch 13 项 + 同时需要两者 3 项，见 §2） | 本机没有 PostgreSQL、OpenSearch（Barry 决定本机不用 Docker） |
| DEVPLAN 🧪 必测项中没有运行结果的 | **17 条**（T06、T07、T08、T13、T14、T15，见 §3） | 同上 |
| 前后端联调 | **一次都没做过**（T10、T16 只对着临时模拟接口检查） | 真实后端需要数据库 |
| 非测试类未验证性质 | 约 30 项（见 §5） | 真实环境、真实文件、Linux、Windows |
| 未达成的里程碑 | 基础系统、MVP-0、MVP-1（均未打 tag） | 上面三项 + 没有评测数据 |
| 未完成的任务 | T00（部分）、T20–T32 | — |

本机能跑的测试全部通过（记录值）：`backend/` 540 项、`shared/` 105 项、`services/ocr_worker/` 63 项（main 环境）+ 4 项真实识别（ocr 环境）、`frontend/` 48 项。

------------------------------------------------------------------------

## 1. 统一补测的前提条件（一次准备好，全部解锁）

| # | 需要什么 | 解锁哪些测试 | 说明 |
|---|---|---|---|
| E1 | PostgreSQL 16 + 空库 `docmgr_test`，设置 `TEST_DATABASE_URL` | §2 中全部数据库集成测试（172 项） | 库里已有表会直接失败，不会清库 |
| E2 | OpenSearch 2.19.1 + analysis-smartcn 插件，设置 `TEST_OPENSEARCH_URL` | T13 的 13 项 | 用 `deploy/docker-compose.yml` 构建；需要联网下插件 |
| E3 | E1 + E2 同时具备 | T14 的 2 项端到端、T15 的 1 项真实索引；`backend/` 全量 728 项 0 跳过 | 测试只用带随机前缀的索引 |
| E4 | 能运行 Docker 的机器（不一定是本机） | T00 剩余实测 OS-1～OS-7、compose 文件、`/health` | 下载项先征得 Barry 同意并登记 `docs/downloads.md` |
| E5 | 真实后端 + 真实前端 + E1 + E2 + 两个 Worker | 全部联调（§4） | 依赖 E1–E3 先通过 |
| E6 | 真实文件（Office/WPS 保存的 docx/xlsx、真实扫描件、手机照片、中文 PDF、大文件） | §5 中“真实文件”类 | 可在收集评测数据时顺带做 |
| E7 | Linux 机器 | 内存上限（Worker、OCR 子进程） | `RLIMIT_AS` 在 macOS 不生效 |
| E8 | 评测数据集 + 标注 | B0–B2 真实数字、MVP-1 | 由 Barry 负责，已滞后 |

推荐顺序：E1 → E2 → E3 → E5 → E6 → E8；E4、E7 可并行或放到部署前。

------------------------------------------------------------------------

## 2. 未运行的自动化测试（188 项）

| 任务 | 测试文件 | 项数 | 需要 | 代码复核情况 |
|---|---|---|---|---|
| T03 数据库迁移 | `backend/tests/integration/test_migrations.py` | 13 | E1 | 未复核（T03 当时曾在本地 PG 16.15 通过，当前机器无法重跑） |
| T06 认证与权限 | `backend/tests/integration/test_auth.py` | 19 | E1 | 已复核，未发现问题 |
| T07 任务框架 | `backend/tests/integration/test_task_queue.py` | 18 | E1 | 已复核；`shared/tasks.py` 全部 SQL 从未在数据库上执行 |
| T08 文档管理 | `backend/tests/integration/test_documents.py` | 41 | E1 | 已复核，改过 1 处断言 |
| T13 文本索引 | `backend/tests/opensearch/test_text_index_live.py` | 13 | E2 | 已复核；两个 mapping 从未被 OpenSearch 接受过 |
| T14 解析流水线 | `backend/tests/integration/test_pipeline_db.py` | 23 | E1（21 项）/ E3（2 项） | 已复核 |
| T15 检索 v1 | `backend/tests/integration/test_search_db.py` | 20 | E1（19 项）/ E3（1 项） | 已复核；局限见 D28 |
| T16 抽取文本接口 | `backend/tests/integration/test_document_text.py` | 11 | E1 | 已复核 |
| T17 OCR Worker 读写库 | `backend/tests/integration/test_ocr_worker_db.py` | 10 | E1 | 已复核 |
| T18 一致性检查 | `backend/tests/integration/test_consistency_db.py` | 12 | E1 | 已复核；首轮误删问题已修 |
| T19 实验框架 | `backend/tests/integration/test_experiments_db.py` | 8 | E1 | 已复核；结果目录重名、P@K 口径已修 |
| **合计** | | **188** | | |

补测命令（`backend/` 目录，main 环境）：

```bash
export $(grep '^TEST_DATABASE_URL=' ../.env) && ../.venv-main/bin/pytest
```

```bash
TEST_OPENSEARCH_URL=http://localhost:9200 ../.venv-main/bin/pytest tests/opensearch -v
```

```bash
export $(grep '^TEST_DATABASE_URL=' ../.env) && TEST_OPENSEARCH_URL=http://localhost:9200 ../.venv-main/bin/pytest
```

最后一条预期：728 项全部运行、0 跳过。逐项测试名见 `docs/untested.md` §3。

------------------------------------------------------------------------

## 3. DEVPLAN 🧪 必测项中没有运行结果的（17 条）

| 任务 | 🧪 要求 | 对应测试 | 有无替代验证 |
|---|---|---|---|
| T06 | 访问他人文档 403 | `test_auth.py::test_document_access_over_http` | 无 |
| T06 | 管理员可见全部 | `test_auth.py::test_admin_sees_all_documents` | 无 |
| T06 | 共享后可见、取消共享后不可见 | `test_auth.py::test_share_grants_access_and_unshare_revokes_it_immediately` | 无 |
| T07 | 崩溃恢复 | `test_task_queue.py::test_task_of_killed_worker_is_reclaimed_after_lease_expires` | 无（**里程碑“基础系统”的硬条件**） |
| T07 | 两个 Worker 不会领到同一任务 | `test_uncommitted_claim_is_skipped_not_waited_for`、`test_many_workers_never_claim_the_same_task` | 无（同上） |
| T07 | 幂等 | `test_task_executed_twice_does_not_duplicate_results` | 无（同上） |
| T07 | 超过重试上限标记 failed | `test_failing_task_is_retried_up_to_max_attempts_then_failed`、`test_crashing_task_is_failed_after_max_attempts_with_reason` | 无（同上） |
| T08 | 上传中途失败不留半成品 | `test_documents.py` 两项 | 假数据库会话版本已通过 |
| T08 | 删除后列表和下载都不可见 | `test_deleted_document_disappears_everywhere_immediately` | 无 |
| T08 | 非法类型被拒绝 | `test_unsupported_content_is_415_and_leaves_nothing` | 存储层类型识别已通过 |
| T13 | 重复索引不产生重复数据 | `test_text_index_live.py` 两项 | 模拟应答版本已通过 |
| T13 | 删除后查不到 | `test_deleted_document_cannot_be_found_in_either_index` | 模拟应答版本已通过 |
| T14 | 端到端：上传 PDF → 任务完成 → chunks 有数据 | `test_pipeline_db.py::test_upload_parse_index_then_delete_and_cleanup` | 假库假索引版本已通过 |
| T15 | 删除后立即查不到 | `test_search_db.py` 两项 | 替身版本已通过 |
| T15 | 取消共享后立即查不到 | `test_unsharing_removes_the_document_from_search_immediately` | 替身版本已通过 |
| T15 | 同一文件不重复出现 | `test_document_hit_by_both_channels_appears_once_with_both_ranks` | RRF 单元测试已通过 |
| T15 | 服务故障与“无结果”可区分 | `test_no_match_is_200_with_an_empty_list`、`test_search_service_down_is_503_search_unavailable` | 替身版本已通过 |

T17、T18 的 🧪 部分完成：T17 真实识别 4 项已在 ocr 环境通过，但“OCR 失败时任务标记 failed、原文件仍在”的数据库版本在 `test_ocr_worker_db.py` 里未运行；T18 的“三类不一致都能检测出来”在 `test_consistency_db.py` 里未运行（单元测试版本已通过）。T19 的指标手算样例已通过。

------------------------------------------------------------------------

## 4. 待联调（从未做过）

前端只对着临时模拟接口（按 `api.md` 写、未提交）在浏览器里检查过。字段名、状态码、multipart 细节这类前后端不一致，模拟接口发现不了。

| # | 联调路径 | 来自 | 通过标准 |
|---|---|---|---|
| J1 | 后端 + PostgreSQL 启动；`alembic upgrade head`；`/health` | T01、T03 | database、opensearch 为 ok，clip_service 为 unavailable，整体 degraded |
| J2 | 注册 → 登录 → me；管理员 `create-admin` 后登录 | T06、T10 | 前端登录页可登录，管理员标记显示 |
| J3 | 上传 PDF、Word、Excel、图片 → 列表状态 pending → processing → succeeded | T08、T10、T14 | 前端自动刷新看到状态变化；坏文件显示 failed 和原因 |
| J4 | 下载、删除、共享给另一用户、取消共享、改标签 | T08、T10 | 删除后列表和下载立即不可见；被共享者只读 |
| J5 | 扫描版 PDF / 独立图片 → OCR Worker 处理 → OCR 文字可检索 | T14、T17 | 检索范围选 ocr 时能命中 |
| J6 | 检索页：文件名命中、正文命中、两路都命中只出现一次 | T15、T16 | 结果带高亮、位置、通道名次 |
| J7 | 检索页：停掉 OpenSearch → 503 提示；正常但无匹配 → 空结果提示 | T15、T16 | 两种提示文字不同 |
| J8 | 预览：PDF 跳到命中页、Word 滚到命中段、Excel 显示范围、图片原生显示 | T16 | 用中文 PDF 和接近 50 MB 的 PDF 各试一次 |
| J9 | 高亮转义：正文含 `<script>` 的文档被检索 | T15、T16（OS-10） | 摘要显示为文字，只有 `<em>` 是标签 |
| J10 | 删除后立即搜不到；取消共享后被共享者立即搜不到 | T15 | 不等 cleanup 任务 |
| J11 | Worker 崩溃恢复：处理中 kill 通用 Worker → 租约过期 → 重新领取 → 无重复片段 | T07、T14 | 同时看数据库和索引 |
| J12 | 一致性检查：`check` 在正常系统上 0 问题；人为删文件、删索引、改版本后能检出并 `repair` | T18 | 按 D31 退出码 |
| J13 | 实验：`validate` → `import` → 两个 Worker 处理完 → `run --config ../experiments/configs/B1.json` | T19 | 产出 `experiments/runs/` 三个文件和 `experiment_runs` 一行 |
| J14 | 管理员视角：看到全部文档、“管理员可见”来源标记 | T10 | 模拟接口里从未显示过 |

**MVP-0 验收**（DEVPLAN §4 T16 记录）：J1–J4、J6、J8、J10 通过 + §2 全部集成测试通过后，打 tag `mvp-0`。

------------------------------------------------------------------------

## 5. 非测试类、同样未验证的性质

### 5.1 环境与部署

| 项目 | 现状 | 记录 |
|---|---|---|
| T00 OS-1～OS-6：OpenSearch 启动、分词对比、BM25 延迟、`script_score` 向量检索、JVM 堆、四组件并发内存 | 未测 | `env_check/未测试/清单.md`、`untested.md` §6 |
| A13 选 smartcn | Barry 已选定，但没有实测数据 | decisions A13 |
| A14 是否启用降级预案 | 依赖 OS-5、OS-6，未定（按不启用实现） | decisions §2 |
| `deploy/docker-compose.yml` | 只用 Ruby 读过 YAML 结构，容器从未启动，`docker compose config` 未跑 | T01 |
| `deploy/opensearch/Dockerfile` | 从未构建 | D26 |
| `action.auto_create_index: "false"` 是否生效、不影响 `ensure_indices` | 未验证 | D27 |
| mapping 随 shared 普通安装打包 | 只做过 editable 安装 | D26、D30 |
| Windows 上运行 | 有两处兼容处理，从未在 Windows 跑过 | — |
| Linux 上的内存上限（通用 Worker 子进程、OCR 子进程） | macOS 不生效 | D16、D30 |

### 5.2 OpenSearch 实际行为

| 项目 | 记录 |
|---|---|
| 两个 mapping（smartcn 分析器、改默认相似度、`dynamic: strict`、`locator` `enabled: false`）能否被 2.19.1 接受 | D26 |
| T15 查询体：`collapse` + `sort` + `highlight`（`encoder=html`、`no_match_size`）同时使用；`multi_match` 小数权重 | D28 |
| smartcn 下高亮摘要的位置与长度 | D28 |
| 一致性检查的 `search_after` 扫描、`_mapping`/`_settings` 结构比对、单文档重建、`rebuild-indices` | D31 |

### 5.3 真实子进程与时序

| 项目 | 记录 |
|---|---|
| `handle_parse`、`handle_cleanup`、`task_context` 在真实 Worker 子进程里运行（读 `.env`、自己连库和索引） | D27 |
| `shared/tasks.py` 在 T14 新增的 `RETURNING ...` 和 `_MARK_DOCUMENTS_FAILED_SQL` | D27 |
| cleanup 硬删除与父进程续租的时序（级联删任务后续租判为租约丢失） | D27 |
| 解析超时对真的卡住的解析器生效（端到端） | D24 |
| OCR Worker 完整链路：领取 → 识别 → 写 OCRResult/DocumentChunk → 写索引 → 复查 | D30 |

### 5.4 真实文件

| 项目 | 记录 |
|---|---|
| PDF 解析器：真实扫描件、多栏、带表格、带水印；阈值 20 无实验依据 | D20 |
| Word/Excel/图片解析器：Office/WPS 实际保存的文件、手机照片；Excel 公式缓存值 | D24 |
| zip 200 MB / 5000 条目 / 1 亿像素上限：接近上限的大文件的内存与耗时 | D24 |
| OCR：真实扫描件、手机照片、多栏、竖排、手写 | D30 |
| PDF 预览：中文、扫描件、接近 50 MB、加密 PDF | D29 |

### 5.5 前端

| 项目 | 记录 |
|---|---|
| 页面组件没有自动化测试（项目没有组件测试工具，加装要 Barry 同意） | D22、D29 |
| 上传前不检查文件大小，超限要传完才被拒 | DEVPLAN §4 |
| 打包体积：主包约 874 KB、pdf.worker 约 1.27 MB 超过 500 KB 提示 | DEVPLAN §4 |
| T24s 界面优化：只对着临时模拟后端检查；拖拽上传只用脚本派发的 drop 事件；只在 Chrome 内核的浏览器里看过（2026-11-21 补） | untested.md 第 4 节 T24s、D48 |

### 5.6 实验与参数（阶段五才有数据）

| 项目 | 记录 |
|---|---|
| B0–B2 从未在真实数据上运行；没有评测数据集和标注 | D32 |
| 切分 500/50、是否给 Excel 片段补表头 | D25、DEVPLAN §4 |
| RRF k=60、截断深度 100、两项字段权重 1.0 | D28 |
| `OCR_MIN_CONFIDENCE`、`OCR_PDF_DPI` 没有记进实验配置 | D32、DEVPLAN §4 |
| CER 评测、性能实验 | T27 |

------------------------------------------------------------------------

## 6. 未完成的任务与里程碑

### 6.1 任务

| 任务 | 状态 | 剩余内容 |
|---|---|---|
| T00 环境实测 | 部分完成 | OpenSearch、分词、并发内存（§5.1）；OCR 只用 3 张合成图，CER 区分不出两个模型 |
| T20 CLIP 服务 🔒 | 已完成（2026-11-21 修正） | 见 DEVPLAN §5 T20 |
| T21 图片向量与 M10 | 已完成（2026-11-21 修正） | 见 DEVPLAN §5 T21、decisions.md D35 |
| T22 检索 v2 + RRF 🔒 | 已完成（2026-11-21 修正） | 见 DEVPLAN §5 T22、decisions.md D36 |
| T23 前端 v2 | 已完成（2026-11-21 修正） | 见 DEVPLAN §5 T23 |
| T24 B3 与消融 | 已完成（2026-11-21 修正），T24a–T24i、T24k–T24s 也已完成 | B3 与消融从未在真实数据上运行（untested.md §4） |
| T25–T28 实验 | 未开始 | 依赖评测数据 |
| T29–T32 论文与答辩 | 未开始 | T30 前要补根目录 `README.md` |

### 6.2 里程碑

| 里程碑 | 状态 | 缺什么 |
|---|---|---|
| 方案评审 | 已通过（2026-11-13） | — |
| 基础系统 | **未达成** | T07 四项 🧪、其余数据库集成测试、前后端联调 |
| MVP-0（tag `mvp-0`） | **未达成** | §2 全部 + §4 J1–J4、J6、J8、J10 |
| MVP-1（tag `mvp-1`） | **未达成** | MVP-0 + OCR 可检索联调（J5）+ 评测数据 + B0–B2 真实数字 |
| MVP-2 | 未开始 | T20–T24 |

------------------------------------------------------------------------

## 7. 待 Barry 决定的事项（不是测试，但会影响测试或验收）

> 2026-11-19：下面 1–5 项已由 Barry 统一决定（`decisions.md` D39）：1 排为 T24a；2 已确认；3 排为 T24e；4 暂缓；5 中 `/health` 排为 T24b，其余写进论文局限。第 6 项仍由 Barry 负责。

1. 通用 Worker 启动时不检查数据库、OCR Worker 启动即退出，是否统一（DEVPLAN §4 T18 记录）。
2. qrels `grade` 0–3 各等级的含义（`experiments/README.md` 里是建议写法）。
3. 文本预览接口中 OCR 片段是否按页码穿插（现在排在正文之后）。
4. Word 片段是否增加结束段落字段（数据契约变更）。
5. 答辩可能被问到的安全项：登录无尝试次数限制、无用户存储配额、`/health` 的 `detail` 暴露内部主机名和端口。
6. 评测数据收集（200–500 个文件）与每周标注尽快开始。
