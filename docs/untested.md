# 未测试清单（Not Tested）

更新日期：2026-11-19（T24 完成后；同日按 Barry 批准整理）

这里列出**已经写好但从未实际执行过**的测试，以及其他没有经过验证的性质。
规则来自 GLOBAL.md“测试执行限制与代码验证要求”：跑不了的测试不强行执行、不安装工具，
在这里如实登记，并对相关代码做人工复核。

> **2026-11-19 整理（Barry 批准）：** 已在 2026-11-16 Windows 补测中实际通过的项目从本文件删除，包括：原第 3 节的 11 个连调文件（T03、T06、T07、T08、T13、T14、T15、T16、T17、T18、T19，共 190 项，含原第 2 节列出的全部 🧪）、第 6 节的 OS-1、OS-3、OS-4、OS-5、OS-8、OS-9、OS-10，以及第 4 节中因此得到验证的 7 行（两个 mapping 被 OpenSearch 接受、检索查询体被接受、高亮转义、`shared/tasks.py` 的 SQL、真实子进程里的处理函数、OCR Worker 完整链路、OpenSearch 启动与 smartcn 分词）。补测环境：Windows 11、Python 3.14.0、PostgreSQL 16.15、OpenSearch 2.19.1 + analysis-smartcn；证据在 `change-deepseek-v4/`（JUnit 原始结果 `test-results/integration-results.xml`），记录见 DEVPLAN §5“T00–T19 补测”“修复合入”。
>
> 两点限制，写论文和测试报告时要照实说明：（1）通过的是 Windows 上的验证副本，本仓库在 macOS 上没有 PostgreSQL 和 OpenSearch，没能复跑；副本与本仓库在合入 C01–C12 后逐行一致。（2）2026-11-16 之后，T21–T24 和 D34 的复核修正又改过部分代码路径（检索编排、实验框架、一致性检查、cleanup），这些改动之后上述 190 项没有再跑过；它们新增的测试仍登记在下面。
>
> 计数：本机 backend 跳过 212 项，其中 188 项属于上述 11 个文件（Windows 上同一批文件收集到 190 项，差异来自 `test_migrations.py`、`test_auth.py` 各多 1 项），剩下 24 项见第 1 节。

**复核不等于测试通过。** 本文件中的任何一项，在实际运行通过之前，都不能在论文、测试报告或答辩中写成“已验证”。

维护方式：每完成一个任务，把新增的未测试项加进来；某一项实际运行通过后，从这里删除，并在 DEVPLAN §5 对应任务的备注里写明运行环境和结果。

## 1. 汇总

| 任务 | 测试文件 | 未测试项数 | 原因 | 代码复核 |
|---|---|---|---|---|
| T22 检索 v2 | `backend/tests/integration/test_search_db.py` 中 T22 新增的 1 项 | 1 | 本机没有 PostgreSQL（该文件其余 20 项已在 Windows 补测中通过） | 已复核；局限见 `decisions.md` D36 |
| T15–T19 复核修正、T24 | `backend/tests/integration/test_experiments_db.py` 中 D34 新增的 3 项和 T24 新增的 4 项 | 7 | 本机没有 PostgreSQL（该文件其余 8 项已在 Windows 补测中通过） | 已复核，见 `decisions.md` D34、D38 |
| T21 图片向量（embed 任务） | `backend/tests/integration/test_embed_db.py` | 8 | 本机没有 PostgreSQL | 已复核；复核发现的两处问题已修复，见 `decisions.md` D35 |
| T21 向量索引 | `backend/tests/opensearch/test_vector_index_live.py` | 8 | 本机没有 OpenSearch | 已复核；检索写法与 T00 在 2.19.1 上实测通过的一致 |
| **合计** | | **24** | | 与本机 backend 跳过的 212 项减去已补测的 188 项一致 |

T05（存储）、T09（PDF 解析器）、T11（Word、Excel、图片解析器）和 T12（切分）不需要数据库，它们的测试全部在本机执行并通过，没有未测试项。

对照：2026-11-19（T24）本机实测 `backend/` 678 项通过、212 项跳过，`shared/` 105 项通过。

## 2. 影响最大的几项

原来列在这里的 T06、T07、T08、T13、T14、T15 的 🧪 测试已在 2026-11-16 Windows 补测中通过（见文件开头）。**里程碑“基础系统”要求的 T07 四项测试已满足（在 Windows 验证副本上）。** 仍未运行的 🧪：

