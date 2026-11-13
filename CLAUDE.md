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
- 不主动 commit；汇报后给出建议的 commit message，等 Barry 确认。

## 环境

- `backend/`、`shared/` 使用 main 虚拟环境；`services/ocr_worker` 使用 ocr 环境；`services/clip_service` 使用 clip 环境。不得混装依赖。
- 环境实测结论见 `env_check/env_report.md` 和 `docs/decisions.md`。

## 常用命令

首次准备（项目根目录）：

```bash
cp .env.example .env                                  # 然后修改其中的密码
python -m venv .venv-main
.venv-main/bin/pip install -e "shared[dev]" -e "backend[dev]"   # Windows：.venv-main\Scripts\pip
```

- 启动依赖服务（项目根目录）：`docker compose --env-file .env -f deploy/docker-compose.yml up -d`
- 启动后端（`backend/` 目录，main 环境）：`uvicorn app.main:create_app --factory --reload`，然后访问 `http://127.0.0.1:8000/health`
- 数据库迁移（`backend/` 目录，main 环境）：`alembic upgrade head`；说明见 `docs/data-model.md` §4
- 运行测试（main 环境）：在 `backend/` 和 `shared/` 目录下分别执行 `pytest`
- 集成测试需要专用的空测试库：先建库 `docmgr_test`，再设置 `TEST_DATABASE_URL`（见 `.env.example`）；不设置时这些测试被跳过，算“未运行”
- 代码检查（`backend/`、`shared/` 目录分别执行）：`ruff check . && ruff format --check .`
- 启动 Worker：T07 完成后补充
- 运行前端：T10 完成后补充
