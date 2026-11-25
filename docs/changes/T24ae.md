# 修改记录：T24ae 把失败的 embed、ocr 任务成批放回队列（2026-11-25）

- 来源：`docs/changes/2026-11-23-代码复核建议.md` R2 的 b，Barry 于 2026-11-25 批准（“做 T24ae”）
- 任务性质：新增一个命令行工具，不带 🔒；没有改表结构、索引、接口、配置、附录 A，没有新依赖
- 决策：`docs/decisions.md` D56
- 修改者：Claude（Opus 5.5）

## 逐文件修改记录

| 文件 | 位置 | 修改 | 原因与影响 |
|---|---|---|---|
| `backend/app/modules/documents/requeue.py` | 新增 | `plan_requeue`（纯函数，挑选与统计）、`load_failed_tasks`、`requeue` | 挑选规则与数据库分开，可以单独测试 |
| `backend/app/modules/documents/__main__.py` | 新增 | `requeue-failed --type embed\|ocr [--yes]`，默认演练；连不上数据库时只输出异常类型 | 与现有命令（`reocr`、`repair`）的约定一致 |
| `backend/tests/unit/test_requeue_failed.py` | 新增 20 项 | 挑选、原因统计、放回的列、演练、参数与错误 | 不需要数据库 |
| `backend/tests/integration/test_requeue_failed_db.py` | 新增 3 项 | 演练不改数据；只动指定类型的失败任务、放回后马上能领取；旧版本 OCR 任务不动 | **需要 PostgreSQL，本机未运行** |
| `CLAUDE.md` | 常用命令 | 加一条命令说明 | 与其他命令一致 |
| `docs/decisions.md`、`docs/untested.md`、`windows任务书.md`、`DEVPLAN.md`、`docs/changes/2026-11-23-代码复核建议.md` | — | D56；登记 3 项未运行的测试；任务书第 17.16 节；任务与完成记录；R2 的 b 标记已做 | — |

## 验证

- 已运行（macOS，main 环境）：`backend/` pytest 752 passed、240 skipped（比上次多 20 项通过、3 项跳过）；ruff check、format check 通过。shared、OCR Worker 没有改动，没有重跑
- 已运行：真实命令对着连不上的数据库，退出码 1，输出不含口令和地址；`--type parse` 被参数检查拒绝
- 反证：分别改成不跳过已删除文档、不跳过旧版本、不清空 `started_at`、去掉条件更新、演练也执行，各有 1–5 项测试失败；恢复后通过
- **未测试（Not Tested）**：真实 PostgreSQL 上的查询与更新（3 项集成测试）；CLIP 关闭一段时间、恢复后补齐向量的全过程（任务书第 17.16 节）。代码复核：联表查询与条件更新的列名对照了 `db/models.py`；清空的列与 `retry_task` 逐项相同

## 修改建议（后续）

1. 前端仍没有重试按钮。要不要加由 Barry 决定。
2. R2 的 c（一致性检查新增一类）不再需要，理由见 D56。