| 任务 | DEVPLAN 要求 | 对应测试 | 状态 |
|---|---|---|---|
| T21 | 重复图片只编码一次 | `test_embed_db.py::test_duplicate_images_are_encoded_once`、`test_concurrent_tasks_for_the_same_content_encode_once` | 未测试（假对象版本已通过，见 `tests/unit/test_embed.py`） |
| T21 | 过滤后只返回有权限的文档 | `test_vector_index_live.py::test_filter_returns_only_accessible_documents` 等 3 项 | 未测试（模拟应答版本已通过，见 `tests/unit/test_vector_index.py`） |
| T22 | 关闭 CLIP 服务后检索仍然正常并带降级标记 | `test_search_db.py::test_clip_service_down_degrades_to_text_search` | 未测试（假网络层版本已通过） |

## 3. 逐项清单

括号里的数字是该测试的参数化用例数，未标注的为 1。

### T22 `test_search_db.py`（1）

需要 PostgreSQL：

- 🧪 `test_clip_service_down_degrades_to_text_search`（CLIP 地址指向没有服务的端口：200，文本结果照常，image 为 unavailable 且 detail 不含地址，没有向 `image_vectors` 发查询，检索日志记录降级）

### D34、T24 `test_experiments_db.py`（7）

需要 PostgreSQL，检索服务用假的：

- D34 新增：`test_preflight_reports_failed_ocr_tasks_of_the_current_version`、`test_documents_outside_the_dataset_are_counted`、`test_import_replaces_a_changed_file_and_deletes_the_old_document`（复核说明见第 4 节“T15–T19 复核修正”）
- T24 新增（CLIP 用假的网络层或不可达的端口）：`test_image_preflight_counts_images_without_a_vector_of_the_current_model`、`test_image_preflight_reports_clip_down`、`test_b3_refuses_to_run_when_clip_is_down`、`test_rrf_k_override_is_used_and_recorded`

### T21 `test_embed_db.py`（8）

需要 PostgreSQL。CLIP 服务和检索服务用假的：

- 🧪 重复图片只编码一次：`test_duplicate_images_are_encoded_once`、`test_concurrent_tasks_for_the_same_content_encode_once`（并发版本，验证咨询锁）
- `test_different_content_gets_separate_vectors`、`test_rerunning_a_task_does_not_add_rows`
- 失败与删除：`test_rejected_image_leaves_no_row_and_releases_the_lock`、`test_embeddings_survive_document_deletion`、`test_deleted_document_is_skipped`
- parse 建 embed 任务：`test_parsing_an_image_creates_one_embed_task`

单元测试 `tests/unit/test_embed.py` 用假对象验证了同样的“只编码一次”分支（已通过），但咨询锁、`ON CONFLICT DO NOTHING` 和真实事务都没有执行过。

### T21 `test_vector_index_live.py`（8）

需要 OpenSearch：

- `test_exact_search_ranks_by_similarity`
- 🧪 过滤后只返回有权限的文档：`test_filter_returns_only_accessible_documents`、`test_empty_accessible_set_returns_nothing`、`test_unknown_document_ids_in_the_filter_are_harmless`
- `test_vectors_of_another_model_are_not_compared`
- `test_rewriting_an_image_overwrites_instead_of_adding`、`test_deleted_document_is_no_longer_found`
- `test_search_before_any_vector_creates_the_index`

单元测试 `tests/unit/test_vector_index.py` 用模拟应答验证了请求体（已通过）。

## 4. 不是测试、但同样没有验证过的性质

