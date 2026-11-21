# 基于多模态信息检索的智能文档管理系统

本科毕业设计（网络工程专业）。系统管理 Word、PDF、Excel 和图片文件，支持四种检索方式，并能用实验比较它们的效果：

| 检索方式 | 做法 | 对照组 |
|---|---|---|
| 文件名、标签检索 | OpenSearch BM25，文件级索引 `doc_meta` | B0 |
| 正文检索 | 解析出的文本切成片段，BM25，片段索引 `chunks`（`source_type=body`） | B1 |
| OCR 文字检索 | 扫描页和图片用 PaddleOCR 识别出文字，进同一个片段索引（`source_type=ocr`） | B2 |
| 图文跨模态检索 | Chinese-CLIP 把图片和查询文字编码成向量，精确余弦检索 | B3（与上面三路用 RRF 融合） |

所有通道的结果都聚合到文件（`document_id`）再融合和评测；每条结果都能回溯到来源（PDF 页码、Word 段落、Excel 区域、图片）。预训练模型只做推理，不训练、不微调。CLIP 服务不可用时自动降级为文本检索，并在结果里标明。

范围、约束和全部设计决策见 [`GLOBAL.md`](GLOBAL.md)（附录 A 为已确定的决策）；开发进度见 [`DEVPLAN.md`](DEVPLAN.md)。

## 组成

| 进程 | 目录 | Python 环境 | 作用 |
|---|---|---|---|
| API 服务 | `backend/` | main（`.venv-main`） | FastAPI：登录与权限、文档管理、检索编排（RRF）、检索日志 |
| 通用 Worker | `backend/`（`python -m app.worker`） | main | 解析、切分、写索引、清理、调用 CLIP 服务生成图片向量 |
| OCR Worker | `services/ocr_worker/` | ocr（`env_check/.venv-ocr`，PaddleOCR） | 只处理 OCR 任务 |
| CLIP 服务 | `services/clip_service/` | clip（`env_check/.venv-clip`，PyTorch） | 常驻加载模型，提供图片和文字编码接口 |
| 前端 | `frontend/` | Node.js（项目内 `.tools/node/`） | Vue 3 + TypeScript + Element Plus |

依赖的外部服务：PostgreSQL（数据库，同时承担任务队列）、OpenSearch 2.19.1 + analysis-smartcn（BM25 与向量检索）。PaddlePaddle 与 PyTorch 分在两个虚拟环境，不混装。

```
backend/       API 与通用 Worker（app/modules 下按模块 M1–M13 划分）
shared/        各环境共用：数据契约、ID 规则、任务队列、切分、文本索引
services/      ocr_worker（M6）、clip_service（M9）
frontend/      前端（M14）
experiments/   实验数据集、查询集、标注、实验配置与结果（M12）
deploy/        docker-compose.yml（PostgreSQL + OpenSearch）
scripts/       手动烟测脚本
env_check/     阶段一环境实测脚本与报告
docs/          设计文档与记录（见下文）
```

## 快速开始

下面是最短路径，完整命令（迁移、Worker、OCR、CLIP、一致性检查、实验）见 [`CLAUDE.md`](CLAUDE.md) 的“常用命令”。Windows 上把 `bin/` 换成 `Scripts\`。

1. **配置**（项目根目录）：`cp .env.example .env`，修改其中的数据库密码和 `JWT_SECRET`。
2. **依赖服务**：`docker compose --env-file .env -f deploy/docker-compose.yml up -d`；也可以自己安装 PostgreSQL 和带 analysis-smartcn 插件的 OpenSearch 2.19.1。
3. **后端**：
   ```bash
   python -m venv .venv-main
   .venv-main/bin/pip install -e "shared[dev]" -e "backend[dev]"
   cd backend
   ../.venv-main/bin/alembic upgrade head
   ../.venv-main/bin/python -m app.modules.auth create-admin admin
   ../.venv-main/bin/uvicorn app.main:create_app --factory
   ```
   打开 `http://127.0.0.1:8000/health` 查看数据库、OpenSearch、CLIP 服务的状态。
4. **Worker**（另开终端，`backend/` 目录）：`../.venv-main/bin/python -m app.worker`。OCR Worker 和 CLIP 服务需要先把模型文件放到 `models/`，见 `docs/decisions.md` D30、D33；不启动它们时，OCR 和图像检索不可用，其余功能照常。
5. **前端**（`frontend/` 目录）：
   ```bash
   export PATH="$(git rev-parse --show-toplevel)/.tools/node/bin:$PATH"
   npm install
   npm run dev
   ```
   打开 `http://127.0.0.1:5173`。

模型文件缺失时服务启动即报错退出，不会联网下载。

## 测试

| 位置 | 命令 |
|---|---|
| `backend/`、`shared/` | `../.venv-main/bin/python -m pytest` |
| `services/ocr_worker/`、`services/clip_service/` | `../../.venv-main/bin/python -m pytest`；真实模型测试见 CLAUDE.md |
| `frontend/` | `npm run typecheck`、`npm test`、`npm run build` |
| 代码检查 | 四个 Python 目录分别 `ruff check . && ruff format --check .` |

需要 PostgreSQL 的集成测试要设置 `TEST_DATABASE_URL`（专用的空库，见 `.env.example`），不设置时跳过。**没有实际运行过的测试逐项登记在 [`docs/untested.md`](docs/untested.md)，在运行通过之前不算“已验证”。**

## 文档

| 文件 | 内容 |
|---|---|
| [`GLOBAL.md`](GLOBAL.md) | 全局规范：目标、优先级、技术约束、检索设计、禁止事项、验收标准 |
| [`DEVPLAN.md`](DEVPLAN.md) | 任务清单（T00–T32）、待议事项、每个任务的完成记录 |
| [`docs/architecture.md`](docs/architecture.md) | 分层、模块、进程与数据流 |
| [`docs/data-model.md`](docs/data-model.md) | 表结构与迁移 |
| [`docs/api.md`](docs/api.md) | HTTP 接口（含 CLIP 服务） |
| [`docs/decisions.md`](docs/decisions.md) | 设计决策与理由（D1 起） |
| [`docs/untested.md`](docs/untested.md) | 未测试清单 |
| [`docs/downloads.md`](docs/downloads.md) | 下载与安装记录 |
| [`docs/changes/`](docs/changes/) | 每个任务的逐文件修改记录 |
| [`experiments/README.md`](experiments/README.md) | 实验数据格式、操作顺序、对照组配置 |
| [`frontend/README.md`](frontend/README.md) | 前端说明 |

## 当前状态

以 [`DEVPLAN.md`](DEVPLAN.md) 为准。概括地说：阶段二到阶段四的功能（文件管理与权限、解析、OCR、BM25、CLIP 图像检索、RRF 融合、一致性检查、实验框架）都已实现；里程碑 MVP-0、MVP-1、MVP-2 还没有宣布达成；评测数据集和标注尚未建立，阶段五的实验（T25–T28）和阶段六的文档（T29–T32，其中 T30 会补全部署说明）还没有开始。
