"""T12 🧪：M7 切分。

- 切分后拼接覆盖原文（不丢字）；
- locator 正确（PDF 页、图片不合并；Word 定位到片段起始段落；Excel 是外接矩形）；
- 参数变化时 parse_version 变化。
"""

import re
import uuid

import docx
import openpyxl
import pytest
from parsing_helpers import ZIP_LIMITS
from shared.chunking import (
    ChunkingParams,
    chunk_blocks,
    chunk_document,
    make_parse_version,
    split_spans,
)
from shared.contracts import (
    Chunk,
    DocxParaLocator,
    ImageLocator,
    ParsedDocument,
    PdfPageLocator,
    TextBlock,
    XlsxRangeLocator,
)
from shared.ids import PARSE_VERSION_PATTERN, make_chunk_id, make_image_id

from app.modules.parsing import parse_docx, parse_xlsx

DOC = uuid.UUID("11111111-2222-4333-8444-555555555555")
PV = "c1-test"
SMALL = ChunkingParams(max_chars=60, overlap_chars=10)


def para(i: int, text: str) -> TextBlock:
    return TextBlock(text=text, locator=DocxParaLocator(para_index=i))


def row(sheet: str, cell_range: str, text: str) -> TextBlock:
    return TextBlock(text=text, locator=XlsxRangeLocator(sheet=sheet, range=cell_range))


def page(n: int, text: str) -> TextBlock:
    return TextBlock(text=text, locator=PdfPageLocator(page=n))


def parsed(*blocks: TextBlock) -> ParsedDocument:
    return ParsedDocument(parser_name="test", parser_version="1", blocks=list(blocks))


def chunk(*blocks: TextBlock, params: ChunkingParams = SMALL) -> list[Chunk]:
    return chunk_document(parsed(*blocks), document_id=DOC, parse_version=PV, params=params)


def assert_covers(text: str, pieces: list[str]) -> None:
    """pieces 依次覆盖 text 的全部内容。

    每段都是 text 的子串，前后相接或重叠，中间只允许跳过空白。
    """
    covered = 0
    previous = -1
    for piece in pieces:
        index = text.find(piece, previous + 1)
        assert index != -1, f"片段不是原文的子串：{piece!r}"
        assert index <= covered or text[covered:index].strip() == "", "片段之间漏掉了内容"
        previous = index
        covered = max(covered, index + len(piece))
    assert text[covered:].strip() == "", "末尾的内容没有被覆盖"


LONG_ZH = "".join(f"第{i}句话讲的是检索系统的一个细节。" for i in range(40))
LONG_EN = " ".join(f"word{i}" for i in range(300))


# ---- split_spans ----


def test_short_text_is_one_span():
    assert split_spans("短文本", max_chars=10, overlap_chars=2) == [(0, 3)]


@pytest.mark.parametrize("text", [LONG_ZH, LONG_EN, "x" * 1000, "a\nb" * 400])
@pytest.mark.parametrize(("max_chars", "overlap"), [(60, 10), (100, 0), (50, 25)])
def test_spans_reconstruct_the_text_exactly(text, max_chars, overlap):
    spans = split_spans(text, max_chars=max_chars, overlap_chars=overlap)

    assert spans[0][0] == 0
    assert spans[-1][1] == len(text)
    rebuilt = text[: spans[0][1]]
    for (s0, e0), (s1, e1) in zip(spans, spans[1:], strict=False):
        assert s0 < s1 <= e0, "下一段必须向前推进，且不能留下空隙"
        assert e0 - s1 <= overlap
        rebuilt += text[e0:e1]
    assert rebuilt == text
    assert all(e - s <= max_chars for s, e in spans)


def test_split_prefers_sentence_end_over_hard_cut():
    spans = split_spans(LONG_ZH, max_chars=60, overlap_chars=0)

    # 除最后一段外，每段都在句号处结束
    assert all(LONG_ZH[e - 1] == "。" for _, e in spans[:-1])


