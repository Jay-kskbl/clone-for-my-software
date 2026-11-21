# Windows 任务书（2026-11-19）

- 签发：Barry
- 执行：在 Barry 的 Windows 机器上工作的 GPT
- 撰写：Claude（macOS 会话）。Claude 不参与执行，也不在 macOS 上测试本任务书中的任何内容
- 基线：GitHub `main` 上包含本文件的那个提交（本文件随该提交一起推送）
- 增补：2026-11-21 14:26 添加 W4（T24s 前端界面优化的真实后端联调与界面核对，第 10 节），并在第 1、8、9 节补了对应的行
- 增补：2026-11-21 14:29 第 1 节补上 T24k–T24r（任务书写成之后、T24s 之前完成的 8 项；T24j 就是 W2，还没有做）
- 增补：2026-11-21 14:37 添加 W5（T24k、T24l、T24m、T24o、T24p 在真实环境上的补测，第 11 节），并在第 1、4、8、9 节补了对应的行
- 增补：2026-11-21 19:40 收到第一轮执行结果（GitHub `bb3883c`，执行者 Codex，基于 `8fb5830`）后添加：第 0 节（当前状态、基线同步、报告格式、测试计划、怎样才算完成）；W6（新基线复测、符号链接、其余真实环境补测、补交 W1–W3 原始数据，第 12 节）；W7（跨机器 CLIP 向量一致性、同时运行的内存、负载下的查询编码，第 13 节）；第 14 节（交回的原始数据与 Claude 的核对方法）；第 15 节（不交给 Windows 的项目）。并在第 2、8、9 节补了对应的行。W1–W5 已写的内容没有改

本任务书有七项任务。**执行顺序以第 0.4 节为准**（W4 于 2026-11-21 14:26 添加，W5 于 14:37 添加，W6、W7 于 19:40 添加；W1–W3 第一轮已执行，状态见第 0.1 节）：

| 编号 | 任务 | 结果 |
|---|---|---|
| W1 | 补测：T24g 之后的代码、8 项符号链接测试、OCR 烟测脚本 | 全部测试的原始结果（JUnit XML） |
| W2 | T24j：写 DocVQA 数据集的下载与转换脚本 | 一个脚本 + 它的单元测试 + 转换好的实验数据 |
| W3 | 用 DocVQA 把实验流程从导入到 B0–B3 全部跑通 | 10 组实验的结果目录和汇总 |
| W4 | T24s 前端：真实后端联调、鼠标真实拖入、Windows 浏览器显示、重新截图（2026-11-21 14:26 添加） | 报告里的逐项核对结果 + 新界面截图 |
| W5 | T24k/T24l/T24m/T24o/T24p 的补测：换行符预检、一致性检查的结构比较与重建、空库启动 Worker、连接超时、生产构建（2026-11-21 14:37 添加） | 报告里的逐项结果（命令输出、退出码、耗时） |
| W6 | 新基线上的全套复测；8 项符号链接测试（Barry 本人的终端）；一致性修复、Worker 崩溃恢复与并发、解析超时、Ctrl-C、端口占用、真实文件解析与 OCR 的真实环境补测；补交 W1–W3 的原始数据（2026-11-21 19:40 添加） | JUnit XML、数据库与索引的导出文件、命令输出、真实样本与人工抄录文本 |
| W7 | 跨机器 CLIP 向量一致性；数据库、OpenSearch、后端、两个 Worker、CLIP 同时运行时的内存采样；OCR 负载下的查询编码耗时（2026-11-21 19:40 添加） | 向量 JSON、内存采样 CSV、检索耗时 CSV |

做完后按第 8 节交付，按第 9 节自查，按第 14 节交回原始数据。

------------------------------------------------------------------------

## 0. 当前状态与测试计划（2026-11-21 19:40 添加）

### 0.1 各任务的状态

| 编号 | 状态（2026-11-21 19:40） | 依据 | 还差什么 |
|---|---|---|---|
| W1 | **部分完成**：除 8 项符号链接测试外全部通过（backend 932 passed、6 failed；shared 103 passed、2 failed；OCR Worker、CLIP 真实模型、前端、ruff、OCR 烟测都通过）。失败原因：执行账号 `codexsandboxoffline` 没有 `SeCreateSymbolicLinkPrivilege`，提权返回退出码 4 | `windows任务报告.txt` 第二、三节，`output/windows-w1/*.xml` | ① 8 项符号链接测试由 Barry 本人的终端跑（W6 第 12.3 节）；② W1 测的是 `8fb5830`，之后 Mac 上的提交（T24k–T24s）没测过，要在新基线上重跑（W6 第 12.2 节） |
| W2 | **执行方报告完成**：500 条查询、500 张 JPEG、重跑逐字节一致、`validate` 退出码 0、脚本测试 12 passed | 报告第四节，`bba3a1b` | Claude 核对（第 14.2 节） |
| W3 | **执行方报告完成**：10 个配置 × 3 次重复，退出码都是 0；`reocr` 前后 OCR 片段都是 1589；一致性检查退出码 0 | 报告第五至七节，`docvqa-runs.zip`（SHA-256 `287E939A…452504`） | ① 补交原始数据（W6 第 12.11 节）；② Claude 核对（第 14.2 节） |
| W4 | 未开始 | — | 按第 10 节做 |
| W5 | 未开始 | — | 按第 11 节做 |
| W6、W7 | 新增，未开始 | — | 按第 12、13 节做 |

第一轮里值得记下的发现（Claude 会写进 `docs/untested.md` 和 T27 的参考）：两张图片（`mjbw0217.jpg`、`mkvw0217.jpg`）的 OCR 子进程以 `0xC0000005`（访问违例）退出，自动重试 3 次都失败，改成只开一个 OCR Worker 后手动重试才成功；处理阶段同时开了 4 个 OCR Worker，OCR 每个任务平均 53.57 秒（macOS 单张测试图 0.44 秒，两者条件不同，不能直接比较）；DocVQA 上 B3 的指标低于 B2（CLIP 对英文查询起了负作用）。

### 0.2 基线同步（Barry 做，Claude 不 push）

GitHub `main`（`bb3883c`）上有第一轮的 4 个提交，但**没有** Mac 上之后的提交（截至本次修订前共 26 个：T24k–T24s、W4、W5、开发报告；加上本次修订是 27 个）。W4–W7 都要用新代码，所以开始之前：

1. Barry 在 Mac 上把 `origin/main` 合进本地 `main`（Claude 可以代做合并，但要 Barry 说“合并”），再由 Barry 推到 GitHub。
2. Windows 上 `git pull`，确认是快进（fast-forward），`git log -1 --format=%H` 的提交里包含本任务书第 0 节（`git show HEAD:windows任务书.md` 能找到“0. 当前状态与测试计划”）。
3. 把这个提交号写进报告，并写进每个任务的 `output/windows-<任务>/git-head.txt`（第 14.1 节）。W6、W7 的结果只对这个提交有效。

### 0.3 报告格式

Barry 要求 Windows 上的执行者不新建、不修改 `.md` 文件。所以：

- 报告继续写在 `windows任务报告.txt`，在末尾按 W4、W5、W6、W7 各加一节，不改前面已有的内容。
- 任务书里要求写成 `.md` 的交付物（例如第 8 节的 `docs/changes/T24j.md`、`docs/downloads.md`），改为同名 `.txt`。Claude 核对后再转成 `.md` 并入文档。
- 文中的“GPT”指在 Windows 上执行本任务书的 AI（第一轮是 Codex），规则相同。

### 0.4 测试计划（执行顺序）

| 顺序 | 内容 | 谁做 | 依赖 | 预计耗时 |
|---|---|---|---|---|
| 1 | 基线同步（第 0.2 节） | Barry | — | 10 分钟 |
| 2 | W5 第 11.2 节：换行符预检 | GPT | 1 | 10 分钟 |
| 3 | W6 第 12.2 节：新基线全套复测 | GPT | 2 | 1 小时 |
| 4 | W6 第 12.3 节：8 项符号链接测试 | **Barry 本人**（开发人员模式或管理员终端） | 1 | 20 分钟 |
| 5 | W6 第 12.11 节：补交 W1–W3 原始数据（`docmgr_docvqa` 还在时先导出，免得后面的步骤改了它） | GPT | 1 | 30 分钟 |
| 6 | W5 第 11.3–11.6 节 | GPT | 3 | 1 小时 |
| 7 | W4（第 10 节） | GPT；第 10.3 节的鼠标拖入要有人操作 | 3 | 2 小时 |
| 8 | W6 第 12.4–12.10 节 | GPT；第 12.9 节的真实样本和人工抄录由 Barry 准备 | 3、5 | 半天 |
| 9 | W7（第 13 节） | GPT | 8（用 W6 建好的 `docmgr_w6`） | 1 小时 |
| 10 | 按第 14.1 节整理原始数据、算 SHA-256、提交；Barry 推送，大文件另交 | GPT、Barry | 全部 | 30 分钟 |

某一步做不了时，按第 9 节最后一句处理：写明卡在哪里，继续做不依赖它的步骤。

### 0.5 怎样才算“测试已成功完成”

一项测试要同时满足下面三条，Claude 才会把它从 `docs/untested.md` 删除、在 DEVPLAN 里记成已验证：

1. **执行方自查通过**：该节“验收标准”里的每一条都打了勾，报告里写了命令、输出、退出码。
2. **原始数据齐全**：第 14.1 节列出的文件都交回了，`SHA256SUMS.txt` 与收到的文件一致，`git-head.txt` 是第 0.2 节确认的提交。
3. **Claude 核对通过**：按第 14.2 节的方法，用原始数据重算或比对，结果与报告一致。

只有报告里的一句“通过”、没有原始数据的，记为“执行方报告通过，未核对”，不算完成。Claude 核对的结果与报告不一致时，以原始数据为准，把这一项列给 Barry，不在 `untested.md` 里删除。

------------------------------------------------------------------------

## 1. 背景

本仓库是 Barry 的本科毕业设计：基于多模态信息检索的智能文档管理系统。开始前**必须先读**：

1. `GLOBAL.md`：全局约束，冲突时以它为准；附录 A 是已定决策，不得修改
2. `CLAUDE.md`：命令速查（启动后端、Worker、OCR Worker、CLIP 服务、测试、实验）
3. `experiments/README.md`：实验数据的三个文件怎么填、操作顺序、结果格式、退出码
4. `docs/changes/windows-2026-11-19-原始说明.txt`（原在仓库根目录，T24r 移到这里）：上一轮 Windows 测试（2026-11-19，基于 `50b244b`）的结果
5. `docs/untested.md`：当前的未测试清单，尤其是第 1、3、7 节

上一轮之后新增的代码：

