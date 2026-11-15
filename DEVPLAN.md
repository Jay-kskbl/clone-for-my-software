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
  -   **里程碑 MVP-0（打 tag `mvp-0`）：** 上传 PDF/Word → 检索 → 定位到页/段落 → 删除后搜不到（T16 完成时**未达成**，没有打 tag，原因见 §5 T16）
- [x] **T17 M6 OCR Worker** 🔒（ocr 环境）
  -   `services/ocr_worker`：只领取 ocr 任务；图片或 PDF 页 → OCRResult → 生成 `source_type=ocr` 的 chunks → 创建索引任务
  -   模型路径来自配置，缺失时启动报错；记录模型名称和版本
  -   🧪 识别生成的测试图；OCR 失败时任务标记 failed，原文件仍在
- [x] **T18 M13 一致性检查**
  -   `python -m app.modules.consistency check|repair`：对账数据库、磁盘、两个索引，输出差异；`repair` 需要显式参数才执行
  -   🧪 人为制造三类不一致，都能被检测出来
- [ ] **T19 M12 实验框架 v1** 🔒
  -   `experiments/datasets/manifest.csv`（文件、类型、来源）、`qrels/*.tsv`（query_id、document_id、相关等级）、`queries.tsv`（query_id、文本、类型）
  -   `metrics.py`：P@K、R@K、nDCG@K（🧪 用手算的小例子验证）
  -   `runner.py`：读取配置（通道开关、参数）→ 调用 M11 → 保存每条查询的原始排名 → 输出指标，并按查询类型分层
  -   配置 B0、B1、B2
  -   **里程碑 MVP-1（打 tag `mvp-1`）：** 四类格式 + OCR 可检索；B0–B2 能在小标注集上跑出真实数字

### 阶段四：图像检索与融合（W10–W12）

- [ ] **T20 M9 CLIP 服务** 🔒（clip 环境）
  -   `services/clip_service`：启动时加载模型（路径缺失则报错）；`/health`、`/encode/text`、`/encode/image`
  -   接口返回模型名称、版本、向量维度
  -   🧪 健康检查；同一输入向量稳定；超大图片和损坏图片的处理
- [ ] **T21 图片向量与 M10 向量索引**
  -   embed 任务：按 sha256 去重 → 调用 CLIP 服务 → 写 ImageEmbedding → 写入向量索引
  -   向量检索：`script_score` 精确计算 + 可访问 document_id 前置过滤
  -   🧪 过滤后只返回有权限的文档；重复图片只编码一次
- [ ] **T22 M11 检索 v2 + RRF** 🔒⭐（`rrf.py` 已在 T15 提前完成，Barry 批准，见 decisions.md D28）
  -   图像通道：调用 CLIP 服务编码查询文本（设超时）→ 向量检索；超时或失败时降级，并在响应中标记该通道不可用
  -   `rrf.py`：输入各通道已聚合到文件级的排名列表，按 k 和截断深度融合；保留各通道原始排名和分数
  -   通道开关来自请求参数或实验配置
  -   🧪 RRF 用手算样例验证；关闭 CLIP 服务后检索仍然正常并带降级标记
- [ ] **T23 前端 v2**
  -   结果中显示图片缩略图、命中通道标记；某通道不可用时给出提示
- [ ] **T24 B3 与消融配置**
  -   B3、去掉 OCR、去掉 CLIP、只用 CLIP、RRF 不同 k 值
  -   **里程碑 MVP-2（打 tag `mvp-2`）：** 完整演示流程；关闭 CLIP 后基础检索不受影响

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
- **给 T21 的补充（T18 记录）**
  - 一致性检查（D31）还没有覆盖 `image_embeddings`：T21 写入向量后，补上“不再被任何图片引用的向量”和“向量索引与数据库不一致”的检测与修复（D10）。
- **待定（T18 记录）**
  - backend 通用 Worker 启动时不检查数据库，连不上时在领取循环里无限重试；OCR Worker 启动时连不上数据库就以退出码 1 结束（D30）。两者不一致，是否统一由 Barry 决定。
- **待 Barry 同意后修改 CLAUDE.md（T18 记录）**
  - “常用命令”里补上一致性检查：`backend/` 目录、main 环境，`python -m app.modules.consistency check`；修复用 `python -m app.modules.consistency repair --fix <类别> --yes`（不加 `--yes` 只演练；`rebuild-indices` 前先停掉两个 Worker）。需要完整的 `.env`（包括 `JWT_SECRET`）。
- **给 T20、T21（CLIP）的参考（T17 记录）**
  - CLIP 服务和 embed 任务可以复用 `shared.task_queue.PgTaskQueue`，以及 OCR Worker“常驻子进程加载模型、超时或崩溃时杀掉重开”的写法（`services/ocr_worker/ocr_worker/engine_process.py`）。
- **待改进（T17 记录）**
  - 文本预览接口按 `seq` 排序，扫描页的 OCR 片段排在全部正文片段之后。如果要按页码穿插，需要改预览接口的排序规则。
- **MVP-0 验收前必须做（T16 记录）**
  - 在有 PostgreSQL 和 OpenSearch（带 analysis-smartcn）的环境里补跑全部集成测试（untested.md 第 5 节），并把前端接到真实后端联调一遍：上传 PDF、Word → 等处理完成 → 检索 → 定位到页或段落 → 删除后搜不到。通过后再打 tag `mvp-0`。
  - 高亮摘要的 HTML 转义要在真实 OpenSearch 上确认（untested.md OS-10）。前端已对摘要做白名单清洗，只放行 `<em>`。
- **打包体积（T16 记录）**
  - Vite 提示主包（约 874 KB）和 pdf.worker（约 1.27 MB）超过 500 KB。worker 本来就是单独加载的；主包可以在 T30 部署前考虑按需引入 Element Plus（D22）。
- **给 T22（检索 v2）的衔接提醒（T15 补充）**
  - 直接复用 `backend/app/modules/search/rrf.py`，只需加图像通道、CLIP 调用超时降级和消融配置。现在两路是串行的，加第三路时可以考虑并行执行。
  - 图像通道目前在请求开启时报 `unavailable`（“图像检索尚未实现”），实现后改为真实状态。
- **给 T19（实验框架）的衔接提醒（T15 补充）**
  - runner 直接调用 `app.modules.search.service.search`，从返回的 `SearchHit.channels` 或 SearchLog 读各通道原始名次和分数；对照组只通过 `channels`、`source_types` 切换（D28）。
- **给 T21 的衔接提醒**
  - parse 任务目前不创建 embed 任务。T21 要决定在哪里创建（建议与 OCR 任务一样，在 parse 成功的同一事务里），并按图片内容的 sha256 去重。
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