def test_split_prefers_newline_over_punctuation():
    # 只在窗口的后四分之一（这里是第 45–59 个字符）里找断点。
    # 换行和句号都在范围内时，取换行
    both = "甲" * 50 + "\n" + "乙" * 3 + "。" + "丙" * 30
    (first, *_rest) = split_spans(both, max_chars=60, overlap_chars=0)
    assert first == (0, 51)

    # 换行在范围之外（第 40 个字符）：不为了它把片段截得太短，取范围内的句号
    far = "甲" * 40 + "\n" + "乙" * 5 + "。" + "丙" * 30
    (first, *_rest) = split_spans(far, max_chars=60, overlap_chars=0)
    assert first == (0, 47)


def test_english_words_are_not_cut_in_the_middle():
    spans = split_spans(LONG_EN, max_chars=60, overlap_chars=0)

    for _, end in spans[:-1]:
        assert LONG_EN[end - 1] == " "


@pytest.mark.parametrize(("max_chars", "overlap"), [(0, 0), (10, 10), (10, -1)])
def test_invalid_split_parameters(max_chars, overlap):
    with pytest.raises(ValueError):
        split_spans("abc", max_chars=max_chars, overlap_chars=overlap)


def test_invalid_params_object():
    with pytest.raises(ValueError):
        ChunkingParams(max_chars=10, overlap_chars=10)


# ---- PDF 页与图片：不合并 ----


def test_pdf_pages_are_never_merged_even_when_short():
    chunks = chunk(page(1, "第一页"), page(2, "第二页"), page(5, "第五页"))

    assert [(c.locator, c.text) for c in chunks] == [
        (PdfPageLocator(page=1), "第一页"),
        (PdfPageLocator(page=2), "第二页"),
        (PdfPageLocator(page=5), "第五页"),
    ]
    assert all(c.source_type == "body" for c in chunks)


def test_long_page_is_split_and_every_piece_points_to_that_page():
    chunks = chunk(page(1, "短的一页"), page(2, LONG_ZH), page(3, "又一页"))

    on_page_2 = [c for c in chunks if c.locator == PdfPageLocator(page=2)]
    assert len(on_page_2) > 1
    assert all(len(c.text) <= SMALL.max_chars for c in chunks)
    assert_covers(LONG_ZH, [c.text for c in on_page_2])
    assert chunks[0].locator.page == 1 and chunks[-1].locator.page == 3


def test_ocr_text_of_an_image_is_chunked_as_ocr_with_the_image_locator():
    image = ImageLocator(image_id=make_image_id(DOC))
    blocks = [TextBlock(text=LONG_ZH, locator=image)]

    chunks = chunk_blocks(
        blocks, document_id=DOC, parse_version=PV, source_type="ocr", params=SMALL
    )

    assert len(chunks) > 1
    assert {c.locator for c in chunks} == {image}
    assert {c.source_type for c in chunks} == {"ocr"}
    assert_covers(LONG_ZH, [c.text for c in chunks])


# ---- Word：相邻段落合并，定位到起始段落 ----


def test_short_paragraphs_are_merged_and_located_at_the_first_one():
    chunks = chunk(para(0, "标题"), para(1, "第一段。"), para(3, "第三段。"))

    assert len(chunks) == 1
    assert chunks[0].text == "标题\n第一段。\n第三段。"
    assert chunks[0].locator == DocxParaLocator(para_index=0)


def test_paragraph_packing_respects_the_limit_and_overlaps_by_whole_paragraphs():
    texts = [f"第{i}段" + "字" * 15 for i in range(12)]  # 每段 18 或 19 个字
    blocks = [para(i, t) for i, t in enumerate(texts)]

    chunks = chunk(*blocks)

    assert len(chunks) > 1
    assert all(len(c.text) <= SMALL.max_chars for c in chunks)
    for c in chunks:
        # 每个片段由整段组成，并且定位到它的第一段
        lines = c.text.split("\n")
        assert all(line in texts for line in lines)
        assert c.locator.para_index == texts.index(lines[0])
    for before, after in zip(chunks, chunks[1:], strict=False):
        # 每段都超过重叠上限（10 字），所以不会被带到下一个片段：相邻片段不重复
        assert before.text.split("\n")[-1] != after.text.split("\n")[0]
    # 覆盖：每一段都出现在某个片段里
    assert all(any(t in c.text.split("\n") for c in chunks) for t in texts)


