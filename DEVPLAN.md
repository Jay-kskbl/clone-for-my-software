# 开发流程与任务清单（DEVPLAN.md）

> 本文件是 GLOBAL.md v2 的执行计划，也是项目进度的唯一记录。
> Claude Code 每次开始任务前读取本文件，完成任务后勾选并写一行完成记录。
> 周次为相对周（W1 = 开工第一周），实际日期由 Barry 确认后填在 §5。

------------------------------------------------------------------------

## 1. 在 Claude Code 中的工作循环

### 1.1 一次性准备（W1 第 1 天）

```bash
cd ~/Desktop/"BARRY zou"
git init
claude          # 在项目根目录启动 Claude Code
```

根目录下的 `CLAUDE.md` 会被 Claude Code 自动读取，其中已经引用了 `GLOBAL.md`。
`.claude/commands/` 下有两个自定义命令：`/next-task`、`/finish-task`。

### 1.2 每个任务的固定循环

```
① /clear                 每个任务开新上下文，避免上一个任务的内容干扰
② /next-task             Claude 读 DEVPLAN，找到下一个未完成任务，读相关代码，给出计划
③ 审计划                  涉及数据契约、数据库表、索引结构的任务，先切到 Plan 模式（Shift+Tab）只出计划
④ 批准 → 实现             Claude 小步修改、写测试、跑测试
⑤ 自己验证一次            按 Claude 给的命令亲手跑一遍（答辩时你要能讲清楚）
⑥ /finish-task           Claude 按 GLOBAL §11.3 汇报、勾选 DEVPLAN、自动 commit 并补填 commit 编号
⑦ 一个任务一个 commit      不 push；里程碑打 tag（mvp-0、mvp-1、mvp-2）由你确认
```

### 1.3 和 Claude Code 协作的规则

-   **一次只做一个任务编号。** 想加功能，先在 §4 "待议事项"里记一笔，不在当前任务里顺手做。
-   **先看计划再放权。** 带 🔒 的任务必须先出计划、你批准后才能写代码。
-   **测试是完成标准。** Claude 报告里写"未运行"的测试，不算完成。
-   **决策变更走附录 A。** 任何与 GLOBAL.md 附录 A 冲突的建议，Claude 必须先停下来问你。
-   **卡住超过两轮就换方式：** 让 Claude 先写一个最小复现测试，再修。
-   **你要能讲清楚每一块。** 每个里程碑后，让 Claude 用 5 句话解释该模块的设计，你复述一遍。这是答辩准备。

------------------------------------------------------------------------

## 2. 仓库结构（T01 建立）

```
BARRY zou/
├── CLAUDE.md  GLOBAL.md  DEVPLAN.md
├── .claude/commands/          next-task.md  finish-task.md
├── docs/                      architecture.md  data-model.md  api.md  env_report.md  decisions.md
│                              untested.md（未测试清单）  downloads.md（下载与安装记录）
├── env_check/                 阶段一环境实测脚本
├── shared/                    【所有环境共用】数据契约(§3.5)、ID 规则、任务领取库、切分(M7)、文本索引(M8)、存储路径检查 —— 依赖 pydantic + psycopg + httpx（T17 起）
├── backend/                   【main 环境】
│   ├── app/
│   │   ├── main.py  config.py
│   │   ├── api/               路由：auth / documents / search / tasks / health
│   │   ├── core/              安全、错误类型、日志
│   │   ├── db/                SQLAlchemy 模型、会话、Alembic 迁移
│   │   ├── modules/
│   │   │   ├── auth/          M1
│   │   │   ├── documents/     M2
│   │   │   ├── storage/       M3
│   │   │   ├── parsing/       M5
│   │   │   ├── vector_index/  M10
│   │   │   ├── search/        M11（编排 + rrf.py）
│   │   │   └── consistency/   M13
│   │   └── worker/            通用 Worker 入口与任务处理器（M4 运行时）
│   └── tests/                 unit/  integration/  fixtures/
├── services/
│   ├── ocr_worker/            【ocr 环境】M6，独立 requirements
│   └── clip_service/          【clip 环境】M9，独立 requirements，FastAPI
├── experiments/               M12：datasets/ qrels/ configs/ runs/ metrics.py runner.py
├── frontend/                  M14：Vue 3 + TS + Element Plus
└── deploy/                    docker-compose.yml（postgres + opensearch）、.env.example
```

------------------------------------------------------------------------

## 3. 任务清单

图例：🔒 必须先出计划并获批准　⭐ 关键路径　🧪 必须包含的测试

### 阶段一：需求与方案（W1–W3）

- [ ] **T00 环境实测**（Barry 自己运行，W1）
  -   按 `env_check/README.md` 跑完 00–05，得到 `env_check/env_report.md`
  -   根据报告填写附录 A13（分词器）、A14（是否需要降级预案）、OCR/CLIP 模型规格
  -   完成标准：报告 §6 的决策全部填写
- [x] **T01 仓库骨架** ⭐
  -   按 §2 建目录；`backend/pyproject.toml`（ruff + pytest）；`.gitignore`（含 `.venv-*`、`models/`、`storage/`、`.env`）
  -   `deploy/docker-compose.yml`：PostgreSQL + OpenSearch（分词插件按 T00 结论）
  -   `config.py`：从环境变量读取，启动时检查必填项并给出可读错误；`.env.example`
  -   `GET /health`：分别报告数据库、OpenSearch、CLIP 服务的状态（不可用时如实报告，而不是报错退出）
  -   🧪 缺失必填配置时启动失败且错误信息明确
- [x] **T02 数据契约** 🔒⭐
  -   `shared/contracts`：`ParsedDocument`、`TextBlock`、`SourceLocator`（四种类型）、`Chunk`、`OCRResult`、`SearchHit`、`ChannelResult`
  -   `shared/ids`：`chunk_id`、`image_id` 生成与解析函数
  -   🧪 每种 locator 的序列化往返；ID 生成确定性（同输入同输出）
- [x] **T03 数据库模型与迁移** 🔒⭐
  -   SQLAlchemy 模型：User、Document、DocumentShare、Tag、DocumentTag、ProcessingTask、DocumentChunk、ImageAsset、OCRResult、ImageEmbedding、SearchLog、ExperimentRun
  -   Alembic 初始迁移；`docs/data-model.md`（ER 图 + 字段说明）
  -   🧪 迁移能在空库上升级、降级
- [x] **T04 设计文档**
  -   `docs/architecture.md`（分层图、模块表、数据流，可直接取自 GLOBAL §3.2）
  -   `docs/api.md`（接口清单：路径、方法、权限、请求/响应结构、错误码）
  -   `docs/decisions.md`（把附录 A 和 T00 结论落成文字，论文可直接引用）
  -   **里程碑：方案评审** —— Barry 通读 docs/，确认后进入阶段二

**并行准备（W2 起）：** 开始收集评测文档。目标规模先定为 200–500 个文件，覆盖 PDF（含扫描件）、Word、Excel、图片四类，记录每个文件的来源。

### 阶段二：基础系统（W4–W6）

- [x] **T05 M3 存储抽象** ⭐
  -   `put(stream) -> StoredFile(storage_key, sha256, size)`；`open(key)`；`delete(key)`
  -   先写临时文件、校验后再移动到 `{yyyy}/{document_id}/{sha256}.{ext}`
  -   文件魔数校验（不信任扩展名和 MIME）
  -   🧪 路径穿越（`../`、绝对路径、符号链接）被拒绝；中途失败不残留临时文件
- [x] **T06 M1 认证与权限**
  -   注册/登录（JWT）、密码哈希、管理员角色
  -   `current_user` 依赖；`accessible_document_ids(user)`；`can_access(user, doc)`
  -   🧪 未登录 401；访问他人文档 403；管理员可见全部；共享后可见、取消共享后不可见
- [x] **T07 M4 任务框架** 🔒⭐（全项目风险最高的基础模块，越早完成越好）
  -   `shared/tasks`：用 `FOR UPDATE SKIP LOCKED` 领取、续租、回收过期租约、重试计数、失败原因
  -   `backend/app/worker`：主循环、按任务类型分发、子进程执行（超时、内存上限）、处理 N 个任务后自动退出
  -   🧪 **崩溃恢复：** 领取后杀掉 Worker → 租约过期 → 任务被重新领取
  -   🧪 **并发：** 两个 Worker 不会领到同一任务
  -   🧪 **幂等：** 同一任务执行两次，结果不重复
  -   🧪 超过最大重试次数后标记为 `failed` 并保存原因