| 项目 | 说明 | 记录位置 |
|---|---|---|
| Worker 子进程的内存上限 | 用 `RLIMIT_AS` 实现，只在 Linux 上有效；开发机是 macOS，内核基本不执行这个限制 | `decisions.md` D16 |
| 后端连上真实数据库后的整体运行 | 没有在本机启动过“后端 + PostgreSQL”，注册、上传、下载等接口没有人工点过一遍 | — |
| `deploy/docker-compose.yml` | 只校验过语法，容器从未启动 | DEVPLAN §5 T01 |
| 前端与真实后端的联调 | **未测试。** 本机没有 PostgreSQL，真实后端的登录、上传等接口跑不起来。T10 的页面是对着一个临时写的模拟接口在浏览器里检查的（模拟接口按 `api.md` 的结构应答，不是项目代码，没有提交）。前端与真实后端之间的不一致——字段名、状态码、multipart 的细节——这种检查发现不了。T16 的检索页、预览页和抽取文本接口同样只对着模拟接口检查过（检索、PDF 跳页、Word 跳到命中段、图片、503 与空结果的区分），从未与真实后端和真实 OpenSearch 联调 | DEVPLAN §5 T10、T16 |
| 前端页面组件的自动化测试 | 没有写，项目里也没有组件测试工具（加装需要 Barry 同意）。48 项前端单元测试只覆盖接口封装、格式化、摘要清洗和位置格式；登录页、文件列表、共享对话框、检索页、预览页、PDF 查看器只做过人工浏览器检查 | DEVPLAN §5 T10、T16 |
| PDF 预览在真实文件上的表现 | 只用模拟接口返回的一份 5 页、纯英文、PyMuPDF 现场生成的测试 PDF 验证过跳页、翻页、缩放。没有用中文、扫描件、大文件（接近 50 MB）或加密的 PDF 试过 | `decisions.md` D29 |
| 真实后端经开发代理的访问 | **部分验证。** T05–T10 核查时启动了真实后端（数据库地址指向不存在的端口）和真实的前端开发代理，用 curl 验证了不需要数据库的路径：健康检查、数据库不可用返回 503、未登录 401、参数校验 422、未登录上传（multipart 经代理）401、超大上传 413。需要数据库的路径（登录成功之后的一切）仍未验证 | DEVPLAN §5 核查记录 |
| Windows 上的运行 | 2026-11-16 在 Windows 11 上跑过 backend 完整套件（728 项）；其中 8 项符号链接测试在普通权限下失败（WinError 1314，环境权限问题），以管理员权限重跑后通过。T21 之后的代码没有在 Windows 上跑过 | DEVPLAN §5“T00–T19 补测” |
| 管理员视角的前端 | 模拟接口里没有管理员账号，页面上“管理员”标记和“管理员可见”来源没有实际显示过 | — |
| PDF 解析器在真实文件上的表现 | T09 的测试用 PyMuPDF 现场生成的 PDF；没有用真实的扫描件、多栏排版、带表格或带水印的 PDF 验证过，阈值 20 也没有实验依据 | `decisions.md` D20 |
| Word、Excel、图片解析器在真实文件上的表现 | T11 的测试文件是用 python-docx、openpyxl、PyMuPDF 现场生成的；没有用 Microsoft Word / Excel / WPS 实际保存的文件、手机或相机拍的照片验证过。尤其是 Excel 公式的缓存值，测试里是手工改 XML 模拟的 | `decisions.md` D24 |
| 解析超时对真实解析器的作用 | 超时在 Worker 子进程边界执行，机制本身有测试（`test_worker_runner.py`）；但解析器要到 T14 才接入 Worker，“一个真的卡住的解析被杀掉”还没有端到端跑过 | `decisions.md` D24 |
| mapping 文件随安装包发布 | T17 起 mapping 在 `shared/text_index/mappings/`，`shared/pyproject.toml` 声明了 package-data（`shared.text_index` 下的 `mappings/*.json`）。两个环境都是 editable 安装，没有做过普通安装来验证文件确实被打包。验证方法：在一个临时虚拟环境里 `pip install ./shared`（会联网下载依赖，按规则先征得同意），然后确认 `site-packages/shared/text_index/mappings/` 下有两个 JSON 文件 | `decisions.md` D26、D30 |
| B0–B2 实验 | 从未在真实数据上运行过：现在没有评测数据集和标注；也从未连真实 PostgreSQL 和 OpenSearch 跑过导入和运行。指标计算本身已用手算样例验证（单元测试） | `decisions.md` D32 |
| 一致性检查对真实 OpenSearch 的操作 | 索引扫描（`search_after` 分页）、结构检查（`_mapping`、`_settings` 的返回结构）、单个文档重建和 `rebuild-indices` 全部重建都从未在真实 OpenSearch 上运行过；单元测试和集成测试里的应答是按文档写的 | `decisions.md` D31 |
| 一致性检查在真实数据上的运行 | 从未对一个真实使用过的系统跑过 `check` 和 `repair`，误报率、耗时和内存占用都没有数据 | `decisions.md` D31 |
| OCR 在真实文件上的表现 | 只用 PyMuPDF 现场生成的扫描版 PDF 页、图片和空白图验证过；没有真实扫描件、手机照片、多栏排版、竖排或手写文字 | `decisions.md` D30 |
| OCR 子进程的内存上限 | `OCR_WORKER_MEMORY_LIMIT_MB` 用 `RLIMIT_AS` 实现，只在 Linux 上有效；本机（macOS）启动时打印“无法设置识别子进程的内存上限”，只受超时保护。没有在 Linux 上验证过 | `decisions.md` D16、D30 |
| `deploy/opensearch/Dockerfile` | 从未构建过。安装 analysis-smartcn 需要联网 | `decisions.md` D26 |
| `deploy/docker-compose.yml` 的语法 | 只用 macOS 自带的 Ruby 读过一遍 YAML，确认结构和 `build`、`image` 两项能读出来；没有用 `docker compose config` 校验过（本机没有 Docker），compose 自己的规则没有检查 | — |
| smartcn 的切分效果 | A13 选定时没有任何实测数据，切分是否合理、对 B0–B2 的影响要到阶段五 | `decisions.md` A13 |
| `action.auto_create_index: "false"` | 只写进了 `deploy/docker-compose.yml`，没有在真实 OpenSearch 上确认它生效、也没有确认它不影响 `ensure_indices` 显式建索引 | `decisions.md` D27 |
| cleanup 硬删除与续租的配合 | 硬删除后任务记录被级联删除，父进程的下一次续租会把子进程按“租约丢失”终止。代码把硬删除放在最后一步来规避，但真实时序没有观察过 | `decisions.md` D27 |
| 切分参数对检索效果的影响 | 默认 500 字、重叠 50 字是经验值。“片段长度、重叠、是否给 Excel 片段补表头”对 B1、B2 的影响要到阶段五才有数据 | `decisions.md` D25 |
| zip 与像素上限的默认值 | 200 MB、5000 个条目、1 亿像素都是经验值；没有用接近上限的真实大文件测过解析时的内存和耗时 | `decisions.md` D24 |
| smartcn 下的高亮效果 | 摘要是否落在命中词附近、长度是否接近 `SEARCH_SNIPPET_CHARS`，没有实际看过 | `decisions.md` D28 |
| `scripts/smoke/ocr_e2e.py`（N01 烟测，2026-11-19 放进仓库） | 原版在 2026-11-16 Windows 补测中 PASS；放进仓库时改了解释器路径、连接串来源和清理逻辑（D39），改写后没有实际运行（本机没有 PostgreSQL 和 OpenSearch）。只验证了 ruff 检查、能编译、缺 `TEST_DATABASE_URL` 时退出码 2 | `decisions.md` D39 |
| IK 分词、并发内存 | T00 环境实测中仍未完成的部分：IK（没有匹配 OpenSearch 2.19.1 的版本）和 OS-6。OpenSearch 启动、smartcn 分词、BM25 与精确向量检索已在 2026-11-16 Windows 补测中完成 | 第 6 节 |

