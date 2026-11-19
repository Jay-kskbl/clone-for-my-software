# Windows 任务书（2026-11-19）

- 签发：Barry
- 执行：在 Barry 的 Windows 机器上工作的 GPT
- 撰写：Claude（macOS 会话）。Claude 不参与执行，也不在 macOS 上测试本任务书中的任何内容
- 基线：GitHub `main` 上包含本文件的那个提交（本文件随该提交一起推送）

本任务书有三项任务，按顺序做：

| 编号 | 任务 | 结果 |
|---|---|---|
| W1 | 补测：T24g 之后的代码、8 项符号链接测试、OCR 烟测脚本 | 全部测试的原始结果（JUnit XML） |
| W2 | T24j：写 DocVQA 数据集的下载与转换脚本 | 一个脚本 + 它的单元测试 + 转换好的实验数据 |
| W3 | 用 DocVQA 把实验流程从导入到 B0–B3 全部跑通 | 10 组实验的结果目录和汇总 |

做完后按第 8 节交付，按第 9 节自查。

------------------------------------------------------------------------

## 1. 背景

本仓库是 Barry 的本科毕业设计：基于多模态信息检索的智能文档管理系统。开始前**必须先读**：

1. `GLOBAL.md`：全局约束，冲突时以它为准；附录 A 是已定决策，不得修改
2. `CLAUDE.md`：命令速查（启动后端、Worker、OCR Worker、CLIP 服务、测试、实验）
3. `experiments/README.md`：实验数据的三个文件怎么填、操作顺序、结果格式、退出码
4. `本轮测试失败与未完成.txt`：上一轮 Windows 测试（2026-11-19，基于 `50b244b`）的结果
5. `docs/untested.md`：当前的未测试清单，尤其是第 1、3、7 节

上一轮之后新增的代码：

| 任务 | 改动 | 要补的测试 |
|---|---|---|
| T24g | 实验运行前检查拦下混用的 OCR 模型 | `test_experiments_db.py::test_preflight_reports_mixed_ocr_models` |
| T24h | 烟测脚本 `scripts/smoke/ocr_e2e.py` 查 `ocr_results.params` | 运行烟测脚本 |
| T24i | 新命令 `python -m app.modules.experiments reocr [--yes]` | `test_experiments_db.py` 中 `test_reocr_requeues_finished_ocr_tasks_of_the_current_version`、`test_reocr_refuses_while_parse_or_ocr_tasks_are_unfinished` |

------------------------------------------------------------------------

## 2. 必须遵守的规则

1. **不改附录 A 的任何决策**，不改数据契约（`shared/` 里的 Pydantic 模型）、表结构、索引结构、API。需要改时停下来问 Barry。
2. **不装新依赖。** 本任务书只批准一项网络下载：W2 的 DocVQA 数据（见第 5.1 节）。其他任何下载或安装（pip 包、模型、工具、Docker）都先问 Barry。
3. **不调参。** 实验结果不理想时如实报告，不改检索参数、切分参数、OCR 参数、RRF k 来“改善”结果。
4. **不伪造。** 没有实际执行的测试写“未测试（Not Tested）”并说明原因，不写“通过”。
5. **不改 W2 以外的业务代码。** W1、W3 中发现的 bug：先记录（现象、复现步骤、日志），再问 Barry 要不要修；修复必须是最小改动，并单独提交。
6. **文档分工**：`DEVPLAN.md`、`docs/untested.md`、`docs/decisions.md` 由 Claude 收到结果后统一更新，**GPT 不要改这三个文件**。GPT 只写第 8 节列出的文件。
7. 依赖分环境：backend、shared 和 W2 脚本用 main 环境（`.venv-main`）；OCR Worker 用 `env_check/.venv-ocr`；CLIP 服务用 `env_check/.venv-clip`。不得混装。
8. 提交：每项任务（W1、W2、W3）各一个 commit，只包含该任务的改动，提交信息用中文，写明任务编号。**不要 push**，由 Barry 决定。
9. 不在日志、报告、提交里写密码、令牌和连接串。