| 任务 | 改动 | 要补的测试 |
|---|---|---|
| T24g | 实验运行前检查拦下混用的 OCR 模型 | `test_experiments_db.py::test_preflight_reports_mixed_ocr_models` |
| T24h | 烟测脚本 `scripts/smoke/ocr_e2e.py` 查 `ocr_results.params` | 运行烟测脚本 |
| T24i | 新命令 `python -m app.modules.experiments reocr [--yes]` | `test_experiments_db.py` 中 `test_reocr_requeues_finished_ocr_tasks_of_the_current_version`、`test_reocr_refuses_while_parse_or_ocr_tasks_are_unfinished` |
| T24k（2026-11-21 14:29 添加） | `891facb`：通用 Worker 与 OCR Worker 连接数据库带 `connect_timeout`，新配置 `WORKER_DB_CONNECT_TIMEOUT_SECONDS`、`OCR_WORKER_DB_CONNECT_TIMEOUT_SECONDS`（默认 10 秒，`.env.example` 已同步）。对执行的影响：`.env` 不用改（不写就用默认值）；数据库连不上时 Worker 约 10 秒内报错退出，不再卡一两分钟 | W1 第 1–3 项会一并跑到（shared `test_task_queue.py`，backend `test_worker_main.py` 等，OCR Worker `test_store_connect.py`）；连不通的地址上的实际超时见 W5 第 11.5 节（2026-11-21 14:37 添加） |
| T24l（2026-11-21 14:29 添加） | `f31590b`：通用 Worker 启动时比对 `alembic_version` 与代码里的最新迁移，OCR Worker 启动时检查它读写的表和列；不一致就以退出码 1 结束并提示 `alembic upgrade head`。迁移仍只到 `0002`。对执行的影响：W3 的 `docmgr_docvqa`、W4 的 `docmgr_ui` 必须先 `alembic upgrade head` 再启动 Worker（第 6.1、10.1 节已写），漏了 Worker 会直接退出 | W1 第 1、3 项会一并跑到（`test_worker_schema.py`、`test_store_schema.py` 是假连接的单元测试）；W3、W4 启动 Worker 时等于在真实 PostgreSQL 上走了一次“已迁移、检查通过”；空库和版本落后的情况见 W5 第 11.4 节（2026-11-21 14:37 添加） |
| T24m（2026-11-21 14:29 添加） | `49c67e4`：前端测试逐文件核对 `public/pdfjs/` 与已安装的 pdfjs-dist（比 sha256），新增 `npm run sync:pdfjs`；`package.json` 只加了这个脚本，依赖没变，不用重新 `npm install`。对执行的影响：如果这台机器的 git 开了 `core.autocrlf`，`public/pdfjs/` 里的 LICENSE、`.js` 等文本文件检出时会变成 CRLF，与 `node_modules` 里的 LF 版本 sha256 不同，`pdfjs-assets.test.mjs` 会失败。遇到时按第 4.2 节记成环境问题，写出 `git config core.autocrlf` 的值，**不要**运行 `sync:pdfjs` 去覆盖、也不要改测试 | W1 第 5 项的 `npm test`（`tests/pdfjs-assets.test.mjs` 3 项）；**W1 之前先做 W5 第 11.2 节的换行符预检**（2026-11-21 14:37 添加） |
| T24n（2026-11-21 14:29 添加） | `0754962`：文件列表的标签不再被截断（文件名单行省略、标签换行）。T24s 又重排了这张表。对执行的影响：无 | W1 第 5 项；显示效果在 W4 第 10.2 节第 2 项一起看 |
| T24o（2026-11-21 14:29 添加） | `33a2384`：一致性检查的结构比较从 3 个键扩大到 12 个（含 `search_analyzer`），分析配置逐项比较，提示写出具体差异；mapping 和索引结构没有改，不需要重建索引。对执行的影响：W3 第 6.2 节第 5 步是这个检查第一次对真实 OpenSearch 运行。如果新建的索引就报“结构不一致”，多半是 OpenSearch 自己补上的键造成的误报：把提示原文写进报告，不要为此运行 `repair --fix rebuild-indices` | W1 第 1 项（`test_consistency.py`）；W3 第 6.2 节第 5 步；人为制造结构差异再重建见 W5 第 11.3 节（2026-11-21 14:37 添加） |
| T24p（2026-11-21 14:29 添加） | `aaa4bbc`：Element Plus 改为按需引入，首屏 JS 约 874 KB → 483 KB；没有新依赖，不用重新 `npm install`。对执行的影响：无；`npm run build` 在本机（T24s 之后）已不再提示分块超过 500 KB，Windows 上若仍提示，写进报告即可，不算失败 | W1 第 5 项（`tests/element.test.ts` 3 项和构建）；生产构建在浏览器里打开见 W5 第 11.6 节（2026-11-21 14:37 添加） |
| T24q（2026-11-21 14:29 添加） | `b18909e`：新增根目录 `README.md`（课题说明、快速开始、文档索引）。对执行的影响：无；命令仍以 `CLAUDE.md` 和本任务书为准 | 无 |
| T24r（2026-11-21 14:29 添加） | `f0ef765`：整理零散文件，上一轮的原始说明移到 `docs/changes/windows-2026-11-19-原始说明.txt`，截图移到 `docs/screenshots/windows-2026-11-19/`，空的 `output/` 目录删了。对执行的影响：第 1 节第 4 项的路径已改；W1 的 JUnit XML 仍写到 `output/windows-w1/`，`pytest --junitxml` 会自己建目录 | 无 |
| T24s（2026-11-21 14:26 添加） | 前端界面优化（`281b226`，只改前端）：侧栏布局、拖拽上传与逐个文件的上传记录、检索通道面板、每条结果三个通道的名次与 RRF 融合分。只对着临时模拟后端检查过 | W1 第 5 项的前端测试（本机 93 项）；W4（第 10 节）的联调与界面核对 |

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
10. **交回原始数据**（2026-11-21 19:40 添加）：W4–W7 每一项都按第 14.1 节交回原始文件（JUnit XML、`--json` 输出、SQL 导出、命令输出原文），不能只在报告里写结论。导出前检查一遍，去掉密码、令牌、连接串。
11. **写明基线**（2026-11-21 19:40 添加）：每个任务开始前记下 `git rev-parse HEAD` 和 `git status --porcelain`；工作区有未提交改动时先停下来问 Barry，不要带着改动测试。

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

**（2026-11-21 14:37 添加）开始本节之前，先做第 11.2 节的 T24m 换行符预检**，把结果记进报告，否则第 5 项的前端测试失败时分不清是代码问题还是换行符问题。

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
| `windows任务报告.md` 的 W4 一节（2026-11-21 14:26 添加） | 第 10 节每个核对点的结果（通过 / 不符 / 未测试 + 原因）、浏览器名称和版本、发现的问题 | 是 |
| `docs/screenshots/windows-<执行日期>-t24s/*.png`（2026-11-21 14:26 添加） | 第 10.5 节的新界面截图 | 是 |
| `windows任务报告.md` 的 W5 一节（2026-11-21 14:37 添加） | 第 11 节每一步的命令、完整输出（去掉密码和连接串）、退出码、耗时；`core.autocrlf` 的值和 `git ls-files --eol` 的结果；结果与预期不符的逐条写出 | 是 |

| `windows任务报告.txt` 的 W6、W7 两节（2026-11-21 19:40 添加；报告用 `.txt`，见第 0.3 节） | 第 12、13 节每一步的命令、输出、退出码、耗时；结果与预期不符的逐条写出 | 是 |
| `output/windows-w4/` 至 `output/windows-w7/`（2026-11-21 19:40 添加） | 第 14.1 节列出的原始数据、`git-head.txt`、`SHA256SUMS.txt` | 是（单个文件超过 5 MB 的除外，见第 14.1 节） |
| 大文件压缩包（2026-11-21 19:40 添加） | 第 14.1 节中标“另交”的文件，按任务各打一个 zip | 否，交给 Barry；SHA-256 写进对应目录的 `SHA256SUMS.txt` |

提交顺序：W1（报告初稿 + XML）→ W2（脚本、测试、数据、`.gitignore`、`downloads.md`、`T24j.md`）→ W3（报告补全）→ W4（报告的 W4 一节 + 截图）→ W5（报告的 W5 一节；第 11.2 节的预检结果在 W1 的提交里先写进报告初稿）→ W6 → W7（各一个 commit，2026-11-21 19:40 添加）。

**注意（2026-11-21 19:40 添加）：** 第一轮把 `docvqa-runs.zip`（8 MB）提交进了 Git，与第 6.5 节“不提交 Git”不符。已经提交的不用撤回，是否从仓库里删除由 Barry 决定；以后的大文件按第 14.1 节另交。

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
| 16 | W4 用独立的库、存储、索引；第 10.2 节每个核对点都有结果（2026-11-21 14:26 添加） | 10.6 |
| 17 | 鼠标真实拖入：支持的类型上传成功，不支持的类型显示拒绝原因（2026-11-21 14:26 添加） | 10.6 |
| 18 | 写明看过的浏览器名称和版本（2026-11-21 14:26 添加） | 10.6 |
| 19 | 新界面截图齐全，画面里没有密码、令牌和个人文件（2026-11-21 14:26 添加） | 10.6 |
| 20 | W1 之前做了换行符预检，写明 `core.autocrlf` 和 `public/pdfjs/` 的换行符（2026-11-21 14:37 添加） | 11.7 |
| 21 | 只在 `w5_` 前缀下：结构差异被报出，重建（含 `--force`）后检查干净；其他前缀的索引没有变（2026-11-21 14:37 添加） | 11.7 |
| 22 | 空库、版本落后的库上两个 Worker 都以退出码 1 结束，提示与预期一致（2026-11-21 14:37 添加） | 11.7 |
| 23 | 连不通的地址上两个 Worker 都在设定秒数左右以退出码 1 结束（或如实写出不同的结果）（2026-11-21 14:37 添加） | 11.7 |
| 24 | 生产构建经 `npm run preview` 打开，各页面正常、没有未注册的组件（2026-11-21 14:37 添加） | 11.7 |
| 25 | 新基线上 backend、shared 0 failed（符号链接 8 项除外，单独看第 26 条）；收集到的测试与 Mac 上同一提交收集到的一致（2026-11-21 19:40 添加） | 12.12 |
| 26 | 8 项符号链接测试在 Barry 本人的终端通过，写明用的开发人员模式还是管理员终端（2026-11-21 19:40 添加） | 12.12 |
| 27 | 一致性检查的四类人为不一致都被检出并修好，之后 B2 结果与 W3 相同（2026-11-21 19:40 添加） | 12.12 |
| 28 | 强制结束 Worker 后任务被回收重做，最终没有重复数据（SQL 导出为证）（2026-11-21 19:40 添加） | 12.12 |
| 29 | 解析超时、Ctrl-C、端口占用三项的现象与预期一致，或如实写出不同（2026-11-21 19:40 添加） | 12.12 |
| 30 | 真实样本的原文件、抽取结果、人工抄录文本都交回（2026-11-21 19:40 添加） | 12.12 |
| 31 | W1–W3 的原始数据按第 12.11 节补交（2026-11-21 19:40 添加） | 12.12 |
| 32 | CLIP 向量 JSON、内存采样 CSV、负载下检索耗时 CSV 都交回，采样没有长于 15 秒的空档（2026-11-21 19:40 添加） | 13.5 |
| 33 | 每个任务目录都有 `git-head.txt`、`SHA256SUMS.txt`，与第 0.2 节的提交一致（2026-11-21 19:40 添加） | 14.1 |

任何一项做不到，不要硬凑：在报告里写明哪一项、卡在哪里、已经试过什么，然后继续做不依赖它的部分。

------------------------------------------------------------------------

## 10. W4：T24s 前端联调与界面核对（2026-11-21 14:26 添加）

T24s（`281b226`，2026-11-21）重做了前端界面，只改前端，后端和接口没有改。它只对着一个临时的模拟后端检查过（模拟后端返回虚构数据，不在仓库里），所以 `docs/untested.md` 第 4 节“T24s 前端界面优化”登记了 3 项未测试。本节把它们放到 Windows 上做。改了哪些地方见 `docs/changes/T24s.md`、`docs/decisions.md` D48。

规则：

- 只核对，**不改前端代码**。看到不符的地方按第 2 节第 5 条处理：记下现象、复现步骤、截图和浏览器控制台的报错，问 Barry 要不要修。
- 每个核对点在报告里写“通过 / 不符 / 未测试 + 原因”。`docs/untested.md` 里对应的条目由 Claude 收到报告后删除或改写（第 2 节第 6 条；CLAUDE.md 的规则是实际跑通后才删除），GPT 不改这个文件。
- 不为截图或浏览器核对安装任何新工具或浏览器扩展；截图用系统自带的截图工具（Win+Shift+S）或浏览器自带的功能。

