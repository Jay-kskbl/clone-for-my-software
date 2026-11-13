# 下载与安装记录

更新日期：2026-11-13（T08 完成后）

这里登记开发过程中**从网络下载到本机的全部内容**：是什么、从哪里来、装在哪里、占多大、为什么需要、谁批准的。
GLOBAL.md 规定不安装任何新内容；确实需要时先问 Barry，批准后在这里登记。

维护方式：每次下载或安装之后立刻加一行；卸载后把该行移到“已移除”一节，不直接删除。

## 1. 记录范围

从 T05（2026-11-13）起的下载逐项登记。T05 之前的下载不在记录范围内（Barry 决定不补记）。

## 2. 逐项记录（T05 起）

安装位置都在项目根目录的 `.venv-main/lib/python3.11/site-packages/` 下，表中只写其中的目录名。
大小是安装后占用的磁盘空间（按各包的 `RECORD` 文件逐个统计），不是下载的压缩包大小。

| # | 时间 | 内容 | 版本 | 来源 | 安装位置 | 安装后大小 | 用途 | 任务 | 批准 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-11-13 22:41 | PyJWT | 2.15.1 | PyPI | `jwt/` | 约 261 KB | 签发和校验登录令牌 | T06 | 在“不安装”规则写入 GLOBAL.md 之前安装，未单独请示 |
| 2 | 2026-11-13 22:41 | argon2-cffi | 25.1.0 | PyPI | `argon2/` | 约 73 KB | 密码哈希（Argon2id） | T06 | 同上 |
| 3 | 2026-11-13 22:41 | argon2-cffi-bindings | 26.2.0 | PyPI | `_argon2_cffi_bindings/` | 约 79 KB | argon2-cffi 的依赖（Argon2 的 C 实现） | T06 | 同上，随 #2 自动安装 |
| 4 | 2026-11-13 22:41 | cffi | 2.1.1 | PyPI | `cffi/`、`_cffi_backend.cpython-311-darwin.so` | 约 1.04 MB | argon2-cffi-bindings 的依赖 | T06 | 同上，随 #2 自动安装 |
| 5 | 2026-11-13 22:41 | pycparser | 3.12 | PyPI | `pycparser/` | 约 558 KB | cffi 的依赖 | T06 | 同上，随 #2 自动安装 |
| 6 | 2026-11-13 23:01 | python-multipart | 0.0.33 | PyPI | `python_multipart/`、`multipart/` | 约 199 KB | 解析 `multipart/form-data` 上传 | T08 | Barry 于 2026-11-13 批准（`decisions.md` D19） |

合计：6 个包，安装后约 2.2 MB。

说明：

- #1、#2、#6 是直接依赖，版本锁定在 `backend/pyproject.toml`。#3–#5 是 pip 按依赖关系自动带进来的，没有单独锁定版本。
- pip 会把下载过的安装包另存一份在用户级缓存 `~/Library/Caches/pip/` 里，那一份的大小没有单独统计。
- T05、T07 没有下载任何内容。

## 3. 没有下载、但曾经考虑过的

| 内容 | 原因 | 结论 |
|---|---|---|
| PostgreSQL（或 pip 包 `pgserver`） | 本机没有 PostgreSQL，91 项集成测试跑不了 | 未安装。按 GLOBAL.md 的规则跳过这些测试，见 `docs/untested.md` |

## 4. 已移除

（空）