------------------------------------------------------------------------

## 3. 环境准备

沿用上一轮的 Windows 环境：Windows 11、Python 3.14.0、PostgreSQL 16.15、OpenSearch 2.19.1 + analysis-smartcn 2.19.1、三个虚拟环境、`models/ocr/` 与 `models/clip/clip_cn_vit-b-16.pt` 已就位。

1. 拉取 GitHub `main` 的最新提交，确认工作区干净（`git status`）。
2. **开启“开发人员模式”**（设置 → 系统 → 开发者选项），注销重登，在普通用户终端执行 `whoami /priv`，确认有 `SeCreateSymbolicLinkPrivilege`。拿不到这项权限时，W1 的 8 项符号链接测试改用有该权限的管理员终端运行，并在报告里写明用的是哪种。
3. 主库迁移到最新：在 `backend/` 下执行 `alembic upgrade head`，确认到 `0002`。
4. 测试库：确认空测试库 `docmgr_test` 存在，设置 `TEST_DATABASE_URL`、`TEST_OPENSEARCH_URL`（见 `.env.example`）。
5. 记录环境：Windows 版本、CPU、内存、Python 版本、PostgreSQL 版本、OpenSearch 版本，写进报告。

------------------------------------------------------------------------

## 4. W1：补测

### 4.1 要做的事

| # | 内容 | 命令（目录） |
|---|---|---|
| 1 | backend 全部测试，设置 `TEST_DATABASE_URL` 和 `TEST_OPENSEARCH_URL` | `backend/`：`..\.venv-main\Scripts\python -m pytest --junitxml=..\output\windows-w1\backend.xml` |
| 2 | shared 全部测试 | `shared/`：`..\.venv-main\Scripts\python -m pytest --junitxml=..\output\windows-w1\shared.xml` |
| 3 | OCR Worker：main 环境测试 + ocr 环境真实识别 | 见 `CLAUDE.md`；main 环境加 `--junitxml=..\..\output\windows-w1\ocr_worker.xml` |
| 4 | CLIP 服务：main 环境测试 + clip 环境真实模型 | 见 `CLAUDE.md`；main 环境加 `--junitxml=..\..\output\windows-w1\clip_service.xml` |
| 5 | 前端：`npm run typecheck`、`npm test`、`npm run build` | `frontend/` |
| 6 | 代码检查：`ruff check . && ruff format --check .` | `backend/`、`shared/`、`services/ocr_worker/`、`services/clip_service/` |
| 7 | OCR 烟测（T24h），需要 PostgreSQL、OpenSearch、OCR 模型 | 仓库根目录，用法见 `scripts/smoke/ocr_e2e.py` 开头的说明；运行前测试库要先 `alembic upgrade head` 到 `0002` |
| 8 | `reocr` 命令手动走一遍（T24i）：在 W3 的数据处理完后执行 `reocr`（演练）和 `reocr --yes`，再跑一次 OCR Worker，确认任务重新完成、片段数不翻倍 | 放到 W3 的第 6.4 节一起做 |

pytest 输出的跳过（skipped）项要逐条列出原因。

### 4.2 验收标准

- [ ] backend：**0 failed、0 skipped**（包括 8 项中的 6 项符号链接测试、T24g 的 1 项、T24i 的 2 项）
- [ ] shared：0 failed（包括 2 项符号链接测试）
- [ ] OCR Worker、CLIP 服务：0 failed；skipped 的逐条说明原因
- [ ] 前端三项命令都成功；四个目录的 ruff 都通过
- [ ] 烟测脚本最后输出 PASS，且打印出 `ocr_results.params` 的三个键
- [ ] `output/windows-w1/` 下有 4 份 JUnit XML
- [ ] 有失败时：报告里写清测试名、完整错误、判断是环境问题还是代码问题；**不改测试来让它通过**（上一轮改异常类名断言那样的兼容修改，要先问 Barry）

------------------------------------------------------------------------