### 10.1 环境（2026-11-21 14:26 添加）

和 W3 一样用独立的一套数据，不往主库、W3 的 `docmgr_docvqa`、测试库 `docmgr_test` 里写：

| 项目 | 设置 |
|---|---|
| 数据库 | 新建空库 `docmgr_ui`，`alembic upgrade head` |
| 文件存储 | `STORAGE_ROOT` 指向一个新的空目录 |
| 索引 | `OPENSEARCH_INDEX_PREFIX=ui_` |

切换方法同第 6.1 节：在每个启动进程的 PowerShell 窗口里先设置 `DATABASE_URL`、`STORAGE_ROOT`、`OPENSEARCH_INDEX_PREFIX` 三个环境变量。然后：

1. 启动后端、通用 Worker、OCR Worker、CLIP 服务（命令见 `CLAUDE.md`），用 `http://127.0.0.1:8000/health` 确认三项都是 `ok`。
2. 在 `frontend/` 下 `npm run dev`（与 W1 第 5 项用同一套 Node.js），浏览器打开 `http://127.0.0.1:5173`。开发服务器把 `/api`、`/health` 转发到 8000 端口。
3. 账号：用 `python -m app.modules.auth create-admin <用户名>` 建一个管理员；再在登录页注册一个普通用户。
4. 样例文件：上一轮用过的真实样本即可（中文 PDF、Word、Excel、相机 JPEG、PaddleOCR 示例图），再准备一个扫描版 PDF 或带文字的图片（看 OCR 命中）和一个不支持的文件（例如 `.txt` 或 `.gif`）。不要用个人文件。

### 10.2 用真实后端联调（2026-11-21 14:26 添加）

对应 `docs/untested.md` 第 4 节“T24s 前端界面优化”表的第 1 条“与真实后端联调”。和接口返回值比对时，打开浏览器开发者工具的“网络”面板看 `POST /api/search`、`GET /health` 的应答。

| # | 页面 | 核对点 | 预期 |
|---|---|---|---|
| 1 | 侧栏 | 管理员登录、普通用户登录各看一次 | 侧栏显示用户名；只有管理员有“管理员”标签；“文件 / 检索”导航和退出登录可用（顺带覆盖 untested.md 第 4 节“管理员视角的前端”，管理员看别人的文件时来源一栏显示管理员可见） |
| 2 | 文件页：加载 | 打开文件页；切换“全部 / 我上传的 / 共享给我的” | 列表 5 列（文件名、处理状态、大小、上传时间、操作），类型、上传者、来源在文件名下面一行，文件名前有类型色块；空列表按范围显示不同说明 |
| 3 | 文件页：上传记录 | 点击上传区一次选 3–4 个文件 | 每个文件一条记录，依次经过“等待上传 → 上传中 → 已上传”；“清除已结束的记录”能清掉已结束的 |
| 4 | 文件页：5 秒自动刷新 | 上传后不刷新页面，看处理状态 | 有等待处理或处理中的文件时，每 5 秒自动刷新一次，状态变成已完成后停止刷新 |
| 5 | 文件页：加载失败提示 | ① 停掉后端，刷新文件页；② 有文件在处理时停掉后端，等下一次自动刷新 | ① 页内红色提示“文件列表没有加载出来”；② 页内提示“自动刷新失败，列表里的状态可能不是最新的”；两种都不是弹出消息，也不是空列表。重新启动后端后恢复 |
| 6 | 文件页：共享对话框 | 打开共享对话框，再把浏览器窗口拉窄 | 对话框宽度不超出窗口（T24s 改为 `min(520px, 92vw)`，没有单独截图检查过） |
| 7 | 检索页：四个开关与 `ch` 参数 | 依次关掉“文件名”“正文”“OCR 文字”，再打开“图像（CLIP）”；四个全关一次；另用旧地址 `/search?q=<词>&img=1` 打开一次 | 默认地址里没有 `ch`；改开关后地址变成 `ch=…`，只列开着的开关；请求体的 `channels` 与开关一致，正文和 OCR 都关时请求里没有 `source_types`；四个全关时显示“至少选择一个检索通道”，不发请求；旧地址打开后图像开关是开的 |
| 8 | 检索页：改开关自动重查 | 检索过一次后改动开关；检索进行中再改一次 | 每次改动都自动重新检索（网络面板里多一次 `POST /api/search`）；进行中改动的，等这次返回后再查一次，最后显示的是按最新开关的结果 |
| 9 | 检索页：三格名次与融合分 | 对 3–5 个结果，逐个比对卡片右侧和应答里的 `hits[].channels`、`hits[].score` | 三格（文件名 / 文字 / 图像）的“第 N 名”与应答的 `rank` 一致；应答里没有该通道、但通道执行了时显示“未命中”，没开的显示“未开启”，不可用的显示“不可用”；融合分等于 `score` 保留 4 位小数 |
| 10 | 检索页：各通道耗时 | 比对结果汇总行和应答 | 总用时等于应答 `took_ms`；每个通道的耗时等于 `channels[].took_ms`，没开的写“未开启” |
| 11 | 检索页：CLIP 状态 | 进入检索页时看通道面板旁的 CLIP 状态，对照 `GET /health` | `clip_service.status` 为 `ok` 时显示“CLIP 服务在线” |
| 12 | 关掉 CLIP 服务后的降级显示（T32 答辩要演示） | 开着图像开关，停掉 CLIP 服务，再检索一次；然后重新启动 CLIP 服务再检索 | 停掉后：CLIP 状态变红（“CLIP 服务不可用，图像通道会被跳过”），出现黄色提示“图像检索暂时不可用，本次结果只来自文字检索（原因：…）”，图像格显示“不可用”，文字结果照常返回、没有报错页。重新启动后：图像通道检索成功，状态回到“CLIP 服务在线”。顺带覆盖 untested.md 第 4 节 T23 的“与真实后端、真实 CLIP 服务联调” |
| 13 | 预览页“返回” | ① 从检索结果点进预览页再点“← 返回”；② 把预览页地址复制到新标签页打开，再点“← 返回” | ① 回到检索页，检索词和开关还在；② 回到文件列表，不离开本系统 |

### 10.3 用鼠标从文件管理器真实拖入文件（2026-11-21 14:26 添加）

对应 `docs/untested.md` 第 4 节“T24s 前端界面优化”表的第 2 条。T24s 时是用脚本派发 drop 事件模拟的。

1. 从 Windows 文件资源管理器选中 2–3 个支持的文件（PDF、Word、Excel、PNG、JPEG），用鼠标拖到文件页的上传区松开。
2. 再拖入一个不支持的文件（例如 `.txt` 或 `.gif`）。点击选择文件时有类型过滤，拖入时没有，所以要用拖的方式才能送到后端。
3. 拖动经过上传区时看高亮：进入时高亮，在区内移动时不闪，移出时取消。

预期：支持的文件出现“已上传”记录，并开始处理；不支持的文件记录为“上传失败”，原因写明文件类型不支持（后端 415 `UNSUPPORTED_FILE_TYPE`）；浏览器没有直接打开被拖入的文件。

### 10.4 Windows 上的浏览器显示（2026-11-21 14:26 添加）

对应 `docs/untested.md` 第 4 节“T24s 前端界面优化”表的第 3 条“Chrome 以外的浏览器”。

1. 在 Edge 上把第 10.2 节的第 2、3、7、9、12 项和第 10.3 节看一遍；装了 Chrome 或 Firefox 的话也各看一遍。窗口拉到大约 1280 宽和 400 宽以下各看一次：窄的时候侧栏应收成页面顶部的一行，结果卡片的名次条换到卡片下面。
2. 报告里写明每个浏览器的名称和版本号。
3. 手边有装 Safari 的设备时，顺带看拖拽高亮会不会闪：拖动文件经过上传区里的文字时，高亮如果一闪一闪，记下来（untested.md 这一条的代码复核里记了：部分 Safari 版本拖动事件的 `relatedTarget` 可能为 null）。没有这样的设备就写“Safari 未测试”。

只看了 Edge、Chrome 时，这一条在 untested.md 里会缩小为“Safari、Firefox 未看过”，不会整条删除。

### 10.5 联调后重新截图（论文与 T31 用，2026-11-21 14:26 添加）

不对应 untested.md 的条目，对应 DEVPLAN §4 前端“待议（T24s 记录）”里的提醒：T24s 改了全部页面的布局和配色，旧截图（包括 `docs/screenshots/windows-2026-11-19/` 的 5 张）是改版之前的样子。T31 要逐条核对论文、README、截图和实际功能。

- 放到 `docs/screenshots/windows-<执行日期>-t24s/`，PNG，浏览器窗口约 1280×800；文件名用英文和连字符，写明画面内容。
- 至少要有：登录页；文件页（含上传记录和处理状态）；检索页的说明状态（还没检索时）；全通道检索结果（能看清三格名次和融合分）；关掉一个通道后的对照结果；CLIP 停掉后的降级显示；预览页的 PDF 原文件和图片的抽取文本；窄窗口布局一张。
- 画面里不能有密码、令牌、连接串和个人文件。
- 旧截图不要删，用不用由 Barry 和 Claude 定。

### 10.6 验收标准（2026-11-21 14:26 添加）

- [ ] 全程使用独立的库、存储、索引前缀（`docmgr_ui`、`ui_`）；主库、`docmgr_docvqa`、`docmgr_test` 没有被写入（报告里写明怎么确认的）
- [ ] 第 10.2 节 13 个核对点都有结果；不符的附截图、复现步骤和控制台报错
- [ ] 第 10.3 节：鼠标拖入的支持类型上传成功，不支持的类型显示了拒绝原因
- [ ] 第 10.4 节：写明看过的浏览器名称和版本；Safari 有没有看写清楚
- [ ] 第 10.5 节的截图齐全，画面里没有敏感信息
- [ ] 没有改任何前端代码；发现的问题只记录、问 Barry


------------------------------------------------------------------------

## 11. W5：T24k、T24l、T24m、T24o、T24p 的补测（2026-11-21 14:37 添加）

这五项在 macOS 上只跑了单元测试（假连接、假应答），真实环境上的行为没有验证过（`docs/untested.md` 第 4 节、第 7.2 节）。改了什么见第 1 节对应的行和 `docs/changes/T24k.md`、`T24l.md`、`T24m.md`、`T24o.md`、`T24p.md`。

规则与 W4 相同：

- 只核对，**不改任何代码和配置文件**（包括 `.gitattributes`、`package.json`、mapping 文件）。结果不符时记下现象、复现步骤、完整输出，问 Barry（第 2 节第 5 条）。
- 每一步在报告里写命令、输出（去掉密码和连接串）、退出码；要计时的写耗时。`docs/untested.md` 里对应的条目由 Claude 收到报告后删除或改写，GPT 不改这个文件。
- 不装任何新工具；下面用到的 `git`、`psql`、`curl.exe`、PowerShell 的 `Invoke-RestMethod` 都是这台机器上已有的。
- 第 11.2 节在 W1 之前做；第 11.3–11.6 节按顺序做。

### 11.1 环境（2026-11-21 14:37 添加）

和 W3、W4 一样用独立的一套数据，不碰主库、`docmgr_test`、W3 的 `docmgr_docvqa` 和 W4 的 `docmgr_ui`：

| 项目 | 设置 | 用在 |
|---|---|---|
| 数据库 | 新建空库 `docmgr_w5`，`alembic upgrade head` | 11.3、11.6 |
| 数据库 | 新建空库 `docmgr_w5_empty`，**不要**执行 `alembic upgrade` | 11.4 |
| 文件存储 | `STORAGE_ROOT` 指向一个新的空目录 | 11.3、11.6 |
| 索引 | `OPENSEARCH_INDEX_PREFIX=w5_`（索引名为 `w5_doc_meta`、`w5_chunks`、`w5_image_vectors`） | 11.3、11.6 |

