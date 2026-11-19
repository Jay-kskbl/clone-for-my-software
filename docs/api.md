# API 接口清单（T04）

这是接口的**设计稿**：除 `GET /health` 已在 T01 实现外，其余接口都还没有实现。
实现时如果需要偏离本文档，先改这里并说明原因，再写代码；前端（M14）只依赖本文档。

## 1. 通用约定

| 项目 | 约定 |
|---|---|
| 路径前缀 | 业务接口统一以 `/api` 开头；`/health` 例外，不带前缀 |
| 数据格式 | 请求和响应都是 JSON（UTF-8）；上传用 `multipart/form-data`；下载返回文件流 |
| 认证 | 登录后拿到 JWT，之后每个请求带 `Authorization: Bearer <token>` |
| 时间 | ISO 8601，带时区，例如 `2026-11-13T04:38:46Z` |
| ID | `document_id`、`user_id`、`task_id` 都是 UUID 字符串 |
| 分页 | 请求参数 `page`（从 1 开始，默认 1）、`page_size`（默认 20，最大 100）；响应带 `items`、`total`、`page`、`page_size` |

### 1.1 权限级别

| 标记 | 含义 |
|---|---|
| 公开 | 不需要登录 |
| 登录 | 任何已登录用户 |
| 可访问 | 文档的 owner、被共享者或管理员（M1 的 `can_access`） |
| owner | 文档的 owner 或管理员。被共享者只有只读和检索权限，不能删除、共享、改标签 |
| 管理员 | 仅管理员 |

访问一个存在但无权访问的文档返回 403；文档不存在或已被删除返回 404。

### 1.2 错误响应

所有错误使用同一种结构：

```json
{ "error": { "code": "FILE_TOO_LARGE", "message": "文件超过大小上限 50 MB" } }
```

`code` 给程序判断，`message` 给人看。`message` 中不包含密码、令牌、服务器路径或文件内容。

| HTTP 状态 | code | 含义 |
|---|---|---|
| 401 | `UNAUTHENTICATED` | 未登录、令牌无效或已过期 |
| 401 | `INVALID_CREDENTIALS` | 用户名或密码错误（不区分是哪一个错） |
| 403 | `FORBIDDEN` | 已登录但无权执行该操作 |
| 404 | `NOT_FOUND` | 资源不存在，或已被删除 |
| 409 | `USERNAME_TAKEN` | 注册时用户名已存在 |
| 409 | `TASK_NOT_RETRYABLE` | 任务不是 `failed` 状态，不能重试 |
| 413 | `FILE_TOO_LARGE` | 上传文件超过大小上限 |
| 415 | `UNSUPPORTED_FILE_TYPE` | 文件真实类型不在允许范围内（按魔数判断，与扩展名无关） |
| 422 | `VALIDATION_ERROR` | 请求参数不合法（含文件名过长、空文件） |
| 500 | `INTERNAL_ERROR` | 未预期的服务器错误，详情只写日志 |
| 503 | `SEARCH_UNAVAILABLE` | 检索引擎不可用。**不是**“没有搜到”——没有结果时返回 200 和空列表 |
| 503 | `DATABASE_UNAVAILABLE` | 数据库不可用 |

上传限制都来自配置（`.env`），默认值如下：

| 限制 | 配置项 | 默认值 | 超出时 |
|---|---|---|---|
| 单个文件大小 | `UPLOAD_MAX_BYTES` | 50 MB | 413 `FILE_TOO_LARGE` |
| 允许的类型 | `UPLOAD_ALLOWED_TYPES` | pdf、docx、xlsx、png、jpg | 415 `UNSUPPORTED_FILE_TYPE` |
| 文件名长度 | `UPLOAD_MAX_FILENAME_CHARS` | 255 个字符 | 422 `VALIDATION_ERROR` |
| 单个标签长度 | —（与数据库列一致） | 64 个字符 | 422 `VALIDATION_ERROR` |
| 每个文档的标签数 | — | 20 个 | 422 `VALIDATION_ERROR` |

类型按文件内容识别，与扩展名和浏览器上报的类型无关。旧版 `.doc`、`.xls` 不支持。

## 2. 接口总览