## 5. W2：T24j DocVQA 下载与转换脚本

### 5.1 数据集

| 项目 | 内容 |
|---|---|
| 名称 | `vidore/docvqa_test_subsampled`（Hugging Face） |
| 页面 | https://huggingface.co/datasets/vidore/docvqa_test_subsampled |
| 许可 | MIT（数据集卡片）；图片原始来源为 UCSF Industry Documents Library，原论文 DocVQA（arXiv 2007.00398） |
| 规模 | 500 行，1 个 split（`test`）；原始 Parquet 约 292 MB |
| 每行 | 一条英文查询 + 一张扫描文档页图片 |
| 用到的列 | `questionId`（字符串）、`query`（字符串）、`image`（图片）、`docId`（整数）、`image_filename`（字符串，8 个字符，如 `rnbx0223`）、`page`（字符串） |
| 不用的列 | `answer`、`question_types`（全为空）、`data_split`、`source` |

**下载方式（Barry 批准的方案 B）**：不下载 Parquet，不装 pyarrow。用 main 环境已有的 httpx 调 Hugging Face 的数据接口：

```
GET https://datasets-server.huggingface.co/rows?dataset=vidore/docvqa_test_subsampled&config=default&split=test&offset=<0,100,...,400>&length=100
```

应答的 `rows[i].row` 是一行数据，其中 `image` 是 `{"src": <临时签名地址>, "height": ..., "width": ...}`，再逐个下载 `src`。签名地址会过期，必须在同一次运行里取完列表后立刻下载；过期了就重新取列表。

**用途声明**：这批数据**只用于打通实验流程和记录性能**，不作为论文的正式检索效果结论。原因：只有英文文字型查询，没有视觉型和混合型（附录 A18）；系统的分词器 smartcn 和图文模型 Chinese-CLIP 都面向中文。

### 5.2 脚本规格

文件：`scripts/datasets/docvqa_import.py`（新建目录 `scripts/datasets/`）。用 main 环境运行：

```bash
.venv-main\Scripts\python scripts\datasets\docvqa_import.py --out experiments\docvqa
```

| 参数 | 含义 |
|---|---|
| `--out` | 输出的实验目录（即 `experiments` 命令的 `--root`），必填 |
| `--limit N` | 只处理前 N 行，用来试跑；默认全部 500 行 |
| `--timeout` | 单次请求超时秒数，默认 60 |

输出目录结构（与 `experiments/README.md` 第 1 节一致）：

```
experiments/docvqa/
  datasets/manifest.csv
  datasets/files/docvqa/<image_filename>.<png|jpg>
  datasets/source_rows.jsonl     # 原始行（不含图片），留作出处，见下文
  queries.tsv
  qrels/docvqa.tsv
```

要求：

1. **编号确定**，重跑结果完全相同：
   - `file_id` = `dv_` + `image_filename`（例如 `dv_rnbx0223`）
   - `query_id` = `dvq_` + `questionId`（例如 `dvq_57344`）
   - 两个文件按编号排序写出
2. **一张图片一个文件。** 多条查询指向同一个 `image_filename` 时，只下载一次、只写一行 manifest，qrels 里每条查询各一行。重复的图片数写进脚本输出。
3. **manifest.csv**：`type` 全部为 `image`；`source` 写 `DocVQA via vidore/docvqa_test_subsampled (MIT); images: UCSF Industry Documents Library`；`notes` 写 `docId=<docId>; page=<page>`。CSV 用标准库 `csv` 写，处理好逗号和引号。
4. **queries.tsv**：`type` 全部为 `text`；`text` 为 `query` 原文。查询里的制表符、换行替换成空格（替换了几条写进输出）。
5. **qrels/docvqa.tsv**：每条查询一行，`grade` 为 `3`（就是要找的那页，见 README 的等级定义）。只标这一页，不推测其他页是否相关。
6. **图片校验**：按文件头判断真实格式，只接受 PNG（`\x89PNG\r\n\x1a\n`）和 JPEG（`\xff\xd8\xff`），扩展名按真实格式写；其他格式不转换，脚本报错并列出这些行。单张超过 `UPLOAD_MAX_BYTES`（50 MB）也报错。记录每张图片的 sha256、字节数、宽、高。
7. **可续跑**：已存在且 sha256 与上次记录一致的图片跳过不下；中途失败（网络、超时）重试 3 次，仍失败就报错退出（退出码 1），已下载的保留。
8. **原始行留底**：`source_rows.jsonl` 每行写一条原始数据（全部列，`image` 只留宽、高，不留签名地址），外加 `sha256`、`bytes`、`saved_as`。
9. **不碰数据库和后端**：脚本只下载和写文件，不上传。上传交给 `experiments import`。
10. 结束时打印汇总：行数、查询数、不重复的图片数、重复数、下载数、跳过数、总字节数、耗时。
11. 代码风格与仓库一致：中文注释解释原因，ruff 通过；纯函数（行 → manifest/queries/qrels 的转换、文件头判断、文本清洗）与网络部分分开。

