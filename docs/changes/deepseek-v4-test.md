# deepseek-v4-test：数据集冻结与评测结论

> 本文件用于存放 T25「冻结数据集与标注」的结论与统计，以及 T26 起的正式评测结果。
> 按 Barry 2026-11-19 决定：不改动 `experiments/README.md`，结论统一放在本文件；
> 数据文件本身仍按 `experiments/README.md` 的格式填写（manifest.csv、queries.tsv、qrels/*.tsv）。

## 1. 决定与方案（2026-11-19 已批准）

- 数据集方向：自建「中文 + 混合格式 + 三类查询」最小真实集，不用公开数据集。
- 规模目标：40–60 份真实文件；约 30 条查询。
- 文件类型五类各若干：`pdf`（带文本层）、`scanned_pdf`（扫描件）、`docx`、`xlsx`、`image`。
- 查询类型分层：`text`（文字型）、`visual`（视觉型）、`mixed`（混合型），每类约 1/3。
- 相关性等级 `grade` 沿用 0–3（0 不相关、1 部分相关、2 相关、3 高度相关）。
- 数据必须真实、来源可说明；合成数据只能验证框架，不能当正式结果。

## 2. 文件格式（与 experiments/README.md 一致，此处复制关键格式）

`experiments/datasets/manifest.csv`（逗号分隔，UTF-8，首行表头不动）：

```
file_id,path,type,source,notes
f001,pdf/学院2025年度报告.pdf,pdf,学院官网公开,
```

`experiments/queries.tsv`（制表符分隔，UTF-8）：

```
query_id	type	text
q001	text	2025年度经费预算总额是多少
```

`experiments/qrels/qrels.tsv`（制表符分隔，可拆多个文件，程序会读入 qrels/ 下所有 .tsv）：

```
query_id	file_id	grade
q001	f001	3
```

文件 `type` 五选一：pdf / scanned_pdf / docx / xlsx / image。
查询 `type` 三选一：text / visual / mixed。
原文件放 `experiments/datasets/files/`（可建子目录，不进 Git）。

## 3. 收集与标注清单（给 Barry）

1. 收集文件：五类各至少 6 份，总数 40–60；优先中文、来源可写（学院通知、公开资料、自己拍摄等）。
2. 文件放进 `experiments/datasets/files/` 下的子目录（如 pdf/、docx/、image/），并在 manifest.csv 登记。
3. 写约 30 条查询，text / visual / mixed 各约 10 条；查询就是检索框里输入的句子。
4. 对每条查询标 qrels：找到相关 file_id 并给 0–3 级；没写的文件默认按 0 处理。
5. 全部填好后在 backend/ 目录运行 `python -m app.modules.experiments validate` 检查格式。
6. 冻结：确认不再增删改后，把统计数字填进第 4 节，冻结后数据集不再改动。

## 4. 冻结记录（收集完成后回填，冻结后不再修改）

| 项目 | 数量 |
|---|---|
| 文件总数 | 待填 |
| pdf | 待填 |
| scanned_pdf | 待填 |
| docx | 待填 |
| xlsx | 待填 |
| image | 待填 |
| 查询总数 | 待填 |
| text 查询 | 待填 |
| visual 查询 | 待填 |
| mixed 查询 | 待填 |
| qrels 条数 | 待填 |
| 有相关文件的查询数 | 待填 |
| 无相关文件的查询数 | 待填 |
| 冻结日期 | 待填 |

## 5. 正式评测结果（T26 跑完后回填）

B0 / B1 / B2 / B3 及各消融的 P@K、R@K、nDCG@K，按查询类型分层后回填到这里。
当前为待填；没有真实数据前不得声称有正式指标。

## 6. 变更记录

- 2026-11-19：建立本文件，确定自建数据集方案；当前 0 文件、0 查询、0 标注，未冻结。
