# 实验数据与运行说明（M12）

本目录存放评测数据集、相关性标注和实验配置。代码在 `backend/app/modules/experiments/`，规则见 `docs/decisions.md` D32；B3 与消融配置见 D38。

## 1. 目录结构

```
experiments/
├── README.md                 本文件
├── configs/                  实验配置：B0–B3 与消融，共 10 个（见第 5 节前的“实验配置”）
├── datasets/
│   ├── manifest.csv          文件清单（进 Git）
│   ├── files/                原文件（不进 Git）
│   └── document_map.csv      导入时自动生成（不进 Git）
├── queries.tsv               查询集（进 Git）
├── qrels/                    相关性标注，可分多个 .tsv 文件（进 Git）
└── runs/                     每次运行的结果（不进 Git）
```

## 2. 三个文件怎么填

三个文件的第一行都是表头，不要改。`manifest.csv` 用逗号分隔，`queries.tsv` 和 `qrels/*.tsv` 用制表符分隔。文件都用 UTF-8 编码保存。

### datasets/manifest.csv：文件清单

| 列 | 含义 |
|---|---|
| `file_id` | 你给这个文件起的编号，例如 `f001`，不能重复 |
| `path` | 原文件相对 `datasets/files/` 的路径，例如 `pdf/年度报告.pdf` |
| `type` | `pdf`（有文本层的 PDF）、`scanned_pdf`（扫描件）、`docx`、`xlsx`、`image` 五选一 |
| `source` | 文件来源，必填（例如“学院公开通知”“自己拍摄”），论文要说明数据集的来源 |
| `notes` | 备注，可以空着 |

### queries.tsv：查询集

| 列 | 含义 |
|---|---|
| `query_id` | 查询编号，例如 `q001`，不能重复 |
| `type` | `text`（文字型：要找的内容以文字形式出现在正文或 OCR 文字里）、`visual`（视觉型：要找的图片里没有可检索的文字）、`mixed`（混合型）三选一（附录 A18） |
| `text` | 查询文本，就是在检索框里输入的那句话 |

### qrels/*.tsv：相关性标注

| 列 | 含义 |
|---|---|
| `query_id` | 必须在 `queries.tsv` 里 |
| `file_id` | 必须在 `manifest.csv` 里 |
| `grade` | 相关等级，0 到 3 的整数 |

等级的含义（**建议，待 Barry 最终确认**）：

| grade | 含义 |
|---|---|
| 0 | 不相关（可以不写；没写的文件都按 0 处理） |
| 1 | 部分相关：提到了，但不是要找的主要内容 |
| 2 | 相关：能回答这个查询 |
| 3 | 高度相关：就是要找的那个文件 |

- 标注可以分多个文件逐周补充，例如 `qrels/week01.tsv`、`qrels/week02.tsv`，程序会读入 `qrels/` 下所有 `.tsv`。
- 同一对（查询，文件）在多个文件里出现时，等级必须相同，否则检查会报矛盾。
- 没有任何相关文件的查询可以存在，但它不参与任何指标的平均，会单独列出。

### 为什么用 file_id，不用系统里的文档编号

系统里的文档编号（document_id）要上传之后才生成，重新导入一次就全部改变。`file_id` 由你自己起，标注可以长期保存、反复使用。导入时程序把两者的对应关系写进 `datasets/document_map.csv`。

## 3. 原文件放在哪里

把原文件放进 `datasets/files/`，可以建子目录。这个目录不进 Git：原文件可能很大，也可能有版权或隐私问题。`manifest.csv` 里的 `path` 要和实际位置一致。

## 4. 操作顺序

在 `backend/` 目录、main 环境下执行（需要完整的 `.env`，包括 `JWT_SECRET`）：

1. **检查格式**：`python -m app.modules.experiments validate`
   只读取文件、不连数据库。会列出每个问题出在哪个文件第几行，并输出文件数、查询数、标注数的统计。
2. **导入**：`python -m app.modules.experiments import`
   把清单里的文件上传到系统，生成 `document_map.csv`。第一次运行时会自动创建实验账号 `experiment`。已导入且内容没变的文件会跳过。
3. **处理**：启动通用 Worker 和 OCR Worker，等全部文件处理完成（命令见 `CLAUDE.md`）。
4. **运行**：`python -m app.modules.experiments run --config ../experiments/configs/B1.json`
   可加 `--repeat 3` 重复运行，用来看结果的波动。