### T20 CLIP 服务（2026-11-17 登记）

T20 的测试都在本机实际运行过（接口测试 39 项，真实模型测试 17 项，见 DEVPLAN §5 T20）。下面是没有验证过的性质：

| 项目 | 说明 | 记录位置 |
|---|---|---|
| CPU 以外的设备 | `CLIP_DEVICE=mps`、`cuda` 从未运行；只核对过“选了不支持的设备就报错退出”的代码 | `decisions.md` D33 |
| 其他操作系统 | 只在 macOS（arm64）上运行过。Windows、Linux 没有测，clip 环境也没有在别的机器上按 requirements.txt 重建过 | `decisions.md` D33 |
| 跨机器的向量一致性 | 同一输入向量稳定只在同一进程里验证过；不同机器、不同 torch 版本之间是否逐位相同没有验证 | `decisions.md` D33 |
| 后端 `/health` 对着真实 CLIP 服务 | 后端的检查只看 `GET /health` 是否 200，已用 curl 确认服务返回 200；没有同时启动后端实际看一次 `clip_service: ok` | `api.md` §3、§9.1 |
| 真实图片 | 测试图片都是现场生成的纯色或色块图。真实照片、带 EXIF 的手机照片、渐进式 JPEG、接近 50 MB 的大图没有测 | — |
| 并发与长时间运行 | 没有并发压测，没有长时间运行观察内存；吞吐和内存留给 T27 | DEVPLAN T27 |
| 端口被占用 | 没有测；按 uvicorn 的行为会报错退出 | — |
| OCR 与 CLIP 同时运行的内存（OS-6） | 现在 CLIP 服务已有，可以补测，尚未做 | 第 6 节 |

### T15–T19 复核修正（2026-11-17 登记，见 `decisions.md` D34；其中 3 项测试也列在第 3 节）

| 项目 | 原因 | 代码复核 |
|---|---|---|
| `test_experiments_db.py::test_preflight_reports_failed_ocr_tasks_of_the_current_version` | 需要 PostgreSQL | 已复核：查询只用到 `processing_tasks` 的 `document_id`、`task_type`、`status`、`payload` 四列，版本比较在 Python 里做 |
| `test_experiments_db.py::test_documents_outside_the_dataset_are_counted` | 需要 PostgreSQL | 已复核 |
| `test_experiments_db.py::test_import_replaces_a_changed_file_and_deletes_the_old_document` | 需要 PostgreSQL | 已复核：软删除用的是文档接口同一个 `soft_delete_document` |
| `consistency repair` 在检索服务不可用时的提示与退出码 1 | 命令要连数据库，本机没有 | 已复核；没有自动化测试 |
| `consistency repair --fix index`、`rebuild-indices` 给解析失败的文档写回 `doc_meta` | 完整路径需要 PostgreSQL；`reindex_document` 本身有单元测试（已通过） | 已复核 |
| OCR 识别子进程忽略 Ctrl-C | 没有在终端里对着正在识别的 Worker 实际按过 | 已复核；子进程启动与识别的现有测试（含 ocr 环境真实识别 4 项）通过 |
| PDF 预览的绘制排队 | 只对着临时模拟接口、用一份 5 页的测试 PDF 检查过；没有自动化测试 | 已复核 |


