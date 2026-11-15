# T15–T19 opus5.5 develop：开发标记与查验指引

整理日期：2026-11-15
用途：标出 T15–T19 由 Opus 5.5 完成的开发范围，供 Fable 5.2 逐项查验。
整理依据：`git log 68385a0~1..d2de104`、`DEVPLAN.md` §3–§5、`docs/decisions.md` D28–D32、`docs/untested.md`。

------------------------------------------------------------------------

## 0. 给查验者的说明

### 0.1 开发方式

T15–T19 五个任务的代码都由“T11 实施 (fork)”会话编写；测试、复核、文档、提交由主会话完成。两个会话的模型都是 Opus 5.5。每个任务的计划批准记录写在 DEVPLAN §5 和对应的 D 编号里。

### 0.2 查验范围（提交）

| 任务 | 主提交 | 附带提交 | 日期 |
|---|---|---|---|
| T15 M11 检索 v1 | `68385a0` | `7fea619`（DEVPLAN 填 commit 号） | 2026-11-15 |
| T16 前端检索页与预览页 | `066350f` | `9e37f99`（填 commit 号）、`20b65cc`（记录保留 @napi-rs/canvas） | 2026-11-15 |
| T17 M6 OCR Worker | `0151f34` | `eda019d`（填 commit 号）、`0ec026f`（CLAUDE.md 命令） | 2026-11-15 |
| T18 M13 一致性检查 | `12f4ebb` | `de26101`（填 commit 号）、`b0524ad`（CLAUDE.md 命令） | 2026-11-15 |
| T19 M12 实验框架 v1 | `496d86b` | `0b0c173`（填 commit 号）、`d2de104`（CLAUDE.md 命令） | 2026-11-15 |

查看某个任务的全部改动：

```bash
git show --stat 68385a0
```

```bash
git diff 68385a0~1 d2de104 --stat
```

### 0.3 查验时的约束（来自 GLOBAL.md / CLAUDE.md）

- 不安装任何新依赖或工具；跑不了的测试标“未测试（Not Tested）”，并做代码复核。
- 本机没有 PostgreSQL、OpenSearch、Docker。所有需要它们的测试只能做代码复核，不能写成“通过”。
- 附录 A 的决策不得改动；发现与附录 A 冲突，先报告给 Barry。
- 能在本机执行的命令（main 环境）：`backend/`、`shared/` 下 `pytest`；`services/ocr_worker/` 下 `../../.venv-main/bin/python -m pytest`；三处 `ruff check . && ruff format --check .`；`frontend/` 下 `npm run typecheck && npm test && npm run build`（先把 `.tools/node/bin` 加进 PATH）。
- 记录值：backend 540、shared 105、ocr_worker 63（+ ocr 环境 4 项真实识别）、frontend 48，全部通过。查验时可重跑核对。

### 0.4 跨任务的重要改动（先看这一条）

**T17 把四个模块从 backend 移到了 shared**，因此 T13–T15 的代码路径在 T17 之后变了：

| 原位置 | 新位置 |
|---|---|
| `backend/app/modules/chunking/` | `shared/chunking/` |
| `backend/app/modules/text_index/`（含 `mappings/*.json`） | `shared/text_index/` |
| `backend/app/worker/loop.py` 里的 `PgTaskQueue` | `shared/task_queue.py`（loop.py 保留再导出） |
| backend 存储模块的 key 校验 | `shared/storage_keys.py`（`_resolve_key` 改为调用它） |

查验 T15 的检索代码时，`text_index` 应到 `shared/text_index/` 去找。`shared` 因此新增依赖 httpx 0.28.1。

------------------------------------------------------------------------

## 1. T15 M11 检索 v1（`68385a0`）

### 1.1 DEVPLAN 要求

B0 + BM25 双索引查询 → 聚合到 document_id（最佳片段作证据）→ 数据库二次校验 → 返回 `SearchHit`；OpenSearch 故障返回明确错误；每次检索写 SearchLog。
🧪 删除后立即查不到；取消共享后立即查不到；同一文件不重复；服务故障与“无结果”可区分。

