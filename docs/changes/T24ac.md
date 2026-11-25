# 修改记录：T24ac OCR Worker 收到停止信号时以 130 退出（2026-11-23）

- 来源：`docs/changes/2026-11-23-代码复核建议.md` R5，Barry 于 2026-11-23 批准（“修 R5”）
- 任务性质：代码修复，不带 🔒；没有改表结构、索引、接口、配置项、附录 A，没有新依赖
- 决策：`docs/decisions.md` D54
- 修改者：Claude（Opus 5.5）

## 逐文件修改记录

| 文件 | 位置 | 修改前 | 修改后 | 原因与影响 |
|---|---|---|---|---|
| `services/ocr_worker/ocr_worker/__main__.py` | `main` 末尾 | `return 0` | `return 130 if stop_requested else 0` | 外层循环把 0 当作“重新拉起”，收到停止信号后会马上又启动 |
| 同上 | 模块说明 | 退出码只写了 0、1 | 写明 0、1、130 的含义 | 与通用 Worker 的说明一致 |
| `services/ocr_worker/tests/test_main.py` | 新增，4 项 | — | 做满任务数返回 0；SIGINT、SIGTERM 各返回 130；最后一个任务途中收到信号返回 130 | 入口原来没有测试 |
| `docs/decisions.md` | 新增 D54 | — | — | D52 里“OCR Worker 返回 0”以 D54 为准 |
| `docs/changes/2026-11-23-代码复核建议.md` | R5 | 待决定 | 已修，补上实测结果 | — |
| `docs/untested.md` | 第 7.4 节 | “由代码得出，没有实际按过” | macOS 上已用真实信号验证，Windows 脚本待验证 | — |
| `windows任务书.md` | 第 17.5 节、第 17.12 节 | OCR Worker 退出码 0 | 130；新增 D 步验证循环脚本 | 退出码约定变了 |
| `DEVPLAN.md` | §3、§4、§5 | — | T24ac 勾选与记录，§4 R5 标记已解决 | — |

没有改的调用方：`CLAUDE.md` 的循环（非 0 即停）、`run_ocr_worker_loop.ps1`（本来就判断 130）、`scripts/smoke/ocr_e2e.py`（`OCR_WORKER_MAX_TASKS=1`，做满退出，仍是 0）。

## 验证

- 已运行（macOS，main 环境）：`services/ocr_worker/` pytest 80 passed、4 skipped；ruff check、format check 通过。backend、shared 没有改动，没有重跑
- 已运行（macOS，ocr 环境）：真实识别 4 项通过
- 反证：改之前新增的 4 项中 3 项失败（都是“应为 130，实际 0”）
- 真实信号、真实循环（macOS；真实的 `main()` 和任务循环，模型、数据库、索引换成假的，脚本在会话临时目录；向整个进程组发一次 SIGINT，模拟终端里的 Ctrl+C）：

  | 外层循环 | 改之前 | 改之后 |
  |---|---|---|
  | bash | 启动 2 次，循环没停 | 启动 1 次，循环停下 |
  | zsh | 启动 1 次，循环停下 | 启动 1 次，循环停下 |

- **未测试（Not Tested）**：Windows 上 `run_ocr_worker_loop.ps1` 里按 Ctrl+C（任务书第 17.5 节 D）；只给 Worker 进程发 SIGTERM 时的真实循环（退出码有单元测试）

## 备注：W6 12.7 记录的退出码 1

12.7 的记录写 Worker 退出码为 1，D52 和核对记录据此写成“Worker 以退出码 1 结束”。重新读代码：`loop.py` 会捕获任务里的异常并记为失败，之后 `main()` 当时应当返回 0；日志里“已处理 1 个任务，退出”也说明走到了正常结尾。所以这个 1 **不能由代码解释**，可能来自启动方式（例如虚拟环境的启动器收到 Ctrl+C），当时没有保存窗口原始输出，无法确认。任务被打断、记一次失败这一点有任务记录为证，不受影响。第 17.5 节要求直接记下退出码，届时一并核对。