### T21 图片向量与向量索引（2026-11-19 登记，见 `decisions.md` D35）

| 项目 | 说明 | 记录位置 |
|---|---|---|
| 向量检索在真实 OpenSearch 上运行 | `image_vectors` 的 mapping（不开 `index.knn` 的 `knn_vector`）和 `search_vectors` 的查询体（`script_score` + `knn_score` + `cosinesimil`，前置过滤、按 `document_id` 折叠）从未被本项目代码发给真实 OpenSearch。写法与 T00 在 2.19.1 上实测通过的 `env_check/01_check_opensearch.py` 一致，但 collapse 与排序的组合没有实测 | `decisions.md` D35 |
| embed 端到端 | 从未连真实 CLIP 服务、PostgreSQL、OpenSearch 和真实 Worker 子进程跑过：上传图片 → parse 建 embed 任务 → 编码 → 写 `image_embeddings` → 写索引 | `decisions.md` D35 |
| 一致性检查的向量部分 | 向量相关的采集、5 种新检测项、`embeddings` 修复和带向量的重建从未在真实数据和真实 OpenSearch 上运行过；只有单元测试（假对象） | `decisions.md` D35 |

### T22 检索 v2：图像通道（2026-11-19 登记，见 `decisions.md` D36）

| 项目 | 说明 | 记录位置 |
|---|---|---|
| 图像通道的查询体在真实 OpenSearch 上运行 | 与 T21 相同：`search_vectors` 的查询体从未发给真实 OpenSearch；T22 只是从检索编排调用它 | `decisions.md` D35、D36 |
| 对着真实 CLIP 服务编码查询 | `encode_text` 只对假网络层测过；从未连真实 CLIP 服务，也没有用真实向量在真实索引里检索过“文本找图片” | `decisions.md` D36 |
| 并行线程在真实负载下的表现 | 图像通道在单独线程里执行，单元测试只覆盖功能；没有在真实后端、并发请求下观察线程、连接和耗时 | `decisions.md` D36 |
| 3 秒查询超时是否合适 | 没有实测：CLIP 在 CPU 上编码一条查询的耗时、embed 批量编码时排队多久都没有量过，留给 T27 | `decisions.md` D36 |

### T23 前端 v2（2026-11-19 登记，见 `decisions.md` D37）

前端单元测试（缩略图加载、命中依据、降级提示）在本机执行并通过；浏览器检查只对着临时模拟后端做过。以下没有验证：

| 项目 | 说明 | 记录位置 |
|---|---|---|
| 与真实后端、真实 CLIP 服务联调 | 缩略图（真实下载接口、真实图片大小）、图片证据、通道标记和图像通道降级提示，都没有在真实后端 + 真实 CLIP 服务 + OpenSearch 上看过 | `decisions.md` D37 |
| 检索页组件的自动化测试 | `SearchView.vue` 没有组件测试；开关、地址栏、缩略图显示只靠浏览器手动检查 | `decisions.md` D37 |

### T24 B3 与消融配置（2026-11-19 登记，见 `decisions.md` D38）

| 项目 | 说明 | 记录位置 |
|---|---|---|
| B3 及消融在真实数据上运行 | B3、B3-no-ocr、B3-no-clip、clip-only、B3-k10/k30/k100 从未在真实数据、真实 PostgreSQL + OpenSearch + CLIP 服务上运行过；评测数据集也还没有 | `decisions.md` D38 |
| 图像通道运行前检查 | 缺向量的统计（`image_assets` 左连接 `image_embeddings`）只写了集成测试，未运行 | `decisions.md` D38 |
| MVP-2 里程碑 | 未达成，没有打 tag `mvp-2` | `decisions.md` D38 |

## 5. 补测方法

需要一个 PostgreSQL 16 实例和一个**空的**专用测试库（库里已有表时测试会直接失败，不会清库）。

1. 建库 `docmgr_test`，把连接串写进 `.env` 的 `TEST_DATABASE_URL`（格式见 `.env.example`）。
2. 在 `backend/` 目录执行：

   ```bash
   export $(grep '^TEST_DATABASE_URL=' ../.env) && ../.venv-main/bin/pytest
   ```

3. 预期结果：除 `tests/opensearch/` 的 13 项、`test_pipeline_db.py` 的 2 项端到端测试和 `test_search_db.py` 的 1 项真实索引测试外全部运行。两类都补测时的预期见下面的“OpenSearch 测试”。
4. 有失败的话先修；全部通过后更新本文件和 DEVPLAN §5。

在另一台机器上补测时，把那台机器的系统和 PostgreSQL 版本一起记下来。

**OpenSearch 测试（T13 的 13 项、T14 的 2 项端到端、T15 的 1 项）**