开了图像通道的配置（B3、B3-no-ocr、clip-only、B3-k10/k30/k100）还要先：

- 启动 CLIP 服务（命令见 `CLAUDE.md`）；
- 让通用 Worker 处理完全部 embed 任务（图片向量）。

运行前检查会拦下两种情况：CLIP 服务连不上；数据集里有图片还没有当前 CLIP 模型的向量（embed 任务失败或未完成）。加 `--allow-incomplete` 可以放行，但这次运行会标为不完整（退出码 2）。

## 实验配置

`configs/` 下每个文件是一组实验。各组之间只通过配置里的开关切换，用的是同一套检索代码（GLOBAL §9.2）。

| 配置 | 通道（meta / text / image） | text 查哪些来源 | RRF k | 用途 |
|---|---|---|---|---|
| `B0` | 开 / 关 / 关 | — | — | 文件名/标签检索，基础基线 |
| `B1` | 关 / 开 / 关 | 正文 | — | 正文 BM25 |
| `B2` | 关 / 开 / 关 | 正文 + OCR | — | 正文 + OCR 文字 BM25 |
| `B3` | 开 / 开 / 开 | 正文 + OCR | 后端配置（默认 60） | 文本检索 + CLIP 图像检索 + RRF |
| `B3-no-ocr` | 开 / 开 / 开 | 正文 | 后端配置 | 消融：去掉 OCR |
| `B3-no-clip` | 开 / 开 / 关 | 正文 + OCR | 后端配置 | 消融：去掉 CLIP |
| `clip-only` | 关 / 关 / 开 | — | — | 消融：只用 CLIP |
| `B3-k10`、`B3-k30`、`B3-k100` | 同 B3 | 同 B3 | 10、30、100 | RRF k 值消融；k=60 就是 B3 |

- `B3-no-clip` 与 `B2` 不同：它保留了 meta 通道，和 B3 只差图像这一个通道，用来单独看 CLIP 的作用。`B2` 只开 text 通道，是 OCR 的基线。
- 只开一个通道时，RRF 不改变该通道内的顺序，k 没有影响。

配置文件的字段：

| 字段 | 必填 | 含义 |
|---|---|---|
| `name` | 是 | 实验名，只能有字母、数字、`_`、`.`、`-`，会出现在结果目录名里 |
| `description` | 否 | 说明 |
| `channels` | 是 | `meta`、`text`、`image` 三项都要写明 `true` 或 `false` |
| `source_types` | 否 | text 通道查哪些来源，默认 `["body", "ocr"]` |
| `top_k`、`ks` | 否 | 每条查询取多少个文件；计算哪些 K 的指标 |
| `rrf_k` | 否 | 覆盖后端的 `SEARCH_RRF_K`，只影响这次实验，不影响 API。不写时用后端配置。生效的值记进 `config.json` 的 `search_params` 和检索日志 |

## 5. 结果

每次运行的结果在 `runs/<时间>_<实验名>_<随机串>/` 下：

| 文件 | 内容 |
|---|---|
| `config.json` | 这次运行的完整配置：实验配置、检索参数（含生效的 RRF k）、切分参数、数据集统计、代码与模型版本（三个索引 `doc_meta`、`chunks`、`image_vectors` 的结构 hash）、CLIP 模型（`clip_model`：开了图像通道时为模型名、版本、维度，版本里含权重文件 sha256 的前 12 位；没开时为 `null`）、OpenSearch 版本、机器信息、运行前检查发现的问题、是否完整 |
| `results.jsonl` | 每条查询一行：返回的文件排名（含各通道的名次和分数）、耗时、通道状态、各项指标 |
| `metrics.json` | 汇总指标：先按查询类型分层，再给总体；重复运行时附带波动；查询延迟 P50、P95 |

`run` 的退出码：

- 0：运行完整，结果可以作为正式数据。
- 2：运行完了，但结果不完整（有检索失败、通道不可用，或带 `--allow-incomplete` 跳过了运行前检查），不能当正式数据。
- 1：没有运行，原因会打印出来（例如数据集为空、还没导入、运行前检查没通过、数据库连不上）。

## 6. 注意事项

- 实验期间不要在系统里上传或删除别的文件：运行前检查统计的是整个系统里未完成的任务和未清理的文档，不只是数据集里的文件。
- 合成数据或测试数据跑出来的数字只能用来验证框架，不能当实验结果。
- 正式结果是否提交进 Git，等 T25 冻结数据集之后再定。