### 1.2 与原计划的偏离（已获批）

`rrf.py` 原属 T22（🔒），提前到 T15。Barry 于 2026-11-15 选“T15 就用 RRF (Recommended)”。附录 A 未改。

### 1.3 主要文件

- `backend/app/modules/search/`：`channels.py`（meta、text 两路查询体与应答解析）、`rrf.py`、`params.py`、`service.py`（编排）、`schemas.py`
- `backend/app/api/search.py`：`POST /api/search`
- `backend/app/core/errors.py`：`SearchUnavailableError`（503 `SEARCH_UNAVAILABLE`）
- `backend/app/config.py`、`.env.example`：11 项 `SEARCH_*`
- 测试：`tests/unit/test_search_rrf.py`、`tests/unit/test_search_service.py`、`tests/integration/test_search_db.py`（未运行）

### 1.4 查验要点

1. **处理顺序**是否与 GLOBAL §4.4、§4.5 一致：各通道先聚合到 document_id → RRF（只用名次）→ 数据库二次校验 → 先过滤后截取 top_k → 写 SearchLog。
2. **二次校验**是否每次都查库、不缓存，是否用的是 `accessible_filter(user)`（D15 的唯一规则来源），是否对管理员同样过滤已软删除的文档。
3. **前置过滤**：普通用户两路都带可访问 ID 的 `terms`；管理员不加。确认它只用于召回，权限的保证仍在第 2 点。
4. **RRF**：Σ 1/(k + rank)，同分按 document_id 排序（确定性）；各通道原始名次和分数是否原样保留进 `SearchHit` 与 SearchLog。
5. **故障**：任一路 `TextIndexError`/`TextIndexUnavailable` → 整体 503；故障也写 SearchLog；返回的错误信息不含服务地址；422 不写日志。
6. **索引不存在**时先 `ensure_indices` 再查一次（检索接口因此不是纯只读），确认不会把“索引不存在”当空结果。
7. **高亮**：`encoder=html`；应答无 highlight 时在 Python 端 `html.escape` 后截取。
8. **配置约束**：`DEFAULT_TOP_K ≤ MAX_TOP_K ≤ CHANNEL_DEPTH`、至少一个通道开启，否则启动报错。
9. **图像通道**：默认关闭；开启时状态为 `unavailable`、其余通道照常。

### 1.5 已知局限（D28 已记录，查验时不必重复报告，但可评估是否可接受）

`terms` 超过 `max_terms_count` 会 503；管理员结果可能少于 top_k；`fragment_size` 只是近似；一路失败即整体 503；两路串行；查询路径可能建索引。

### 1.6 未测试

`test_search_db.py` 20 项（19 项需 PostgreSQL，1 项另需 OpenSearch）；查询体从未被真实 OpenSearch 接受过；高亮转义（OS-10）。

------------------------------------------------------------------------

## 2. T16 前端检索页与预览页、抽取文本接口（`066350f`）

### 2.1 DEVPLAN 要求

搜索框、结果列表（文件名 + 高亮片段 + 来源位置）、PDF 用 pdf.js 跳到对应页、Word/Excel 显示抽取文本。

### 2.2 主要文件

- 后端：`backend/app/api/document_text.py`（`GET /api/documents/{id}/text`）、`tests/integration/test_document_text.py`（未运行）
- 前端：`frontend/src/views/SearchView.vue`、`PreviewView.vue`、`components/PdfViewer.vue`、`api/search.ts`、`api/types.ts`、`utils/snippet.ts`、`utils/locator.ts`、`router.ts`、`App.vue`、`DocumentsView.vue`
- 前端测试：`tests/search.test.ts`、`tests/snippet.test.ts`、`tests/locator.test.ts`
- 新依赖：pdfjs-dist 6.5.438（Barry 批准，downloads.md #21；附带 @napi-rs/canvas #22、#23，Barry 决定保留）

