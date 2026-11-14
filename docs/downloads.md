# 下载与安装记录

更新日期：2026-11-14（T11 完成后）

这里登记开发过程中**从网络下载到本机的全部内容**：是什么、从哪里来、装在哪里、占多大、为什么需要、谁批准的。
GLOBAL.md 规定不安装任何新内容；确实需要时先问 Barry，批准后在这里登记。

维护方式：每次下载或安装之后立刻加一行；卸载后把该行移到“已移除”一节，不直接删除。

## 1. 记录范围

从 T05（2026-11-13）起的下载逐项登记。T05 之前的下载不在记录范围内（Barry 决定不补记）。

## 2. 逐项记录（T05 起）

### 2.1 Python 包（main 环境）

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
| 7 | 2026-11-13 23:13 | PyMuPDF | 1.28.2 | PyPI | `pymupdf/`、`fitz/` | 约 58.1 MB（下载的安装包 23.9 MB） | PDF 解析（M5） | T09 | Barry 于 2026-11-13 批准，并选定 1.28.2 而不是 2.1（`decisions.md` D21） |
| 17 | 2026-11-14 13:27 | python-docx | 1.2.0 | PyPI | `docx/` | 约 2.3 MB | Word 解析（M5） | T11 | Barry 于 2026-11-14 批准（`decisions.md` D24） |
| 18 | 2026-11-14 13:27 | lxml | 6.1.3 | PyPI | `lxml/` | 约 19.1 MB（下载的安装包 8.6 MB） | python-docx 的依赖（XML 解析）；openpyxl 检测到它时也会使用 | T11 | 同上，随 #17 自动安装 |
| 19 | 2026-11-14 13:27 | openpyxl | 3.1.5 | PyPI | `openpyxl/` | 约 2.0 MB | Excel 解析（M5） | T11 | Barry 于 2026-11-14 批准（`decisions.md` D24） |
| 20 | 2026-11-14 13:27 | et-xmlfile | 2.0.0 | PyPI | `et_xmlfile/` | 约 92 KB | openpyxl 的依赖 | T11 | 同上，随 #19 自动安装 |

小计：11 个包，安装后约 83.8 MB。编号 8–16 是下面的 Node.js 和 npm 包。

说明：

- #1、#2、#6、#7、#17、#19 是直接依赖，版本锁定在 `backend/pyproject.toml`。#3–#5、#18、#20 是 pip 按依赖关系自动带进来的，没有单独锁定版本。python-docx 还依赖 typing_extensions，环境里已有 4.16.0，没有重新下载。
- pip 会把下载过的安装包另存一份在用户级缓存 `~/Library/Caches/pip/` 里，那一份的大小没有单独统计。
- T05、T07 没有下载任何内容。#7 没有带入任何附加依赖。

### 2.2 Node.js（T10）

| # | 时间 | 内容 | 版本 | 来源 | 安装位置 | 大小 | 用途 | 批准 |
|---|---|---|---|---|---|---|---|---|
| 8 | 2026-11-14 13:12 | Node.js（含 npm 11.20.0） | 26.13.1 LTS，darwin-arm64 | `https://nodejs.org/dist/v26.13.1/node-v26.13.1-darwin-arm64.tar.gz` | 项目根目录 `.tools/node/` | 下载 58.3 MB，解压后约 222 MB | 运行前端的构建、类型检查、测试和开发服务器 | Barry 于 2026-11-14 批准，并选定“装到项目内” |

- 下载的压缩包已用官方 `SHASUMS256.txt` 校验 SHA-256，一致。
- 没有安装到系统：不需要密码，不修改 `PATH` 和任何系统目录。删除 `.tools/node/` 即完全卸载。
- `.tools/` 已加入 `.gitignore`，不进版本库。换一台机器需要重新下载（或直接安装系统级的 Node.js）。

### 2.3 npm 包（T10）

2026-11-14 13:13 安装，来源是 npm 官方仓库 `registry.npmjs.org`，全部装在 `frontend/node_modules/`。
Barry 于 2026-11-14 批准。

直接依赖 8 个，版本锁定在 `frontend/package.json`：

| # | 包 | 版本 | 安装后大小 | 用途 |
|---|---|---|---|---|
| 9 | vue | 3.5.45 | 约 2.6 MB | 前端框架 |
| 10 | vue-router | 5.5.1 | 约 1.5 MB | 页面路由 |
| 11 | element-plus | 2.14.8 | 约 61 MB | 界面组件库 |
| 12 | vite | 8.3.8 | 约 2.4 MB | 开发服务器与构建 |
| 13 | @vitejs/plugin-vue | 6.0.11 | 约 88 KB | 让 Vite 处理 `.vue` 文件 |
| 14 | typescript | 6.0.3 | 约 25 MB | 类型检查 |
| 15 | vue-tsc | 3.3.14 | 约 844 KB | 对 `.vue` 文件做类型检查 |
| 16 | vitest | 5.1.0 | 约 3.0 MB | 前端单元测试 |

- 连同这 8 个包自动带入的间接依赖，`node_modules/` 里共 131 个包，合计约 183 MB。间接依赖的精确版本记录在 `frontend/package-lock.json`（已进版本库）。
- 间接依赖中体积较大的：`@rolldown/binding-darwin-arm64`（约 18 MB，Vite 的打包器）、`lightningcss-darwin-arm64`（约 9 MB）。
- typescript 先装了 7.0.2，发现 vue-tsc 3.3.14 不支持它（启动即报错），随即换成 6.0.3；7.0.2 已被替换掉，不再占用空间。
- npm 同样会在用户级缓存 `~/.npm/` 里保留一份安装包，大小没有单独统计。
- `frontend/node_modules/` 已在 `.gitignore` 中。

### 2.4 合计

T05 至 T11：Python 包约 84 MB，Node.js 约 222 MB，npm 包约 183 MB，共约 489 MB。

## 3. 没有下载、但曾经考虑过的

| 内容 | 原因 | 结论 |
|---|---|---|
| PostgreSQL（或 pip 包 `pgserver`） | 本机没有 PostgreSQL，91 项集成测试跑不了 | 未安装。按 GLOBAL.md 的规则跳过这些测试，见 `docs/untested.md` |

## 4. 已移除

（空）