切换方法同第 6.1 节：每个 PowerShell 窗口先设置 `DATABASE_URL`、`STORAGE_ROOT`、`OPENSEARCH_INDEX_PREFIX`。建库可以用 `psql -h localhost -U <用户> -c "CREATE DATABASE docmgr_w5"`（`docmgr_w5_empty` 同样）。第 11.4、11.5 节会把 `DATABASE_URL` 改成别的值，**每一节开一个新窗口**，做完关掉，免得后面的命令带着错误的设置运行。

### 11.2 T24m 换行符预检（在 W1 之前做，2026-11-21 14:37 添加）

对应 `docs/untested.md` 第 7.2 节“T24g 之后的代码”一行里的 T24m（只在 macOS 上跑过）。背景：`tests/pdfjs-assets.test.mjs` 逐个比较 `frontend/public/pdfjs/` 与 `node_modules/pdfjs-dist` 里文件的 sha256。202 个文件里有 15 个是文本（LICENSE、`.js`），git 开了 `core.autocrlf=true` 时，这 15 个文件签出后会变成 CRLF，sha256 跟着变，测试就会失败，但代码其实没问题。

1. 记下设置：在仓库根目录执行 `git config --show-origin --get core.autocrlf`（没有输出就是没设置，等同 `false`）。
2. 看这个目录里文件的实际换行符：`git ls-files --eol -- frontend/public/pdfjs`。每行开头的 `i/` 是仓库里的换行符，`w/` 是工作区的。预期：文本文件都是 `i/lf w/lf`，二进制文件是 `i/-text w/-text`。**注意：** `git diff --stat -- frontend/public/pdfjs` 在 `autocrlf=true` 时看不出来，因为 git 比较前会把 CRLF 当成 LF，所以要用 `--eol`。
3. 再跑这一个测试：在 `frontend/` 下 `npm test -- tests/pdfjs-assets.test.mjs`。预期 3 项通过。
4. 如果第 2 步有 `w/crlf`，或第 3 步报 `changed: …LICENSE…` 之类：
   - **不要**按测试提示运行 `npm run sync:pdfjs`。它会用 `node_modules` 里的文件覆盖，测试暂时能过，但下一次签出又会变回 CRLF，问题被掩盖了。
   - 临时处理（只对本仓库，不加 `--global`，不影响这台机器上别的仓库）：
     1. 先确认这个目录没有未提交的改动：`git status --short -- frontend/public/pdfjs` 没有输出。
     2. `git config core.autocrlf input`。签出时不再转换，提交时仍把 CRLF 转成 LF。不建议设成 `false`：那样以后在 Windows 上编辑、提交的文件如果是 CRLF，会原样进入仓库。
     3. 只重新签出这个目录：`Remove-Item -Recurse -Force frontend\public\pdfjs`，然后 `git checkout -- frontend/public/pdfjs`。这个目录里的文件都在 Git 里，删掉再签出不会丢东西。
     4. 重做第 2、3 步，应为 `w/lf`、3 项通过。
   - 影响：改了设置以后，其他文本文件要等下次签出才会变成 LF，现在工作区里已有的 CRLF 文件不变，`git status` 也不会因此显示改动。Python、Node.js、PowerShell 都能读 LF 文件。报告里写明改前、改后的 `core.autocrlf` 值。
   - 根治办法是在仓库里加 `.gitattributes`，把 `frontend/public/pdfjs/**` 标成不转换（`-text`）。这是仓库配置的改动，**等 Barry 决定，本任务不做**。

### 11.3 T24o 一致性检查：人为制造结构差异，再只重建 `w5_` 的索引（2026-11-21 14:37 添加）

对应 `docs/untested.md` 第 4 节“一致性检查对真实 OpenSearch 的操作”（T24o 扩大了结构比较的范围，担心真实 OpenSearch 自己补上的键造成误报），以及“T24d rebuild-indices --force”一节的“对真实 OpenSearch 执行 `--fix rebuild-indices --force --yes`”。做法参照 `docs/changes/T24o.md` 修改建议第 1 条、`docs/decisions.md` D31、D43。

**每一步执行 `consistency` 命令之前，先确认前缀：** `echo $env:OPENSEARCH_INDEX_PREFIX` 必须输出 `w5_`，`echo $env:DATABASE_URL` 必须指向 `docmgr_w5`。前缀为空时，重建会删掉并重建主索引 `doc_meta`、`chunks`、`image_vectors`。这一节不要启动任何 Worker：重建会删索引，Worker 这时写索引会失败（D31）。

在 `backend/` 下（main 环境），先记一次全部索引：`curl.exe -s "http://127.0.0.1:9200/_cat/indices?v&h=index,docs.count,creation.date.string"`。

| # | 命令 | 预期 |
|---|---|---|
| 1 | `python -m app.modules.consistency check` | 退出码 2，报 2 个 `index_missing`：“索引 doc_meta 不存在”“索引 chunks 不存在”（提示里写的是不带前缀的名字；库里还没有图片向量，所以向量索引不存在不算问题） |
| 2 | `python -m app.modules.consistency repair --fix rebuild-indices` | 演练：打印要重建三个索引的计划和“先停掉 Worker”的提示，退出码 2，不做任何改动 |
| 3 | `python -m app.modules.consistency repair --fix rebuild-indices --yes` | 退出码 0；`_cat/indices` 里出现 `w5_doc_meta`、`w5_chunks`、`w5_image_vectors`（重建时三个一起建），其他索引的创建时间没有变 |
| 4 | `python -m app.modules.consistency check` | **退出码 0，没有任何结构问题。** 这是 T24o 的比较第一次对着真实 OpenSearch 新建的索引运行：如果这里就报“结构不一致”，就是误报，把提示原文全部写进报告，后面的步骤照做 |
| 5 | 改一处 mapping（见下面的命令） | OpenSearch 返回 `acknowledged: true` |
| 6 | `python -m app.modules.consistency check` | 退出码 2，报 `index_structure_mismatch`。用办法 A 时提示应为“索引 chunks 的结构与版本库里的 mapping 不一致：字段 text 的定义不同：search_analyzer 为 standard，应为 （未设置）”；用办法 B 时为“……多出字段 w5_extra” |
| 7 | `repair --fix rebuild-indices`（演练），再加 `--yes` | 演练退出码 2；执行退出码 0；只有 `w5_` 三个索引的创建时间变了 |
| 8 | `python -m app.modules.consistency check` | 退出码 0 |
| 9 | `repair --fix rebuild-indices --force`（演练），再加 `--yes`（D43） | 检查没有问题时也能强制重建：演练打印 `forced_rebuild` 计划，退出码 2；执行退出码 0；仍然只有 `w5_` 的索引被重建 |
| 10 | `python -m app.modules.consistency check`，最后再记一次 `_cat/indices` | 退出码 0；与开始时比较，只有 `w5_` 开头的索引是新的，其他前缀（包括主索引、`docvqa_`、`ui_`）的创建时间和文档数都没有变 |

第 5 步改 mapping 的办法：只动 `w5_chunks`，不删数据，改完由第 7 步重建恢复。

- **办法 A（优先，正好覆盖 T24o 新加的比较项）：** 给 `text` 字段加 `search_analyzer`。OpenSearch 允许对已有字段更新 `search_analyzer`，但要把原来的 `type` 和 `analyzer` 一起写上（与 `shared/text_index/mappings/chunks.json` 里一致）：

  ```powershell
  Invoke-RestMethod -Method Put -Uri "http://127.0.0.1:9200/w5_chunks/_mapping" -ContentType "application/json" -Body '{"properties":{"text":{"type":"text","analyzer":"docmgr_text","search_analyzer":"standard"}}}'
  ```

- **办法 B（A 被拒绝时用）：** 加一个版本库 mapping 里没有的字段。索引是 `dynamic: strict`，但 strict 只拒绝文档里的未知字段，用 mapping 接口显式加字段是允许的：

  ```powershell
  Invoke-RestMethod -Method Put -Uri "http://127.0.0.1:9200/w5_chunks/_mapping" -ContentType "application/json" -Body '{"properties":{"w5_extra":{"type":"keyword"}}}'
  ```

  办法 B 走的是 T24o 之前就有的“多出字段”比较，覆盖不到 T24o 新加的比较项。报告里写明用的是哪种，A 被拒绝时附上 OpenSearch 的错误原文。

不要改分析配置（`_settings` 里的 analysis）：那要先关闭索引，步骤多，容易误操作到别的索引。

### 11.4 T24l 空库上启动 Worker（2026-11-21 14:37 添加）

对应 `docs/untested.md` 第 4 节“T24l Worker 启动时检查数据库迁移”的两行（通用 Worker 的迁移版本检查、OCR Worker 的列检查，在真实 PostgreSQL 上）。提示文字取自 `backend/app/worker/schema.py`、`services/ocr_worker/ocr_worker/__main__.py`。

新开一个窗口，`DATABASE_URL` 指向 `docmgr_w5_empty`（其余两个变量照 11.1 设置），然后：

| # | 操作 | 预期 |
|---|---|---|
| 1 | 在 `backend/` 下 `..\.venv-main\Scripts\python -m app.worker`，然后 `echo $LASTEXITCODE` | 立刻结束，退出码 1，输出“Worker 无法启动：数据库还没有建表（没有 alembic_version），先在 backend/ 目录运行 alembic upgrade head” |
| 2 | 在 `services/ocr_worker/` 下 `..\..\env_check\.venv-ocr\Scripts\python -m ocr_worker`，然后 `echo $LASTEXITCODE` | 先加载 OCR 模型（日志“OCR 模型已加载”），然后结束，退出码 1，输出“OCR Worker 无法启动：数据库缺少 34 个需要的列（……等），先在 backend/ 目录运行 alembic upgrade head”，括号里列出前 5 个，都是 `document_chunks.` 开头 |
| 3 | 在 `backend/` 下 `..\.venv-main\Scripts\python -m alembic upgrade 0001`（只升到第一个迁移），再重复第 1、2 步 | 通用 Worker：退出码 1，“数据库结构版本为 ['0001']，代码要求 ['0002']：数据库落后时先在 backend/ 目录运行 alembic upgrade head；数据库比代码新时请更新代码”。OCR Worker：退出码 1，“数据库缺少 1 个需要的列（ocr_results.params）” |
| 4 | `..\.venv-main\Scripts\python -m alembic upgrade head`，再分别启动两个 Worker，启动后没有报错、进入等待时按 Ctrl+C | 两个都正常启动，不报结构问题（库里没有任务，所以只是空转） |

输出里不能有数据库密码；如果有，记下来（那是 bug）。做完关掉这个窗口，`docmgr_w5_empty` 留着或删掉都可以，报告里写明。

### 11.5 T24k 连不通的数据库地址（2026-11-21 14:37 添加）

对应 `docs/untested.md` 第 7.2 节“T24g 之后的代码”一行里的 T24k：连接超时只在 macOS 主环境实测过，OCR Worker 在 ocr 环境没有实际连过。

新开一个窗口，把 `DATABASE_URL` 设成一个**会超时**的地址，用户名、密码随便写，不要用真实的：

```powershell
$env:DATABASE_URL = "postgresql://w5:w5@10.255.255.1:5432/w5"
```

`10.255.255.1` 是一个通常不会回应的内网地址。不要用 `127.0.0.1` 上没有服务的端口：那会立刻被拒绝，测不到超时。

计时的写法（PowerShell）：