- [x] **T08 M2 文档管理** ⭐
  -   上传（大小、格式、文件名长度限制）→ 存储 → 写 Document → 创建 parse 任务
  -   列表（分页、只列可访问文档）、下载、软删除（创建清理任务）、共享、标签
  -   🧪 上传中途失败不留半成品；删除后列表和下载都不可见；非法类型被拒绝
- [x] **T09 M5 PDF 解析器**（可与 T05–T08 并行，纯函数）
  -   PyMuPDF 按页抽文本 → `ParsedDocument`；按页判断是否需要 OCR（阈值来自配置）
  -   🧪 fixtures：文本型 PDF、扫描型 PDF、混合型 PDF、加密或损坏的 PDF
- [x] **T10 前端骨架**
  -   登录页、文件列表（含处理状态）、上传、下载、删除、共享
  -   **里程碑：基础系统** —— 能完整管理文件，数据库与文件存储一致，T07 的四项测试全部通过
  -   ⚠️ 里程碑状态（2026-11-14）：**未达成**。T05–T10 的代码已全部完成，但 T07 的四项测试和其余数据库集成测试共 91 项从未执行（本机没有 PostgreSQL），前端也没有与真实后端联调过。详见 `docs/untested.md`
  -   ⚠️ 更新（2026-11-16 补测，见 §5“T00–T19 补测”）：T07 四项 🧪 在内的全部数据库集成测试已在 Windows 验证副本上通过（`test_task_queue.py` 18/18，backend 728/728）。通过依赖的修复 C01–C12 已于 2026-11-17 合入本仓库（与通过测试的副本逐行一致）；本机没有 PostgreSQL，没能在本仓库上重跑这些数据库测试。前端与真实后端的浏览器联调仍未做

**并行标注（W4 起，每周 2–3 小时）：** 每周补 10–20 条查询；按文字型、视觉型、混合型分类；标注相关文件（qrels 格式见 T19）。

### 阶段三：解析、OCR 与 BM25（W7–W9）

- [x] **T11 M5 其余解析器**
  -   Word（段落级 locator）、Excel（工作表 + 单元格范围 locator）、图片（只做元数据，交给 OCR）
  -   zip 炸弹防护（解压总大小和文件数上限）、解析超时
  -   🧪 每种格式至少 2 个 fixture，外加 1 个畸形文件
- [x] **T12 M7 切分**
  -   切分长度、重叠长度由配置控制；每个 chunk 带 locator；Excel 按行组切分
  -   🧪 切分后拼接覆盖原文；locator 正确；参数变化时 `parse_version` 变化
- [x] **T13 M8 文本索引** 🔒
  -   `doc_meta`、`chunks` 两个索引的 mapping（分词器按 T00 结论），mapping 文件纳入版本管理
  -   `index_document(doc_id, chunks)`：先删除该文档的旧 `parse_version` 再写入；`delete_document(doc_id)`
  -   🧪 重复索引不产生重复数据；删除后查不到
- [x] **T14 解析流水线**
  -   parse 任务处理器：解析 → 切分 → 写 DocumentChunk → 索引 → 回写状态；需要 OCR 的页和图片创建 ocr 任务
  -   清理任务处理器：删索引 → 删文件 → 硬删除记录
  -   🧪 端到端：上传 PDF → 等任务完成 → chunks 索引中有该文档的数据
- [x] **T15 M11 检索 v1** ⭐
  -   B0 + BM25 双索引查询 → 聚合到 document_id（取最佳片段作为证据）→ **数据库二次校验** → 返回 `SearchHit`
  -   OpenSearch 故障时返回明确的错误，而不是空结果；每次检索写 SearchLog
  -   🧪 删除后立即查不到；取消共享后立即查不到；同一文件不重复出现；服务故障与"无结果"可以区分
- [x] **T16 前端检索页**
  -   搜索框、结果列表（文件名 + 命中片段高亮 + 来源位置）、PDF 用 pdf.js 打开并跳到对应页、Word/Excel 显示抽取文本
  -   **里程碑 MVP-0（打 tag `mvp-0`）：** 上传 PDF/Word → 检索 → 定位到页/段落 → 删除后搜不到（T16 完成时**未达成**，没有打 tag，原因见 §5 T16。2026-11-16 补测后：数据库与 OpenSearch 测试已通过、高亮转义已在真实 OpenSearch 上确认；剩余前后端浏览器联调，见 §4）
- [x] **T17 M6 OCR Worker** 🔒（ocr 环境）
  -   `services/ocr_worker`：只领取 ocr 任务；图片或 PDF 页 → OCRResult → 生成 `source_type=ocr` 的 chunks → 创建索引任务
  -   模型路径来自配置，缺失时启动报错；记录模型名称和版本
  -   🧪 识别生成的测试图；OCR 失败时任务标记 failed，原文件仍在
- [x] **T18 M13 一致性检查**
  -   `python -m app.modules.consistency check|repair`：对账数据库、磁盘、两个索引，输出差异；`repair` 需要显式参数才执行
  -   🧪 人为制造三类不一致，都能被检测出来
- [x] **T19 M12 实验框架 v1** 🔒
  -   `experiments/datasets/manifest.csv`（文件、类型、来源）、`qrels/*.tsv`（query_id、document_id、相关等级）、`queries.tsv`（query_id、文本、类型）
  -   `metrics.py`：P@K、R@K、nDCG@K（🧪 用手算的小例子验证）
  -   `runner.py`：读取配置（通道开关、参数）→ 调用 M11 → 保存每条查询的原始排名 → 输出指标，并按查询类型分层
  -   配置 B0、B1、B2
  -   **里程碑 MVP-1（打 tag `mvp-1`）：** 四类格式 + OCR 可检索；B0–B2 能在小标注集上跑出真实数字（T19 完成时**未达成**，没有打 tag，原因见 §5 T19。2026-11-16 补测后：OCR 全链路与 `test_experiments_db.py` 已通过，剩余阻塞只有评测数据和标注）

### 阶段四：图像检索与融合（W10–W12）

- [x] **T20 M9 CLIP 服务** 🔒（clip 环境）
  -   `services/clip_service`：启动时加载模型（路径缺失则报错）；`/health`、`/encode/text`、`/encode/image`
  -   接口返回模型名称、版本、向量维度
  -   🧪 健康检查；同一输入向量稳定；超大图片和损坏图片的处理
- [x] **T21 图片向量与 M10 向量索引**
  -   embed 任务：按 sha256 去重 → 调用 CLIP 服务 → 写 ImageEmbedding → 写入向量索引
  -   向量检索：`script_score` 精确计算 + 可访问 document_id 前置过滤
  -   🧪 过滤后只返回有权限的文档；重复图片只编码一次
- [x] **T22 M11 检索 v2 + RRF** 🔒⭐（`rrf.py` 已在 T15 提前完成，Barry 批准，见 decisions.md D28）
  -   图像通道：调用 CLIP 服务编码查询文本（设超时）→ 向量检索；超时或失败时降级，并在响应中标记该通道不可用
  -   `rrf.py`：输入各通道已聚合到文件级的排名列表，按 k 和截断深度融合；保留各通道原始排名和分数
  -   通道开关来自请求参数或实验配置
  -   🧪 RRF 用手算样例验证；关闭 CLIP 服务后检索仍然正常并带降级标记
- [x] **T23 前端 v2**
  -   结果中显示图片缩略图、命中通道标记；某通道不可用时给出提示
- [x] **T24 B3 与消融配置**
  -   B3、去掉 OCR、去掉 CLIP、只用 CLIP、RRF 不同 k 值
  -   **里程碑 MVP-2（打 tag `mvp-2`）：** 完整演示流程；关闭 CLIP 后基础检索不受影响——**未达成，没有打 tag**：数据库、OpenSearch、CLIP 的端到端联调都没做，评测数据集也还没有（与 MVP-0 相同，见 decisions.md D38）

### 阶段五：实验（W13–W15）

