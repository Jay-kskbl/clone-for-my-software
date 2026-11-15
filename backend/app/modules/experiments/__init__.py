"""M12 实验评测：数据集与标注、评价指标、对照组运行器（DEVPLAN T19，GLOBAL §9.2）。

代码在这里，数据在仓库根目录的 experiments/。命令行用法见 __main__.py。
"""

from app.modules.experiments.config import ExperimentConfig, load_config
from app.modules.experiments.dataset import Dataset, DatasetError, load_dataset
from app.modules.experiments.metrics import ndcg_at, precision_at, recall_at
from app.modules.experiments.runner import RunResult, SearchFailed, SearchResult, run_queries

__all__ = [
    "Dataset",
    "DatasetError",
    "ExperimentConfig",
    "RunResult",
    "SearchFailed",
    "SearchResult",
    "load_config",
    "load_dataset",
    "ndcg_at",
    "precision_at",
    "recall_at",
    "run_queries",
]