```powershell
$t0 = Get-Date; <启动命令>; $code = $LASTEXITCODE; "{0:N1} 秒，退出码 {1}" -f ((Get-Date) - $t0).TotalSeconds, $code
```

| # | 操作 | 预期 |
|---|---|---|
| 1 | 通用 Worker（`backend/` 下 `..\.venv-main\Scripts\python -m app.worker`），不设超时变量（默认 10 秒） | 约 10 秒后结束，退出码 1，输出“Worker 无法连接数据库（ConnectionTimeout），请确认数据库已启动、DATABASE_URL 正确” |
| 2 | 同上，先 `$env:WORKER_DB_CONNECT_TIMEOUT_SECONDS = "3"` | 约 3 秒后结束，退出码 1 |
| 3 | OCR Worker（`services/ocr_worker/` 下 `..\..\env_check\.venv-ocr\Scripts\python -m ocr_worker`），`$env:OCR_WORKER_DB_CONNECT_TIMEOUT_SECONDS = "5"` | 先加载模型，再约 5 秒后结束，退出码 1，输出“OCR Worker 无法连接数据库（ConnectionTimeout），请确认数据库已启动” |
| 4 | 同上，改成 `"20"` | 比第 3 步约多 15 秒 |

OCR Worker 是先加载模型、再连数据库的，总耗时里包括加载模型的时间。所以用第 3、4 步的差值（约 15 秒）判断超时设置生效，也可以对照日志里“OCR 模型已加载”那一行的时间。

如果这台机器所在的网络会立刻回绝这个地址（几秒内就报 `OperationalError`，而不是等到设定的秒数），这一节就测不到超时：如实记下现象和耗时，两种结果都有用。不要为此改网络设置。

### 11.6 T24p 生产构建在浏览器里打开（2026-11-21 14:37 添加）

对应 `docs/untested.md` 第 4 节“T24p Element Plus 按需引入”一行（生产构建产物没有在浏览器里打开过）。T24p 之前只在开发服务器上检查过：开发服务器和生产构建用的是同一份注册代码，但打包方式不同，按需引入漏掉的组件、样式只在生产构建里才可能暴露。这一步顺带看 T24s 的新界面在生产构建里的样子。

1. 用 11.1 的 `docmgr_w5`（第 11.3 节已经建好 `w5_` 索引）启动后端和通用 Worker。OCR Worker、CLIP 服务可开可不开：不开时检索页会显示 CLIP 不可用，也正好看提示条。用 `create-admin` 建一个管理员。
2. 在 `frontend/` 下 `npm run build`，再 `npm run preview`，浏览器打开它显示的地址（默认 `http://localhost:4173`）。
3. **先确认转发：** Vite 的 `preview` 沿用 `vite.config.ts` 里 `server.proxy` 的设置（本仓库用的 Vite 8.3.8 的源码里，`preview.proxy` 默认取 `server.proxy`），所以 `/api`、`/health` 应当照样转发到 8000 端口。打开开发者工具的“网络”面板登录一次，`POST /api/auth/login` 应为 200。如果是 404 或连不上，说明没有转发：这一步只能看登录页，记为限制，后面的页面不用看了。
4. 登录后各打开一次，每页都看开发者工具的“控制台”有没有报错：
   - 文件页：先上传一份中文 PDF、一张图片、一份 Word（不要用个人文件），等通用 Worker 处理完；看表格、标签、状态标签、“全部 / 我上传的 / 共享给我的”单选按钮组、分页（含每页条数下拉）、加载中的遮罩、上传区和上传记录、共享对话框、删除确认框（打开后取消，不要真删）
   - 检索页：输入框、检索通道的复选框、提示条、结果卡片、三格名次和融合分
   - 预览页：PDF 的“原文件 / 抽取文本”标签页和翻页、缩放（中文 PDF 应正常显示文字，CMap 等资源从 `pdfjs/` 加载）、图片的原图和抽取文本、Word 的抽取文本
   - 登录页：卡片、表单、注册链接
5. **怎么判断有没有漏注册的组件：** 生产构建里 Vue 不会在控制台提示“Failed to resolve component”，漏注册的组件只会原样留成一个不认识的标签、不显示内容。所以在开发者工具的“元素”面板里按 Ctrl+F 搜索 `<el-`：正常情况下一个都找不到，Element Plus 的组件会渲染成 `div`、`button` 等，class 以 `el-` 开头。找到了就记下标签名和所在页面。

### 11.7 验收标准（2026-11-21 14:37 添加）

- [ ] 第 11.2 节在 W1 之前做了：写明 `core.autocrlf` 的值、`git ls-files --eol` 的结果、单个测试的结果；做了临时处理的，写明改前改后的值；没有运行 `sync:pdfjs`，没有加 `.gitattributes`
- [ ] 第 11.3 节：每条 `consistency` 命令之前都确认了前缀是 `w5_`；第 4 步的结果如实写出（干净还是误报）；第 6 步报出了具体差异；第 7–10 步之后检查干净；其他前缀的索引没有变
- [ ] 第 11.4 节：空库、只升到 `0001` 的库上，两个 Worker 都以退出码 1 结束，提示与预期一致；升到最新后正常启动
- [ ] 第 11.5 节：两个 Worker 的耗时和退出码都记下了；超时设置生效（或如实写出这台机器的网络测不到超时）
- [ ] 第 11.6 节：写明 preview 有没有转发 `/api`；各页面的检查结果；“元素”面板里搜索 `<el-` 的结果
- [ ] 全程没有碰主库、`docmgr_test`、`docmgr_docvqa`、`docmgr_ui` 和它们的索引；没有改任何代码和配置文件

------------------------------------------------------------------------

## 12. W6：新基线复测与其余真实环境补测（2026-11-21 19:40 添加）

来源：第一轮结果（第 0.1 节），以及 `docs/untested.md` 第 4 节里还能在这台机器上、不装新东西就能补的项目。不能补的列在第 15 节。

规则与 W4、W5 相同：只核对，不改代码和配置文件；结果不符时记录现象、复现步骤、完整输出，问 Barry。每一步的原始数据按第 14.1 节放进 `output/windows-w6/`。

### 12.1 环境

| 用途 | 数据库 | 存储 | 索引前缀 | 用在 |
|---|---|---|---|---|
| 测试库 | `docmgr_test`（空库） | 测试自建 | 测试自建 | 12.2、12.3 |
| W3 的数据 | `docmgr_docvqa`（已有，500 个文档） | W3 的 `storage/w3-docvqa` | `docvqa_` | 12.4、12.11 |
| 本任务新建 | `docmgr_w6`（新建，`alembic upgrade head`） | 新的空目录 | `w6_` | 12.5–12.9 |

切换方法同第 6.1 节。每执行一条会写数据的命令之前，先 `echo $env:DATABASE_URL $env:OPENSEARCH_INDEX_PREFIX` 确认（输出里的密码不要抄进报告）。

### 12.2 新基线上的全套复测

**为什么：** W1 测的是 `8fb5830`。之后 Mac 上的提交里，T24k、T24l、T24o 改了后端和 shared，T24m、T24n、T24p、T24s 改了前端，都没有在 Windows 上跑过（`docs/untested.md` 第 7.2 节）。

**做法：** 在第 0.2 节确认的提交上，把第 4.1 节第 1–6 项完整重做一遍，JUnit 输出改到 `output/windows-w6/`（`backend.xml`、`shared.xml`、`ocr_worker.xml`、`clip_service.xml`）。前端三项命令的完整输出存成 `frontend-typecheck.txt`、`frontend-test.txt`、`frontend-build.txt`；ruff 的输出存成 `ruff.txt`。第 4.1 节第 7 项 OCR 烟测也重做一次，输出存成 `ocr-smoke.txt`。

另外导出收集到的测试清单，供 Claude 与 Mac 对照（先在仓库根目录 `New-Item -ItemType Directory -Force output\windows-w6`，重定向不会自己建目录）：

```powershell
# backend/ 下；shared/ 下同样做一次，文件名换成 shared-collect.txt
..\.venv-main\Scripts\python -m pytest --collect-only -q > ..\output\windows-w6\backend-collect.txt
```

**预期：** 除第 12.3 节的 8 项外，backend、shared 0 failed、0 skipped；OCR Worker、CLIP 0 failed（main 环境里因为没装 paddleocr、torch 而跳过的项，和第一轮一样逐条说明）；前端三项命令成功（T24s 之后前端单元测试在 Mac 上是 93 项）；ruff 通过；烟测 PASS。第 11.2 节的换行符预检要先做。

### 12.3 8 项符号链接测试（Barry 本人的终端）

**为什么：** 执行方的沙箱账号拿不到建符号链接的权限（第 0.1 节），这 8 项两轮都没跑成。它们测的是“存储拒绝经符号链接指向外部的路径”（GLOBAL §7.2 防路径穿越），不能跳过。

**谁做：** Barry 在自己登录的 Windows 账号下操作，不经过执行方的沙箱。

1. 设置 → 系统 → 开发者选项 → 打开“开发人员模式”，注销后重新登录。做不到时改用“以管理员身份运行”的 PowerShell。
2. `whoami /priv | Select-String SeCreateSymbolicLink`，确认有这一行。把整行输出存成 `output/windows-w6/symlink-priv.txt`。
3. 只跑这 8 项：

   ```powershell
   # backend/ 下
   ..\.venv-main\Scripts\python -m pytest --junitxml=..\output\windows-w6\symlink-backend.xml "tests/unit/test_consistency.py::test_symlinks_are_never_treated_as_stored_files" "tests/unit/test_storage.py::test_file_symlink_pointing_outside_rejected" "tests/unit/test_storage.py::test_directory_symlink_pointing_outside_rejected" "tests/unit/test_storage.py::test_put_refuses_to_write_through_directory_symlink" "tests/unit/test_storage.py::test_symlinked_temp_directory_refused_at_startup"
   # shared/ 下
   ..\.venv-main\Scripts\python -m pytest --junitxml=..\output\windows-w6\symlink-shared.xml "tests/test_storage_keys.py::test_symlinked_directory_is_rejected" "tests/test_storage_keys.py::test_symlinked_file_is_rejected"
   ```

**预期：** backend 6 passed（`test_directory_symlink_pointing_outside_rejected` 有 `[year]`、`[document]` 两个参数），shared 2 passed。报告里写明用的是开发人员模式还是管理员终端。

### 12.4 一致性检查的修复路径（在 W3 的数据上）

**为什么：** `docs/untested.md` 第 4 节：`repair --fix index`、带向量的修复、检索服务不可用时的提示，都只在假数据上测过（D31、D34、D35）。W3 的一致性检查只证明了“干净的数据检查结果干净”，没有证明“不干净的数据能被查出来、能修好”。

**前提：** 第 12.11 节的导出已经做完；所有 Worker 都停着；窗口里的变量指向 `docmgr_docvqa`、`docvqa_`。在 `backend/` 下执行。每条 `consistency` 命令都加 `--json`（`check` 支持；`repair` 不支持的就存原文），输出存成 `output/windows-w6/consistency/<步骤号>-<名称>.json|txt`，并记下退出码。

先从 `experiments/docvqa/datasets/document_map.csv` 取第一行的 `document_id`，下面记作 `<D1>`；再取第二行，记作 `<D2>`。