### 2.3 查验要点

1. **XSS**：只在两处用 `v-html`（D22 已改），都先转义、再只放行 `<em>`。核对 `utils/snippet.ts` 的白名单逻辑和两处调用点，确认没有第三处 `v-html`。
2. **抽取文本接口**：只返回当前 `parse_version` 的片段、按 `seq` 排序、来自数据库（检索服务不可用时仍能预览）；`chunk_id` 跳页规则（不属于当前版本回第 1 页；格式错或属于别的文档 422）；权限与下载接口相同。
3. **503 与空结果**在界面上分开显示（GLOBAL §12）；失败通道逐个提示。
4. **pdf.js**：传入的是数据副本（ArrayBuffer 会被转交）；离开页面调用 `destroy()`；页码超范围时夹到有效页。
5. **位置显示**：`para_index` 0 起，界面 1 起；Word 只到段落（附录 A9，不能出现页码）。
6. **下载带令牌**：PDF、图片先带令牌取字节再显示，令牌不出现在 URL 里。
7. 前端类型 `api/types.ts` 与后端 `schemas.py`、`docs/api.md` 的字段是否一一对应。

### 2.4 未测试

`test_document_text.py` 11 项；前后端联调；页面组件无自动化测试；PDF 只用一份 5 页英文测试文件。**MVP-0 未达成，没有打 tag。**

------------------------------------------------------------------------

## 3. T17 M6 OCR Worker（`0151f34`）

### 3.1 DEVPLAN 要求

只领取 ocr 任务；图片或 PDF 页 → OCRResult → `source_type=ocr` 的 chunks → 索引；模型路径来自配置，缺失启动报错；记录模型名称和版本。
🧪 识别生成的测试图；OCR 失败时任务标记 failed、原文件仍在。

### 3.2 批准记录

Barry：“批准，开始写”；“按原计划做 OCR Worker”“PP-OCRv5 mobile (Recommended)”“沿用 env_check/.venv-ocr (Recommended)”。往 ocr 环境装 psycopg、PyMuPDF 时又单独确认（downloads.md #24–#26）。

### 3.3 主要文件

- `services/ocr_worker/ocr_worker/`：`config`、`models`（模型目录校验、hash/版本串）、`rendering`（200 dpi、像素上限）、`engine`、`engine_process`（常驻识别子进程）、`store`（psycopg 直接写 SQL 的 `PgStore`）、`pipeline`、`loop`、`__main__`
- `services/ocr_worker/tests/`（main 环境 63 项）、`tests/test_real_ocr.py`（ocr 环境 4 项）
- backend 侧：`worker/handlers/parse.py`（创建 ocr 任务时带 `payload.chunking`）、`tests/integration/test_ocr_worker_db.py`（未运行）
- shared 侧：见 §0.4 的模块迁移；`shared/text_index/indexer.py` 新增 `write_chunks`、`delete_chunk_range`

### 3.4 查验要点

1. **环境隔离（附录 A4）**：`services/ocr_worker` 不得导入 `backend`；只依赖 `shared` 和 ocr 环境里的包。可用 `grep -rn "from app\|import app" services/ocr_worker` 核对。
2. **不联网下载**：两个模型都显式 `model_dir`；三个可选子模型关闭；`PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK` 作保险；模型目录缺失时退出码 1。
3. **启动检查**：配置、模型目录、模型加载、数据库 `ping` 任一失败即退出码 1。
4. **结果取用**：只用 `rec_texts`、`rec_scores`、`rec_polys`（不用 `dt_polys`）。
5. **幂等**：`ocr_results` 按“文档 + locator”先删后插；索引先 `delete_chunk_range` 再写。
6. **序号**：`OCR_SEQ_BASE = 1e9`，PDF 第 p 页从 1e9 + (p−1)×1000；一页超过 1000 片段报错不重试；`seq` 为 32 位整数时的容量（约 114 万页）。
7. **竞争**（D30 的 4 步）：开始比较 `parse_version`；保存事务里 `FOR SHARE` 再查；写索引只写不删；写完复查，被删除则撤全部、被重新解析则只撤自己的区间。重点看第 4 步是否可能误删新版本片段。
8. **切分参数**来自 `payload.chunking`，与同版本正文一致，不读 OCR Worker 自己的配置。
9. **一页的行拼成一个文本块**再切分（不是每行一个片段）。
10. **模块迁移**后 backend 所有引用是否都改到 shared，`backend/pyproject.toml` 去掉 package-data、`shared/pyproject.toml` 加上，是否有遗漏。