def test_short_trailing_paragraph_is_carried_over_as_overlap():
    blocks = [para(0, "甲" * 30), para(1, "乙" * 20), para(2, "丙丙"), para(3, "丁" * 30)]

    chunks = chunk(*blocks)

    # 第一个片段：甲 + 乙 + 丙（30+1+20+1+2=54）；丁放不下，开始新片段，
    # 末尾的“丙丙”（2 字 ≤ 重叠上限 10）带过去
    assert [c.text for c in chunks] == [
        "甲" * 30 + "\n" + "乙" * 20 + "\n丙丙",
        "丙丙\n" + "丁" * 30,
    ]
    assert [c.locator.para_index for c in chunks] == [0, 2]


def test_long_paragraph_is_split_on_its_own():
    chunks = chunk(para(0, "前言"), para(1, LONG_ZH), para(2, "结语"))

    assert chunks[0].text == "前言" and chunks[0].locator.para_index == 0
    assert chunks[-1].text == "结语" and chunks[-1].locator.para_index == 2
    middle = chunks[1:-1]
    assert {c.locator.para_index for c in middle} == {1}
    assert_covers(LONG_ZH, [c.text for c in middle])


# ---- Excel：同一工作表按行组合并，定位为外接矩形 ----


def test_rows_of_one_sheet_are_grouped_with_bounding_range():
    chunks = chunk(
        row("成绩", "B2:C2", "姓名\t分数"),
        row("成绩", "B3:C3", "张三\t95"),
        row("成绩", "B5:D5", "李四\t88\t备注"),
        row("成绩", "AB10", "远处"),
    )

    assert len(chunks) == 1
    assert chunks[0].text == "姓名\t分数\n张三\t95\n李四\t88\t备注\n远处"
    assert chunks[0].locator == XlsxRangeLocator(sheet="成绩", range="B2:AB10")


def test_rows_are_never_merged_across_sheets():
    chunks = chunk(row("一月", "A1", "房租"), row("二月", "A1", "水电"))

    assert [(c.locator.sheet, c.locator.range, c.text) for c in chunks] == [
        ("一月", "A1", "房租"),
        ("二月", "A1", "水电"),
    ]


def test_row_groups_cover_every_row_and_ranges_contain_their_rows():
    blocks = [row("表", f"A{r}:C{r}", f"第{r}行\t数据{r}\t" + "值" * 10) for r in range(1, 21)]

    chunks = chunk(*blocks)

    assert len(chunks) > 1
    for c in chunks:
        rows_in_chunk = [int(re.search(r"第(\d+)行", line).group(1)) for line in c.text.split("\n")]
        assert rows_in_chunk == list(range(rows_in_chunk[0], rows_in_chunk[-1] + 1))
        assert c.locator.range == f"A{rows_in_chunk[0]}:C{rows_in_chunk[-1]}"
    covered = {line for c in chunks for line in c.text.split("\n")}
    assert covered == {b.text for b in blocks}


def test_wide_columns_are_handled_in_the_bounding_range():
    chunks = chunk(row("S", "Z1", "a"), row("S", "AA2:AZ2", "b"), row("S", "XFD3", "c"))

    assert chunks[0].locator.range == "Z1:XFD3"


def test_long_row_is_split_with_its_own_range():
    chunks = chunk(row("S", "A1", "表头"), row("S", "A2:Z2", LONG_ZH))

    assert chunks[0].locator.range == "A1"
    assert {c.locator.range for c in chunks[1:]} == {"A2:Z2"}


# ---- 一般性质 ----


def test_mixed_locator_types_do_not_merge():
    chunks = chunk(para(0, "段落"), page(1, "页"), para(1, "又一段"))

    assert [c.text for c in chunks] == ["段落", "页", "又一段"]


def test_seq_and_chunk_id_are_contiguous_and_deterministic():
    blocks = [page(1, LONG_ZH), page(2, "二")]

    first = chunk_blocks(
        blocks, document_id=DOC, parse_version=PV, source_type="body", params=SMALL, seq_start=7
    )
    second = chunk_blocks(
        blocks, document_id=DOC, parse_version=PV, source_type="body", params=SMALL, seq_start=7
    )

    assert first == second
    assert [c.seq for c in first] == list(range(7, 7 + len(first)))
    assert [c.chunk_id for c in first] == [make_chunk_id(DOC, PV, c.seq) for c in first]


