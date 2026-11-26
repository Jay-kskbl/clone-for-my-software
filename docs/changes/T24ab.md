# 修改记录：T24ab Worker 被强制结束时，它的子进程跟着退出（2026-11-23）

- 来源：`docs/changes/2026-11-23-代码复核建议.md` R1，Barry 于 2026-11-23 批准（“先修 R1”）
- 任务性质：代码修复，不带 🔒；没有改表结构、索引、接口、配置项、附录 A，没有新依赖
- 决策：`docs/decisions.md` D53
- 修改者：Claude（Opus 5.5）

## 逐文件修改记录

| 文件 | 位置 | 修改 | 原因 | 影响 |
|---|---|---|---|---|
| `shared/parent_watch.py` | 新增 | `exit_when_parent_dies()`：在子进程里启动一个后台线程，等父进程的 sentinel（`multiprocessing.parent_process().sentinel`），父进程一消失就 `os._exit(1)`；在主进程里调用什么也不做 | `daemon=True` 的子进程只在父进程**正常退出**时才会被结束；父进程被强制结束时，子进程没有人管超时和续租 | 正常运行、超时、租约丢失、Ctrl-C 的行为都不变 |
| `backend/app/worker/runner.py` | `_child_main` 开头 | 调用 `exit_when_parent_dies()` | W6 12.5 的日志里，被强杀的通用 Worker 的子进程照常跑完了任务 | 未提交的数据库事务回滚；已写的部分由重新领取的任务覆盖 |
| `services/ocr_worker/ocr_worker/engine_process.py` | `_child_main` 开头 | 同上 | W6 12.5 的 OCR 识别子进程同样 | 不再白占 CPU 和约 3 GB 内存 |
| `backend/tests/unit/test_worker_runner.py` | 新增 1 项与辅助函数 | 另起一个进程当 Worker 父进程，子进程每 0.05 秒写一个字节；强制结束父进程后，文件必须停止变长 | 端到端验证；`Popen.kill()` 在 Windows 上是 TerminateProcess，等同于 `Stop-Process -Force`，所以这一项在 Windows 上也会执行 | 每次约 2.2 秒 |
| `services/ocr_worker/tests/fakes.py`、`test_engine_process.py` | 新增 `HeartbeatEngine` 与 1 项测试 | 同上，对象是识别子进程 | 同上 | 每次约 2.3 秒 |
| `shared/tests/test_parent_watch.py` | 新增 1 项 | 在主进程里调用不启动线程、不结束进程 | 防止误用 | — |
| `docs/decisions.md` | 新增 D53 | — | — | — |
| `docs/changes/2026-11-23-代码复核建议.md` | R1、§3、新增 R5 | R1 标记已修；**更正**：§3 原来说两个 Worker 停止后的退出码不同“功能上没有问题”，这是错的，移到 R5 | 见下 | — |
| `docs/untested.md` | 第 7.4 节 | 新增两行（Windows 上的孤儿子进程重测、OCR Worker 的退出码） | — | — |
| `windows任务书.md` | 第 17.1、17.5 节 | 新增 17.5 C：强制结束 Worker，看子进程是否跟着退出；A 步注明直接运行、不要套循环 | — | — |
| `DEVPLAN.md` | §3、§4、§5 | T24ab 勾选与记录；§4 R1 标记已解决，新增 R5 | — | — |

## 验证

- 已运行（macOS，main 环境）：`backend/` pytest 726 passed、229 skipped（跳过的都需要 PostgreSQL / OpenSearch）；`shared/` 109 passed；`services/ocr_worker/` 76 passed、4 skipped；三个目录 ruff check、format check 通过
- 已运行（macOS，ocr 环境）：真实识别 `tests.test_real_ocr` 4 项通过
- 反证：让 `exit_when_parent_dies()` 直接返回，两项强杀测试都失败，并且确实留下了 2 个孤儿进程（父进程号变成 1，约 60 秒后自行结束）；恢复后两项各重复 6 次都通过，之后没有残留的子进程
- **未测试（Not Tested）**：Windows 上的强制结束（两项自动化测试会在 Windows 上执行，另有任务书第 17.5 节 C 的真实 Worker 验证）；macOS 上对着真实 Worker 强制结束（本机没有 PostgreSQL）

## 修改建议（后续）

1. **R5（新发现，未改）：** OCR Worker 收到停止信号后返回 0。`CLAUDE.md` 的写法 `while true; do … || break; done` 和 `scripts/windows/run_ocr_worker_loop.ps1` 都把 0 当作“做满任务数、重新拉起”，所以在循环里按 Ctrl+C，OCR Worker 停下后可能马上又被拉起。通用 Worker 为此返回 130。建议 OCR Worker 也返回 130，等 Barry 决定。
2. `_create_ocr_tasks` 的“先查有没有、再插入”没有锁。孤儿消除之后，同一文档同时有两个 parse 在跑的机会小了很多，但父进程卡死超过租约时仍可能出现。暂不改，只记录。