- [ ] **T25 冻结数据集与标注**：查询总数、各类型数量、qrels 数量写进 `experiments/README.md`；冻结后不再修改
- [ ] **T26 质量实验**：B0–B3 和消融，每组重复运行，保存全部原始结果
- [ ] **T27 性能实验**：查询延迟 P50/P95（每个通道分别统计）、索引构建时间、OCR 每页耗时、CLIP 吞吐、各组件内存
- [ ] **T28 分析**：图表、按查询类型分层的结论、失败案例分析、负面结果和局限性

### 阶段六：论文与答辩（W16–W20）

- [ ] **T29 测试报告**：汇总所有 🧪 测试和覆盖率
- [ ] **T30 部署说明与使用说明**：Docker 方式和非 Docker 方式都写
- [ ] **T31 一致性核对**：逐条核对论文描述、README、截图和实际功能（参照 GLOBAL §13、§14）
- [ ] **T32 答辩演示脚本**：固定演示数据、固定操作步骤，包含关闭 CLIP 服务的降级演示

------------------------------------------------------------------------

## 4. 待议事项（P4 及新想法先记在这里，不做）

以下是 2026-11-14 核查 T05–T10 时发现、但不属于已完成任务范围的事项，留给后续任务或由 Barry 决定：

- **（T14 已解决）** 之前记给 T14 的提醒都已处理，做法见 `decisions.md` D27：存储新增 `local_path()`；文档状态只跟随 parse 任务的规则已定，并在任务失败、回收、重试时一并更新；parse 处理函数开头检查文档是否已删除；按 `mime_type` 选解析器，图片写 `image_assets`；`parser_options` 只传 PDF 的 `pdf_ocr_min_chars`；索引改为在每个任务开始时 `ensure_indices`（没有放在 API、Worker 启动时）；上传后由 parse 任务写 `doc_meta`，删除由 cleanup 任务调用 `delete_document`，改标签接口提交后尽力同步 `doc_meta`；`TextIndexUnavailable` / `TextIndexError` / `ParseError` / `PipelineError` 都由 Worker 按 `retryable` 处理。
- **（T21 已解决）给 T21 的补充（T18 记录）**
  - ~~一致性检查（D31）还没有覆盖 `image_embeddings`~~：T21 已补上无用向量（`embedding_orphan`，修复类别 `embeddings`）和向量索引与数据库不一致（`vector_*`，修复类别 `index`、`rebuild-indices`）的检测与修复，见 `decisions.md` D35。
- **待定（T18 记录）**
  - backend 通用 Worker 启动时不检查数据库，连不上时在领取循环里无限重试；OCR Worker 启动时连不上数据库就以退出码 1 结束（D30）。两者不一致，是否统一由 Barry 决定。
- **（T20、T21 已处理）给 T20、T21（CLIP）的参考（T17 记录）**
  - ~~CLIP 服务和 embed 任务可以复用~~（两者都没有采用：CLIP 服务不领任务（D33）；embed 任务由通用 Worker 领取，只发 HTTP 请求，见 D35） `shared.task_queue.PgTaskQueue`，以及 OCR Worker“常驻子进程加载模型、超时或崩溃时杀掉重开”的写法（`services/ocr_worker/ocr_worker/engine_process.py`）。
- **待改进（T17 记录）**
  - 文本预览接口按 `seq` 排序，扫描页的 OCR 片段排在全部正文片段之后。如果要按页码穿插，需要改预览接口的排序规则。
- **2026-11-16 补测的后续（来源：`change-deepseek-v4/`，见 §5“T00–T19 补测”）**
  - **修复已合入（2026-11-17）：** C01–C12 的 9 个文件已按 `change-deepseek-v4/modified-files/` 合入本仓库（只去掉了 Windows 换行符，逐行核对与报告一致，没有夹带其他改动）。N01 烟测脚本 `storage-smoke/ocr_e2e.py` 没有合入，是否进仓库待 Barry 决定。合入后本机（macOS）重跑结果见 §5“修复合入”。
  - **C12 的取舍：** OCR 引擎在 Windows 上关闭 oneDNN（`enable_mkldnn=os.name != "nt"`），macOS/Linux 不变。若阶段五在 Windows 上测 OCR 耗时，需要在论文里注明这一点。
  - **`docs/untested.md` 待整理：** 2026-11-17 只在文件开头加了补测说明，逐项清单和补测步骤没有删。是否按 CLAUDE.md 规定删除已在 Windows 上通过的项（本机无法复跑），待 Barry 决定。
  - **仍未验证：** 8 项符号链接测试在普通权限的 Windows 上失败（WinError 1314，环境权限问题），以管理员权限重跑后通过；前端与真实后端的浏览器联调（T10、T16）；OCR 与 CLIP 同时运行的内存（OS-6，CLIP 尚未实现）；IK 分词器（没有匹配 OpenSearch 2.19.1 的版本）；真实扫描件、手机照片、Office 实际保存的文件；Dockerfile 构建。
  - **测试项数变化：** untested.md 记的是 188 项，实际收集到 190 项（`test_migrations.py` 13→14，`test_auth.py` 19→20），更新 untested.md 时一并核对。
- **MVP-0 验收前必须做（T16 记录）**
  - ~~在有 PostgreSQL 和 OpenSearch（带 analysis-smartcn）的环境里补跑全部集成测试~~（2026-11-16 已在 Windows 验证副本上完成，190/190 通过，修复已于 2026-11-17 合入）。还需要把前端接到真实后端联调一遍：上传 PDF、Word → 等处理完成 → 检索 → 定位到页或段落 → 删除后搜不到。通过后再打 tag `mvp-0`。
  - ~~高亮摘要的 HTML 转义要在真实 OpenSearch 上确认（untested.md OS-10）~~（2026-11-16 已确认：`<script>` 被转义，只保留 `<em>`）。前端已对摘要做白名单清洗，只放行 `<em>`。
- **打包体积（T16 记录）**
  - Vite 提示主包（约 874 KB）和 pdf.worker（约 1.27 MB）超过 500 KB。worker 本来就是单独加载的；主包可以在 T30 部署前考虑按需引入 Element Plus（D22）。
- **给 T22（检索 v2）的衔接提醒（T15 补充）**
  - 直接复用 `backend/app/modules/search/rrf.py`，只需加~~图像通道、CLIP 调用超时降级~~和消融配置。~~现在两路是串行的，加第三路时可以考虑并行执行。~~（T22 已处理：图像通道与文本通道并行、超时降级，见 D36；消融配置属于 T24）
  - ~~图像通道目前在请求开启时报 `unavailable`（“图像检索尚未实现”），实现后改为真实状态。~~（T22 已处理，D36）
- **评测数据（T19 记录，由 Barry 负责，已滞后）**
  - 收集评测文档（原计划 W2 起，200–500 个文件）和每周标注（原计划 W4 起）都还没有开始。框架已就绪，格式和操作步骤见 `experiments/README.md`。没有数据就达不到 MVP-1，也无法开展阶段五的实验，建议尽快开始。
  - `grade` 0–3 各等级的含义（README 里是建议写法）待 Barry 确认。
- **给 T22、T26 的补充（T19 记录）**
  - OCR Worker 的参数（`OCR_MIN_CONFIDENCE`、`OCR_PDF_DPI`）还没有记录进实验配置，因为 backend 读不到 OCR Worker 的配置。正式实验前要补上，例如让 OCR Worker 把参数写进 `ocr_results`，或在实验配置里显式填写。
- **给 T21、T22 的衔接提醒（T20 记录）**
  - CLIP 服务的接口见 `api.md` §9：~~`POST /encode/text` 传 `{"texts": [...]}`（T22 用）~~（T22 已处理，D36）。~~`POST /encode/image` 写进 `image_embeddings`~~（T21 已实现，D35）。向量已归一化；T21 的精确检索用的是 `knn_score` + `cosinesimil`（与 T00 实测写法一致），对归一化向量排序与点积相同。
  - ~~调用方自己设超时（A5）。服务一次只算一个请求，embed 任务批量入库时，查询编码可能要排队，T22 定超时时要考虑。~~（T22 已处理：`SEARCH_IMAGE_TIMEOUT_SECONDS` 默认 3 秒，超时降级，D36）
  - ~~413、422 标为不可重试~~、~~向量维度 512 用于 mapping~~、~~embed 任务在哪个进程领取~~：T21 已处理（ClipRejected 不可重试；mapping 维度 512；通用 Worker 领取），见 D35。换模型仍要重建向量索引。
