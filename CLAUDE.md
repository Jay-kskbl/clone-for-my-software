# CLAUDE.md

本仓库是 Barry 的本科毕业设计：基于多模态信息检索的智能文档管理系统。请称呼用户为 Barry。

## 必读

全局约束（必须遵守，与本文件冲突时以 GLOBAL.md 为准）：

@GLOBAL.md

开发进度与任务清单：`DEVPLAN.md`。开始任何任务前先读它，确认当前任务编号。

## 工作约定（速查）

- 一次只做 DEVPLAN 中的一个任务编号；不在当前任务里顺手做其他事。新想法记到 DEVPLAN §4。
- 带 🔒 的任务：先给出计划（要改哪些文件、接口、表结构或索引结构），等 Barry 批准后再写代码。
- 修改附录 A 中的任何决策，先停下来问 Barry。
- 完成任务后按 GLOBAL §11.3 汇报；没跑过的测试写"未运行"。
- 每完成一个任务编号就自动 commit，不必等 Barry 确认（Barry 于 2026-11-13 决定）：一个任务一个 commit，只提交该任务的改动；不 push。未完成或被阻塞的任务不提交。
- 每完成一个任务，当场更新 `DEVPLAN.md`：勾选任务，在 §5 写完成记录。任务提交后，紧接着把 §5 里的 commit 编号补上并单独提交，不留到下一个任务。
- 没有实际执行的测试，除了在 DEVPLAN §5 标注“未测试（Not Tested）”，还要逐项登记到 `docs/untested.md`；之后实际运行通过了，再从该文件中删除。
- 任何从网络下载或安装的内容（依赖包、模型、工具），先按 GLOBAL.md 的规则征得 Barry 同意，装完立刻登记到 `docs/downloads.md`：内容、版本、来源、安装位置、大小、用途。

## 环境

- `frontend/` 使用 Node.js（项目内 `.tools/node/`，见 `docs/decisions.md` D23）。
- `backend/`、`shared/` 使用 main 虚拟环境；`services/ocr_worker` 使用 ocr 环境；`services/clip_service` 使用 clip 环境。不得混装依赖。
- ocr 环境就是环境实测时建的 `env_check/.venv-ocr`（Barry 决定沿用，见 `docs/decisions.md` D30），`shared` 以开发模式装在里面。
- clip 环境就是环境实测时建的 `env_check/.venv-clip`（沿用，见 `docs/decisions.md` D33）。
- 环境实测结论见 `env_check/env_report.md` 和 `docs/decisions.md`。

## 常用命令

首次准备（项目根目录）：

```bash
cp .env.example .env                                  # 然后修改其中的密码和 JWT_SECRET
python -m venv .venv-main
.venv-main/bin/pip install -e "shared[dev]" -e "backend[dev]"   # Windows：.venv-main\Scripts\pip
```