def test_empty_and_whitespace_blocks_produce_nothing():
    assert chunk() == []
    assert chunk(para(0, "有字"), para(1, "  \n ")) == chunk(para(0, "有字"))


def test_chunks_round_trip_through_the_contract():
    for c in chunk(page(1, LONG_ZH), row("S", "A1", "x"), para(0, "y")):
        assert Chunk.model_validate_json(c.model_dump_json()) == c


def test_default_size_keeps_ordinary_pages_whole():
    defaults = ChunkingParams(max_chars=500, overlap_chars=50)
    text = "这一页大约三百个字。" * 30

    chunks = chunk(page(1, text), params=defaults)

    assert [c.text for c in chunks] == [text]


# ---- 与真实解析器衔接 ----


def test_real_docx_paragraphs_are_all_covered(tmp_path):
    document = docx.Document()
    texts = [f"第{i}段：" + "这是正文内容。" * (i % 5 + 1) for i in range(30)]
    for t in texts:
        document.add_paragraph(t)
    document.add_paragraph(LONG_ZH)
    path = tmp_path / "doc.docx"
    document.save(path)
    result = parse_docx(path, **ZIP_LIMITS)

    chunks = chunk_document(result, document_id=DOC, parse_version=PV, params=SMALL)

    for block in result.blocks:
        holders = [c for c in chunks if block.text in c.text.split("\n")]
        if len(block.text) > SMALL.max_chars:
            pieces = [c.text for c in chunks if c.locator == block.locator]
            assert_covers(block.text, pieces)
        else:
            assert holders, f"段落没有出现在任何片段里：{block.text!r}"
            # 包含它的片段定位到它或它之前的段落
            assert all(c.locator.para_index <= block.locator.para_index for c in holders)


def test_real_xlsx_rows_are_all_covered(tmp_path):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "明细"
    sheet.append(["日期", "项目", "金额"])
    for i in range(40):
        sheet.append([f"2026-01-{i % 28 + 1:02d}", f"项目{i}", i * 10])
    other = workbook.create_sheet("汇总")
    other["B2"] = "合计"
    path = tmp_path / "book.xlsx"
    workbook.save(path)
    result = parse_xlsx(path, **ZIP_LIMITS)

    chunks = chunk_document(result, document_id=DOC, parse_version=PV, params=SMALL)

    lines = {(c.locator.sheet, line) for c in chunks for line in c.text.split("\n")}
    assert lines == {(b.locator.sheet, b.text) for b in result.blocks}
    assert chunks[-1].locator == XlsxRangeLocator(sheet="汇总", range="B2")


# ---- parse_version ----


def pv(**overrides) -> str:
    args = {
        "parser_name": "pymupdf",
        "parser_version": "1.28.2",
        "params": ChunkingParams(max_chars=500, overlap_chars=50),
        "parser_options": {"pdf_ocr_min_chars": 20},
    } | overrides
    return make_parse_version(**args)


def test_parse_version_is_deterministic_and_valid():
    version = pv()

    assert version == pv()
    assert re.fullmatch(PARSE_VERSION_PATTERN, version)
    assert len(version) <= 64
    assert version.startswith("c1-m500-o50-")
    # 能直接用来生成 chunk_id
    Chunk.build(
        document_id=DOC,
        parse_version=version,
        seq=0,
        source_type="body",
        text="x",
        locator=PdfPageLocator(page=1),
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"params": ChunkingParams(max_chars=400, overlap_chars=50)},
        {"params": ChunkingParams(max_chars=500, overlap_chars=0)},
        {"parser_version": "1.28.3"},
        {"parser_name": "python-docx"},
        {"parser_options": {"pdf_ocr_min_chars": 30}},
        {"parser_options": {}},
    ],
)
def test_parse_version_changes_when_anything_that_affects_chunks_changes(overrides):
    assert pv(**overrides) != pv()


def test_parse_version_does_not_depend_on_option_order():
    a = pv(parser_options={"x": 1, "y": "z"})
    b = pv(parser_options={"y": "z", "x": 1})

    assert a == b