### 3.5 已知局限（D30）

预览中 OCR 片段排在正文之后；多栏可能错序；只用合成图验证；macOS 上内存上限不生效；常驻子进程约 1 GB；单 Worker 串行。

### 3.6 未测试

`test_ocr_worker_db.py` 10 项；完整链路从未连真实数据库和 OpenSearch；真实扫描件；Linux 内存上限。

------------------------------------------------------------------------

## 4. T18 M13 一致性检查（`12f4ebb`）

### 4.1 DEVPLAN 要求

`python -m app.modules.consistency check|repair`：对账数据库、磁盘、两个索引；`repair` 需要显式参数。🧪 人为制造三类不一致都能检出。

### 4.2 主要文件

`backend/app/modules/consistency/`：`model.py`（问题类型与报告结构）、`collect.py`（读库、扫盘、扫索引）、`analyze.py`（19 种检测）、`repair.py`（7 类修复）、`__main__.py`（命令行、退出码）。测试：`tests/unit/test_consistency.py`（36 项新增中的大部分）、`tests/integration/test_consistency_db.py`（未运行）。

### 4.3 查验要点

1. **以数据库为准**：所有修复都朝数据库方向；`check` 只读。
2. **`repair` 安全阀**：必须 `--fix <类别>`，没有“全部”；不加 `--yes` 只演练；每个动作执行前复查数据库。
3. **busy 跳过**：有 pending/processing 的 parse、ocr 任务的文档，跳过片段类与索引类检查和修复。这是首轮复核修过的误删问题（`repair --fix db-chunks` 会删掉解析中的新片段），重点复核修复是否彻底，包括 `index` 单文档重建。
4. **`--min-age`**（默认 3600 秒）：无记录文件、临时文件不足此时间不报告（D17 的上传窗口）。
5. **`orphan-files`** 删除前再确认无记录；`unknown_file`（含符号链接）只报告不删。路径是否全部经过 `shared/storage_keys.py` 校验，避免越出存储根目录。
6. **`rebuild-indices`**：删 → 按版本库 mapping 重建 → 从数据库重新索引；帮助文字与演练输出提示先停 Worker。
7. **退出码**：0 无问题/修复完成；2 发现问题或演练；1 配置/数据库错误或检索服务不可用（后者仍输出库和盘的结果）。
8. 检测项与修复类别的对应表（D31）与代码是否一致。

### 4.4 已知局限（D31）

检查与修复之间不加锁；全量读进内存；`image_embeddings` 留给 T21；`missing_file` 不能自动修；需要完整后端配置。

### 4.5 未测试

`test_consistency_db.py` 12 项（含三类不一致 🧪）；从未对真实 OpenSearch 扫描、结构比对、重建；从未在真实数据上跑过。

------------------------------------------------------------------------

## 5. T19 M12 实验框架 v1（`496d86b`）

### 5.1 DEVPLAN 要求

`manifest.csv`、`qrels/*.tsv`、`queries.tsv`；`metrics.py` 的 P@K、R@K、nDCG@K（🧪 手算小例子）；`runner.py` 读配置 → 调 M11 → 保存原始排名 → 按查询类型分层输出指标；配置 B0、B1、B2。

### 5.2 批准记录

Barry：“批准，开始写”（由编写会话转述）。没有装 psutil，用标准库代替。

### 5.3 主要文件

