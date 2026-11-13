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
⑥ /finish-task           Claude 按 GLOBAL §11.3 汇报、勾选 DEVPLAN、提出 commit
⑦ 你确认后 commit         一个任务一个 commit；里程碑打 tag（mvp-0、mvp-1、mvp-2）
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
├── env_check/                 阶段一环境实测脚本
├── shared/                    【所有环境共用】数据契约(§3.5)、ID 规则、任务领取库 —— 只依赖 pydantic + psycopg
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
│   │   │   ├── chunking/      M7
│   │   │   ├── text_index/    M8
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

- [ ] **T05 M3 存储抽象** ⭐
  -   `put(stream) -> StoredFile(storage_key, sha256, size)`；`open(key)`；`delete(key)`
  -   先写临时文件、校验后再移动到 `{yyyy}/{document_id}/{sha256}.{ext}`
  -   文件魔数校验（不信任扩展名和 MIME）
  -   🧪 路径穿越（`../`、绝对路径、符号链接）被拒绝；中途失败不残留临时文件
- [ ] **T06 M1 认证与权限**
  -   注册/登录（JWT）、密码哈希、管理员角色
  -   `current_user` 依赖；`accessible_document_ids(user)`；`can_access(user, doc)`
  -   🧪 未登录 401；访问他人文档 403；管理员可见全部；共享后可见、取消共享后不可见
- [ ] **T07 M4 任务框架** 🔒⭐（全项目风险最高的基础模块，越早完成越好）
  -   `shared/tasks`：用 `FOR UPDATE SKIP LOCKED` 领取、续租、回收过期租约、重试计数、失败原因
  -   `backend/app/worker`：主循环、按任务类型分发、子进程执行（超时、内存上限）、处理 N 个任务后自动退出
  -   🧪 **崩溃恢复：** 领取后杀掉 Worker → 租约过期 → 任务被重新领取
  -   🧪 **并发：** 两个 Worker 不会领到同一任务
  -   🧪 **幂等：** 同一任务执行两次，结果不重复
  -   🧪 超过最大重试次数后标记为 `failed` 并保存原因
- [ ] **T08 M2 文档管理** ⭐
  -   上传（大小、格式、文件名长度限制）→ 存储 → 写 Document → 创建 parse 任务
  -   列表（分页、只列可访问文档）、下载、软删除（创建清理任务）、共享、标签
  -   🧪 上传中途失败不留半成品；删除后列表和下载都不可见；非法类型被拒绝
- [ ] **T09 M5 PDF 解析器**（可与 T05–T08 并行，纯函数）
  -   PyMuPDF 按页抽文本 → `ParsedDocument`；按页判断是否需要 OCR（阈值来自配置）
  -   🧪 fixtures：文本型 PDF、扫描型 PDF、混合型 PDF、加密或损坏的 PDF
- [ ] **T10 前端骨架**
  -   登录页、文件列表（含处理状态）、上传、下载、删除、共享
  -   **里程碑：基础系统** —— 能完整管理文件，数据库与文件存储一致，T07 的四项测试全部通过

**并行标注（W4 起，每周 2–3 小时）：** 每周补 10–20 条查询；按文字型、视觉型、混合型分类；标注相关文件（qrels 格式见 T19）。

### 阶段三：解析、OCR 与 BM25（W7–W9）

- [ ] **T11 M5 其余解析器**
  -   Word（段落级 locator）、Excel（工作表 + 单元格范围 locator）、图片（只做元数据，交给 OCR）
  -   zip 炸弹防护（解压总大小和文件数上限）、解析超时
  -   🧪 每种格式至少 2 个 fixture，外加 1 个畸形文件
- [ ] **T12 M7 切分**
  -   切分长度、重叠长度由配置控制；每个 chunk 带 locator；Excel 按行组切分
  -   🧪 切分后拼接覆盖原文；locator 正确；参数变化时 `parse_version` 变化
- [ ] **T13 M8 文本索引** 🔒
  -   `doc_meta`、`chunks` 两个索引的 mapping（分词器按 T00 结论），mapping 文件纳入版本管理
  -   `index_document(doc_id, chunks)`：先删除该文档的旧 `parse_version` 再写入；`delete_document(doc_id)`
  -   🧪 重复索引不产生重复数据；删除后查不到
- [ ] **T14 解析流水线**
  -   parse 任务处理器：解析 → 切分 → 写 DocumentChunk → 索引 → 回写状态；需要 OCR 的页和图片创建 ocr 任务
  -   清理任务处理器：删索引 → 删文件 → 硬删除记录
  -   🧪 端到端：上传 PDF → 等任务完成 → chunks 索引中有该文档的数据
- [ ] **T15 M11 检索 v1** ⭐
  -   B0 + BM25 双索引查询 → 聚合到 document_id（取最佳片段作为证据）→ **数据库二次校验** → 返回 `SearchHit`
  -   OpenSearch 故障时返回明确的错误，而不是空结果；每次检索写 SearchLog
  -   🧪 删除后立即查不到；取消共享后立即查不到；同一文件不重复出现；服务故障与"无结果"可以区分
- [ ] **T16 前端检索页**
  -   搜索框、结果列表（文件名 + 命中片段高亮 + 来源位置）、PDF 用 pdf.js 打开并跳到对应页、Word/Excel 显示抽取文本
  -   **里程碑 MVP-0（打 tag `mvp-0`）：** 上传 PDF/Word → 检索 → 定位到页/段落 → 删除后搜不到
- [ ] **T17 M6 OCR Worker** 🔒（ocr 环境）
  -   `services/ocr_worker`：只领取 ocr 任务；图片或 PDF 页 → OCRResult → 生成 `source_type=ocr` 的 chunks → 创建索引任务
  -   模型路径来自配置，缺失时启动报错；记录模型名称和版本
  -   🧪 识别生成的测试图；OCR 失败时任务标记 failed，原文件仍在
- [ ] **T18 M13 一致性检查**
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
- [ ] **T22 M11 检索 v2 + RRF** 🔒⭐
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

- （空）

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