| 方法 | 路径 | 权限 | 说明 | 任务 |
|---|---|---|---|---|
| GET | `/health` | 公开 | 各依赖服务的状态 | T01 ✅ |
| POST | `/api/auth/register` | 公开 | 注册普通用户 | T06（已实现） |
| POST | `/api/auth/login` | 公开 | 登录，获取令牌 | T06（已实现） |
| GET | `/api/auth/me` | 登录 | 当前用户信息 | T06（已实现） |
| POST | `/api/documents` | 登录 | 上传文件 | T08（已实现） |
| GET | `/api/documents` | 登录 | 列出可访问的文档 | T08（已实现） |
| GET | `/api/documents/{id}` | 可访问 | 文档详情 | T08（已实现） |
| GET | `/api/documents/{id}/download` | 可访问 | 下载原文件 | T08（已实现） |
| GET | `/api/documents/{id}/text` | 可访问 | 抽取出的文本（Word / Excel 预览用） | T16（已实现） |
| DELETE | `/api/documents/{id}` | owner | 删除（软删除，立即不可见） | T08（已实现） |
| GET | `/api/documents/{id}/shares` | owner | 查看共享给了谁 | T08（已实现） |
| POST | `/api/documents/{id}/shares` | owner | 共享给指定用户 | T08（已实现） |
| DELETE | `/api/documents/{id}/shares/{user_id}` | owner | 取消共享 | T08（已实现） |
| PUT | `/api/documents/{id}/tags` | owner | 设置文档的标签（整体替换） | T08（已实现） |
| GET | `/api/tags` | 登录 | 当前用户可访问文档上用到的标签 | T08（已实现） |
| GET | `/api/documents/{id}/tasks` | 可访问 | 该文档的处理任务及状态 | T08（已实现） |
| POST | `/api/tasks/{id}/retry` | owner | 重试一个失败的任务 | T08（已实现） |
| GET | `/api/tasks` | 管理员 | 全部任务，可按状态、类型过滤 | T08（已实现） |
| POST | `/api/search` | 登录 | 检索 | T15、T22 |

## 3. 健康检查

### GET /health（已实现）

依赖不可用时也返回 200，在响应体里如实报告。

```json
{
  "status": "degraded",
  "database":     { "status": "ok",          "detail": null },
  "opensearch":   { "status": "ok",          "detail": "集群状态为 yellow" },
  "clip_service": { "status": "unavailable", "detail": "ConnectError" }
}
```

`status`：三项全部正常为 `ok`，否则为 `degraded`。每一项为 `ok` 或 `unavailable`。

`detail`（T24b 起）：不可用时只给异常类型，例如 `OperationalError`、`ConnectError`；对方返回 HTTP 错误时为 `HTTPStatusError: HTTP 503` 这种形式。这是公开接口，所以不返回内部主机名、端口和数据库用户名，完整原因只写在后端日志里（`健康检查：<组件> 不可用：<类型>: <消息>`）。OpenSearch 正常时仍返回集群状态（`集群状态为 green/yellow`），red 时为 `集群状态为 red`。

## 4. 认证

### 4.1 数据结构

**User**

```json
{ "id": "…uuid…", "username": "barry", "role": "user", "created_at": "2026-11-13T04:38:46Z" }
```

`role` 为 `user` 或 `admin`。任何接口都不返回密码哈希。

### 4.2 POST /api/auth/register

注册一个普通用户。管理员不能通过接口注册，由命令行工具创建（T06）。

- 请求：`{ "username": "barry", "password": "…" }`
- 响应 201：`User`
- 错误：409 `USERNAME_TAKEN`；422 `VALIDATION_ERROR`（用户名或密码不符合长度、字符要求）
- 用户名：3–32 个字符，只允许英文字母、数字、下划线 `_`、点 `.`、连字符 `-`，区分大小写
- 密码：8–128 个字符
- 请求中出现其他字段（例如 `role`）返回 422，不会被忽略

### 4.3 POST /api/auth/login