- **T15–T19 复核留下的事项（2026-11-17 记录，详见 decisions.md D34）**
  - 已定（Barry，2026-11-17）：库里有数据集以外的文档时保持只提示并记录 `documents_outside_dataset`，不拦截运行。待 Barry 决定：`rebuild-indices` 是否需要一个无条件强制重建的开关（现在只在检查发现索引缺失或结构不一致时才执行）。
  - 待改进：重新解析与旧版本 OCR 的竞争窗口（旧版本 OCR 片段可能残留，一致性检查能清掉）。修它要改 T14 的 parse 流水线，需要在有 PostgreSQL 的机器上验证后再做。
  - 部署到 Linux 前要实测：OCR 识别子进程的内存上限用的是 `RLIMIT_AS`（默认 3072 MB），PaddlePaddle 可能因此加载失败。
- **待 Barry 决定（T20 记录）**
  - ~~`CLAUDE.md` 的“常用命令”还没有加 CLIP 服务的启动和测试命令~~（Barry 于 2026-11-17 同意，已补）。
  - `env_check/models/clip_cn_vit-b-16.pt`（约 718 MB）已复制到 `models/clip/`，原文件是否删除。
- **（T21 已解决）给 T21 的衔接提醒**
  - ~~parse 任务目前不创建 embed 任务~~：T21 在解析图片成功的同一事务里创建（与 OCR 任务同处），按 payload 去重；同内容只编码一次靠 sha256 咨询锁 + 查 `image_embeddings`，见 D35。
- **给 T22、T24 的衔接提醒（T21 记录）**
  - ~~向量检索：`app.modules.vector_index.search_vectors(client, query_vector, *, document_ids, model_name, model_version, depth) -> list[VectorHit]`（`VectorHit` 含 document_id、image_id、score）。`document_ids` 传 M1 的可访问集合，管理员传 `None`（不过滤），空集合直接返回空、不发请求；`model_name`、`model_version` 取 CLIP `/health` 的当前模型，只比较同一模型的向量；结果已按文档折叠、按分数排好，score 是 1+余弦相似度，只用于排名。索引不存在时先建索引、返回空；其他故障照常抛出，T22 要把它当作通道不可用，而不是空结果。返回前仍需 M11 的数据库二次校验。~~（T22 已处理：模型标识取自 `/encode/text` 的应答，故障记为通道不可用，见 D36）
  - ~~实验记录的 mapping hash（`backend/app/modules/experiments/environment.py` 的 `code_versions`）只遍历 `INDEX_NAMES`，不含 `image_vectors.json`，跑 B3 前要补~~（T24 已处理，D38）。
  - ~~CLIP 服务一次只算一个请求：embed 任务批量编码时，查询编码可能排在后面（单张图片最长等 `CLIP_ENCODE_TIMEOUT_SECONDS`），T22 定查询编码超时时要考虑。~~（T22 已处理：查询超时 3 秒、超时降级；排队导致降级仍是局限，见 D36）
- **待 Barry 决定（T24 记录）**
  - `CLAUDE.md` 的“实验”命令一行是否补一句：B3 类配置（开了图像通道的）需先启动 CLIP 服务，并让通用 Worker 处理完 embed 任务。`experiments/README.md` 已写明；改 `CLAUDE.md` 需 Barry 同意。
- **待 Barry 决定（T21 记录）**
  - ~~`CLAUDE.md` 一致性检查命令的说明仍写“对账数据库、磁盘和两个索引”，类别列表里没有新增的 `embeddings`~~（Barry 于 2026-11-19 同意，已补）。
- **待实验决定（T12 记录）**
  - 是否给每个 Excel 片段补上该工作表的表头行：片段里只有数据、没有列名，按“列名 + 值”的方式搜索可能搜不到后面的行。补表头会让表头词在同一文件里重复计分。阶段五用实验比较。
  - Word 片段只定位到起始段落。如果实验或演示发现跳转偏差影响使用，再考虑给 `DocxParaLocator` 增加结束段落字段（数据契约变更，需 Barry 批准）。
- **评测数据收集时顺带做**
  - 用几份真实的 Word、Excel（由 Office 或 WPS 保存）和手机照片过一遍 T11 的解析器，结果记到 `docs/untested.md` §4 对应的行。
- **安全方面，本科毕设范围内可以不做，但答辩可能被问到**
  - 登录接口没有限制尝试次数，可以被暴力猜密码。
  - 没有每个用户的存储配额。
  - `/health` 是公开接口，依赖不可用时返回的 `detail` 里带有内部主机名和端口（数据库认证失败时还会带数据库用户名）。T01 的实现，建议改成只返回异常类型、详情写日志。
- **文档**
  - 项目根目录没有 `README.md`。GLOBAL §11.2 要求配置变化时同步更新 README，§14 的验收标准也要求 README；目前相关说明分散在 `CLAUDE.md` 和 `frontend/README.md` 里。T30 之前需要补。
- **前端**
  - 新想法（T23 记录）：后端缩略图接口。现在检索页的缩略图取的是原图（D37），图片多、图片大时费流量。可以在后端加一个按需生成并缓存小图的接口，但需要 Pillow 之类的图像库（主环境新依赖），须 Barry 批准；不属于核心验收条件。
  - 上传前没有在浏览器里检查文件大小（上限在后端配置里，前端不知道）。超限的文件要传完才被拒绝。
  - 文件名一栏较窄时，标签会被省略号截断。

------------------------------------------------------------------------

## 5. 日期与完成记录

开工日期（W1 周一）：______

