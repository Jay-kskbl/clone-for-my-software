# 环境实测报告

生成时间：2026-11-13T14:42:14+09:00

## 1. 硬件与软件环境

| 项目 | 值 |
|---|---|
| os | macOS-26.6.2-arm64-arm-64bit |
| machine | arm64 |
| cpu_model | Apple M4 |
| cpu_count | 10 |
| total_mem_gb | 24.0 |
| disk_free_gb | 341.4 |
| python | 3.11.18 |
| docker | 未安装 |
| docker_compose | 未安装 |
| java | The operation couldn’t be completed. Unable to locate a Java Runtime. |
| node | 未安装 |
| psql | 未安装 |
| git | xcode-select: note: No developer tools were found, requesting install. |

## 2. OpenSearch

不可达或未运行：未运行 01_check_opensearch.py

## 3. PaddleOCR

- paddle 3.3.1 / paddleocr 3.7.0 / 设备 cpu
- 接口与模型：3.x predict API + 默认模型
- 模型加载：46.2979 s；加载后内存：1037.7 MB；峰值：1121.5 MB
- 平均每图耗时：0.6208 s；平均 CER：0.0

| 图片 | 平均耗时(s) | CER | 平均置信度 |
|---|---|---|---|
| ocr_clean.png | 0.7022 | 0.0 | 0.993 |
| ocr_small.png | 0.5438 | 0.0 | 0.994 |
| ocr_lowq.png | 0.6164 | 0.0 | 0.9998 |

## 4. Chinese-CLIP

- torch 2.15.0 / cn_clip unknown / 设备 cpu
- 模型：ViT-B-16；向量维度：512
- 模型加载：2.376 s；加载后内存：1405.8 MB；峰值：2025.1 MB
- 查询文本编码：P50 20.1885 ms / P95 20.4864 ms
- 图片编码吞吐：30.9 张/秒（batch=8）
- 合理性检查 top1：0.8（仅链路验证，不作为论文检索效果数据）

## 5. 并发内存

未运行 04_mem_snapshot.py

## 6. 决策（由 Barry 根据以上数据填写）

- [ ] 中文分词方案（附录 A13）：
- [ ] OpenSearch 版本与堆大小：
- [ ] 是否需要启用 OpenSearch 降级预案（附录 A14）：
- [ ] OCR 模型规格（mobile / server）：
- [ ] Chinese-CLIP 模型规格与运行设备：
- [ ] 开发时是否需要按需启停 CLIP 服务：

## 7. 错误与警告