- 请求：`{ "username": "barry", "password": "…" }`
- 响应 200：`{ "access_token": "…", "token_type": "bearer", "expires_in": 3600 }`（`expires_in` 单位为秒，值来自配置）
- 错误：401 `INVALID_CREDENTIALS`
- 令牌中只包含用户 ID 和过期时间。角色每次请求都从数据库读取，账号被删除后其令牌立即失效
- 没有登出和刷新接口：令牌到期后重新登录

### 4.4 GET /api/auth/me

- 响应 200：`User`
- 错误：401 `UNAUTHENTICATED`

## 5. 文档

### 5.1 数据结构

**Document**

```json
{
  "id": "…uuid…",
  "filename": "年度报告.pdf",
  "mime_type": "application/pdf",
  "size_bytes": 1048576,
  "status": "succeeded",
  "tags": ["财务", "2026"],
  "owner": { "id": "…uuid…", "username": "barry" },
  "access": "owner",
  "created_at": "2026-11-13T04:38:46Z",
  "updated_at": "2026-11-13T04:39:10Z"
}
```

| 字段 | 说明 |
|---|---|
| `status` | 处理状态：`pending` 等待处理、`processing` 处理中、`succeeded` 成功、`failed` 失败 |
| `access` | 当前用户与该文档的关系：`owner`、`shared`（被共享）、`admin`（以管理员身份可见） |

不返回 `storage_key`、`sha256` 等服务器内部信息。已删除的文档不出现在任何接口中。

**Task**

```json
{
  "id": "…uuid…",
  "document_id": "…uuid…",
  "task_type": "parse",
  "status": "failed",
  "attempts": 3,
  "max_attempts": 3,
  "error": "解析超时（60 秒）",
  "created_at": "…", "started_at": "…", "finished_at": "…"
}
```

### 5.2 POST /api/documents

上传一个文件。解析在后台进行，本接口只负责保存文件并创建解析任务。

- 请求：`multipart/form-data`
  - `file`：文件本体（必填）
  - `tags`：标签，可重复多次（可选）
- 响应 201：`Document`（`status` 为 `pending`）
- 错误：413 `FILE_TOO_LARGE`；415 `UNSUPPORTED_FILE_TYPE`；422 `VALIDATION_ERROR`

上传失败时不会留下文件或数据库记录。

- 文件名中的目录部分和控制字符会被去掉；文件名只用于展示和检索，不参与存储路径
- 标签会去掉首尾空白并去重
- `Content-Length` 明显超过上限的请求在读取请求体之前就被拒绝（413）

### 5.3 GET /api/documents

列出当前用户可访问的文档：自己上传的、别人共享的；管理员可见全部。

- 查询参数：`page`、`page_size`、`status`（可选）、`tag`（可选）、`scope`（可选：`mine` 只看自己上传的，`shared` 只看被共享的；不传为全部）
- 响应 200：`{ "items": [Document, …], "total": 57, "page": 1, "page_size": 20 }`
- 排序：按上传时间从新到旧

### 5.4 GET /api/documents/{id}

- 响应 200：`Document`
- 错误：403 `FORBIDDEN`；404 `NOT_FOUND`

### 5.5 GET /api/documents/{id}/download

返回原文件的字节流。PDF 的在线预览（pdf.js）和图片的显示也使用这个接口。

- 响应 200：文件流；`Content-Type` 为识别出的真实类型；`Content-Disposition` 带原始文件名（`attachment`；中文文件名用 `filename*=UTF-8''…` 携带）
- 错误：403、404

### 5.6 GET /api/documents/{id}/text

返回从文档中抽取的文本片段，用于 Word、Excel 的文本预览，以及从检索结果跳转到命中位置。

- 查询参数：
  - `page`、`page_size`：通用分页，默认 1 和 20，`page_size` 最大 100（前端预览页用 50）
  - `source_type`（可选）：`body` 或 `ocr`
  - `chunk_id`（可选）：指定后忽略 `page`，直接返回这个片段所在的那一页（从检索结果跳转时用）。片段不属于文档当前版本时（文档被重新解析过）返回第 1 页；格式不正确或属于别的文档时返回 422
- 只返回文档当前解析版本（`parse_version`）的片段，按 `seq` 排序；数据来自数据库，检索服务不可用时也能使用
- 响应 200：

