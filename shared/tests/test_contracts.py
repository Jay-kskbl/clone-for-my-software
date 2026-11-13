"""T02 🧪：每种 locator 的序列化往返，以及各契约的校验规则。"""

from uuid import UUID

import pytest
from pydantic import TypeAdapter, ValidationError

from shared.contracts import (
    ChannelResult,
    Chunk,
    DocxParaLocator,
    Evidence,
    ImageLocator,
    OCRLine,
    OCRResult,
    ParsedDocument,
    PdfPageLocator,
    Point,
    SearchHit,
    SourceLocator,
    TextBlock,
    XlsxRangeLocator,
)
from shared.ids import make_chunk_id

DOC = UUID("0b9f6c1e-3d2a-4c5b-8e7f-123456789abc")
LOCATOR = TypeAdapter(SourceLocator)

ALL_LOCATORS = [
    (PdfPageLocator(page=3), {"type": "pdf_page", "page": 3}),
    (DocxParaLocator(para_index=0), {"type": "docx_para", "para_index": 0}),
    (
        XlsxRangeLocator(sheet="销售数据", range="A1:C10"),
        {"type": "xlsx_range", "sheet": "销售数据", "range": "A1:C10"},
    ),
    (ImageLocator(image_id=str(DOC)), {"type": "image", "image_id": str(DOC)}),
]


# ---------- 来源定位 ----------


@pytest.mark.parametrize(("locator", "as_dict"), ALL_LOCATORS)
def test_locator_dict_shape_matches_spec(locator, as_dict):
    assert locator.model_dump() == as_dict


@pytest.mark.parametrize(("locator", "as_dict"), ALL_LOCATORS)
def test_locator_json_round_trip_keeps_concrete_type(locator, as_dict):
    restored = LOCATOR.validate_json(LOCATOR.dump_json(locator))
    assert restored == locator
    assert type(restored) is type(locator)
    # 从普通 dict（例如数据库 JSONB、OpenSearch 文档）也能还原
    assert LOCATOR.validate_python(as_dict) == locator


@pytest.mark.parametrize(("locator", "_"), ALL_LOCATORS)
def test_locator_round_trip_inside_parent_model(locator, _):
    block = TextBlock(text="正文", locator=locator)
    restored = TextBlock.model_validate_json(block.model_dump_json())
    assert restored == block
    assert type(restored.locator) is type(locator)


@pytest.mark.parametrize(
    "bad",
    [
        {"type": "pptx_slide", "slide": 1},  # 未知类型
        {"page": 1},  # 缺 type
        {"type": "pdf_page", "page": 0},  # 页码从 1 开始
        {"type": "pdf_page", "page": 1, "bbox": [0, 0, 1, 1]},  # 多余字段
        {"type": "docx_para", "para_index": -1},
        {"type": "docx_para", "para_index": 0, "page": 2},  # Word 不允许伪造页码
        {"type": "xlsx_range", "sheet": "", "range": "A1"},
        {"type": "xlsx_range", "sheet": "S", "range": "a1:b2"},
        {"type": "xlsx_range", "sheet": "S", "range": "A0"},
        {"type": "image", "image_id": "not-an-id"},
    ],
)
def test_invalid_locator_rejected(bad):
    with pytest.raises(ValidationError):
        LOCATOR.validate_python(bad)


def test_single_cell_and_embedded_image_accepted():
    assert LOCATOR.validate_python({"type": "xlsx_range", "sheet": "S", "range": "B2"})
    assert LOCATOR.validate_python({"type": "image", "image_id": f"{DOC}:img:2:0"})


def test_contracts_are_immutable():
    locator = PdfPageLocator(page=1)
    with pytest.raises(ValidationError):
        locator.page = 2


# ---------- ParsedDocument ----------


def test_parsed_document_round_trip():
    parsed = ParsedDocument(
        parser_name="pymupdf",
        parser_version="1.0",
        blocks=[
            TextBlock(text="第一页", locator=PdfPageLocator(page=1)),
            TextBlock(text="第三页", locator=PdfPageLocator(page=3)),
        ],
        ocr_targets=[PdfPageLocator(page=2)],
    )
    assert ParsedDocument.model_validate_json(parsed.model_dump_json()) == parsed


def test_parsed_document_may_be_empty():
    parsed = ParsedDocument(parser_name="image", parser_version="1.0")
    assert parsed.blocks == [] and parsed.ocr_targets == []