| # | 操作 | 预期 |
|---|---|---|
| 1 | `python -m app.modules.consistency check --json` | 退出码 0，没有问题（与 W3 相同） |
| 2 | 停掉 OpenSearch，再 `check --json` | 退出码 1；仍然输出数据库和磁盘的检查结果，并写明检索服务不可用、索引没有检查（D31、D34） |
| 3 | OpenSearch 仍停着，`repair --fix index --yes` | 退出码 1；明确提示索引类别这次没有修复，**不是**“没有需要修复的问题”（D34 修正过的行为） |
| 4 | 重新启动 OpenSearch，等 `_cluster/health` 不是 red；删掉 `<D1>` 在 `docvqa_chunks` 里的全部片段（命令见下），再 `check --json` | 退出码 2；报出 `<D1>` 的索引与数据库不一致，修复类别为 `index` |
| 5 | 删掉 `<D2>` 在 `docvqa_image_vectors` 里的向量，再 `check --json` | 退出码 2；除第 4 步的问题外，报出 `<D2>` 的向量缺失（`vector_*` 一类，D35） |
| 6 | 在 `STORAGE_ROOT` 下造一个孤立文件（做法见下），再 `check --json` | 退出码 2；多报一条 `orphan_file` |
| 7 | `repair --fix index --fix orphan-files`（演练） | 退出码 2；列出要修的三类问题，不做改动（再 `check` 一次应与第 6 步相同） |
| 8 | `repair --fix index --fix orphan-files --yes` | 退出码 0 |
| 9 | `check --json`；再数一次 `docvqa_chunks` 中 `source_type=ocr` 的片段数和 `docvqa_image_vectors` 的文档数 | 退出码 0；ocr 片段 1589、向量 500，与修复前相同 |
| 10 | 启动 CLIP 服务（B3 要用，Worker 仍然不开），`python -m app.modules.experiments --root ..\experiments\docvqa run --config ..\experiments\configs\B2.json`，再用 `B3.json` 跑一次 | 都是退出码 0；指标与 W3 的 B2、B3 相同（Claude 会逐条比对排名，见第 14.2 节） |

第 4、5 步的删除命令（只针对一个文档，`refresh=true` 让删除立刻可见）：

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:9200/docvqa_chunks/_delete_by_query?refresh=true" -ContentType "application/json" -Body '{"query":{"term":{"document_id":"<D1>"}}}'
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:9200/docvqa_image_vectors/_delete_by_query?refresh=true" -ContentType "application/json" -Body '{"query":{"term":{"document_id":"<D2>"}}}'
```

应答里的 `deleted` 分别应大于 0、等于 1，写进报告。前缀一定是 `docvqa_`，不要写成别的索引。

第 6 步造孤立文件：在 `STORAGE_ROOT\2026\` 下新建一个目录，名字是一个新生成的 UUID（`[guid]::NewGuid().ToString()`）；从 `experiments\docvqa\datasets\files\docvqa\` 复制任意一张图片进去，改名为它自己的 SHA-256（`(Get-FileHash <文件> -Algorithm SHA256).Hash.ToLower()`）加 `.jpg`。这样它的路径形状合法、数据库里没有记录。把目录名和文件名写进报告。

计数命令（第 9 步）：

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:9200/docvqa_chunks/_count" -ContentType "application/json" -Body '{"query":{"term":{"source_type":"ocr"}}}'
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:9200/docvqa_image_vectors/_count"
```

### 12.5 Worker 崩溃恢复与并发（在真实数据上）

**为什么：** T07 的崩溃恢复、并发不重复领取已经用集成测试验证过（假任务）；第一轮 W3 同时开了 4 个 OCR Worker，但没有导出能证明“没有重复数据”的原始记录。这一节在真实解析、OCR、编码上强制结束 Worker，用 SQL 导出证明任务被回收、结果没有重复（GLOBAL §9.1“Worker 中途崩溃后任务能被回收重新执行，且重复执行不产生重复记录或重复索引”）。

**准备 60 个文件的小数据集**（放在仓库外的新目录，不进 Git；不联网，从 W2 已下载的文件里复制）。在仓库根目录：

```powershell
$dst = "<仓库外的新目录>\docvqa60"
.\.venv-main\Scripts\python -I -c @'
import csv, shutil, sys
from pathlib import Path
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
with open(src / "datasets/manifest.csv", encoding="utf-8", newline="") as f:
    rows = list(csv.DictReader(f))[:60]
ids = {r["file_id"] for r in rows}
(dst / "datasets/files/docvqa").mkdir(parents=True)
(dst / "qrels").mkdir()
with open(dst / "datasets/manifest.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
for r in rows:
    shutil.copy2(src / "datasets/files" / r["path"], dst / "datasets/files" / r["path"])
qrels = (src / "qrels/docvqa.tsv").read_text(encoding="utf-8").splitlines()
keep = [qrels[0]] + [line for line in qrels[1:] if line.split("\t")[1] in ids]
qids = {line.split("\t")[0] for line in keep[1:]}
(dst / "qrels/docvqa.tsv").write_text("\n".join(keep) + "\n", encoding="utf-8", newline="\n")
queries = (src / "queries.tsv").read_text(encoding="utf-8").splitlines()
picked = [queries[0]] + [line for line in queries[1:] if line.split("\t")[0] in qids]
(dst / "queries.tsv").write_text("\n".join(picked) + "\n", encoding="utf-8", newline="\n")
print(len(rows), "files,", len(qids), "queries")
'@ experiments\docvqa $dst
```

预期打印 `60 files, 60 queries`。然后在 `docmgr_w6`、`w6_` 下 `validate`、`import`（`--root $dst`）。

**步骤：**

1. 启动 CLIP 服务；开**两个**通用 Worker、**两个** OCR Worker（各自一个窗口）。把四个进程的 PID 写进报告（`Get-Process python | Select-Object Id, StartTime, Path`，或各窗口的启动日志）。
2. 等到至少 10 个 parse 任务完成、还有 parse 任务在处理时，查出正在处理的任务和领取者：

   ```sql
   SELECT id, task_type, document_id, claimed_by, attempts, lease_expires_at FROM processing_tasks WHERE status = 'processing';
   ```

   用 `Stop-Process -Id <PID> -Force` 强制结束其中一个通用 Worker（不是 Ctrl+C）。记下被结束的 Worker 当时持有的任务 id。
3. 用同样的办法，在 OCR 任务处理中强制结束一个 OCR Worker，记下任务 id。
4. **不要**重启被结束的两个进程。等剩下的一个通用 Worker、一个 OCR Worker 把所有任务做完（租约 60 秒到期后，被结束的进程持有的任务会回到 pending 再被领取）。
5. 全部完成后，导出下面的查询结果（第 14.1 节的 `sql/` 目录），并执行 `consistency check --json`。

```sql
-- 1 各类任务的状态与尝试次数
SELECT task_type, status, attempts, count(*) FROM processing_tasks GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;
-- 2 尝试过不止一次的任务（应包含第 2、3 步记下的任务）
SELECT id, task_type, document_id, status, attempts, claimed_by, error, started_at, finished_at FROM processing_tasks WHERE attempts > 1 ORDER BY started_at;
-- 3 每个领取者处理了多少任务（应能看到四个不同的领取者）
SELECT claimed_by, task_type, count(*) FROM processing_tasks GROUP BY 1, 2 ORDER BY 1, 2;
-- 4 同一文档同时存在多个解析版本的片段（应为 0 行）
SELECT document_id, count(DISTINCT parse_version) FROM document_chunks GROUP BY 1 HAVING count(DISTINCT parse_version) > 1;
-- 5 每个文档每种来源的片段数（Claude 用来与索引计数对照）
SELECT document_id, source_type, count(*) FROM document_chunks GROUP BY 1, 2 ORDER BY 1, 2;
-- 6 同一对象的 OCR 结果重复（应为 0 行）
SELECT document_id, locator::text, count(*) FROM ocr_results GROUP BY 1, 2 HAVING count(*) > 1;
-- 7 同一内容、同一模型的向量重复（应为 0 行）
SELECT sha256, model_name, model_version, count(*) FROM image_embeddings GROUP BY 1, 2, 3 HAVING count(*) > 1;
-- 8 总数
SELECT (SELECT count(*) FROM documents) AS documents, (SELECT count(*) FROM document_chunks) AS chunks, (SELECT count(*) FROM ocr_results) AS ocr_results, (SELECT count(*) FROM image_embeddings) AS embeddings;
```

导出写法（每条一个 CSV；`psql` 的 `\copy` 在客户端写文件，不需要数据库服务器的文件权限）：

```powershell
psql -h localhost -U <用户> -d docmgr_w6 -c "\copy (<上面的查询，去掉末尾分号>) TO 'output/windows-w6/sql/w6-<编号>.csv' CSV HEADER"
```

同时导出索引计数：`curl.exe -s "http://127.0.0.1:9200/_cat/indices/w6_*?v&h=index,docs.count"` 存成 `w6-indices.txt`；再对 `w6_chunks` 按 `source_type` 做两次 `_count`（同第 12.4 节）存成 `w6-chunks-count.txt`。

**预期：** 所有任务最终 `succeeded`；第 2 条查询里有第 2、3 步记下的任务，`attempts` 为 2；第 4、6、7 条为 0 行；一致性检查退出码 0；数据库片段数与索引计数一致。

### 12.6 解析超时的端到端

**为什么：** `docs/untested.md` 第 4 节“解析超时对真实解析器的作用”：超时机制有单元测试，但“一个真的跑太久的解析被杀掉”没有端到端跑过。

1. 用 main 环境的 PyMuPDF（已有，不是新依赖）在仓库外生成一个大 PDF：

   ```powershell
   .\.venv-main\Scripts\python -I -c "import fitz,sys; d=fitz.open(); [d.new_page().insert_text((72,72), f'第 {i} 页 timeout test ' * 20, fontname='china-s') for i in range(3000)]; d.save(sys.argv[1])" "<仓库外的目录>\big3000.pdf"
   ```

2. 停掉第 12.5 节剩下的通用 Worker，在一个新窗口里设 `$env:WORKER_TASK_TIMEOUT_SECONDS = "2"`（只在这个窗口），启动一个通用 Worker。
3. 登录拿令牌、上传这个 PDF：

   ```powershell
   $tok = (Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/auth/login" -ContentType "application/json" -Body '{"username":"<用户>","password":"<密码>"}').access_token
   curl.exe -s -H "Authorization: Bearer $tok" -F "file=@<仓库外的目录>\big3000.pdf" http://127.0.0.1:8000/api/documents
   ```

   令牌和密码不要写进报告。
4. 等这个文档的 parse 任务结束，导出 `GET /api/documents/<id>` 和 `GET /api/documents/<id>/tasks` 的 JSON。
5. 关掉这个窗口的 Worker，在没有设超时变量的窗口里重新启动通用 Worker，用 `POST /api/tasks/<任务 id>/retry` 重试，等它完成后再导出一次第 4 步的两个 JSON。

**预期：** 第 4 步：parse 任务 `failed`，`attempts` 等于最大重试次数，`error` 写明超时；文档 `status` 为 `failed`；文件仍在（下载接口 200）；同时间段其他文档不受影响。第 5 步：任务 `succeeded`，文档 `succeeded`，片段数大于 0。如果 2 秒内就解析完了（第 4 步成功），把页数加到 10000 再试一次，仍然成功就如实记下耗时。

### 12.7 OCR Worker 在识别中途按 Ctrl+C

**为什么：** D34：识别子进程忽略 SIGINT，按 Ctrl+C 时父进程“处理完当前任务后退出”，正在识别的这一页不应记成失败。只有代码复核，没有实际按过。

1. 先停掉前面各节还开着的所有 Worker。在 `docmgr_w6` 下 `python -m app.modules.experiments --root <docvqa60 目录> reocr --yes`（第 12.6 节的大 PDF 不在数据集里，不受影响），只启动**一个** OCR Worker。
2. 看到日志开始识别某个任务后（记下任务 id），在这个窗口按一次 Ctrl+C。
3. 记下 Worker 打印的内容和退出码，然后查这个任务：`SELECT id, status, attempts, error FROM processing_tasks WHERE id = '<任务 id>';`