```json
{
  "items": [
    {
      "chunk_id": "…uuid…:c1-m500-o50-1a2b3c4d5e6f:0",
      "seq": 0,
      "source_type": "body",
      "text": "……",
      "locator": { "type": "docx_para", "para_index": 0 }
    }
  ],
  "total": 42, "page": 1, "page_size": 20
}
```

- `locator` 的四种形态见 `shared/contracts/locators.py`：`pdf_page`、`docx_para`、`xlsx_range`、`image`
- 文档尚未解析成功时返回空列表，前端结合 `Document.status` 给出提示
- 错误：403、404；422（`chunk_id` 不合法、`source_type` 不合法、分页参数越界）

### 5.7 DELETE /api/documents/{id}

软删除：返回后该文档立即对列表、下载、检索都不可见；索引和文件由后台清理任务删除。

- 响应 204，无内容
- 错误：403（被共享者不能删除）；404

### 5.8 共享

被共享者获得只读和检索权限。不做部门、组织、多级权限（附录 A11）。

**GET /api/documents/{id}/shares**

- 响应 200：`{ "items": [ { "user": { "id": "…", "username": "alice" }, "created_at": "…" } ] }`

**POST /api/documents/{id}/shares**

- 请求：`{ "username": "alice" }`（按用户名共享，系统不提供用户列表接口）
- 响应 201：`{ "user": { "id": "…", "username": "alice" }, "created_at": "…" }`
- 重复共享给同一用户返回 200 和已有记录，不报错
- 错误：404 `NOT_FOUND`（文档或用户不存在）；422（共享给自己）

**DELETE /api/documents/{id}/shares/{user_id}**

- 响应 204。取消后对方立即无法访问和检索该文档
- 错误：404（没有这条共享记录）

### 5.9 标签

**PUT /api/documents/{id}/tags**

用给出的列表整体替换该文档的标签；不存在的标签自动创建。

- 请求：`{ "tags": ["财务", "2026"] }`（传空列表即清空）
- 响应 200：`Document`
- 保存后会尽力把文件名和新标签同步到检索索引 `doc_meta`。检索服务不可用时标签照常保存、接口照常返回 200，索引暂时是旧的（由重新解析或一致性检查补上）

**GET /api/tags**

- 响应 200：`{ "items": ["2026", "财务"] }`（只包含当前用户可访问的文档上的标签）

## 6. 任务

### 6.1 GET /api/documents/{id}/tasks

- 响应 200：`{ "items": [Task, …] }`，按创建时间从新到旧
- 错误：403、404

### 6.2 POST /api/tasks/{id}/retry

把一个 `failed` 的任务重新放回队列，尝试次数清零。

- 响应 200：`Task`（`status` 为 `pending`）
- 错误：403；404；409 `TASK_NOT_RETRYABLE`
- 被共享者可以查看任务，但不能重试（403）
- 文档已被删除时，其任务（此时只有清理任务有意义）只有管理员可以重试；其他人得到 404
- 重试的是 parse 任务、且文档状态为 `failed` 时，文档状态同时改回 `pending`；其他类型的任务不改文档状态（`decisions.md` D27）

### 6.3 GET /api/tasks

- 权限：管理员
- 查询参数：`page`、`page_size`、`status`（可选）、`task_type`（可选）
- 响应 200：`{ "items": [Task, …], "total": …, "page": …, "page_size": … }`

## 7. 检索

### 7.1 POST /api/search

用 POST 是因为请求里带有通道开关等结构化参数。

**请求**