- 启动依赖服务（项目根目录）：`docker compose --env-file .env -f deploy/docker-compose.yml up -d`
- 启动后端（`backend/` 目录，main 环境）：`uvicorn app.main:create_app --factory --reload`，然后访问 `http://127.0.0.1:8000/health`
- 数据库迁移（`backend/` 目录，main 环境）：`alembic upgrade head`；说明见 `docs/data-model.md` §4
- 创建管理员（`backend/` 目录，main 环境）：`python -m app.modules.auth create-admin <用户名>`，密码在终端里输入
- 一致性检查（`backend/` 目录，main 环境）：`python -m app.modules.consistency check`，只读，对账数据库、磁盘和三个索引（`doc_meta`、`chunks`、图片向量索引 `image_vectors`）；修复用 `python -m app.modules.consistency repair --fix <类别>`，要修多类就重复写 `--fix`（如 `--fix index --fix temp-files`），不加 `--yes` 只演练；类别与退出码见 `docs/decisions.md` D31，T21 新增的向量检测项和 `embeddings` 类别（删除不再被任何图片使用的向量记录）见 D35。重建索引（`--fix rebuild-indices`，三个索引一起重建）前先停掉通用 Worker 和 OCR Worker；默认只在检查发现索引缺失或结构不一致时重建，检查没发现问题也要重建（例如改了 `search_analyzer` 等检查比较不到的设置）时加 `--force`，仍需 `--yes` 才执行（T24d，见 D43）
- 实验（`backend/` 目录，main 环境）：`python -m app.modules.experiments validate` 检查 `experiments/` 下清单、查询集和标注的格式；`python -m app.modules.experiments import` 上传数据集文件，之后启动 Worker 和 OCR Worker 处理完；`python -m app.modules.experiments run --config ../experiments/configs/B1.json`（可加 `--repeat 3`）运行一组实验，结果写到 `experiments/runs/`。开了图像通道的配置（B3、`B3-*`、`clip-only`）要先启动 CLIP 服务，并让通用 Worker 处理完 embed 任务，否则运行前检查会拦下。数据格式和操作顺序见 `experiments/README.md`
- 运行测试（main 环境）：在 `backend/` 和 `shared/` 目录下分别执行 `pytest`
- 集成测试需要专用的空测试库：先建库 `docmgr_test`，再设置 `TEST_DATABASE_URL`（见 `.env.example`）；不设置时这些测试被跳过，算“未运行”
- 代码检查（`backend/`、`shared/`、`services/ocr_worker/`、`services/clip_service/` 目录分别执行）：`ruff check . && ruff format --check .`
- 启动 Worker（`backend/` 目录，main 环境）：`python -m app.worker`；它处理满 `WORKER_MAX_TASKS` 个任务后会退出，长期运行用 `while true; do python -m app.worker || break; done`。通用 Worker 也处理图片的 embed 任务（T21），需要 CLIP 服务已启动；CLIP 服务没开时 embed 任务会重试，最后标为失败，其余处理不受影响；启动时连不上数据库即以退出码 1 结束（T24a，见 `docs/decisions.md` D40），运行中数据库短暂中断则会重试
- 启动 OCR Worker（`services/ocr_worker/` 目录，ocr 环境）：`../../env_check/.venv-ocr/bin/python -m ocr_worker`；它处理满 `OCR_WORKER_MAX_TASKS` 个任务后会退出，长期运行用 `while true; do ../../env_check/.venv-ocr/bin/python -m ocr_worker || break; done`。需要先把模型放到 `models/ocr/`（见 `docs/decisions.md` D30）；配置、模型或数据库有问题时启动即以退出码 1 结束
- OCR Worker 测试（`services/ocr_worker/` 目录）：main 环境 `../../.venv-main/bin/python -m pytest`；真实识别测试用 ocr 环境 `../../env_check/.venv-ocr/bin/python -m unittest tests.test_real_ocr -v`
- 启动 CLIP 服务（`services/clip_service/` 目录，clip 环境）：`../../env_check/.venv-clip/bin/python -m clip_service`，然后访问 `http://127.0.0.1:8001/health`。需要先把权重放到 `models/clip/clip_cn_vit-b-16.pt`（见 `docs/decisions.md` D33）；配置、权重或模型有问题时启动即以退出码 1 结束，不会联网下载。接口见 `docs/api.md` §9
- CLIP 服务测试（`services/clip_service/` 目录）：main 环境 `../../.venv-main/bin/python -m pytest`；真实模型测试用 clip 环境 `../../env_check/.venv-clip/bin/python -m unittest tests.test_real_clip -v`
- 前端（`frontend/` 目录）。Node.js 装在项目内的 `.tools/node/`，不在系统 `PATH` 里，每个新开的终端先执行一次：`export PATH="$(git rev-parse --show-toplevel)/.tools/node/bin:$PATH"`
  - 首次准备：`npm install`
  - 开发服务器：`npm run dev`，然后访问 `http://127.0.0.1:5173`（需要后端已在 8000 端口启动）
  - 类型检查：`npm run typecheck`；单元测试：`npm test`；生产构建：`npm run build`