**预期：** 日志出现“收到信号 SIGINT，完成当前任务后退出”；这个任务 `succeeded`、`attempts` 为 1、`error` 为空；Worker 在这个任务之后退出，没有再领新任务。之后重新启动 OCR Worker 把剩下的任务做完（W7 要用完整的数据）。

### 12.8 端口被占用

`docs/untested.md` 第 4 节“端口被占用”。在后端已经在 8000 端口运行时，再开一个窗口在 `backend/` 下启动第二个后端（同样的命令）；CLIP 服务已经在 8001 端口时，再启动第二个 CLIP 服务。

**预期：** 第二个进程报端口被占用并退出（记下退出码和输出原文），第一个进程不受影响：`/health` 仍然 200，CLIP 的 `/health` 仍然 200。第二个 CLIP 服务会先加载模型再报错，写明从启动到退出的耗时。

### 12.9 真实文件的解析与 OCR

**为什么：** `docs/untested.md` 第 4 节：解析器和 OCR 只用程序现场生成的文件测过，没有用 Office/WPS 真正保存的文件、真实扫描件、手机照片测过。论文里的“支持格式”要有真实文件的依据。

**样本（由 Barry 准备，不要用个人文件；每个文件写清来源，填进 `output/windows-w6/real-files/sources.csv`，列为 `name,kind,made_by,source,notes`）：**

| 类型 | 至少几个 | 要求 |
|---|---|---|
| Word（Microsoft Word 保存） | 2 | 有标题、正文段落、一张表格；其中一个含中英文混排 |
| Word（WPS 保存） | 1 | 这台机器装了 WPS 才做，没有就写“未测试” |
| Excel | 2 | 至少一个有多个工作表、合并单元格、公式（公式的计算结果要已保存） |
| 有文本层的 PDF | 2 | 一份中文、一份双栏排版（例如公开的论文） |
| 扫描 PDF | 1 | 打印一页公开文字再扫描或拍照转 PDF，没有文本层 |
| 手机照片 | 2 | 拍公开海报、书的版权页之类；至少一张是竖着拍的（带 EXIF 方向） |
| 截图 | 1 | 一张带中文文字的系统截图（不要有个人信息） |

**步骤：** 在 `docmgr_w6` 下用前端或接口上传全部样本，等处理完。对每个文件导出 `GET /api/documents/<id>`、`GET /api/documents/<id>/text`、`GET /api/documents/<id>/tasks` 三个 JSON，存到 `output/windows-w6/real-files/<name>/`。**原文件也交回**（打进 W6 的另交压缩包，第 14.1 节），Claude 要在 Mac 上用同一个解析器重新解析对照。

**人工抄录（用来算 OCR 字符错误率 CER）：** 从扫描 PDF、两张手机照片、截图里各选一段（每段 50–200 字），Barry 照着原图逐字抄录，存成 `output/windows-w6/real-files/<name>/ground-truth.txt`（UTF-8，第一行写这段文字在原图里的位置，例如“第 1 页第 2 段”，第二行起是正文）。不要照着 OCR 结果改，抄错了宁可留着。

**预期（Claude 核对，见第 14.2 节）：** Word 的定位都是 `docx_para`，没有页码；Excel 是 `xlsx_range`，工作表名正确，公式单元格给出的是计算结果；PDF 的 `pdf_page` 页码在 1 到总页数之间；扫描页有 `source_type=ocr` 的片段；竖拍的照片 OCR 结果是正向的文字。

### 12.10 预览页在真实后端上：按页穿插 OCR、抽取文本标签页、高亮

对应 `docs/untested.md` 第 4 节 T24e、T24f 的“真实后端上没有看过”和“smartcn 下的高亮效果”。用第 12.9 节上传的扫描 PDF（或一份既有文本页又有扫描页的 PDF）和手机照片，在 `npm run dev` 的前端上：

1. 打开 PDF 的预览页，切到“抽取文本”标签页：同一页里正文在前、OCR 片段在后，页码从小到大。截图存成 `output/windows-w6/preview/pdf-extracted.png`，同时导出 `/text` 的 JSON 对照。
2. 用照片里 OCR 出来的一个词检索，从结果点进预览页：默认显示“抽取文本”标签页并滚到命中片段，地址栏有 `view=`。截图。
3. 检索三个中文词（各取样本里出现过的），看结果卡片里的摘要：命中词有高亮，摘要落在命中词附近。截图，并导出这三次 `POST /api/search` 的应答 JSON。

### 12.11 补交 W1–W3 的原始数据

第一轮只交了 JUnit XML 和实验结果目录，下面这些数字只在报告里有、没有原始数据，Claude 无法核对。**在第 12.4 节改动 `docmgr_docvqa` 之前先导出**，放到 `output/windows-w3-supplement/`：

| 文件 | 怎么得到 | 用来核对 |
|---|---|---|
| `sql/w3-1.csv` … `sql/w3-8.csv` | 第 12.5 节的 8 条查询，改在 `docmgr_docvqa` 上执行 | parse/ocr/embed 各 500 succeeded；第 4、6、7 条 0 行；片段数 |
| `w3-indices.txt`、`w3-chunks-count.txt` | 同第 12.5 节，前缀换成 `docvqa_` | 索引计数 = 数据库计数（报告写的 ocr 1589） |
| `w3-consistency.json` | `consistency check --json` | 报告写的“没有发现不一致” |
| `w3-ocr-params.csv` | `SELECT model_name, model_version, params::text, count(*) FROM ocr_results GROUP BY 1, 2, 3;` | 只有一种模型和一种参数（T24c、T24g） |
| `w3-ocr-failures.txt` | `mjbw0217.jpg`、`mkvw0217.jpg` 两个 OCR 任务的 id、三次失败的 `error` 原文、OCR Worker 日志里对应的几十行、手动重试的时间和方法 | 第 0.1 节记下的 `0xC0000005` |
| `w3-logs.zip`（另交） | W3 期间四个 OCR Worker、通用 Worker、CLIP 服务的日志（第一轮放在 `storage-smoke/w3-logs/`），去掉连接串 | 报告里 OCR 平均 53.57 秒、P95 131 秒的来源 |
| `w3-memory.csv`（如果第一轮的采样原始数据还在） | 原始采样 | 报告里的峰值内存；不在了就写“没有保留” |
| `document_map.csv` | `experiments/docvqa/datasets/document_map.csv`（它被 `.gitignore` 忽略，复制一份进来） | 结果里的 `document_id` 与 `file_id` 对应 |

### 12.12 验收标准

- [ ] 12.2：在第 0.2 节的提交上重跑；除 8 项符号链接外 0 failed；4 份 JUnit XML、2 份 collect 清单、前端与 ruff 输出、烟测输出都在
- [ ] 12.3：Barry 本人的终端；`symlink-priv.txt` 有那一行；backend 6 passed、shared 2 passed
- [ ] 12.4：10 步都有输出和退出码；第 4–6 步的问题都被报出；第 9 步计数与修复前相同；第 10 步 B2、B3 退出码 0
- [ ] 12.5：四个进程的 PID 和被结束的任务 id 都记了；8 个 CSV 与索引计数都导出；第 4、6、7 条为 0 行；一致性检查退出码 0
- [ ] 12.6–12.8：现象与预期一致，或如实写出不同；JSON 和输出原文都交回
- [ ] 12.9：样本数量达到表里的要求（做不到的写明）；三个 JSON、原文件、`sources.csv`、4 段人工抄录都交回
- [ ] 12.10：三组截图和对应的 JSON
- [ ] 12.11：表里的文件都交回；不在了的写明
- [ ] 全程没有改代码和配置文件；没有碰主库和 `docmgr_test` 之外的测试数据

------------------------------------------------------------------------

## 13. W7：跨机器 CLIP 向量一致性、同时运行的内存、负载下的查询编码（2026-11-21 19:40 添加）

### 13.1 跨机器的 CLIP 向量一致性

**为什么：** `docs/untested.md` 第 4 节 T20“跨机器的向量一致性”：同一输入的向量只在同一进程里比较过。实验如果在一台机器上建向量、在另一台机器上编码查询，或者两台机器的结果要放在一起比较，就需要知道两边算出来的向量是否一致。

**输入（两台机器上都有，都在 Git 里）：**

- 文本 10 条：`会议室里的白板照片`、`一只猫`、`红色的汽车`、`手写的数学公式`、`表格截图`、`扫描的合同第一页`、`夜晚的城市街道`、`a cat`、`a scanned document`、`中文文字的截图`
- 图片 6 张：`docs/screenshots/windows-2026-11-19/` 下的 5 张 PNG，`change-deepseek-v4/test-results/ocr-e2e/20261116-143732/ocr-smoke.png`

**做法：** 启动 CLIP 服务（默认设置，CPU），在仓库根目录：

```powershell
$texts = @('会议室里的白板照片','一只猫','红色的汽车','手写的数学公式','表格截图','扫描的合同第一页','夜晚的城市街道','a cat','a scanned document','中文文字的截图')
$body = @{ texts = $texts } | ConvertTo-Json -Compress
$t = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8001/encode/text" -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($body))
$imgs = @(Get-ChildItem docs\screenshots\windows-2026-11-19\*.png) + @(Get-Item change-deepseek-v4\test-results\ocr-e2e\20261116-143732\ocr-smoke.png)
$iv = foreach ($f in $imgs) { $r = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8001/encode/image" -ContentType "application/octet-stream" -InFile $f.FullName; [pscustomobject]@{ path = (Resolve-Path -Relative $f.FullName); sha256 = (Get-FileHash $f.FullName -Algorithm SHA256).Hash.ToLower(); vector = $r.vector } }
$h = Invoke-RestMethod -Uri "http://127.0.0.1:8001/health"
[pscustomobject]@{ health = $h; model_version = $t.model_version; texts = $texts; text_vectors = $t.vectors; images = $iv } | ConvertTo-Json -Depth 6 -Compress | Out-File -Encoding utf8 output\windows-w7\clip-vectors.json
```

再记下 clip 环境的版本：`env_check\.venv-clip\Scripts\python -c "import torch, cn_clip, platform; print(torch.__version__, cn_clip.__version__, platform.platform())"`，存成 `clip-env.txt`。

**判定（Claude 在 Mac 上用同样的输入、同样的权重编码后比对，第 14.2 节）：** 每条文本、每张图片两边向量的余弦相似度都 ≥ 0.999；10 条文本对 6 张图片的相似度排序两边完全相同。不要求逐位相同（x86 与 arm64 的浮点运算顺序不同）。达不到时不算执行失败，是一条要写进论文“局限”的发现。

### 13.2 同时运行时的内存（OS-6）

**为什么：** `docs/untested.md` 第 6 节 OS-6、第 7.2 节：PostgreSQL、OpenSearch、后端、通用 Worker、OCR Worker、CLIP 服务同时运行时的总内存一直没有原始数据；第一轮只给了四个 Python 进程的峰值，没有数据库和 OpenSearch，也没有采样原始数据。论文“实验环境”一节要用。

**负载：** 在 `docmgr_w6` 上 `reocr --yes`（`--root` 为第 12.5 节的 docvqa60 目录），启动后端、一个通用 Worker、**一个** OCR Worker（默认设置）、CLIP 服务；同时跑第 13.3 节的检索循环。

**采样（每 5 秒一次，至少 15 分钟，或到 OCR 任务全部完成）：** 新开一个 PowerShell 窗口：

