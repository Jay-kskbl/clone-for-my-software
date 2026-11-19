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

小计：11 个包，安装后约 83.8 MB。编号 8–16、21–23 是下面的 Node.js 和 npm 包，24–28 是 ocr 环境的包和 OCR 模型。

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

### 2.4 npm 包（T16）

2026-11-15 12:42 安装，来源是 npm 官方仓库 `registry.npmjs.org`，装在 `frontend/node_modules/`。
命令：`npm install --save-exact pdfjs-dist@6.5.438`（在 `frontend/` 目录，使用 `.tools/node/` 里的 npm）。

| # | 包 | 版本 | 安装后大小 | 用途 | 批准 |
|---|---|---|---|---|---|
| 21 | pdfjs-dist | 6.5.438 | 约 37.5 MB | 在页面里渲染 PDF 并跳到命中页（附录 A16，T16） | Barry 于 2026-11-15 批准：先在编写会话里选了“同意安装 6.5.438 (Recommended)”，又在本会话里选了“同意，现在安装 (Recommended)” |
| 22 | @napi-rs/canvas | 1.1.1 | 约 200 KB | pdfjs-dist 的可选依赖（`optionalDependencies`），只在 Node.js 里渲染 PDF 时用；浏览器里不用（pdfjs-dist 的 `browser` 字段把 `canvas` 设为 `false`） | 随 #21 自动安装；Barry 于 2026-11-15 决定保留 |
| 23 | @napi-rs/canvas-darwin-arm64 | 1.1.1 | 约 27.9 MB | #22 的 macOS arm64 原生二进制（`skia.darwin-arm64.node`） | 随 #21 自动安装；Barry 于 2026-11-15 决定保留 |

- `package.json` 的 `dependencies` 里锁定为 `"pdfjs-dist": "6.5.438"`（不带 `^`）。#22、#23 的精确版本只记录在 `package-lock.json`。
- `package-lock.json` 里还登记了 @napi-rs/canvas 其他 10 个平台的二进制包（Linux、Windows、Android），只在对应平台上安装，本机没有下载。
- #22、#23 没有安装脚本，安装时没有执行任何代码。npm 提示 fsevents 2.3.3（T10 已装）有安装脚本未被允许，与本次安装无关。
- 本次安装共占用约 65.4 MB，其中约 27.9 MB 是浏览器里用不到的 #23。#22、#23 安装前没有预料到；Barry 于 2026-11-15 决定保留（浏览器用不到，不进打包结果）。

### 2.5 Python 包（ocr 环境，T17）

2026-11-15 13:06 安装，来源 PyPI，装在 `env_check/.venv-ocr/lib/python3.11/site-packages/`（T00 环境实测时建的 ocr 环境，T17 起 OCR Worker 也用它）。
命令：`env_check/.venv-ocr/bin/pip install "psycopg[binary]==3.3.9" "PyMuPDF==1.28.2"`。版本与 main 环境相同。

| # | 时间 | 内容 | 版本 | 安装位置 | 安装后大小 | 用途 | 批准 |
|---|---|---|---|---|---|---|---|
| 24 | 2026-11-15 13:06 | PyMuPDF | 1.28.2 | `pymupdf/`、`fitz/` | 约 58.1 MB | OCR Worker 把 PDF 页渲染成图片 | Barry 于 2026-11-15 批准：在编写会话里批准 T17 计划（“批准，开始写”），又在本会话里选“同意，现在安装 (Recommended)” |
| 25 | 2026-11-15 13:06 | psycopg | 3.3.9 | `psycopg/` | 约 1.8 MB | OCR Worker 访问 PostgreSQL（任务队列、写 OCR 结果） | 同上 |
| 26 | 2026-11-15 13:06 | psycopg-binary | 3.3.9 | `psycopg_binary/` | 约 9.7 MB | psycopg 的二进制实现（`[binary]` 附加项） | 同上，随 #25 安装 |

- 大小按各包 `RECORD` 文件逐个统计。psycopg 依赖的 typing-extensions 环境里已有 4.16.0，没有重新下载。除这三个包外没有带入其他包（安装前后 `pip freeze` 比对）。
- 项目的 shared 包将以开发模式（`pip install -e`）装进同一环境，不从网络下载代码；它的依赖都已在环境里。装好后在这里补记。

**OCR 模型（本地复制，没有下载）**

T17 不再从网络下载模型。下面两个目录是 2026-11-13 T00 环境实测时，PaddleOCR 第一次运行自动从 Hugging Face 下载到 `~/.paddlex/official_models/` 的（当时没有在本文件登记，这里补记）。2026-11-15 由本会话复制到项目的 `models/ocr/`。`models/` 已在 `.gitignore` 中，不进版本库。