`.gitignore` 增加（与现有 `/experiments/datasets/files/` 等三行同样的写法）：

```
/experiments/docvqa/datasets/files/
/experiments/docvqa/datasets/document_map.csv
/experiments/docvqa/runs/
```

`manifest.csv`、`queries.tsv`、`qrels/docvqa.tsv`、`source_rows.jsonl` 进 Git；图片不进 Git。

### 5.3 测试

新建 `scripts/datasets/tests/test_docvqa_import.py`（pytest，main 环境），用假的行数据，不联网：

- 编号规则、排序、重跑输出相同
- 两条查询共用一张图片：manifest 一行，qrels 两行
- 文件头判断：PNG、JPEG 通过，其他（例如 GIF、WebP、空文件）报错
- 查询文本里的制表符、换行被替换
- CSV 中带逗号、引号的字段能被 `experiments validate` 读回（可以直接调用 `backend/app/modules/experiments/dataset.py` 的 `load_dataset` 验证）
- 已存在且 sha256 一致的图片不再下载（网络部分用假对象）

### 5.4 验收标准

- [ ] ruff 通过；`test_docvqa_import.py` 全部通过
- [ ] 真实运行一次：500 条查询全部写出，图片数 = 不重复的 `image_filename` 数，全部为 PNG 或 JPEG，没有超过 50 MB 的
- [ ] 再运行一次：下载数为 0，四个输出文件与第一次逐字节相同
- [ ] 在 `backend/` 下 `python -m app.modules.experiments --root ..\experiments\docvqa validate` 退出码 0，统计与脚本汇总一致
- [ ] 新增 `docs/downloads.md` 的一条登记：内容、版本（应答里 `cached-assets` 地址中的数据集修订号，如 `49bf8f13…`）、来源、安装位置、总大小、用途、批准（“Barry 于 2026-11-19 签发 Windows 任务书时批准方案 B”）
- [ ] 新增 `docs/changes/T24j.md`，格式参照 `docs/changes/T24h.md`（来源、任务性质、逐文件修改记录、验证、修改建议）

------------------------------------------------------------------------

## 6. W3：用 DocVQA 跑通实验流程

### 6.1 用独立的库、存储和索引

DocVQA 只是流程验证，**不能和以后的正式数据集混在同一套数据里**（运行前检查会把数据集外的文档算作问题，正式数据集导入时也会受干扰）。为 W3 单独准备：

| 项目 | 设置 |
|---|---|
| 数据库 | 新建空库 `docmgr_docvqa`，`DATABASE_URL` 指向它，`alembic upgrade head` |
| 文件存储 | `STORAGE_ROOT` 指向一个新的空目录 |
| 索引 | `OPENSEARCH_INDEX_PREFIX=docvqa_` |
| 配置 | 其他值与主 `.env` 相同；OCR Worker、CLIP 服务的参数保持默认，不调 |

