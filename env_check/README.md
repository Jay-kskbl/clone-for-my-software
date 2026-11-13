# 环境实测（GLOBAL.md §10 阶段一 · 第 1 周）

目的：在动手写系统之前，用真实数据回答四个问题，并把答案写进附录 A13/A14 和论文"实验环境"一节：

1. OpenSearch 能不能在这台电脑上稳定跑？用哪个中文分词器？
2. PaddleOCR 每张图要多久？识别准不准？
3. Chinese-CLIP 查询编码多快？入库时每秒能编码多少张图？
4. 四个组件同时运行时，内存够不够？

预计耗时：半天到一天半（大部分时间花在下载依赖和模型上）。

## 前置条件

- Python 3.11（推荐，`brew install python@3.11`）
- Docker Desktop（用于 OpenSearch；Docker Desktop 的内存上限建议设为 ≥ 4 GB）
- 网络能访问 PyPI、Docker Hub 和模型下载源

## 目录

```
env_check/
├── setup_envs.sh            创建 3 个隔离虚拟环境并记录实际依赖版本
├── requirements-*.txt       三个环境各自的依赖
├── _common.py               公共工具（计时、内存、CER、结果保存）
├── 00_sysinfo.py            硬件/软件环境         → .venv-main
├── 01_check_opensearch.py   连通性/分词/BM25/向量  → .venv-main
├── 02_check_ocr.py          PaddleOCR 耗时与 CER   → .venv-ocr
├── 03_check_clip.py         Chinese-CLIP 延迟与吞吐 → .venv-clip
├── 04_mem_snapshot.py       并发内存快照          → .venv-main
├── 05_make_report.py        汇总生成 env_report.md → .venv-main
├── opensearch/              测试用 OpenSearch（含 smartcn 插件）
├── samples/                 自动生成的测试图片
├── models/                  CLIP 模型下载位置（勿提交 Git）
└── results/                 每次实测的原始 JSON（history/ 下保留全部历史）
```

## 运行顺序

```bash
cd ~/Desktop/"BARRY zou"/env_check

# 1. 建环境（三个环境互不干扰；某个失败可单独重建：bash setup_envs.sh ocr）
PY=python3.11 bash setup_envs.sh

# 2. 系统信息
.venv-main/bin/python 00_sysinfo.py

# 3. OpenSearch（首次构建要下载镜像，耐心等）
cd opensearch && docker compose up -d --build && cd ..
sleep 60
.venv-main/bin/python 01_check_opensearch.py
#   若想试 2g 堆：OS_HEAP=2g docker compose -f opensearch/docker-compose.yml up -d --force-recreate

# 4. OCR（首次运行会自动下载模型——仅实测阶段允许）
.venv-ocr/bin/python 02_check_ocr.py --mobile
.venv-ocr/bin/python 02_check_ocr.py              # 再测一次默认模型，对比速度和 CER
#   有自己的扫描件/截图：放进一个文件夹，同名 .txt 写标准文本即可算 CER
#   .venv-ocr/bin/python 02_check_ocr.py --mobile --images ~/Desktop/ocr样例

# 5. CLIP
.venv-clip/bin/python 03_check_clip.py
.venv-clip/bin/python 03_check_clip.py --device cpu   # 若 auto 选了 mps，再测一次 CPU 做对比

# 6. 并发内存：开 3 个终端
#   终端 B： .venv-ocr/bin/python 02_check_ocr.py --mobile --hold
#   终端 C： .venv-clip/bin/python 03_check_clip.py --hold
#   终端 D： .venv-main/bin/python 04_mem_snapshot.py
#   完成后在 B、C 按 Ctrl+C

# 7. 生成报告
.venv-main/bin/python 05_make_report.py
open env_report.md

# 8. 结束后关闭 OpenSearch（保留数据卷）
cd opensearch && docker compose down
```

## 读结果时看什么

| 看点 | 判断 |
|---|---|
| 分词对比里 `standard` 是否按单字切 | 正常现象，说明必须用中文分词插件 |
| `smartcn` / `ik_*` 的切分是否把"文档管理""跨模态"这类词切对 | 选切分更合理的那个，写进附录 A13 |
| OCR `avg_s_per_image` | 乘以你预计的扫描页数，估算批量导入耗时 |
| OCR `avg_cer` | `lowq` 图的 CER 明显偏高是正常的，用来说明低质量扫描件的局限 |
| CLIP `text_encode_ms` P95 | 就是每次图文检索额外增加的查询延迟 |
| 并发快照 `system_available_gb` / `swap_used_gb` | 可用 < 1.5 GB 或 swap 持续增长 → 降低 OpenSearch 堆、用 mobile OCR、开发时按需启动 CLIP |

## 注意

- `samples/` 中的合成图片和 CLIP 合理性检查只用于**验证链路可用**，不能作为论文里的检索效果数据。
- `results/freeze-*.txt` 记录了实际安装的版本，正式项目据此锁定依赖（GLOBAL.md §8.3）。
- 测试用 OpenSearch 关闭了安全插件且只绑定 127.0.0.1，正式项目的配置单独编写。
- `models/`、`.venv-*`、`results/history/` 不要提交到 Git。