```json
{
  "query": "去年的差旅报销标准",
  "top_k": 20,
  "channels": { "meta": true, "text": true, "image": true },
  "source_types": ["body", "ocr"]
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `query` | 是 | 查询文本。去掉首尾空白后不能为空，不超过 `SEARCH_MAX_QUERY_CHARS` 个字符（默认 256） |
| `top_k` | 否 | 返回的文件数，1 到 `SEARCH_MAX_TOP_K`（默认 100）；不传为 `SEARCH_DEFAULT_TOP_K`（默认 20） |
| `channels` | 否 | 通道开关。`meta` 文件名与标签，`text` 正文与 OCR 文字，`image` CLIP 图像检索。不传或某一项为 `null` 时使用配置中的默认值（默认 `meta`、`text` 开，`image` 关） |
| `source_types` | 否 | `text` 通道检索哪些来源的片段：`body` 正文、`ocr` OCR 文字。不传为两者都查 |

对照实验只通过这些开关切换：B0 只开 `meta`；B1 只开 `text` 且 `source_types=["body"]`；
B2 只开 `text` 且两种来源都查；B3 三个通道全开。

请求体里出现未定义的字段（包括 `channels` 里的未知通道）、`source_types` 含未知来源，都返回 422。

**图像通道（T22，见 `decisions.md` D36）**：后端调用 CLIP 服务（§9.2）把查询文本编码成向量，再在 `image_vectors` 索引里做精确向量检索（只比较同一模型生成的向量，普通用户带可访问文档集合作为前置过滤）。它与文本类通道并行执行。默认关闭（`SEARCH_CHANNEL_IMAGE_ENABLED=false`），请求里 `channels.image=true` 时开启。

- 编码查询的超时为 `SEARCH_IMAGE_TIMEOUT_SECONDS`（默认 3 秒）。
- **降级**：CLIP 服务超时、连不上、拒绝请求、应答不对，模型向量维度与向量索引不一致，或向量索引查询出错时，仍返回 200，`channels` 中 `image` 为 `unavailable` 并在 `detail` 写明原因（不含服务地址），其余通道的结果照常返回。只开图像通道且它不可用时，返回 200 和空列表。
- 向量索引还不存在（还没有任何图片编码过）时，先建好索引，`image` 为 `ok`、没有结果。
- 证据：同一文件既被 `text` 又被 `image` 命中时，`evidence` 用文本片段；只被 `image` 命中时，`evidence` 为图片：`image_id` 非空，`locator` 为 `{"type": "image", "image_id": …}`。

融合方式为 RRF（k 与每通道截断深度来自配置，见 `decisions.md` D28）；`hits[].channels[].rank` 是该通道内的文件级名次。

**响应 200**

```json
{
  "hits": [
    {
      "document": { "…": "Document 结构，见 5.1" },
      "score": 0.0325,
      "channels": [
        { "channel": "text",  "rank": 1, "score": 12.5 },
        { "channel": "image", "rank": 4, "score": 0.31 }
      ],
      "evidence": {
        "chunk_id": "…uuid…:c1-m500-o50-1a2b3c4d5e6f:4",
        "image_id": null,
        "snippet": "……差旅<em>报销标准</em>按……",
        "source_type": "body",
        "locator": { "type": "pdf_page", "page": 12 }
      }
    }
  ],
  "channels": [
    { "channel": "meta",  "status": "ok",          "took_ms": 8,   "detail": null },
    { "channel": "text",  "status": "ok",          "took_ms": 21,  "detail": null },
    { "channel": "image", "status": "unavailable", "took_ms": 500, "detail": "模型服务超时" }
  ],
  "took_ms": 540
}
```

| 字段 | 说明 |
|---|---|
| `hits` | 文件级结果，同一文件只出现一次，按 `score` 从高到低 |
| `hits[].score` | 融合后的最终分数 |
| `hits[].channels` | 该文件在各通道内的原始排名和原始分数（只列出命中它的通道）。不同通道的分数不能直接比较 |
| `hits[].evidence` | 命中证据：最佳片段或图片，及其来源定位。`chunk_id` 与 `image_id` 恰有一个非空；只被文件名通道命中时整个字段为 `null` |
| `channels` | 顶层的通道状态，每个通道一项 |
| `channels[].status` | `ok` 正常执行；`disabled` 被请求或配置关闭；`unavailable` 本应执行但没有执行成功。200 响应里只有图像通道会是这个状态（降级，见上文）；文本类通道失败时整次检索返回 503 |
| `hits[].evidence.snippet` | 高亮摘要。原文已做 HTML 转义，只有命中词外的 `<em>…</em>` 是标签 |

`hits[]` 除 `document` 外的部分就是 `shared/contracts/search.py` 中的 `SearchHit`。

**没有结果与发生故障的区分**

| 情况 | 响应 |
|---|---|
| 检索正常，没有匹配的文件 | 200，`hits` 为空列表 |
| 图像通道不可用（CLIP 服务超时、未启动、出错，或向量索引出错），文本通道正常 | 200，结果来自文本通道，`channels` 中 `image` 为 `unavailable`，`detail` 写明原因 |
| 只开图像通道，且它不可用 | 200，`hits` 为空列表，`image` 为 `unavailable`（据此与“没有匹配”区分） |
| OpenSearch 不可用，或任何一个文本类通道（`meta`、`text`）出错 | 503 `SEARCH_UNAVAILABLE`，不返回另一路的部分结果 |

**保证**：返回前用数据库校验每一个候选文件，只保留未删除且当前用户有权访问的。
所以删除文件、取消共享之后，下一次检索立即生效（附录 A10）。每次检索都写一条检索日志。

- 错误：401；422 `VALIDATION_ERROR`（`query` 为空或过长、`top_k` 超出范围、所有通道都被关闭、`source_types` 为空列表或含未知值、出现未定义字段）；503 `SEARCH_UNAVAILABLE`
- 请求校验失败（422）不写检索日志；检索服务故障（503）也写一条

## 8. 不提供的接口

以下内容明确不在范围内（GLOBAL §5、附录 A15–A17），列在这里是为了避免实现时顺手加上：

- 用户列表、用户管理、修改角色的接口
- 文档替换或版本接口（替换文件即上传新文档、删除旧文档）
- Word、Excel 的原样排版预览
- 问答、摘要、推荐类接口

## 9. CLIP 模型服务的接口（内部，T20 已实现）

由 `services/clip_service`（clip 环境）提供，默认监听 `http://127.0.0.1:8001`，只给后端和 Worker 调用，**没有鉴权，不对浏览器开放**。前面各节的 `/api/...` 接口都不在这个服务上。规则见 `decisions.md` D33。