| 任务 | 完成日期 | commit | 备注 |
|---|---|---|---|
| T00 | 部分完成（2026-11-13） | e253c74 | 硬件、OCR、CLIP 已实测并写入 decisions.md §2；OpenSearch、分词（A13/A14）、并发内存未测试（Barry 决定不在本机使用 Docker），清单见 env_check/未测试/清单.md；OCR/CLIP 规格待 Barry 选定 |
| T01 | 2026-11-13 | 31e2c95 | 单元测试 13 项通过；docker-compose 只校验了语法，容器未实际启动；OpenSearch 中文分词插件待 T00 结论（A13） |
| T02 | 2026-11-13 | 43f7589 | shared 包测试 93 项通过 |
| T03 | 2026-11-13 | 62f3201 | 后端测试 30 项通过，其中 13 项集成测试在本地 PostgreSQL 16.15 上运行；未在 docker-compose 的 postgres:16.6 容器上运行 |
| T04 | 2026-11-13 | 403664d | 三份文档完成；Barry 于 2026-11-13 确认方案（含 api.md 的接口设计与 D12、D13），里程碑“方案评审”通过。遗留：decisions.md §2 中 OpenSearch、分词（A13）、降级预案（A14）、并发内存未测试，须在 T13 开始前确定；OCR/CLIP 规格分别在 T17、T20 开始前选定 |
| T05 | 2026-11-13 | b39f3dd | 后端测试 74 项通过（其中存储 54 项、配置新增 3 项），13 项集成测试因未设置 TEST_DATABASE_URL 未运行（与本任务无关）；接口为 stage/commit/discard 两步写入 + put 简便方法；支持 pdf/png/jpg/docx/xlsx 五种类型；进程被强杀时残留的临时文件尚无清理入口，留给 T18（已由 T18 的 `temp-files` 处理，见 decisions.md D31） |
| T06 | 2026-11-13 | 56e8336 | 已执行：不需要数据库的测试 113 项通过（T06 新增 37 项：密码哈希、令牌、未登录 401、参数校验 422、数据库不可用 503）。**未测试（Not Tested）**：`tests/integration/test_auth.py` 中 19 项需要 PostgreSQL 的测试（注册登录全流程、重名 409、访问他人文档 403、管理员可见全部、共享后可见与取消共享后不可见、软删除不可见、create-admin 命令），原因是本机没有 PostgreSQL，按 GLOBAL“测试执行限制”不安装；已对这部分代码和测试做人工复核，未发现问题。T03 的 13 项迁移测试同样未测试 |
| T07 | 2026-11-13 | 56e8336 | 计划经 Barry 批准后实现。已执行：后端测试 135 项通过（T07 新增 22 项：子进程执行的正常/异常/超时/崩溃/租约丢失，主循环的分发/回写/处理 N 个后退出/数据库出错不崩溃，配置校验）。**未测试（Not Tested）**：`tests/integration/test_task_queue.py` 的 18 项，包括 DEVPLAN 要求的全部四项 🧪（崩溃恢复、并发不重复领取、幂等、超过重试上限标记 failed），原因是本机没有 PostgreSQL，按 GLOBAL“测试执行限制”不安装；已逐条复核 SQL 与测试逻辑，未发现问题。内存上限在 macOS 上不生效（decisions.md D16）。里程碑“基础系统”要求 T07 四项测试全部通过，目前不满足 |
| T08 | 2026-11-13 | a749a23 | 已执行：后端测试 188 项通过（T08 新增 53 项：文件名与标签规范化、上传各步骤失败后不留文件（用假的数据库会话模拟）、全部路由未登录 401、Content-Length 超限 413、配置校验）。**未测试（Not Tested）**：`tests/integration/test_documents.py` 的 41 项，包括 DEVPLAN 要求的三项 🧪 在真实数据库上的版本（上传中途失败不留半成品、删除后列表和下载都不可见、非法类型被拒绝），以及列表、分页、共享、标签、任务重试；原因是本机没有 PostgreSQL，按 GLOBAL“测试执行限制”不安装；已逐条复核代码与测试。新增依赖 python-multipart 由 Barry 单独批准（decisions.md D19）。至此共 91 项数据库集成测试未测试。未测试项的逐项清单见 `docs/untested.md`，下载记录见 `docs/downloads.md` |
| T09 | 2026-11-13 | d317142 | 后端测试 209 项通过，其中 T09 新增 21 项（PDF 解析 20 项：文本型、扫描型、混合型、加密、损坏；配置 1 项），全部在本机实际执行，没有未测试项。按页判断规则细化为三种情况（decisions.md D20）。新增依赖 PyMuPDF 1.28.2 由 Barry 批准（D21，已登记到 docs/downloads.md）。测试用的 PDF 是现场生成的，未用真实扫描件验证 |
| T10 | 2026-11-14 | e5209a5 | 登录/注册页、文件列表（含处理状态与自动刷新）、上传、下载、删除、共享。已执行：类型检查通过、30 项前端单元测试通过、生产构建成功；在浏览器里对着临时的模拟接口把全部功能人工点了一遍。**未测试（Not Tested）**：与真实后端的联调（本机没有 PostgreSQL，真实后端的登录等接口无法运行）；页面组件没有自动化测试。新下载：Node.js 26.13.1（装在项目内 .tools/node/）和 131 个 npm 包，Barry 批准，已登记到 docs/downloads.md。里程碑“基础系统”未达成 |
| T05–T10 核查 | 2026-11-14 | a0872dc | Barry 要求的整体核查。方法：重跑全部测试与代码检查；从真实应用导出接口清单，与 api.md 和前端类型逐项对照（17 个接口、全部字段一致）；启动真实后端和前端开发代理，用 curl 走通不需要数据库的路径；通读各模块之间的衔接。发现并修复 5 处：① 超大上传经代理时用户看到 502 而不是 413；② 解析器标记的“不可重试”在子进程边界丢失；③ `.env.example` 里的示例 JWT 密钥长度合格，原样复制也能启动；④ 存储和 Worker 各有一处代码在 Windows 上会直接报错；⑤ `.gitignore` 的 `models/` 规则会误忽略任何同名目录。新增 7 项测试，后端现为 216 项通过。未修、留作后续的事项记在 §4。91 项数据库集成测试和前后端联调仍未测试，里程碑“基础系统”仍未达成 |
| T11 | 2026-11-14 | 3bd66e9 | Word、Excel、图片三个解析器，zip 炸弹防护（解压后总大小、条目数、加密条目），图片像素数上限与截断检查。已执行：后端测试 288 项通过（T11 新增 72 项：Word 18、Excel 19、图片 23、zip 检查 11、配置 1），全部在本机实际执行，没有未测试项；代码检查通过。每种格式的 fixture 都不少于 2 个，畸形文件包括 zip 炸弹、谎报大小的条目、截断、XML 损坏、缺主部件、互相冒充、伪造表格范围、像素炸弹。新增依赖 python-docx 1.2.0、openpyxl 3.1.5（带入 lxml、et-xmlfile）由 Barry 批准，已登记到 docs/downloads.md；规则与局限见 decisions.md D24。新增三个配置项（PARSE_ZIP_MAX_TOTAL_BYTES、PARSE_ZIP_MAX_ENTRIES、PARSE_IMAGE_MAX_PIXELS）。解析超时沿用 Worker 子进程边界的超时（T07），解析器内部没有另做；解析器尚未接入 Worker（T14）。测试文件都是现场生成的，未用 Office 实际保存的文件和真实照片验证，已记入 docs/untested.md §4 |
| T12 | 2026-11-14 | 8134a2e | 切分模块 `chunk_document` / `chunk_blocks`、`split_spans`、`make_parse_version`。规则见 decisions.md D25：PDF 页和图片不合并；Word 相邻段落、Excel 同一工作表相邻行按整块打包；Word 定位到起始段落，Excel 用外接矩形；打包时整块重叠，超长块按字符重叠并优先在换行、句末处断开；parse_version 由算法版本、切分参数、解析器名称和版本、解析参数确定性算出。新增配置 CHUNK_MAX_CHARS（500）、CHUNK_OVERLAP_CHARS（50）。已执行：后端测试 336 项通过（T12 新增 48 项：切分 47、配置 1），全部在本机实际执行，没有未测试项；代码检查通过。三项 🧪 都有对应测试，并用 T11 解析器生成的 docx、xlsx 做了衔接测试。没有新下载。切分尚未接入 Worker（T14）；正文与 OCR 片段的序号分配留给 T14/T17，记在 §4。实施过程中另一个会话（T11 实施 fork）曾在同一目录短暂做 T12，已由它撤回自己的改动；提交前逐个核对过文件内容，并重跑了全部测试 |
| T13 | 2026-11-14 | 0600f02 | 计划经 Barry 批准后实现，A13 选 smartcn 由 Barry 于 2026-11-14 在本会话亲自确认；代码由“T11 实施 (fork)”会话编写，复核、测试、文档和提交由本会话完成。`text_index` 模块：httpx 直连 REST（不引入 opensearch-py）、`doc_meta` 与 `chunks` 两个 strict mapping（分析器 `docmgr_text` 直接使用插件自带的 smartcn 分析器，显式 BM25 参数，无权限字段；`backend/pyproject.toml` 声明了 mapping 文件为 package-data）、`ensure_indices`、`index_document`（先删其他版本再批量写入，`_id`=chunk_id）、`index_doc_meta`、`delete_document`，错误分可重试 / 不可重试两类。新增配置 OPENSEARCH_TIMEOUT_SECONDS（10）、OPENSEARCH_INDEX_PREFIX（空）；`deploy/docker-compose.yml` 改为带 analysis-smartcn 的自定义镜像（`deploy/opensearch/Dockerfile`）。附录 A13 按 Barry 的选定改为 analysis-smartcn（未经实测，阶段五可换）；A14 未改，T13 按不启用实现。已执行：后端测试 378 项通过（T13 新增 42 项：模拟应答下的索引测试 41、配置 1），shared 93 项通过，代码检查通过。**未测试（Not Tested）**：`tests/opensearch/test_text_index_live.py` 的 13 项，包括 DEVPLAN 要求的两项 🧪（重复索引不产生重复数据、删除后查不到），原因是本机没有 OpenSearch（没有 Docker 和 Java）；两个 mapping 从未被 OpenSearch 接受过，`deploy/opensearch/Dockerfile` 从未构建，compose 只读过 YAML 结构，package-data 没有用普通安装验证过。复核时指出的两处已由编写会话修改：分析器改为直接用 smartcn 类型（少依赖两个名字）；补上 package-data 声明。已登记到 docs/untested.md，补测步骤见该文件第 5、6 节。没有新下载 |
| T14 | 2026-11-15 | eecd032 | 代码由“T11 实施 (fork)”会话编写（Barry 在该会话里让开始 T14），复核、测试、文档和提交由本会话完成。parse 任务：读文档（已删除则不做）→ processing → 确保索引并写 doc_meta → 按 mime_type 解析、切分 → 换掉正文片段并登记图片 → 写 chunks 索引 → 复查是否被删除 → succeeded + parse_version + 按页创建 OCR 任务。cleanup 任务：只清理已软删除的文档，顺序为索引 → 文件 → 硬删除（最后一步，级联删除连任务记录一起删掉）。文档状态只跟随 parse 任务，最终失败时由 `shared/tasks.py` 的 fail / reclaim_expired 在同一事务里改为 failed；重试 failed 的 parse 任务时文档回到 pending。改标签后尽力同步 doc_meta；compose 关闭 `action.auto_create_index`；存储新增 `local_path()`。规则与局限见 decisions.md D27。已执行：后端测试 415 项通过（T14 新增 37 项：流水线 30、local_path 7），shared 93 项通过，代码检查通过。**未测试（Not Tested）**：`tests/integration/test_pipeline_db.py` 的 23 项，包括 DEVPLAN 要求的 🧪 端到端（上传 PDF → 等任务完成 → chunks 索引中有该文档的数据）。原因是本机没有 PostgreSQL，其中 2 项还需要 OpenSearch。`shared/tasks.py` 新增的 SQL 从未执行，真实子进程里的处理函数从未运行，`action.auto_create_index` 未验证。已登记到 docs/untested.md。复核时指出的 1 个应修问题（改标签可能让 OpenSearch 自动建出错误的索引）和 1 处文字错误已由编写会话修改。没有修改附录 A，没有新下载 |
| T15 | 2026-11-15 | 68385a0 | 代码由“T11 实施 (fork)”会话编写（Barry 在该会话里让开始 T15），复核、测试、文档和提交由本会话完成。融合方式由 Barry 于 2026-11-15 在该会话选定“T15 就用 RRF (Recommended)”：`rrf.py` 从 T22 提前到 T15，k=60、每通道取前 100 个文件，都放配置；T22 只加图像通道、降级和消融配置。实现见 decisions.md D28：校验 → meta（doc_meta，文件名与标签）、text（chunks BM25，collapse 取每文档最佳片段作证据）两路 → RRF（只用名次，同分按 document_id 排序）→ 数据库二次校验（accessible_filter，不缓存）→ 先过滤后截取 top_k → 写 SearchLog；普通用户两路带可访问 ID 的 terms 前置过滤（只为召回），管理员不加；任何一路出错整体 503 SEARCH_UNAVAILABLE，故障也写日志；索引不存在时查询路径先建索引再查；图像通道未实现，默认关闭，开启时报 unavailable。新增 POST /api/search、SearchUnavailableError（503）、11 项 SEARCH_* 配置。已执行：后端测试 462 项通过（T15 新增 47 项，RRF、检索编排、配置），shared 93 项通过，代码检查通过。未测试（Not Tested）：`test_search_db.py` 20 项（19 项需要 PostgreSQL，1 项另需 OpenSearch），含 DEVPLAN 的四项 🧪；查询体从未被真实 OpenSearch 接受过；高亮转义待实测（untested.md OS-10）。复核发现 6 处局限，未改代码，写进 D28。没有修改附录 A，没有新下载 |
| T16 | 2026-11-15 | 066350f | 代码由“T11 实施 (fork)”会话编写（Barry 在该会话里让开始 T16），复核、测试、浏览器检查、文档和提交由本会话完成。新增后端接口 GET /api/documents/{id}/text（当前版本片段，按 seq 排序，来自数据库；chunk_id 直接跳到所在页）；前端检索页（检索词进地址栏，503 与无结果分开显示，失败通道逐个提示）、预览页（PDF 用 pdf.js 画在 canvas 并跳到命中页，图片原生显示，Word/Excel 显示抽取文本并滚到命中片段）、顶部导航、文件列表“查看”。规则见 decisions.md D29；D22 改为“只在两处用 v-html，都先转义再只插入 <em>”。新增依赖 pdfjs-dist 6.5.438，Barry 于 2026-11-15 批准（先在编写会话选“同意安装 6.5.438 (Recommended)”，又在本会话选“同意，现在安装 (Recommended)”），随之自动带入 @napi-rs/canvas 两个可选包（约 28 MB，浏览器不用；Barry 随后决定保留），已登记 downloads.md #21–#23。已执行：后端测试 462 项通过；前端类型检查、构建通过，单元测试 48 项通过（T16 新增 18 项）；浏览器检查是对着临时模拟接口做的（模拟接口不是项目代码，没有提交）：检索结果、摘要里的 <script> 和 <img onerror> 只显示成文字、空结果与 503 分开显示、图像通道提示、刷新保留检索词、PDF 跳到命中页及翻页/页码/缩放、Word 分页并滚到命中段（首轮发现直接打开不滚动，修复后复查通过）、图片预览。未测试（Not Tested）：test_document_text.py 11 项（需要 PostgreSQL）；前端与真实后端联调；页面组件无自动化测试；PDF 只用测试文件验证过。**MVP-0 里程碑未达成，没有打 tag**：全部数据库与 OpenSearch 测试都没有运行，前后端没有联调。没有修改附录 A |
| T17 | 2026-11-15 | 0151f34 | 计划由 Barry 在编写会话里批准（“批准，开始写”；选择“按原计划做 OCR Worker”“PP-OCRv5 mobile (Recommended)”“沿用 env_check/.venv-ocr (Recommended)”）；代码由“T11 实施 (fork)”会话编写，测试、复核、文档和提交由本会话完成。`services/ocr_worker`：只领取 ocr 任务，常驻识别子进程（模型只加载一次），PDF 页 200 dpi 渲染，识别结果按“文档 + 对象”替换，一页的行拼成一个文本块后切分，OCR 片段序号从 1e9 起每页预留 1000 个，保存时加锁复查版本、写索引只写不删、写完复查；启动时配置、模型、数据库任一有问题即退出码 1，不联网下载模型。chunking、text_index、PgTaskQueue、存储路径检查移到 shared（shared 新增 httpx 依赖）；parse 创建 ocr 任务时带上切分参数。规则见 decisions.md D30。新增下载：ocr 环境的 PyMuPDF 1.28.2、psycopg 3.3.9、psycopg-binary 3.3.9（Barry 批准，downloads.md #24–#26）；OCR 模型从本机缓存复制到 models/ocr（#27、#28，不进版本库）；shared 以 editable 方式离线装入两个环境。已执行：后端测试 463 项通过；shared 105 项通过；services/ocr_worker 63 项通过（main 环境）；🧪 真实识别 4 项在 ocr 环境通过（扫描版 PDF 页、独立图片、空白图、模型版本记录），用的是本地模型，~/.paddlex 没有新增模型、没有联网；启动检查三项通过（缺配置、模型目录不存在、数据库连不上都在约 1 秒内以退出码 1 结束）；代码检查通过。首轮复核发现并已修复：每行 OCR 文字各成一个片段；重新解析时 OCR 可能删掉新版本的索引片段；一个无效的测试用例；启动时连不上数据库不退出。未测试（Not Tested）：test_ocr_worker_db.py 10 项（需要 PostgreSQL）；OCR Worker 完整链路从未连真实数据库和 OpenSearch；真实扫描件；Linux 上的内存上限。CLAUDE.md 的命令说明待 Barry 同意后补（§4）。没有修改附录 A |
| T18 | 2026-11-15 | 12f4ebb | 代码由“T11 实施 (fork)”会话编写（Barry 在该会话里让开始 T18），测试、复核、文档和提交由本会话完成。`python -m app.modules.consistency check|repair`：以数据库为准，对账磁盘、`doc_meta`、`chunks`；19 种检测项，7 类修复（index、db-chunks、ocr-results、cleanup-tasks、temp-files、orphan-files、rebuild-indices）；repair 必须 `--fix` 指定类别，不加 `--yes` 只演练，每个动作执行前复查数据库；新文件、清理中的文档、正在处理的文档不报告；rebuild-indices 是 D26 要求的重建入口，需先停 Worker。规则见 decisions.md D31。首轮复核发现并已修复：对正在解析的文档，`repair --fix db-chunks` 会删掉解析中的新片段（另有 3 个小问题和 3 个新增检测项）。已执行：后端测试 499 项通过（T18 新增 36 项）；代码检查通过；命令行冒烟（三种 --help、repair 缺 --fix 时退出码 2、数据库连不上时立即以退出码 1 结束）。未测试（Not Tested）：test_consistency_db.py 12 项（需要 PostgreSQL，含 DEVPLAN 要求的三类不一致 🧪）；从未对真实 OpenSearch 扫描、检查结构和重建；从未在真实数据上跑过。CLAUDE.md 的命令说明待 Barry 同意后补（§4）。没有修改附录 A，没有新下载 |
| T19 | 2026-11-15 | 496d86b | 计划由 Barry 在编写会话里批准（“批准，开始写”，由编写会话转述）；代码由“T11 实施 (fork)”会话编写，测试、复核、文档和提交由本会话完成。框架已完成：`python -m app.modules.experiments validate|import|run`；数据格式 manifest.csv / queries.tsv / qrels/*.tsv（标注用 file_id，导入时生成 document_map.csv）；P@K、R@K、nDCG@K（手算样例验证），先按查询类型分层再给总体；B0、B1、B2 三个配置只切换通道、source_types、top_k、K；每次运行保存 config.json、results.jsonl、metrics.json 并写 experiment_runs；运行前检查不通过就拒绝运行；检索失败或通道不可用时标为不完整。规则见 decisions.md D32，使用说明见 experiments/README.md。首轮复核发现并已修复：结果目录可能重名导致整次运行丢失；P@K 与另两项的平均口径不一致。已执行：后端测试 540 项通过（T19 新增 41 项）；代码检查通过；命令行冒烟（validate 空模板退出码 0；run 空数据集退出码 1；用临时小数据集时 import、run 在数据库连不上时以退出码 1 结束；不进 Git 的三类路径确认被忽略）。没有新下载（没有装 psutil，用标准库代替）。未测试（Not Tested）：test_experiments_db.py 8 项（需要 PostgreSQL）；从未在真实数据和真实 OpenSearch 上运行。**里程碑 MVP-1 未达成，没有打 tag**：没有评测数据，B0–B2 还没有真实数字；全部数据库和 OpenSearch 测试也都没有运行。CLAUDE.md 的命令说明待 Barry 同意后补（§4）。没有修改附录 A |
| T00–T19 补测 | 2026-11-16 | bc671e0 | 由 Barry 在另一台机器上完成，报告和改动上传到仓库的 `change-deepseek-v4/`（00–04 五份说明、`modified-files/`、`test-results/`）；本行只是据此整理，本会话没有重跑。环境：Windows 11、Python 3.14.0、PostgreSQL 16.15、OpenSearch 2.19.1 + analysis-smartcn 2.19.1（插件安装器报 AccessDenied，改为手工解压）。**结果（报告所载）：** docs/untested.md §1 的 11 个连调文件 190 passed / 0 failed / 0 skipped（专用空库，JUnit 原始结果在 `test-results/integration-results.xml`），覆盖 T03、T06、T07（含四项 🧪）、T08、T13、T14、T15、T16、T17、T18、T19；backend 完整套件 728 passed（8 项符号链接测试需管理员权限，普通权限下失败）；shared 105 passed；services/ocr_worker 63 passed、4 skipped，另在 ocr 环境真实识别 4/4；前端 48 passed、类型检查与构建通过；ruff 三个目录通过。**T00 补测：** OpenSearch 启动、smartcn 分词（22 词，standard 34 个单字）、BM25 与带权限过滤的精确向量检索正常，BM25 P50 15.28 ms / P95 26.93 ms，JVM 堆 475.5/1024 MB；OS-10 高亮转义已确认。**OCR 全链路（N01 `ocr_e2e.py`）：** 上传图片 → parse → OCR Worker（PP-OCRv5 mobile）→ 写索引 → 检索命中（evidence.source_type=ocr）→ 删除后片段清理、搜不到，PASS。**为通过测试做的修改 C01–C12（9 个文件，没有动表结构、接口、mapping、依赖版本）：** alembic.ini 中文注释导致 GBK 解码失败；实验结果路径改用 `as_posix()`；测试读文件显式 UTF-8；两处排序断言写错；两处测试前置数据不对；env_check 在 Windows 上没有 `resource`；OCR 子进程崩溃时先 join 再读退出码；OCR 在 Windows 上关闭 oneDNN。这些修改补测时只在副本里，已于 2026-11-17 合入本仓库（见下一行）。T00 仍为部分完成（OS-6 并发内存、IK 未测）；里程碑“基础系统”、MVP-0、MVP-1 仍未宣布达成 |
| 修复合入 | 2026-11-17 | 2b4d0f7 | 按 Barry 指示把 C01–C12（9 个文件，+30/−9）合入本仓库，不含 N01。本机（macOS）重跑：ruff 三个目录通过；backend 540 passed、188 skipped、0 failed（跳过的是 11 个连调文件，本机没有 PostgreSQL 和 OpenSearch）；shared 105 passed；services/ocr_worker main 环境 63 passed、4 skipped，ocr 环境真实识别 4/4（覆盖改过的 engine.py、engine_process.py）；`env_check/_common.py` 在 macOS 上 `peak_rss_mb()` 正常返回。**未测试（Not Tested）**：改过的 4 个连调测试文件和 alembic.ini、实验结果路径的数据库路径，在本机都没跑，依据是 2026-11-16 Windows 补测（代码逐行一致） |
| T20 | 2026-11-17 | 90bb44f | 计划由 Barry 于 2026-11-17 在本会话批准（“批准，开始写”；选“装 FastAPI (Recommended)”“默认 CPU，可配置 (Recommended)”）。开始前按 Barry 要求重读了 DEVPLAN、decisions.md、`T15-T19 opus5.5 develop.md` 和 `change-deepseek-v4/` 的记录，确认 C01–C12 与 T15–T19 的改动不影响 T20。`services/clip_service`：启动时检查权重文件（缺失或 sha256 不符即退出码 1，不下载）→ 加载 Chinese-CLIP ViT-B-16 并自检 → 监听 127.0.0.1:8001；`GET /health`、`POST /encode/text`、`POST /encode/image`（请求体为图片字节），响应都带 model_name、model_version（`cn_clip-1.6.0-5997ef32c50d`）、dim（512）；向量 L2 归一化；图片只收 PNG、JPEG，字节数与像素数双重上限（413），损坏（422）；错误格式与后端一致。规则见 decisions.md D33，接口见 api.md §9。新下载：clip 环境 9 个包约 13 MB（downloads.md #29–#37，比征求同意时说的多 1 个 opentelemetry-api）；权重从 env_check/models 复制到 models/clip（#38，没有下载）。已执行（本机 macOS，CPU）：接口测试 39 项通过（main 环境，假编码器）；🧪 真实模型测试 17 项通过（clip 环境，经真实 HTTP 服务）：健康检查、同一文本和同一图片两次编码向量完全一致、超过像素上限与字节上限 413、九种损坏或不支持的图片 422、出错后服务仍可用、EXIF 方向、文本与图片向量在同一空间；命令行冒烟：权重缺失、sha256 不符、端口非法均以退出码 1 结束，正常启动后 curl 三个接口结果正确；代码检查通过。首轮测试发现并已修复：超过字节上限时服务提前断开，调用方看到连接中断而不是 413。未测试（Not Tested）：MPS、CUDA、Windows、Linux；跨机器的向量一致性；后端 /health 对着真实服务；真实照片；并发（已登记 untested.md）。CLAUDE.md 的命令说明待 Barry 同意后补（§4）。提交时工作区里另有 11 个不属于 T20 的文件被别的会话改动（backend 一致性检查与检索、前端、ocr_worker），没有纳入本次提交。没有修改附录 A，没有动表结构和索引 |
| T15–T19 复核修正 | 2026-11-17 | 591f482 | Barry 要求由 Fable 5.2 重新查看 Opus 5.5 写的 T15–T19 并修正不足。方法：通读五个任务的全部源码，逐条对照 `docs/T15-T19 opus5.5 develop.md` 的查验要点；重跑全部能在本机运行的测试。结论：主干（处理顺序、数据库二次校验、幂等、降级）正确，没有发现违反附录 A 的地方；修正 11 处，见 decisions.md D34：① 检索服务应答格式不对时由 500 改为 503；② 索引里 document_id 不合法的残留数据不再让检索失败；③ 预览页关键词高亮会拆坏 `&`、`<`、`'` 的转义，且区分大小写；④ PDF 预览连续翻页时误报“这一页无法显示”；⑤ 检索页重复提交；⑥ OCR 识别子进程被 Ctrl-C 打断；⑦ `PgStore.save` 返回类型标注；⑧ `consistency repair` 在检索服务不可用时报“没有问题”并返回 0；⑨ 重建索引丢掉解析失败文档的 doc_meta；⑩ 实验运行前检查不看 OCR 任务失败，`import` 替换文件后旧文档留在库里，库里有数据集以外的文档时没有提示；⑪ qrels 的 grade 校验遇到特殊字符会崩溃。没有动表结构、接口、mapping 和依赖，没有新下载，没有修改附录 A。已执行：backend 554 passed、191 skipped；shared 105 passed；services/ocr_worker 63 passed、4 skipped，ocr 环境真实识别 4 项通过；前端类型检查与构建通过、单元测试 51 项通过；三个目录代码检查通过；浏览器里对着临时模拟接口检查了 PDF 预览和文本高亮。未测试（Not Tested）：新增的 3 项数据库测试（需要 PostgreSQL）；`consistency repair` 的新提示与退出码；Ctrl-C 实际操作；已登记到 untested.md。看过但没有改的事项记在 §4 |
| T21 | 2026-11-19 | a2facca | 代码由本会话 Opus 5.5 编写（Barry 于 2026-11-19 切换了模型，并要求主会话只写代码、其余交给子代理）；测试、复核、文档和提交由子代理完成。T21 不带 🔒，没有单独的计划批准。新模块 `backend/app/modules/vector_index/`：索引 `image_vectors`（1 分片 0 副本，dynamic strict，`vector` 为 512 维 knn_vector，不开 `index.knn`、不建 HNSW，附录 A12），`_id` = image_id，重复写入即覆盖；`search_vectors` 用 script_score（`knn_score` + `cosinesimil`）精确检索，model_name、model_version 和可访问 document_id 作为前置过滤，按 document_id 折叠。CLIP 客户端 `backend/app/modules/clip/client.py`（连不上、超时、5xx、429 可重试；413、422 等 4xx 不可重试），新增配置 `CLIP_ENCODE_TIMEOUT_SECONDS`（60）。embed 任务由通用 Worker 领取，parse 解析图片成功时在同一事务里创建；按 sha256 加咨询锁后查 `image_embeddings`，同一内容只编码一次（并发时也一样）；文档状态不跟随 embed 任务。cleanup 连带删除向量索引里的数据（`image_embeddings` 不删，D10）。一致性检查覆盖向量：新增 5 种检测项和修复类别 `embeddings`，`index`、`rebuild-indices` 连向量一起重建。规则与局限见 decisions.md D35。复核发现并已修复两处：还没有任何向量记录时误报 `image_vectors` 缺失；删除无用向量时没加锁，与 embed 有竞争。已执行：backend 640 passed、207 skipped（比 T15–T19 复核修正时多 86 项通过、16 项跳过）；shared 105 passed；两个目录代码检查通过。**未测试（Not Tested）**：`test_embed_db.py` 8 项（需要 PostgreSQL，含 🧪“重复图片只编码一次”的数据库版本与并发版本）、`test_vector_index_live.py` 8 项（需要 OpenSearch，含 🧪“过滤后只返回有权限的文档”），两项 🧪 的假对象版本已在单元测试里通过；没有连真实 CLIP 服务与 Worker 端到端跑过；已登记 untested.md。向量检索尚未接入检索编排（T22）。没有新下载，没有改表结构（不需要迁移），没有修改附录 A；新增 mapping 不影响已有两个索引，不需要重建 |
| T22 | 2026-11-19 | 889a48b | 带 🔒：计划由 Barry 于 2026-11-19 在本会话批准（“批准，按推荐做”：图像通道与文本通道并行、`SEARCH_CHANNEL_IMAGE_ENABLED` 仍默认关闭、查询编码超时 3 秒）。代码由主会话编写；复测、复核、文档和提交由子代理完成。图像通道：CLIP `POST /encode/text` 编码查询（应答自带模型标识，每次查询只调用一次）→ 维度核对 → `search_vectors` 精确检索（同模型、权限前置过滤）→ 与 meta、text 一起 RRF → 数据库二次校验；图像通道在单独线程里与文本通道并行执行；CLIP 超时、连不上、拒绝、应答不对、维度不一致、向量索引出错都只把 image 标为 unavailable 并写明原因（200），文本通道出错仍是 503；text 与 image 都命中时证据用文本片段。新增配置 `SEARCH_IMAGE_TIMEOUT_SECONDS`；查询专用 CLIP 客户端放在 `app.state.query_clip`；检索日志记录 `image_model`；实验入口也传入查询客户端。规则见 decisions.md D36，api.md §7.1 已更新。已执行：backend 668 项通过、208 项跳过（T22 新增单元测试 28 项，检索编排与 CLIP 客户端，含三通道 RRF 手算样例和假网络层下“关闭 CLIP 服务后检索正常并带降级标记”），shared 105 项通过，ruff 两个目录通过。未测试（Not Tested）：`test_search_db.py` 新增的 `test_clip_service_down_degrades_to_text_search`（需要 PostgreSQL，是 🧪“关闭 CLIP 服务后检索仍然正常并带降级标记”的真实接口版本）；图像通道查询体从未发给真实 OpenSearch；从未连真实 CLIP 服务编码查询；并行线程在真实负载下的表现、3 秒超时是否合适都没有实测（见 untested.md）。没有修改附录 A，没有新下载 |
| T23 | 2026-11-19 | 38d2c06 | 代码由主会话编写（Barry 要求主会话只写代码），复测、浏览器检查、文档和提交由子代理完成。T23 不带 🔒，没有单独的计划批准。检索页：图片结果左侧显示缩略图（原图取成 Blob 显示，只取 PNG/JPEG，>5 MB 显示占位，并发 4，新检索或离开页面时释放地址）；命中通道标签按通道着色；图片证据写“图像语义匹配（CLIP）”，与 OCR 命中分开；新增“图像语义检索（CLIP）”开关（默认关，`img=1` 进地址栏，请求显式发送 `channels.image`）；不可用通道用黄色提示，图像通道写明“本次结果只来自文字检索”。规则见 decisions.md D37。已执行：前端类型检查、构建通过，单元测试 62 项通过（T23 前为 51 项，新增 11 项：缩略图加载 5、命中依据与降级提示 5、`isImageType` 1）；构建的“chunk 大于 500 kB”警告在 T23 之前就有（在 HEAD 的副本上构建同样出现，主包约 874 kB）。浏览器检查对着临时模拟后端做（模拟后端不是项目代码，没有提交）：不勾选时请求 `image=false`；勾选后请求 `image=true`、地址栏有 `img=1`，刷新和从预览页返回后保持；图片结果显示缩略图，点击进入预览；>5 MB 显示“图片较大”占位；下载失败显示“无法显示”；图片证据显示“图像语义匹配（CLIP）”；通道标签三种颜色；image 不可用时出现黄色提示。未测试（Not Tested）：与真实后端、真实 CLIP 服务的联调；页面组件没有自动化测试。没有修改附录 A，没有新下载 |
| T24 | 2026-11-19 |  | 代码由主会话（Opus 5.5）编写，测试复核、文档和提交由子代理完成；T24 不带 🔒。新增 7 个实验配置：B3、B3-no-ocr、B3-no-clip、clip-only、B3-k10、B3-k30、B3-k100（k=60 即 B3）；实验配置新增可选 `rrf_k`（只覆盖本次实验的 k，随 search_params 与检索日志记录）；开了图像通道的配置运行前检查 CLIP 服务是否可用、数据集图片是否都有当前模型的向量，模型信息记进 config.json 的 `clip_model`；`mapping_sha256` 补上 `image_vectors`。规则见 decisions.md D38。已执行：backend 678 项通过、212 项跳过，shared 105 项通过，ruff 通过（T24 新增单元测试 10 项，跳过数从 208 增至 212 即新增的 4 项集成测试）。未测试（Not Tested）：test_experiments_db.py 新增 4 项（需要 PostgreSQL）；B3 及消融从未在真实数据和真实 CLIP 上运行。**MVP-2 里程碑未达成，没有打 tag**（原因同 MVP-0）。没有修改附录 A，没有新下载 |