**怎么切换：** 后端、通用 Worker、OCR Worker、CLIP 服务都固定读仓库根目录的 `.env`，不支持指定别的文件；但**进程的环境变量优先于 `.env`**（`backend/app/config.py` 用 pydantic-settings，OCR Worker 和 CLIP 服务的 `config.py` 先读 `.env` 再用 `os.environ` 覆盖）。所以不要改主 `.env`，而是在每个启动这些进程的 PowerShell 窗口里先设置：

```powershell
$env:DATABASE_URL = "postgresql://<用户>:<密码>@localhost:5432/docmgr_docvqa"
$env:STORAGE_ROOT = "<新的空目录>"
$env:OPENSEARCH_INDEX_PREFIX = "docvqa_"
```

`experiments`、`consistency`、`alembic` 命令也要在设置过这三个变量的窗口里执行（`alembic` 经 `backend/app/db/migrations/env.py` 调用同一个 `load_settings()`，同样读 `DATABASE_URL`）。每开一个新窗口都要重新设置。在报告里写明用了哪些变量（不写密码），并在启动后用 `/health` 或日志确认连的是 `docmgr_docvqa`。

### 6.2 导入与处理

在 `backend/` 下（main 环境，使用 6.1 的配置）：

1. `python -m app.modules.experiments --root ..\experiments\docvqa validate`
2. `python -m app.modules.experiments --root ..\experiments\docvqa import`
3. 启动 CLIP 服务、通用 Worker（长期运行写法见 `CLAUDE.md`）、OCR Worker，等全部任务完成
4. 记录：开始和结束时间；parse、ocr、embed 三类任务各多少个 succeeded / failed；failed 的逐条写出原因
5. 执行一致性检查 `python -m app.modules.consistency check`，记录输出和退出码

处理期间记录（够用即可，正式的性能实验是以后的 T27）：总耗时、OCR 每张图平均耗时（从 OCR Worker 日志或任务的开始/完成时间算）、四个进程的峰值内存（任务管理器或 `Get-Process` 观察即可，写明方法）。

### 6.3 运行实验

每个配置跑一次，各带 `--repeat 3`：

```bash
python -m app.modules.experiments --root ..\experiments\docvqa run --config ..\experiments\configs\B0.json --repeat 3
```

依次运行：`B0`、`B1`、`B2`、`B3`、`B3-no-ocr`、`B3-no-clip`、`clip-only`、`B3-k10`、`B3-k30`、`B3-k100`（共 10 个）。

- 运行前检查没通过时，**不要加 `--allow-incomplete`**，先按提示把原因处理掉（例如等任务完成、CLIP 服务没开）；处理不了的记录下来问 Barry。
- 每个配置记录：退出码、结果目录名、`metrics.json` 里总体的 P@10、R@10、nDCG@10（或配置里实际计算的 K）、查询延迟 P50/P95、重复 3 次的波动。

**预期现象（用来自查，不是目标）**：数据集全是图片，没有正文，所以 B1（只查正文）应该几乎检不到；B2（正文 + OCR）应明显好于 B1；B0 只匹配文件名（`rnbx0223.png` 这种编号），应该接近 0。如果实际结果与这些预期不符，**不要改参数**，在报告里写出来，并附几条查询的 `results.jsonl` 原始行。

### 6.4 `reocr` 手动检查（W1 第 8 项）

实验跑完后：

1. 记录 `chunks` 索引里 `source_type=ocr` 的片段数（或数据库 `document_chunks` 里 ocr 片段数）
2. `python -m app.modules.experiments --root ..\experiments\docvqa reocr`：记录演练输出
3. `... reocr --yes`，启动 OCR Worker 处理完
4. 再数一次 ocr 片段数：应与第 1 步相同（覆盖，不叠加）；再跑一次 `B2` 确认退出码 0

### 6.5 验收标准

