"""T02 🧪：ID 生成确定性（同输入同输出）与解析往返。"""

from uuid import UUID

import pytest

from shared.ids import (
    ChunkIdParts,
    ImageIdParts,
    make_chunk_id,
    make_image_id,
    parse_chunk_id,
    parse_image_id,
    validate_parse_version,
)

DOC = UUID("0b9f6c1e-3d2a-4c5b-8e7f-123456789abc")
OTHER = UUID("11111111-2222-4333-8444-555555555555")


def test_chunk_id_format():
    assert make_chunk_id(DOC, "v1", 7) == "0b9f6c1e-3d2a-4c5b-8e7f-123456789abc:v1:7"


def test_chunk_id_is_deterministic():
    assert make_chunk_id(DOC, "v1", 7) == make_chunk_id(UUID(str(DOC)), "v1", 7)


def test_chunk_id_differs_when_any_input_differs():
    ids = {
        make_chunk_id(DOC, "v1", 0),
        make_chunk_id(DOC, "v1", 1),
        make_chunk_id(DOC, "v2", 0),
        make_chunk_id(OTHER, "v1", 0),
    }
    assert len(ids) == 4


@pytest.mark.parametrize("parse_version", ["v1", "1.0.3", "c500-o50_a1b2c3", "2026-11-13"])
@pytest.mark.parametrize("seq", [0, 1, 12345])
def test_chunk_id_round_trip(parse_version, seq):
    parsed = parse_chunk_id(make_chunk_id(DOC, parse_version, seq))
    assert parsed == ChunkIdParts(DOC, parse_version, seq)


@pytest.mark.parametrize("bad", ["", "a:b", "v 1", "版本1", "a/b"])
def test_invalid_parse_version_rejected(bad):
    with pytest.raises(ValueError):
        validate_parse_version(bad)
    with pytest.raises(ValueError):
        make_chunk_id(DOC, bad, 0)


def test_negative_seq_rejected():
    with pytest.raises(ValueError):
        make_chunk_id(DOC, "v1", -1)


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "not-a-uuid:v1:0",
        f"{DOC}:v1",
        f"{DOC}:v1:0:extra",
        f"{DOC}:v1:x",
        f"{DOC}:v1:-1",
        f"{DOC}:v1:+1",
        f"{DOC}:v1:01",
        f"{DOC}::0",
        f"{str(DOC).upper()}:v1:0",
        f"{DOC.hex}:v1:0",
    ],
)
def test_malformed_chunk_id_rejected(bad):
    with pytest.raises(ValueError):
        parse_chunk_id(bad)


def test_standalone_image_id_is_document_id():
    assert make_image_id(DOC) == str(DOC)
    assert parse_image_id(str(DOC)) == ImageIdParts(DOC, None, None)
    assert not parse_image_id(str(DOC)).is_embedded


def test_embedded_image_id_format_and_round_trip():
    image_id = make_image_id(DOC, page=3, idx=0)
    assert image_id == f"{DOC}:img:3:0"
    parsed = parse_image_id(image_id)
    assert parsed == ImageIdParts(DOC, 3, 0)
    assert parsed.is_embedded


def test_image_id_is_deterministic():
    assert make_image_id(DOC, 2, 5) == make_image_id(UUID(str(DOC)), 2, 5)


@pytest.mark.parametrize(
    "kwargs", [{"page": 1}, {"idx": 0}, {"page": 0, "idx": 0}, {"page": 1, "idx": -1}]
)
def test_invalid_embedded_image_args_rejected(kwargs):
    with pytest.raises(ValueError):
        make_image_id(DOC, **kwargs)


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "abc",
        f"{DOC}:img:1",
        f"{DOC}:pic:1:0",
        f"{DOC}:img:0:0",
        f"{DOC}:img:1:x",
        f"{DOC}:v1:0",
    ],
)
def test_malformed_image_id_rejected(bad):
    with pytest.raises(ValueError):
        parse_image_id(bad)
