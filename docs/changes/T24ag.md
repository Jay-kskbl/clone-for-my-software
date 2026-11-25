# 修改记录：T24ag 内存上限提示只打一次、网页图标（2026-11-25）

- 来源：`docs/changes/2026-11-23-代码复核建议.md` R4，Barry 于 2026-11-25 批准（“先做 R4”）。R4 的第三处（检索页四个开关全关后地址栏残留 `ch`）Barry 于 2026-11-25 决定保留现状（地址栏记的是最后一次真正执行的检索，刷新能恢复结果），**不改**
- 任务性质：小改动，不带 🔒；没有改表结构、索引、接口、配置、附录 A，没有新依赖
- 修改者：Claude（Opus 5.5）

## 逐文件修改记录

| 文件 | 位置 | 修改前 | 修改后 | 原因与影响 |
|---|---|---|---|---|
| `backend/app/worker/runner.py` | 新增 `memory_limit_supported`；`_limit_memory` | 不支持的系统上，每个任务的子进程打印一次警告（Windows 上 W3 打了 1000 次；macOS 上设置失败，同样每个任务一次） | 只在 Linux 上设置（D16：只有 Linux 有效）；其他系统什么也不做、不打印。Linux 上设置失败仍然警告 | macOS 上原来也设不成功（实测 `ValueError: current limit exceeds maximum limit`），效果不变 |
| `backend/app/worker/__main__.py` | 启动完成处 | — | 不支持时打一次警告 | 说明没有丢，只是不再刷屏 |
| `backend/tests/unit/test_worker_runner.py`、`test_worker_main.py` | 新增 9 项 | — | 子进程不打印；各系统是否支持；Linux 上照常设置、失败照常警告；启动时只提示一次 | — |
| `frontend/public/favicon.svg` | 新增 | — | 与侧栏、登录页相同的标志（`AppIcon` 的 docs 图标，底色为 Element Plus 默认主题色 `#409eff`） | 自己画的，没有新依赖 |
| `frontend/index.html` | `<head>` | 没有声明图标，浏览器请求 `/favicon.ico` 得到 404（W5 11.6） | 声明 `/favicon.svg` | — |
| `frontend/tests/favicon.test.mjs` | 新增 2 项 | — | 声明的图标文件存在；线条与 `AppIcon` 相同 | 改了标志忘了改图标会失败 |
| `docs/untested.md`、`windows任务书.md`、`DEVPLAN.md`、`docs/changes/2026-11-23-代码复核建议.md` | — | — | 登记、任务书第 17.2 节、完成记录、R4 标记 | — |

OCR Worker 的 `_limit_memory` 没有改：Windows 上本来就不打印，其他系统每次启动识别子进程才打一次，没有刷屏。

## 验证

- 已运行（macOS，main 环境）：`backend/` pytest 769 passed、240 skipped；ruff 通过。shared、OCR Worker 没有改动，没有重跑
- 已运行：前端类型检查、生产构建（`dist/favicon.svg` 在）、单元测试 17 个文件 207 项通过
- 已运行：开发服务器上打开登录页，`/favicon.svg` 返回 200、`image/svg+xml`、能解码；16、32、96 像素下与登录页标志一致；没有对 `favicon.ico` 的请求。控制台里的 502 是后端没开
- 反证：用修改前的 `runner.py`，“子进程不打印”一项失败（macOS 上复现了刷屏）；去掉启动提示，“只提示一次”失败；去掉 `index.html` 的声明，图标测试失败
- **未测试（Not Tested）**：Windows 上启动 Worker 处理若干任务后的日志；Safari、Firefox 的图标显示

## 修改建议（后续）

检索页四个开关全关后地址栏残留 `ch`：全关时不发请求，刷新会按上一次的开关重查。Barry 于 2026-11-25 决定保留现状（地址栏记的是最后一次真正执行的检索，刷新能恢复结果）。