- [ ] W3 全程使用独立的库、存储、索引前缀；主库没有被写入（报告里写明怎么确认的）
- [ ] 导入的文档数 = manifest 行数；parse、ocr、embed 任务全部 succeeded；有 failed 的逐条列出原因，并说明是否影响结论
- [ ] 一致性检查退出码 0（或列出每条差异及原因）
- [ ] 10 个配置都以**退出码 0** 结束，每个都有 3 次重复的结果目录，含 `config.json`、`results.jsonl`、`metrics.json`
- [ ] `reocr` 前后 ocr 片段数相同，之后 `B2` 退出码 0
- [ ] 结果目录（`experiments/docvqa/runs/`）**不提交 Git**（是否提交等 T25 时再定）；把整个目录另外打包成 `docvqa-runs.zip` 交给 Barry

------------------------------------------------------------------------

## 7. 不要做的事

- 不改 `DEVPLAN.md`、`docs/untested.md`、`docs/decisions.md`、`GLOBAL.md`、`CLAUDE.md`
- 不改检索、切分、OCR、CLIP、RRF 的参数和默认值；不改 `experiments/configs/` 下的配置
- 不往主库、主存储、主索引里导入 DocVQA
- 不安装 Docker、pyarrow 或任何新包；不下载 DocVQA 以外的数据
- 不为了让测试通过而放宽断言、跳过测试或改成 junction
- 不 push

------------------------------------------------------------------------

## 8. 交付物

| 文件 | 内容 | 进 Git |
|---|---|---|
| `windows任务报告.md`（仓库根目录） | 按第 9 节的表逐项写结果（通过 / 失败 / 未测试 + 原因），环境信息，W1 失败详情，W2 汇总，W3 每个配置的指标表和处理耗时，发现的问题与建议 | 是 |
| `output/windows-w1/*.xml` | W1 的 4 份 JUnit XML | 是 |
| `scripts/datasets/docvqa_import.py`、`scripts/datasets/tests/test_docvqa_import.py` | W2 脚本与测试 | 是 |
| `experiments/docvqa/` 下的 manifest、queries、qrels、`source_rows.jsonl` | W2 生成的数据 | 是 |
| `.gitignore` | 第 5.2 节的三行 | 是 |
| `docs/downloads.md` | 新增一条 DocVQA 登记 | 是 |
| `docs/changes/T24j.md` | W2 修改记录 | 是 |
| `docvqa-runs.zip` | W3 全部结果目录 | 否，直接交给 Barry |

提交顺序：W1（报告初稿 + XML）→ W2（脚本、测试、数据、`.gitignore`、`downloads.md`、`T24j.md`）→ W3（报告补全）。

------------------------------------------------------------------------

## 9. 完成标准汇总

| # | 标准 | 对应 |
|---|---|---|
| 1 | backend 0 failed、0 skipped；shared 0 failed；OCR Worker、CLIP 0 failed | 4.2 |
| 2 | 8 项符号链接测试通过，写明用的开发人员模式还是管理员终端 | 4.2 |
| 3 | T24g 1 项、T24i 2 项集成测试通过 | 4.2 |
| 4 | 烟测脚本 PASS，打印出 params | 4.2 |
| 5 | 前端三项、四个目录的 ruff 通过 | 4.2 |
| 6 | 4 份 JUnit XML | 4.2 |
| 7 | W2 脚本 ruff 通过、单元测试通过 | 5.4 |
| 8 | 500 条查询、图片全部为 PNG/JPEG、重跑输出逐字节相同 | 5.4 |
| 9 | `validate` 退出码 0 | 5.4 |
| 10 | `downloads.md`、`T24j.md` 已写 | 5.4 |
| 11 | 独立的库、存储、索引；主库未被写入 | 6.5 |
| 12 | 全部任务 succeeded（或失败逐条说明）；一致性检查通过 | 6.5 |
| 13 | 10 个配置 × 3 次重复，全部退出码 0 | 6.5 |
| 14 | `reocr` 前后片段数相同 | 6.5 |
| 15 | 报告如实：每项写通过 / 失败 / 未测试，未测试写原因；实验数字只作流程验证 | 8 |

任何一项做不到，不要硬凑：在报告里写明哪一项、卡在哪里、已经试过什么，然后继续做不依赖它的部分。