需要一个装了 analysis-smartcn 插件的 OpenSearch 2.19.1。最简单的办法是用项目自己的 `deploy/docker-compose.yml` 启动（第 6 节第 6 步），它会构建带插件的镜像。

1. 确认插件已装：`curl -s "http://127.0.0.1:9200/_cat/plugins?v"` 的输出里有 `analysis-smartcn`。
2. 在 `backend/` 目录执行：

   ```bash
   TEST_OPENSEARCH_URL=http://localhost:9200 ../.venv-main/bin/pytest tests/opensearch -v
   ```

3. 测试只使用形如 `test_xxxxxxxxxx_doc_meta` 的独立索引，结束时只删除自己建的索引，不碰 `doc_meta`、`chunks` 正式索引。即使这样，也不要对着有真实数据的 OpenSearch 运行。
4. 预期结果：13 项全部通过。最先可能失败的是创建索引（mapping 写法不被接受），报错会写明是哪个字段或设置。
5. T14 的 2 项端到端测试同时需要数据库和 OpenSearch，并且会启动真实的 Worker 子进程。在 `backend/` 目录执行：

   ```bash
   export $(grep '^TEST_DATABASE_URL=' ../.env) && TEST_OPENSEARCH_URL=http://localhost:9200 ../.venv-main/bin/pytest tests/integration/test_pipeline_db.py -v
   ```

   测试会把配置写进环境变量，交给子进程读取（环境变量优先于 `.env`）；索引同样使用带随机前缀的独立索引。
6. T15 的 1 项真实索引测试同样需要两者，在 `backend/` 目录执行：

   ```bash
   export $(grep '^TEST_DATABASE_URL=' ../.env) && TEST_OPENSEARCH_URL=http://localhost:9200 ../.venv-main/bin/pytest tests/integration/test_search_db.py -v
   ```

   预期 20 项全部通过。
7. 高亮摘要的转义（没有自动化测试，手工做一次）：用一个带随机前缀的测试索引，写入一条 `text` 为 `<script>alert(1)</script> 报销标准` 的片段，分别查“报销”（有命中词）和只靠词干匹配、没有可高亮词的查询，确认返回的 `evidence.snippet` 里 `<script>` 显示为 `&lt;script&gt;`，只有 `<em>` 是标签。结果记到本文件第 4 节对应的行。
8. 同时设置 `TEST_DATABASE_URL` 和 `TEST_OPENSEARCH_URL` 运行整个 `pytest`，预期 728 项全部运行，0 项跳过（backend 目录）。

## 6. OpenSearch 相关的未测试项与补测步骤

更新日期：2026-11-14（T13 开始前）

### 6.1 为什么没测

本机（Apple M4，24 GB 内存，macOS 26.6.2）上没有能运行 OpenSearch 的环境：

- Barry 决定不在本机安装和运行 Docker；
- 本机没有 Java 运行时（`/usr/bin/java` 只是系统占位程序，执行时提示找不到 Java）；
- OpenSearch 官方没有发布 macOS 的正式安装包（2026-11-14 查询，只找到面向开发者的快照构建）。

按 GLOBAL.md“测试执行限制”，这些测试不在本机强行执行，也不为它们安装任何东西，统一登记在这里。

### 6.2 未测试项

| 编号 | 项目 | 用什么测 | 要回答的问题 | 影响 |
|---|---|---|---|---|
| OS-2 | 中文分词对比：IK（standard 与 smartcn 已于 2026-11-16 在 Windows 上对比：smartcn 22 词，standard 34 个单字） | 同上 | 附录 A13 选哪个分词器 | T13 的 mapping，`deploy/docker-compose.yml` 的镜像 |
| OS-6 | 四个组件同时运行时的总内存与 swap | `env_check/04_mem_snapshot.py` | 一台机器能否同时运行全部组件 | 开发时是否按需启停 CLIP |
| OS-7 | 项目自己的 `deploy/docker-compose.yml` 能否启动，`/health` 是否报告 OpenSearch 为 ok | Docker + 后端 | T01 的 compose 文件和健康检查在真实容器上是否正确 | T01 |

OS-1 至 OS-6 与 `env_check/未测试/清单.md` 的 1–6 项一一对应。OS-1、OS-3、OS-4、OS-5、OS-8、OS-9、OS-10 已在 2026-11-16 Windows 补测中完成并从上表删除（2026-11-19 整理）；A14 已由 Barry 于 2026-11-19 确定不启用。下面第 6.4 节的步骤原样保留，供在别的机器上复跑。

### 6.3 测试机器要求

