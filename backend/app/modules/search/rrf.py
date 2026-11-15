"""M11：RRF（Reciprocal Rank Fusion，倒数排名融合）。纯函数。

输入是各通道已经聚合到文件级的排名列表，输出一个融合后的文件列表（GLOBAL §4.4）：

    score(d) = Σ  1 / (k + rank_c(d))      对每个命中 d 的通道 c 求和

只用名次，不用各通道的原始分数：BM25 分数和向量相似度的量纲不同，不能直接相加。
每个通道只取前 depth 名参与融合（截断深度）。k 和 depth 都来自配置，随每次检索记录。

各通道的原始名次和原始分数原样保留在结果里，供展示和实验分析。
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from shared.contracts import Channel, ChannelResult

# 一个通道的结果：按名次排好的（document_id，原始分数），第一个是第 1 名
Ranking = Sequence[tuple[uuid.UUID, float]]


@dataclass(frozen=True)
class FusedDocument:
    document_id: uuid.UUID
    score: float
    channels: tuple[ChannelResult, ...]


def fuse(rankings: Mapping[Channel, Ranking], *, k: int, depth: int) -> list[FusedDocument]:
    """按 RRF 融合。结果按融合分数从高到低排列。

    同分时按 document_id 排序，保证同样的输入永远得到同样的顺序（实验可重复）。
    一个通道内同一文档出现多次时只取第一次（通道应当已经聚合到文件级，这里只是防御）。
    """
    if k < 1:
        raise ValueError(f"RRF 的 k 必须是正整数：{k}")
    if depth < 1:
        raise ValueError(f"截断深度必须是正整数：{depth}")

    scores: dict[uuid.UUID, float] = {}
    hits: dict[uuid.UUID, list[ChannelResult]] = {}
    # 通道按固定顺序处理，每个文档的通道列表顺序因此也是固定的
    for channel in sorted(rankings):
        seen: set[uuid.UUID] = set()
        rank = 0
        for document_id, raw_score in rankings[channel]:
            if document_id in seen:
                continue
            seen.add(document_id)
            rank += 1
            if rank > depth:
                break
            scores[document_id] = scores.get(document_id, 0.0) + 1.0 / (k + rank)
            hits.setdefault(document_id, []).append(
                ChannelResult(channel=channel, rank=rank, score=raw_score)
            )

    ordered = sorted(scores, key=lambda d: (-scores[d], str(d)))
    return [FusedDocument(document_id=d, score=scores[d], channels=tuple(hits[d])) for d in ordered]
