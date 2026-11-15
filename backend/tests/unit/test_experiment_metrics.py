"""T19 🧪：评价指标。每个数字都是手算的，写在注释里。"""

import math

import pytest

from app.modules.experiments.metrics import (
    mean_metrics,
    ndcg_at,
    percentile,
    precision_at,
    query_metrics,
    recall_at,
    spread,
)

# 一条查询：a 高度相关（3），b 相关（1），c 相关（2），d 标注为不相关（0）
QRELS = {"a": 3, "b": 1, "c": 2, "d": 0}
# 系统返回：a, x, b, d, None（数据集之外的文件）, c
RANKING = ["a", "x", "b", "d", None, "c"]


def test_precision_hand_computed():
    assert precision_at(RANKING, QRELS, 1) == 1.0  # a
    assert precision_at(RANKING, QRELS, 3) == pytest.approx(2 / 3)  # a, b
    assert precision_at(RANKING, QRELS, 5) == pytest.approx(2 / 5)  # d 不相关，None 不算
    assert precision_at(RANKING, QRELS, 6) == pytest.approx(3 / 6)


def test_precision_divides_by_k_even_when_fewer_results_are_returned():
    # 只返回 2 个，K=10：分母仍是 10，返回少不能“占便宜”
    assert precision_at(["a", "b"], QRELS, 10) == pytest.approx(2 / 10)


def test_recall_hand_computed():
    # 相关文件共 3 个（a、b、c）
    assert recall_at(RANKING, QRELS, 1) == pytest.approx(1 / 3)
    assert recall_at(RANKING, QRELS, 3) == pytest.approx(2 / 3)
    assert recall_at(RANKING, QRELS, 6) == 1.0
    assert recall_at([], QRELS, 5) == 0.0


def test_ndcg_hand_computed():
    # DCG@3 = (2^3-1)/log2(2) + 0/log2(3) + (2^1-1)/log2(4) = 7 + 0 + 0.5 = 7.5
    # IDCG@3：理想顺序 a(3), c(2), b(1) = 7/1 + 3/log2(3) + 1/2
    idcg3 = 7 + 3 / math.log2(3) + 0.5
    assert ndcg_at(RANKING, QRELS, 3) == pytest.approx(7.5 / idcg3)
    # DCG@6 再加上第 6 名的 c：3/log2(7)
    dcg6 = 7.5 + 3 / math.log2(7)
    assert ndcg_at(RANKING, QRELS, 6) == pytest.approx(dcg6 / idcg3)


def test_perfect_ranking_has_ndcg_one():
    assert ndcg_at(["a", "c", "b"], QRELS, 3) == pytest.approx(1.0)
    assert ndcg_at(["a", "c", "b", "x", "y"], QRELS, 10) == pytest.approx(1.0)


def test_binary_relevance_example():
    # 二元相关的小例子：相关的是 p、q；返回 q, r, p
    qrels = {"p": 1, "q": 1}
    # DCG = 1/log2(2) + 0 + 1/log2(4) = 1.5；IDCG = 1 + 1/log2(3)
    assert ndcg_at(["q", "r", "p"], qrels, 3) == pytest.approx(1.5 / (1 + 1 / math.log2(3)))
    assert precision_at(["q", "r", "p"], qrels, 2) == 0.5
    assert recall_at(["q", "r", "p"], qrels, 2) == 0.5


def test_query_without_relevant_files_has_undefined_recall_and_ndcg():
    assert recall_at(["a"], {"a": 0}, 5) is None
    assert ndcg_at(["a"], {}, 5) is None
    # P@K 仍有定义：返回的都不相关，就是 0
    assert precision_at(["a"], {}, 5) == 0.0


@pytest.mark.parametrize("function", [precision_at, recall_at, ndcg_at])
def test_k_must_be_positive(function):
    with pytest.raises(ValueError):
        function(RANKING, QRELS, 0)


def test_query_metrics_names():
    metrics = query_metrics(RANKING, QRELS, [1, 3])

    assert set(metrics) == {"P@1", "R@1", "nDCG@1", "P@3", "R@3", "nDCG@3"}


def test_mean_skips_undefined_values_and_reports_how_many_queries_counted():
    per_query = [
        {"P@5": 0.4, "R@5": 0.5},
        {"P@5": 0.2, "R@5": None},  # 这条查询没有相关文件
    ]

    summary = mean_metrics(per_query)

    assert summary["P@5"] == {"mean": pytest.approx(0.3), "queries": 2}
    assert summary["R@5"] == {"mean": 0.5, "queries": 1}


def test_mean_of_nothing_is_none():
    assert mean_metrics([{"R@5": None}]) == {"R@5": {"mean": None, "queries": 0}}


def test_percentile_nearest_rank():
    values = [30, 10, 20, 50, 40]  # 排序后 10 20 30 40 50

    assert percentile(values, 50) == 30  # ceil(0.5×5)=3 → 第 3 个
    assert percentile(values, 95) == 50  # ceil(4.75)=5
    assert percentile(values, 20) == 10
    assert percentile([], 50) is None
    with pytest.raises(ValueError):
        percentile(values, 0)


def test_spread_across_repeats():
    assert spread([0.5, 0.5, 0.5]) == {"mean": 0.5, "stdev": 0.0, "min": 0.5, "max": 0.5, "runs": 3}
    result = spread([1.0, 3.0])
    assert (result["mean"], result["stdev"]) == (2.0, 1.0)
    assert spread([])["runs"] == 0


def test_query_without_relevant_files_is_left_out_of_every_metric():
    # 汇总时三个指标的查询条数要一致：没有相关文件的查询 P@K 也记为 None
    metrics = query_metrics(["a", "b"], {"a": 0}, [5])

    assert metrics == {"P@5": None, "R@5": None, "nDCG@5": None}