def test_ocr_targets_only_accept_pdf_page_or_image():
    with pytest.raises(ValidationError):
        ParsedDocument(
            parser_name="docx",
            parser_version="1.0",
            ocr_targets=[{"type": "docx_para", "para_index": 0}],
        )


# ---------- Chunk ----------


def _chunk(**overrides) -> Chunk:
    fields = dict(
        document_id=DOC,
        parse_version="v1",
        seq=4,
        source_type="body",
        text="一段正文",
        locator=PdfPageLocator(page=2),
    )
    fields.update(overrides)
    return Chunk.build(**fields)


def test_chunk_build_generates_deterministic_id():
    assert _chunk().chunk_id == make_chunk_id(DOC, "v1", 4)
    assert _chunk() == _chunk()


def test_chunk_round_trip():
    chunk = _chunk(source_type="ocr", locator=ImageLocator(image_id=str(DOC)))
    assert Chunk.model_validate_json(chunk.model_dump_json()) == chunk


def test_chunk_id_must_match_other_fields():
    data = _chunk().model_dump()
    data["seq"] = 5
    with pytest.raises(ValidationError, match="chunk_id"):
        Chunk.model_validate(data)


@pytest.mark.parametrize(
    "overrides", [{"source_type": "title"}, {"text": ""}, {"seq": -1}, {"parse_version": "a:b"}]
)
def test_invalid_chunk_rejected(overrides):
    with pytest.raises((ValidationError, ValueError)):
        _chunk(**overrides)


# ---------- OCRResult ----------


def _line(confidence: float = 0.93) -> OCRLine:
    box = (Point(x=0, y=0), Point(x=10, y=1), Point(x=10, y=6), Point(x=0, y=5))
    return OCRLine(text="发票", bbox=box, confidence=confidence)


def test_ocr_result_round_trip():
    result = OCRResult(
        document_id=DOC,
        locator=PdfPageLocator(page=2),
        lines=[_line()],
        model_name="PP-OCRv4_mobile",
        model_version="2.9",
    )
    assert OCRResult.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_ocr_confidence_out_of_range_rejected(confidence):
    with pytest.raises(ValidationError):
        _line(confidence)


def test_ocr_bbox_needs_four_points():
    with pytest.raises(ValidationError):
        OCRLine(text="x", bbox=[{"x": 0, "y": 0}, {"x": 1, "y": 1}], confidence=0.5)


def test_ocr_result_requires_model_info():
    with pytest.raises(ValidationError):
        OCRResult(document_id=DOC, locator=PdfPageLocator(page=1), model_name="", model_version="1")


# ---------- SearchHit ----------


def test_search_hit_round_trip():
    hit = SearchHit(
        document_id=DOC,
        score=0.0325,
        channels=[
            ChannelResult(channel="text", rank=1, score=12.5),
            ChannelResult(channel="image", rank=4, score=0.31),
        ],
        evidence=Evidence(
            chunk_id=make_chunk_id(DOC, "v1", 4),
            snippet="一段正文",
            source_type="body",
            locator=PdfPageLocator(page=2),
        ),
    )
    restored = SearchHit.model_validate_json(hit.model_dump_json())
    assert restored == hit
    assert isinstance(restored.evidence.locator, PdfPageLocator)


def test_search_hit_without_evidence_allowed():
    hit = SearchHit(
        document_id=DOC, score=1.0, channels=[ChannelResult(channel="meta", rank=1, score=3.2)]
    )
    assert hit.evidence is None


def test_search_hit_needs_at_least_one_channel():
    with pytest.raises(ValidationError):
        SearchHit(document_id=DOC, score=1.0, channels=[])


def test_search_hit_rejects_duplicate_channel():
    with pytest.raises(ValidationError, match="同一通道"):
        SearchHit(
            document_id=DOC,
            score=1.0,
            channels=[
                ChannelResult(channel="text", rank=1, score=1.0),
                ChannelResult(channel="text", rank=2, score=0.5),
            ],
        )


@pytest.mark.parametrize(
    "bad", [{"channel": "audio", "rank": 1, "score": 1}, {"channel": "text", "rank": 0, "score": 1}]
)
def test_invalid_channel_result_rejected(bad):
    with pytest.raises(ValidationError):
        ChannelResult.model_validate(bad)


@pytest.mark.parametrize(
    "targets", [{}, {"chunk_id": make_chunk_id(DOC, "v1", 0), "image_id": str(DOC)}]
)
def test_evidence_needs_exactly_one_target(targets):
    with pytest.raises(ValidationError, match="二者之一"):
        Evidence(locator=PdfPageLocator(page=1), **targets)
