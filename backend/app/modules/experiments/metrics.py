"""M12：检索评价指标（GLOBAL §9.2）。纯函数。

ranking：系统返回的文件列表（file_id），第一个是第 1 名；不属于数据集的文件用 None 占位，
它们占名次、但永远不相关。qrels：{file_id: 等级}，没标注的文件等级为 0；等级 > 0 才算相关。

    P@K    = 前 K 名里相关文件的个数 / K（返回不足 K 个时，分母仍是 K）
    R@K    = 前 K 名里相关文件的个数 / 全部相关文件的个数
    nDCG@K = DCG@K / IDCG@K，DCG = Σ (2^等级 − 1) / log2(名次 + 1)
             IDCG 是把全部标注按等级从高到低排列后的 DCG@K

一条查询没有任何相关文件时，R@K 和 nDCG@K 没有定义，返回 None；汇总时这条查询的 P@K 也不计入
（query_metrics），三个指标的查询条数一致。这类查询单独报告条数。
"""

import math
import statistics
from collections.abc import Iterable, Mapping, Sequence


def _relevant_hits(ranking: Sequence[str | None], qrels: Mapping[str, int], k: int) -> int:
    return sum(1 for f in ranking[:k] if f is not None and qrels.get(f, 0) > 0)


def precision_at(ranking: Sequence[str | None], qrels: Mapping[str, int], k: int) -> float:
    if k < 1:
        raise ValueError("K 必须是正整数")
    return _relevant_hits(ranking, qrels, k) / k


def recall_at(ranking: Sequence[str | None], qrels: Mapping[str, int], k: int) -> float | None:
    if k < 1:
        raise ValueError("K 必须是正整数")
    total = sum(1 for g in qrels.values() if g > 0)
    if total == 0:
        return None
    return _relevant_hits(ranking, qrels, k) / total


def _dcg(grades: Iterable[int]) -> float:
    return sum((2**g - 1) / math.log2(rank + 1) for rank, g in enumerate(grades, start=1))


def ndcg_at(ranking: Sequence[str | None], qrels: Mapping[str, int], k: int) -> float | None:
    if k < 1:
        raise ValueError("K 必须是正整数")
    ideal = _dcg(sorted((g for g in qrels.values() if g > 0), reverse=True)[:k])
    if ideal == 0:
        return None
    actual = _dcg(qrels.get(f, 0) if f is not None else 0 for f in ranking[:k])
    return actual / ideal


def query_metrics(
    ranking: Sequence[str | None], qrels: Mapping[str, int], ks: Sequence[int]
) -> dict[str, float | None]:
    """一条查询的全部指标，键形如 P@10、R@10、nDCG@10。

    这条查询没有任何相关文件时，三个指标都记为 None，都不参与平均：
    否则 P@K 会把它算成 0 拉低平均值，而 R@K、nDCG@K 又不算它，
    同一张表里各指标的查询条数就不一样了。这类查询单独报告（queries_without_relevant）。
    """
    if not any(g > 0 for g in qrels.values()):
        return {f"{name}@{k}": None for k in ks for name in ("P", "R", "nDCG")}
    result: dict[str, float | None] = {}
    for k in ks:
        result[f"P@{k}"] = precision_at(ranking, qrels, k)
        result[f"R@{k}"] = recall_at(ranking, qrels, k)
        result[f"nDCG@{k}"] = ndcg_at(ranking, qrels, k)
    return result


def mean_metrics(
    per_query: Sequence[Mapping[str, float | None]],
) -> dict[str, dict[str, float | int | None]]:
    """对若干条查询取平均。每个指标报告：平均值、参与平均的查询数。"""
    names = sorted({name for metrics in per_query for name in metrics})
    summary: dict[str, dict[str, float | int | None]] = {}
    for name in names:
        values = [m[name] for m in per_query if m.get(name) is not None]
        summary[name] = {
            "mean": statistics.fmean(values) if values else None,
            "queries": len(values),
        }
    return summary


def percentile(values: Sequence[float], p: float) -> float | None:
    """最近秩法的百分位数（P50、P95）：不插值，结果一定是某次实际测得的值。"""
    if not values:
        return None
    if not 0 < p <= 100:
        raise ValueError("百分位必须在 (0, 100] 之间")
    ordered = sorted(values)
    rank = math.ceil(p / 100 * len(ordered))
    return ordered[rank - 1]


def spread(values: Sequence[float]) -> dict[str, float | int | None]:
    """重复运行之间的波动：平均值、总体标准差、最小、最大（GLOBAL §9.2 第 4 条）。"""
    if not values:
        return {"mean": None, "stdev": None, "min": None, "max": None, "runs": 0}
    return {
        "mean": statistics.fmean(values),
        "stdev": statistics.pstdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
        "runs": len(values),
    }
