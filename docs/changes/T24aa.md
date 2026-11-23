# 修改记录：T24aa Ctrl-C 时两个 Worker 都把当前任务做完再退出（2026-11-23）

- 来源：Windows 第四轮核对（`docs/changes/windows-2026-11-23-核对.md` §2 第 1、2 条；W6 12.7 实测 OCR Worker 在 Windows 上按 Ctrl+C 会打断当前任务）。Barry 于 2026-11-23 批准（“先修 Ctrl+C”）
- 任务性质：代码修复，不带 🔒；没有改表结构、索引、接口、配置项、附录 A，没有新依赖
- 决策：`docs/decisions.md` D52
- 修改者：Claude（Opus 5.5）

## 逐文件修改记录

| 文件 | 位置 | 修改前 | 修改后 | 原因 | 影响 |
|---|---|---|---|---|---|
| `services/ocr_worker/ocr_worker/engine_process.py` | 新增函数 `_poll` | — | `conn.poll()` 遇到 `InterruptedError` 时按剩余时间接着等，到期返回 `False` | Windows 上主线程的 `poll()` 收到 Ctrl-C 会直接抛 `InterruptedError`（PEP 475 的自动重试不覆盖这条路径） | 只影响“等待被打断”这一种情况；正常等待、超时的行为不变 |
| 同上 | `EngineProcess.start` | `parent_conn.poll(self._load_timeout)` | `_poll(parent_conn, self._load_timeout)` | 加载模型期间按 Ctrl-C，原来会让启动失败 | 加载超时的判断不变 |
| 同上 | `EngineProcess.run` 的等待循环 | `self._conn.poll(...)` | `_poll(self._conn, ...)` | W6 12.7 的现象就发生在这里 | 当前页照常识别完，Worker 之后按 D34 退出 |
| `backend/app/worker/runner.py` | 导入 | — | `import signal` | 下一行要用 | — |
| 同上 | `_child_main` 开头 | 没有处理 SIGINT | `signal.signal(signal.SIGINT, signal.SIG_IGN)` | 终端里按 Ctrl-C 时子进程也会收到，原来会抛 `KeyboardInterrupt`，被当作一次可重试的失败；OCR 识别子进程在 D34 已经这样做了 | 子进程的结束由父进程决定（正常返回、超时或租约丢失时 kill），这一点原来就是如此 |
| 同上 | 新增函数 `_poll`；`run_in_subprocess` 的等待 | `parent_conn.poll(...)` | `_poll(parent_conn, ...)` | 与 OCR Worker 相同的 Windows 问题 | 同上 |
| `backend/tests/unit/test_worker_runner.py` | 新增 4 项 | — | 子进程自己收到 SIGINT 仍把任务做完（Windows 上跳过：那里 `os.kill(pid, SIGINT)` 会直接结束进程）；`_poll` 被打断后接着等；`_poll` 一直被打断时到期返回；父进程第一次 `poll()` 被打断时任务仍然成功（把 `runner._mp` 换成一个返回包装管道的对象） | 覆盖两处改动 | — |
| `services/ocr_worker/tests/fakes.py` | 新增 `CtrlCEngine`、`ctrl_c_engine` | — | 识别途中给自己发 SIGINT，再正常返回 | 供下一项测试使用（必须在模块顶层，子进程用 spawn 按名字导入） | — |
| `services/ocr_worker/tests/test_engine_process.py` | 新增 4 项 | — | 识别子进程收到 SIGINT 仍返回结果（Windows 上跳过，原因同上；这是 D34 原有行为，之前没有测试）；`_poll` 两项；父进程第一次 `poll()` 被打断时这一页仍然成功、子进程不重开 | 覆盖改动，并给 D34 补上测试 | — |
| `docs/decisions.md` | 新增 D52 | — | 问题、决定、不变的部分、局限 | — | — |
| `docs/untested.md` | 第 4 节“OCR Worker 按 Ctrl-C……”一行、第 7.4 节两行 | 未通过 / 未实测 | 已修复，Windows 上待第 17.5 节重测 | — | — |
| `windows任务书.md` | 第 17.1、17.5 节 | “等修复任务完成后” | 写明修复是 T24aa，拉到包含它的提交后就可以做；同时要重跑 backend、shared、OCR Worker 的测试 | — | — |
| `DEVPLAN.md` | §3 插入任务、§4 待决定、§5 | — | 新增 T24aa 并勾选；§4 那一条注明已批准；§5 完成记录 | — | — |

## 验证

- 已运行（macOS，main 环境）：`backend/` 下 `pytest` 725 passed、229 skipped（跳过的都是需要 PostgreSQL / OpenSearch 的测试，与修改前相同）；`services/ocr_worker/` 下 `pytest` 75 passed、4 skipped（跳过的是只在 ocr 环境运行的真实识别测试）；两个目录 `ruff check .`、`ruff format --check .` 通过
- 已运行（macOS，ocr 环境）：`python -m unittest tests.test_real_ocr -v`，4 项通过（改动在真实识别的等待路径上）
- 反证：临时去掉修复（`except InterruptedError` 改成别的异常、去掉 `SIG_IGN`）再跑，新增的 backend 4 项、OCR 3 项全部失败；恢复后通过。OCR 子进程收到 SIGINT 那一项去掉修复后仍通过，因为它测的是 D34 原有的行为
- **未测试（Not Tested）**：Windows 上真实按 Ctrl+C（`windows任务书.md` 第 17.5 节）；macOS 上对着真实 Worker 按 Ctrl+C（本机没有 PostgreSQL，Worker 起不来）。已登记到 `docs/untested.md`

## 修改建议（后续）

1. Windows 上按第 17.5 节重测通过后，删掉 `docs/untested.md` 第 4 节那一行和第 7.4 节的两行。
2. 父进程从管道读结果的 `recv()` 没有包进重试（理由见 D52）。如果 Windows 重测时日志里仍出现 `InterruptedError`，先看是不是出在 `recv()`。
