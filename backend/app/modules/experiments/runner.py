"""M12：运行一组实验（DEVPLAN T19）。

    读取配置 → 对每条查询调用检索（M11）→ 保存每条查询的原始排名 → 计算指标，按查询类型分层

检索函数由调用方注入（__main__.py 里接的是真实的 app.modules.search.service.search），
这里不碰数据库和网络，便于测试。

检索服务出错的查询记为失败，整次运行标记为不完整（complete=False），
失败的查询不当成“没有结果”算进指标（GLOBAL §12：不得把错误静默转换成空结果）。
"""

from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from app.modules.experiments.config import ExperimentConfig
from app.modules.experiments.dataset import QUERY_TYPES, Dataset
from app.modules.experiments.metrics import mean_metrics, percentile, query_metrics, spread


@dataclass(frozen=True)
class RankedDocument:
    document_id: str
    score: float
    # 各通道的原始名次和分数：[{"channel", "rank", "score"}]
    channels: list[dict[str, Any]]


@dataclass(frozen=True)
class SearchResult:
    ranking: list[RankedDocument]
    took_ms: int
    # 各通道的执行状态：{通道: ok / disabled / unavailable}
    channel_status: dict[str, str]


class SearchFailed(Exception):
    """这一次检索没有得到结果（检索服务故障等）。"""


# 查询文本 → 检索结果；失败时抛 SearchFailed
SearchFn = Callable[[str], SearchResult]


@dataclass
class RunResult:
    records: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    complete: bool = True


def run_queries(
    config: ExperimentConfig,
    dataset: Dataset,
    document_map: Mapping[str, str],
    search: SearchFn,
    *,
    repeats: int = 1,
) -> RunResult:
    """document_map：document_id → file_id（数据集之外的文档不在里面）。"""
    if repeats < 1:
        raise ValueError("重复次数至少为 1")
    result = RunResult()
    for repetition in range(1, repeats + 1):
        for query in dataset.queries.values():
            record: dict[str, Any] = {
                "repetition": repetition,
                "query_id": query.query_id,
                "query_type": query.type,
                "query": query.text,
            }
            try:
                found = search(query.text)
            except SearchFailed as exc:
                record.update(ok=False, error=str(exc))
                result.complete = False
                result.records.append(record)
                continue
            # 图像通道（T22 之前）等本应执行却不可用的通道：结果不完整，如实标记
            unavailable = sorted(c for c, s in found.channel_status.items() if s == "unavailable")
            if unavailable:
                result.complete = False
            ranking = [
                {
                    "rank": rank,
                    "file_id": document_map.get(doc.document_id),
                    "document_id": doc.document_id,
                    "score": doc.score,
                    "channels": doc.channels,
                }
                for rank, doc in enumerate(found.ranking, start=1)
            ]
            file_ranking = [item["file_id"] for item in ranking]
            record.update(
                ok=True,
                took_ms=found.took_ms,
                channel_status=found.channel_status,
                unavailable_channels=unavailable,
                outside_dataset=sum(1 for f in file_ranking if f is None),
                ranking=ranking,
                metrics=query_metrics(
                    file_ranking, dataset.qrels.get(query.query_id, {}), config.ks
                ),
            )
            result.records.append(record)
    result.metrics = summarize(result.records, dataset, repeats)
    return result


def summarize(records: list[dict[str, Any]], dataset: Dataset, repeats: int) -> dict[str, Any]:
    """汇总：每次重复内先按查询类型分层取平均，再看重复之间的波动。"""
    ok = [r for r in records if r["ok"]]
    per_repetition: dict[int, dict[str, Any]] = {}
    for repetition in range(1, repeats + 1):
        rows = [r for r in ok if r["repetition"] == repetition]
        by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            by_type[row["query_type"]].append(row["metrics"])
        per_repetition[repetition] = {
            "overall": mean_metrics([row["metrics"] for row in rows]),
            "by_type": {t: mean_metrics(by_type[t]) for t in QUERY_TYPES if by_type[t]},
        }

    # 检索是确定性的，各次重复的指标应当相同；仍然报告波动，有差异时一眼能看出来
    def values(layer: str, name: str, query_type: str | None = None) -> list[float]:
        out = []
        for summary in per_repetition.values():
            source = (
                summary["overall"] if layer == "overall" else summary["by_type"].get(query_type, {})
            )
            mean = source.get(name, {}).get("mean")
            if mean is not None:
                out.append(mean)
        return out

    first = per_repetition.get(1, {"overall": {}, "by_type": {}})
    latencies = [float(r["took_ms"]) for r in ok]
    return {
        "queries": len(dataset.queries),
        "queries_by_type": {
            t: sum(1 for q in dataset.queries.values() if q.type == t) for t in QUERY_TYPES
        },
        "queries_without_relevant": dataset.summary()["queries_without_relevant"],
        "repeats": repeats,
        "failed_searches": sum(1 for r in records if not r["ok"]),
        "overall": {
            name: {**first["overall"][name], "across_repeats": spread(values("overall", name))}
            for name in first["overall"]
        },
        "by_type": {
            query_type: {
                name: {
                    **layer[name],
                    "across_repeats": spread(values("by_type", name, query_type)),
                }
                for name in layer
            }
            for query_type, layer in first["by_type"].items()
        },
        "latency_ms": {
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
            "searches": len(latencies),
        },
    }