三个接口的成功响应都带 `model_name`、`model_version`、`dim`（GLOBAL §4.3）。向量已做 L2 归一化，两个向量的点积就是余弦相似度。错误响应的格式与 §1.2 相同。

### 9.1 GET /health

模型在服务开始监听之前就已加载，所以能连上就是可用。后端的 `/health`（§3）只看这里是否返回 200。

```json
{ "status": "ok", "model_name": "ViT-B-16", "model_version": "cn_clip-1.6.0-5997ef32c50d", "dim": 512, "device": "cpu" }
```

`model_version` = cn_clip 版本 + 权重文件 sha256 的前 12 位。

### 9.2 POST /encode/text

请求（`application/json`，不允许其他字段）：

```json
{ "texts": ["会议室里的白板照片"] }
```

响应 200，`vectors` 与 `texts` 一一对应：

```json
{ "model_name": "ViT-B-16", "model_version": "cn_clip-1.6.0-5997ef32c50d", "dim": 512, "vectors": [[0.068, 0.014, "..."]] }
```

- 限制：1 至 `CLIP_MAX_TEXTS`（默认 32）条；每条不能为空白，不超过 `CLIP_MAX_TEXT_CHARS`（默认 1000）个字符。模型只用前 52 个 token，更长的部分被截断，不报错。
- 错误：422 `VALIDATION_ERROR`

### 9.3 POST /encode/image

请求体就是一张图片的字节（不是 multipart，也不是 JSON），一次一张。只接受 PNG 和 JPEG，按内容判断，不看 `Content-Type`。

响应 200：

```json
{ "model_name": "ViT-B-16", "model_version": "cn_clip-1.6.0-5997ef32c50d", "dim": 512, "vector": [0.021, -0.043, "..."] }
```

- 错误：
  - 413 `IMAGE_TOO_LARGE`：字节数超过 `CLIP_MAX_IMAGE_BYTES`（默认 50 MB），或像素数超过 `CLIP_MAX_IMAGE_PIXELS`（默认 1 亿）
  - 422 `INVALID_IMAGE`：请求体为空、不是 PNG 或 JPEG、文件截断或损坏
  - 500 `ENCODE_FAILED`：推理过程出错（例如内存不足）
- 超时由调用方设置（附录 A5）。服务一次只算一个请求，其余排队。