- `backend/app/modules/experiments/`：`dataset.py`（格式校验、导入映射）、`metrics.py`（纯函数）、`config.py`、`runner.py`、`environment.py`（版本与机器信息快照）、`__main__.py`（`validate|import|run`）
- `experiments/`：`README.md`、`configs/B0.json`、`B1.json`、`B2.json`、`datasets/manifest.csv`、`queries.tsv`、`qrels/qrels.tsv`（都只有表头）
- `.gitignore`：原文件、`document_map.csv`、`runs/` 不进 Git
- 测试：`tests/unit/test_experiment_metrics.py`、`tests/unit/test_experiment_framework.py`、`tests/integration/test_experiments_db.py`（未运行）

### 5.4 查验要点

1. **指标公式**：P@K 分母恒为 K；R@K 分母为全部相关数；nDCG 增益 2^g − 1、折损 log2(rank+1)、IDCG 由全部标注截取前 K（与 trec_eval `ndcg_cut` 一致）。可自己手算一两个例子核对单元测试。
2. **无相关文件的查询**三项都记为空、不参与平均（首轮修过 P@K 口径）。
3. **对照组只通过配置切换**（GLOBAL §9.2）：B0/B1/B2 只差通道开关、`source_types`、`top_k`、K；`runner.py` 里不得有按实验名分支的检索代码。
4. **调用 M11**：是否直接调 `app.modules.search.service.search`，与线上检索同一条路径。
5. **运行前检查**四条（已导入且成功、无进行中任务、无未清理的已删文档、单一解析版本），`--allow-incomplete` 时写入问题并标不完整。
6. **不完整运行**：503 或通道不可用 → 退出码 2，不能当正式数据（GLOBAL §12）。
7. **结果目录**：UTC 微秒时间 + 实验名 + 6 位随机十六进制，在跑查询前创建（首轮修过重名问题）。
8. **实验账号** `experiment`：管理员、随机密码不保存、无法登录。
9. **记录完整性**：`config.json` 是否包含 GLOBAL §8.2 要求的检索参数、切分参数、OCR 触发阈值、mapping sha256、OCR 模型版本、git 提交号与脏标记。

### 5.5 已知局限（D32）

没有任何评测数据；OCR Worker 的 `OCR_MIN_CONFIDENCE`、`OCR_PDF_DPI` 没记进配置；运行前检查统计全库；中途数据库错误时已跑完的查询不写入 `results.jsonl`；无 CER、无性能实验。

### 5.6 未测试

`test_experiments_db.py` 8 项；从未在真实数据和真实 OpenSearch 上运行。**MVP-1 未达成，没有打 tag。**

------------------------------------------------------------------------

## 6. 首轮复核已发现并修复的问题（可重点回归）

| 任务 | 问题 | 记录 |
|---|---|---|
| T17 | 每行 OCR 文字各成一个片段 | D30 |
| T17 | 重新解析时 OCR 可能删掉新版本的索引片段 | D30 |
| T17 | 一个无效的测试用例 | DEVPLAN §5 |
| T17 | 启动时连不上数据库不退出 | D30 |
| T18 | 对正在解析的文档，`repair --fix db-chunks` 删掉新片段（另 3 个小问题、新增 3 个检测项） | D31 |
| T19 | 结果目录可能重名导致整次运行丢失 | D32 |
| T19 | P@K 与另两项的平均口径不一致 | D32 |

T15 复核发现 6 处局限，未改代码，写进 D28（见 §1.5）。T16 浏览器检查发现“直接打开 Word 预览不滚动”，已修复复查。

------------------------------------------------------------------------

## 7. 建议的查验输出格式

请按任务编号逐条给出：

| 任务 | 查验点编号 | 结论（符合 / 不符合 / 存疑） | 证据（文件:行号） | 建议 |
|---|---|---|---|---|

另列：
- 实际重跑的命令和结果（没跑的写“未运行”）；
- 与附录 A 或 GLOBAL.md 冲突的地方（只报告，不改）；
- 本文件 §1.5、§3.5、§4.4、§5.5 之外的新问题。