- 能运行 Docker 的电脑：Docker Desktop（macOS / Windows）或 Docker Engine（Linux）都可以。不必是本机——Barry 决定本机不装 Docker。
- 内存至少 8 GB，Docker 可用内存设为 4 GB 以上（Docker Desktop：Settings → Resources → Memory）。
- 能访问 Docker Hub（拉取 `opensearchproject/opensearch:2.19.1`）。构建实测镜像时，容器内要能从 OpenSearch 官方地址下载 analysis-smartcn 插件。
- Python 3.11。
- **下载提醒：** 下面的步骤会下载 Docker 镜像（OpenSearch 官方镜像 1 GB 左右）、smartcn 插件和 Python 包 psutil。按 CLAUDE.md，下载前先确认，下载后登记到 `docs/downloads.md`，并写明是在哪台机器上装的。

### 6.4 详细步骤

以下命令都在**测试机器**上执行。`<项目目录>` 指测试机器上本仓库的根目录（用 `git clone` 或直接拷贝整个目录都可以）。

**第 0 步：记录测试机器**

```bash
cd <项目目录>/env_check
python3.11 -m venv .venv-main
.venv-main/bin/pip install -r requirements-main.txt
.venv-main/bin/python 00_sysinfo.py
```

```bash
mv results/00_sysinfo.json results/00_sysinfo.testbox.json
git checkout -- results/00_sysinfo.json   # 恢复仓库里开发机的那份；不是 git 克隆的，就从开发机拷一份回来
```

`00_sysinfo.py` 记下测试机器的 CPU、内存和系统版本，但它固定写到 `results/00_sysinfo.json`，会盖掉仓库里开发机的那份，所以运行后立刻改名，再把开发机的恢复回来。在另一台机器上测得的延迟和内存不代表开发机，写进论文时要注明是哪台机器。

**第 1 步（可选）：决定是否同时测 IK**

1. 到 IK 插件的发布页查找与 OpenSearch **2.19.1 完全一致**的发行包（zip 文件名或说明里写明 2.19.1）。
2. 找到了：打开 `env_check/opensearch/Dockerfile`，取消最后两行的注释，把 `IK_URL=` 填成那个 zip 的地址。
3. 找不到：不装 IK，在结果里写明“IK 没有与 2.19.1 匹配的版本”。这本身就是一条结论：选 IK 就要更换 OpenSearch 版本。

**第 2 步：构建并启动实测用的 OpenSearch（OS-1）**

```bash
cd <项目目录>/env_check/opensearch
docker compose up -d --build
```

等它启动。正常情况下一分钟以内，下面的命令会返回带 `"status"` 的 JSON：

```bash
curl -s http://127.0.0.1:9200/_cluster/health
```

- 返回的 `status` 为 `green` 或 `yellow`：启动成功。单节点时 `yellow` 是正常的。
- 两分钟后仍然连不上：执行 `docker compose logs --tail 100`，把输出保存下来，记为 OS-1 失败，不要往下做。

确认插件已安装（输出里应有 `analysis-smartcn`，装了 IK 的话还有 IK）：

```bash
curl -s "http://127.0.0.1:9200/_cat/plugins?v"
```

**第 3 步：运行实测脚本（OS-1 至 OS-5）**

```bash
cd <项目目录>/env_check
.venv-main/bin/python 01_check_opensearch.py
```

结果写入 `results/01_opensearch.json`。脚本依次做这些事：读版本和插件；用每个候选分词器切分同一句中文；用最好的可用分词器建测试索引，跑 6 个查询；测 BM25 和向量检索的延迟；读 JVM 堆。

**第 4 步：换 2g 堆再测一次（OS-5，只在需要时做）**

满足任意一条才需要做：第 3 步出现内存不足错误、查询明显卡顿、JVM 堆用量接近上限。

```bash
cd <项目目录>/env_check
cp results/01_opensearch.json results/01_opensearch_1g.json
OS_HEAP=2g docker compose -f opensearch/docker-compose.yml up -d --force-recreate
# 等第 2 步的 curl 恢复返回后：
.venv-main/bin/python 01_check_opensearch.py
cp results/01_opensearch.json results/01_opensearch_2g.json
```

**第 5 步：并发内存（OS-6）**

这一步要求测试机器上已经按 `env_check/README.md` 第 1 步建好 ocr 和 clip 两个环境，并下载了模型。做不到就跳过，记为“OS-6 未测试”。

保持 OpenSearch 运行，开三个终端，都先 `cd <项目目录>/env_check`：

```bash
# 终端 B
.venv-ocr/bin/python 02_check_ocr.py --mobile --hold
```

```bash
# 终端 C
.venv-clip/bin/python 03_check_clip.py --hold
```

```bash
# 终端 D（等 B、C 都显示模型已加载后再运行）
.venv-main/bin/python 04_mem_snapshot.py
```

完成后在终端 B、C 按 Ctrl+C。结果写入 `results/04_mem_snapshot.json`。

**第 6 步：项目自己的 compose 与健康检查（OS-7）**

先关掉实测用的 OpenSearch，它和项目的 OpenSearch 都占用 9200 端口：

```bash
cd <项目目录>/env_check/opensearch && docker compose down
```

