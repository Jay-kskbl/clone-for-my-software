"""T15：RRF 融合。用手算的小例子验证（DEVPLAN T22 的 🧪 在这里先满足）。"""

import uuid

import pytest
from shared.contracts import ChannelResult

from app.modules.search import fuse

A = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000000")
B = uuid.UUID("bbbbbbbb-0000-4000-8000-000000000000")
C = uuid.UUID("cccccccc-0000-4000-8000-000000000000")
D = uuid.UUID("dddddddd-0000-4000-8000-000000000000")


def scores(fused) -> dict[uuid.UUID, float]:
    return {f.document_id: f.score for f in fused}


def test_hand_computed_example():
    # meta：A 第 1、B 第 2；text：B 第 1、C 第 2、A 第 3。k = 60
    fused = fuse(
        {"meta": [(A, 9.0), (B, 7.0)], "text": [(B, 12.5), (C, 8.0), (A, 3.0)]}, k=60, depth=10
    )

    expected = {
        A: 1 / 61 + 1 / 63,  # 0.032268...
        B: 1 / 62 + 1 / 61,  # 0.032522...
        C: 1 / 62,  # 0.016129...
    }
    assert [f.document_id for f in fused] == [B, A, C]
    assert scores(fused) == pytest.approx(expected)


def test_original_ranks_and_scores_are_kept_per_channel():
    fused = fuse({"meta": [(A, 9.0), (B, 7.0)], "text": [(B, 12.5)]}, k=60, depth=10)

    by_id = {f.document_id: f for f in fused}
    assert by_id[B].channels == (
        ChannelResult(channel="meta", rank=2, score=7.0),
        ChannelResult(channel="text", rank=1, score=12.5),
    )
    assert by_id[A].channels == (ChannelResult(channel="meta", rank=1, score=9.0),)


def test_only_ranks_matter_not_raw_scores():
    # 原始分数相差几个数量级，融合结果只由名次决定
    small = fuse({"text": [(A, 0.001), (B, 0.0005)]}, k=60, depth=10)
    large = fuse({"text": [(A, 1000.0), (B, 999.0)]}, k=60, depth=10)

    assert scores(small) == scores(large)


def test_single_channel_keeps_its_order():
    fused = fuse({"text": [(C, 3.0), (A, 2.0), (B, 1.0)]}, k=60, depth=10)

    assert [f.document_id for f in fused] == [C, A, B]
    assert [f.score for f in fused] == pytest.approx([1 / 61, 1 / 62, 1 / 63])


def test_depth_cuts_each_channel():
    fused = fuse({"text": [(A, 3.0), (B, 2.0), (C, 1.0)], "meta": [(D, 1.0)]}, k=60, depth=2)

    assert C not in scores(fused)
    assert set(scores(fused)) == {A, B, D}


def test_k_changes_the_scores():
    one = fuse({"text": [(A, 1.0)]}, k=1, depth=10)
    sixty = fuse({"text": [(A, 1.0)]}, k=60, depth=10)

    assert one[0].score == pytest.approx(1 / 2)
    assert sixty[0].score == pytest.approx(1 / 61)


def test_ties_are_broken_by_document_id_deterministically():
    # A 在 meta 第 1，B 在 text 第 1：分数完全相同
    fused = fuse({"text": [(B, 5.0)], "meta": [(A, 5.0)]}, k=60, depth=10)

    assert [f.document_id for f in fused] == [A, B]
    assert fuse({"meta": [(A, 5.0)], "text": [(B, 5.0)]}, k=60, depth=10) == fused


def test_duplicate_document_within_a_channel_counts_once():
    fused = fuse({"text": [(A, 3.0), (A, 2.0), (B, 1.0)]}, k=60, depth=10)

    by_id = {f.document_id: f for f in fused}
    assert by_id[A].channels == (ChannelResult(channel="text", rank=1, score=3.0),)
    # 重复的那条不占名次：B 是第 2 名
    assert by_id[B].channels[0].rank == 2


def test_empty_input_gives_empty_output():
    assert fuse({}, k=60, depth=10) == []
    assert fuse({"meta": [], "text": []}, k=60, depth=10) == []


@pytest.mark.parametrize("k, depth", [(0, 10), (60, 0)])
def test_invalid_parameters_are_rejected(k, depth):
    with pytest.raises(ValueError):
        fuse({"text": [(A, 1.0)]}, k=k, depth=depth)
