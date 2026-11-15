# 实验数据与运行说明（M12）

本目录存放评测数据集、相关性标注和实验配置。代码在 `backend/app/modules/experiments/`，规则见 `docs/decisions.md` D32。

## 1. 目录结构

```
experiments/
├── README.md                 本文件
├── configs/                  实验配置：B0.json、B1.json、B2.json
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

## 5. 结果

每次运行的结果在 `runs/<时间>_<实验名>_<随机串>/` 下：

| 文件 | 内容 |
|---|---|
| `config.json` | 这次运行的完整配置：实验配置、检索参数、切分参数、数据集统计、代码与模型版本、OpenSearch 版本、机器信息、运行前检查发现的问题、是否完整 |
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