```bash
cd <项目目录>
cp .env.example .env
```

编辑 `.env`：

- 把 `POSTGRES_PASSWORD` 改成自己的密码，`DATABASE_URL` 里的密码要与它一致；
- `JWT_SECRET` 换成一个随机值，可以用 `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` 生成。

```bash
docker compose --env-file .env -f deploy/docker-compose.yml up -d
```

```bash
python3.11 -m venv .venv-main
.venv-main/bin/pip install -e "shared[dev]" -e "backend[dev]"
```

```bash
cd backend && ../.venv-main/bin/alembic upgrade head
```

```bash
cd backend && ../.venv-main/bin/uvicorn app.main:create_app --factory
```

在另一个终端执行：

```bash
curl -s http://127.0.0.1:8000/health
```

预期：`database` 和 `opensearch` 都是 `"ok"`；`clip_service` 是 `"unavailable"`（CLIP 服务还没写，属于正常）；整体 `status` 为 `"degraded"`。

这一步顺带让第 5 节的 91 项数据库集成测试有了 PostgreSQL，可以接着按第 5 节补测。

**第 7 步：T13 集成测试（OS-8）**

在第 6 步启动的 OpenSearch 上运行（项目的镜像已装 analysis-smartcn）：

```bash
cd <项目目录>/backend && TEST_OPENSEARCH_URL=http://localhost:9200 ../.venv-main/bin/pytest tests/opensearch -v
```

预期 13 项全部通过。测试只操作带随机前缀的索引，结束时自行删除。

**第 8 步：收尾**

```bash
cd <项目目录> && docker compose --env-file .env -f deploy/docker-compose.yml down
```

`down` 不加 `-v`，数据卷保留。

### 6.5 结果怎么读、怎么用来定 A13 和 A14

**A13（选哪个分词器），看 `results/01_opensearch.json` 的 `analyzers`：**

| 现象 | 结论 |
|---|---|
| `standard` 把中文逐字切开 | 正常现象，证明必须装中文分词插件 |
| `smartcn` 把“文档管理”“信息检索”“跨模态”这类词切成完整的词或合理的两字词 | smartcn 可用 |
| 装了 IK，`ik_max_word` 切得明显更合理（专业词完整、没有错切） | 可以考虑 IK，但要接受“版本必须严格匹配”的维护代价 |
| 两者差别不大 | 选 smartcn：官方插件，与 OpenSearch 同版本发布，以后升级不会卡在插件上 |

另外看 `bm25_hits`：脚本用选出的分词器建了一个 6 条记录的测试索引，跑 6 个查询。按测试数据，排第一的应当分别是：财务报告 → d1，发票 → d2，路由协议 → d3，检索模块 → d4，图文模型 → d5，预算 → d1。排第一的不对，或者没有命中，要记下来。注意：脚本只用选出的那一个分词器建索引（装了 IK 时优先用 `ik_max_word`，否则用 `smartcn`），要比较两者的检索结果，需要改脚本第 112 行的选择顺序后再跑一次。

**A14（是否启用降级预案）：同时满足下面三条就不启用，继续用 OpenSearch。**

1. 第 2 步启动成功，集群状态为 `green` 或 `yellow`；
2. 1g 堆（或第 4 步的 2g 堆）下没有内存不足错误，查询延迟在几十毫秒以内；
3. 第 5 步的 `system_available_gb` 不低于 1.5 GB，`swap_used_gb` 没有持续增长。

任何一条不满足，就把数据交给 Barry，由 Barry 决定是否启用降级预案（GLOBAL §11.4，必须 Barry 同意）。

### 6.6 测完之后要做的事

1. 把测试机器上 `env_check/results/` 里的这些文件拷回开发机的同一目录：`00_sysinfo.testbox.json`、`01_opensearch.json`（做了第 4 步的，还有 `01_opensearch_1g.json`、`01_opensearch_2g.json`）、`04_mem_snapshot.json`，以及 `history/` 下新增的带时间戳的文件。不要拷 `00_sysinfo.json`。
2. 在开发机上运行 `cd env_check && .venv-main/bin/python 05_make_report.py`，重新生成 `env_check/env_report.md`。报告的第 1 节仍是开发机，第 2 节（OpenSearch）和第 5 节（并发内存）来自测试机器，要在这两节开头手工注明“测于另一台机器”，并引用 `00_sysinfo.testbox.json` 里的配置。
3. 在 `docs/decisions.md` §2 填写 A13、A14、JVM 堆大小的结论，并写明测试机器。
4. A13 选定后修改 `deploy/docker-compose.yml`：改用装了所选插件的镜像。插件版本必须与 OpenSearch 版本完全一致。
5. 把通过的项从本节删除；失败的项留在这里，写明失败现象，并附上日志。
6. 在 `docs/downloads.md` 登记测试机器上下载的内容。