| # | 内容 | 来源 | 位置 | 大小 | `inference.pdiparams` 的 sha256 | 用途 |
|---|---|---|---|---|---|---|
| 27 | PP-OCRv5_mobile_det（文本检测，Apache-2.0） | Hugging Face，经 `~/.paddlex/official_models/` 复制 | `models/ocr/PP-OCRv5_mobile_det/` | 约 4.8 MB | `afa1820cb16c1fd0dad589d0f8b389139061c1ef6d68019685fd07be997dda5b` | OCR Worker（T17） |
| 28 | PP-OCRv5_mobile_rec（文本识别，Apache-2.0） | 同上 | `models/ocr/PP-OCRv5_mobile_rec/` | 约 16 MB | `2460da90875937c94db97eba74ae3d9e5d4c4c57c42f1f41531c09a26bcc771a` | 同上 |

- `~/.paddlex/official_models/` 里还有 T00 下载的 PP-OCRv6_medium_det（约 59 MB）、PP-OCRv6_medium_rec（约 73 MB），项目不用，没有复制。

### 2.6 Python 包（clip 环境，T20）

2026-11-17 安装，来源 PyPI，装在 `env_check/.venv-clip/lib/python3.11/site-packages/`（T00 环境实测时建的 clip 环境，T20 起 CLIP 服务也用它）。
命令：`env_check/.venv-clip/bin/pip install fastapi==0.162.5 uvicorn==0.54.0 pydantic==2.14.3`。三个直接依赖的版本与 main 环境相同。
批准：Barry 于 2026-11-17 在本会话选“装 FastAPI (Recommended)”。

| # | 内容 | 版本 | 安装位置 | 安装后大小 | 用途 |
|---|---|---|---|---|---|
| 29 | fastapi | 0.162.5 | `fastapi/` | 约 1.8 MB | CLIP 服务的 HTTP 接口 |
| 30 | uvicorn | 0.54.0 | `uvicorn/` | 约 0.9 MB | ASGI 服务器 |
| 31 | pydantic | 2.14.3 | `pydantic/` | 约 4.2 MB | 配置校验、请求与响应结构 |
| 32 | pydantic-core | 2.50.4 | `pydantic_core/` | 约 4.7 MB | pydantic 的依赖 |
| 33 | starlette | 1.10.0 | `starlette/` | 约 0.8 MB | fastapi 的依赖 |
| 34 | opentelemetry-api | 1.45.2 | `opentelemetry/` | 约 0.5 MB | 随上面的包自动带入，本项目不直接使用 |
| 35 | annotated-types | 0.8.0 | `annotated_types/` | 约 60 KB | pydantic 的依赖 |
| 36 | annotated-doc | 0.0.6 | `annotated_doc/` | 约 16 KB | fastapi 的依赖 |
| 37 | typing-inspection | 0.4.5 | `typing_inspection/` | 约 100 KB | pydantic 的依赖 |

- 共 9 个包，约 13 MB（按 `du` 统计各包目录）。征求同意时说的是“约 8 个包、十几 MB”，实际多出 #34 opentelemetry-api，安装前没有预料到。
- anyio、h11、click、idna、typing_extensions 环境里已有，没有重新下载。安装后重新生成了 `env_check/results/freeze-clip.txt`。
- 没有装 pytest、httpx：接口测试在 main 环境里跑，真实模型测试用标准库 unittest 和 urllib。

**CLIP 模型（本地复制，没有下载）**

| # | 内容 | 来源 | 位置 | 大小 | sha256 | 用途 |
|---|---|---|---|---|---|---|
| 38 | Chinese-CLIP ViT-B-16 权重 `clip_cn_vit-b-16.pt` | 2026-11-13 T00 环境实测时由 cn_clip 自动下载到 `env_check/models/`（当时没有在本文件登记，这里补记）；2026-11-17 复制到项目的 `models/clip/` | `models/clip/clip_cn_vit-b-16.pt` | 约 718 MB | `5997ef32c50de18f3ac06eb5d746c324a639053c3bed8f2986f97ebb22b2ecde` | CLIP 服务（T20） |

- `env_check/models/` 里的原文件已于 2026-11-19 删除（Barry 批准；删除前核对两份 sha256 一致），只保留 `models/clip/` 这一份。注意：重跑 `env_check/03_check_clip.py` 会让 cn_clip 重新联网下载权重，需先征得 Barry 同意。

### 2.7 合计

T05 至 T17：Python 包约 154 MB（main 环境约 84 MB，ocr 环境 T17 新增约 70 MB），Node.js 约 222 MB，npm 包约 248 MB（T10 约 183 MB，T16 约 65 MB），共约 624 MB；另有从本机缓存复制的 OCR 模型约 21 MB。T20 新增：clip 环境 Python 包约 13 MB，从本机复制的 CLIP 权重约 718 MB。

## 3. 没有下载、但曾经考虑过的

| 内容 | 原因 | 结论 |
|---|---|---|
| PostgreSQL（或 pip 包 `pgserver`） | 本机没有 PostgreSQL，91 项集成测试跑不了 | 未安装。按 GLOBAL.md 的规则跳过这些测试，见 `docs/untested.md` |

## 4. 已移除

（空）