```powershell
$out = "output\windows-w7\memory.csv"
"time,group,pid,working_set_mb,private_mb" | Out-File -Encoding utf8 $out
$end = (Get-Date).AddMinutes(15)
while ((Get-Date) -lt $end) {
  $now = (Get-Date).ToString("o")
  Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('postgres.exe','java.exe','python.exe','node.exe') } | ForEach-Object {
    $c = "$($_.CommandLine)"
    $g = if ($_.Name -eq 'postgres.exe') {'postgresql'} elseif ($_.Name -eq 'java.exe') {'opensearch'} elseif ($_.Name -eq 'node.exe') {'node'} elseif ($c -match 'uvicorn') {'api'} elseif ($c -match 'ocr_worker') {'ocr_worker'} elseif ($c -match 'clip_service') {'clip_service'} elseif ($c -match 'app.worker') {'worker'} else {'python_other'}
    $p = Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue
    if ($p) { "$now,$g,$($_.ProcessId),{0:F1},{1:F1}" -f ($p.WorkingSet64/1MB), ($p.PrivateMemorySize64/1MB) | Out-File -Append -Encoding utf8 $out }
  }
  $avail = (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1KB
  "$now,system_available,0,{0:F1},0" -f $avail | Out-File -Append -Encoding utf8 $out
  Start-Sleep -Seconds 5
}
```

（用 `F1` 而不是 `N1`：`N1` 会输出 `1,234.5` 这样带千位逗号的数字，破坏 CSV。可用内存用 CIM 取，不用 `Get-Counter`：中文版 Windows 的性能计数器名称是中文的，英文路径会报错。）OCR 识别子进程是 `python.exe`，命令行里也有 `ocr_worker`，会被归到 `ocr_worker` 组，这是想要的。报告里写明机器总内存、采样开始和结束时间、负载期间 OCR 完成了多少个任务。

### 13.3 OCR 负载下的查询编码耗时

**为什么：** D36 的局限：CLIP 服务一次只算一个请求，embed 和查询编码会排队，3 秒超时会不会经常触发没有量过（`docs/untested.md` 第 4 节 T22“3 秒查询超时是否合适”）。`reocr` 不产生 embed 任务，所以这里量的是“OCR 占满 CPU 时”的查询编码。

与第 13.2 节同时进行，在另一个窗口（先按第 12.6 节第 3 步的写法拿 `$tok`）：

```powershell
$qs = (Get-Content <docvqa60 目录>\queries.tsv -Encoding utf8 | Select-Object -Skip 1) | ForEach-Object { ($_ -split "`t")[2] }
$out = "output\windows-w7\search-under-load.csv"
"time,i,took_ms,image_status,image_took_ms,hits" | Out-File -Encoding utf8 $out
for ($i = 0; $i -lt 200; $i++) {
  $q = $qs[$i % $qs.Count]
  $b = @{ query = $q; channels = @{ meta = $true; text = $true; image = $true } } | ConvertTo-Json -Compress
  $r = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/search" -Headers @{ Authorization = "Bearer $tok" } -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($b))
  $img = $r.channels | Where-Object { $_.channel -eq 'image' }
  "$((Get-Date).ToString('o')),$i,$($r.took_ms),$($img.status),$($img.took_ms),$($r.hits.Count)" | Out-File -Append -Encoding utf8 $out
  Start-Sleep -Milliseconds 500
}
```

（如果应答里 `channels` 的字段名与上面不同，按 `docs/api.md` §7.1 的实际结构改，并在报告里写明改了什么；同时把第一条应答原样存成 `search-sample.json`。）OCR 任务做完后，不开 OCR Worker 再跑一遍同样的循环，存成 `search-idle.csv`，作为对照。

### 13.4 不做的

不改 `SEARCH_IMAGE_TIMEOUT_SECONDS`、不调 CLIP 设备、不开 MPS/CUDA；这一节只量现状。正式的性能实验是 T27。

### 13.5 验收标准

- [ ] 13.1：`clip-vectors.json` 有 10 条文本、6 张图片的向量和 `health` 信息；`clip-env.txt` 有版本
- [ ] 13.2：`memory.csv` 覆盖至少 15 分钟，相邻两次采样的间隔不超过 15 秒；六组进程（postgresql、opensearch、api、worker、ocr_worker、clip_service）都出现过；报告写了总内存和负载情况
- [ ] 13.3：`search-under-load.csv`、`search-idle.csv` 各 200 行，`search-sample.json` 在
- [ ] 没有改任何代码和配置文件

------------------------------------------------------------------------

## 14. 交回的原始数据与 Claude 的核对方法（2026-11-21 19:40 添加）

### 14.1 交回什么、怎么交

每个任务一个目录：`output/windows-w4/`、`output/windows-w5/`、`output/windows-w6/`、`output/windows-w7/`、`output/windows-w3-supplement/`。每个目录里都要有：

- `git-head.txt`：`git rev-parse HEAD` 和 `git status --porcelain` 的输出（第 2 节第 11 条）
- `commands.txt`：按执行顺序列出实际运行的命令（去掉密码、令牌、连接串）和每条的退出码
- `SHA256SUMS.txt`：目录里每个文件以及对应的另交压缩包的 SHA-256（`Get-FileHash -Algorithm SHA256`，一行一个：`<小写 hash>  <相对路径>`）
- 各节要求的原始文件

单个文件超过 5 MB 的（日志、原文件、截图过多时）不进 Git，打进 `<任务>-extra.zip` 另交给 Barry，hash 写进 `SHA256SUMS.txt`。Barry 推送 GitHub、把压缩包放到 Mac 的 `~/Desktop/windows-results/` 后告诉 Claude。

### 14.2 Claude 收到后怎么核对

Claude 在 Mac 上做，不装新东西；Mac 上没有 PostgreSQL 和 OpenSearch，所以只核对原始数据，不重做需要数据库的步骤。核对结果写进 `docs/changes/windows-<收到日期>-核对.md`，按结论更新 `docs/untested.md` 和 DEVPLAN。

| 对象 | Claude 的核对方法 | 判为通过的条件 |
|---|---|---|
| 所有目录 | 重算 `SHA256SUMS.txt`；读 `git-head.txt` | hash 全部一致；提交号是第 0.2 节的那个，`git status` 为空 |
| JUnit XML（W1、12.2、12.3） | 解析 XML，统计 tests/failures/errors/skipped，列出失败和跳过的用例名；与 Mac 上同一提交的 `pytest --collect-only -q` 清单逐条对比（W1 对比 `8fb5830`，12.2 对比第 0.2 节的提交） | 失败只有已知原因的项；Windows 收集到的用例 = Mac 收集到的用例（差异逐条解释）；跳过的都有原因 |
| W2 数据 | 在 Mac 上运行 `experiments validate`（只读文件，不需要数据库）；在 Mac 上跑 `scripts/datasets/tests/`；检查编号规则、500 条、`file_id` 与图片名对应 | 退出码 0；测试通过；统计与报告一致 |
| W3 结果目录（`docvqa-runs.zip`） | 用 `backend/app/modules/experiments/metrics.py` 从 `results.jsonl` 和 qrels 重算每条查询的 P@10、R@10、nDCG@10，与 `metrics.json` 比对；比较 3 次重复的排名是否完全相同；检查 `config.json` 里的 `git_commit`、`git_dirty`、`clip_model`（权重 hash 前 12 位 `5997ef32c50d`）、三个 mapping 的 sha256（与 Mac 上同一提交的文件比对）、`ocr_params`、`complete`；比较 `reocr` 前后两次 B2 的逐条排名 | 重算的指标与 `metrics.json` 相同（浮点误差 1e-9 以内）；重复间排名相同；配置字段齐全、hash 一致；两次 B2 排名逐条相同 |
| W3 补交数据（12.11） | 读 SQL CSV 与索引计数，交叉比对：任务全部 succeeded；片段数（数据库）= 索引计数；重复检查为 0 行；OCR 模型与参数只有一种；从日志里重算 OCR 每任务平均耗时和 P95 | 与报告里的数字一致；不一致的逐条列给 Barry |
| 12.4 一致性修复 | 读每一步的 `--json` 输出和退出码；比对第 10 步的 `results.jsonl` 与 W3 同配置的排名 | 每一步的退出码与问题类别符合预期；修复后计数不变；B2、B3 排名与 W3 逐条相同 |
| 12.5 崩溃与并发 | 读 8 个 CSV：被强制结束时持有的任务 `attempts=2` 且最终 succeeded；四个领取者都出现；第 4、6、7 条 0 行；每个文档的片段数加总 = 索引计数 | 全部满足 |
| 12.6–12.8 | 读 JSON 和输出原文，与预期逐条对照 | 符合预期；不符合的列给 Barry |
| 12.9 真实文件 | 在 Mac 上用同一提交的解析器（`backend/app/modules/parsing/`，纯函数，不需要数据库）重新解析交回的原文件，与 Windows 的 `/text` JSON 比较正文片段和定位；用人工抄录算 OCR 的 CER（编辑距离 / 抄录字数，去掉空白后计算） | 非 OCR 片段的文本和定位两边相同；定位类型符合第 12.9 节的预期；CER 如实记录（不设通过线，作为论文数据） |
| 13.1 CLIP 向量 | 在 Mac 上用同样的权重、同样的输入编码，计算两边每个向量的余弦相似度和 10×6 的排序 | 余弦相似度都 ≥ 0.999 且排序相同；否则记为发现 |
| 13.2 内存 | 按组、按采样时刻加总内存，算每组峰值、总峰值和最低可用内存；检查采样间隔 | 间隔不超过 15 秒、六组都在；数字作为论文“实验环境”的数据 |
| 13.3 负载下检索 | 从两份 CSV 算总耗时与图像通道耗时的 P50/P95、图像通道 `unavailable` 的比例 | 数据完整（各 200 行）；结论作为 T27 与 D36 局限的依据 |
| W4、W5 | 对照报告逐项看截图、命令输出、退出码 | 每个核对点都有结果和证据 |

核对中发现的代码问题，Claude 不自己修，先报给 Barry（与第 2 节第 5 条相同）。

------------------------------------------------------------------------

## 15. 不交给 Windows 的项目（2026-11-21 19:40 添加）

下面这些还没完成，但不放进本任务书，原因各不相同。Barry 改变决定时再加新任务。

| 项目 | 为什么不交给 Windows | 由谁、什么时候 |
|---|---|---|
| T25 评测数据集与标注（文字型、视觉型、混合型查询，200–500 个文件） | 附录 A18 要求分层查询集，视觉型查询要专门收集图片；相关性标注是论文的评测依据，应由 Barry 本人完成，不能由 AI 代标。DocVQA 只是流程验证 | Barry；越早越好，T26–T28 都依赖它 |
| T26–T28 正式实验与分析 | 依赖 T25；正式实验的机器（Mac 还是 Windows）要先定下来并固定，写进论文“实验环境” | T25 之后由 Barry 决定在哪台机器上跑 |
| `deploy/docker-compose.yml`、`deploy/opensearch/Dockerfile`（OS-7） | 要装 Docker，第 2 节第 2 条禁止；Barry 决定 Mac 上不用 Docker | Barry 批准在 Windows 装 Docker 后再加任务（T30 部署说明需要） |
| Linux 上 `RLIMIT_AS` 内存上限 | 这台机器没有 Linux，装 WSL 是新安装 | 需要 Barry 批准；不做就写进论文局限 |
| IK 分词（OS-2） | 没有与 OpenSearch 2.19.1 匹配的 IK 版本 | 不做，写进论文 |
| 前端页面组件的自动化测试 | 要装组件测试工具 | 需要 Barry 批准 |
| `CLIP_DEVICE=mps`、`cuda` | Windows 没有 MPS；这台机器的 GPU 与 CUDA 环境没有确认，装 CUDA 版 torch 是新安装 | MPS 可以在 Mac 上由 Claude 做（Barry 同意后） |
| Safari | W4 第 10.4 节已写成“有设备就看” | 同 W4 |
| T29–T32 测试报告、部署说明、一致性核对、答辩脚本 | 是文档工作，依赖 W4–W7 的核对结果 | Claude 与 Barry |
