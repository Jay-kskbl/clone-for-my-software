"""T11 🧪：Word 解析器。fixtures：纯段落文档、带表格的文档、畸形文件（损坏、炸弹、冒充）。

测试用的 .docx 在运行时用 python-docx 现场生成，不依赖外部文件。
"""

from pathlib import Path

import docx
import openpyxl
import pytest
from parsing_helpers import ZIP_LIMITS, forge_declared_size, rewrite_zip
from shared.contracts import DocxParaLocator, ParsedDocument

from app.modules.parsing import ParseError, parse_docx

TITLE = "智能文档管理系统设计说明"
PARA_1 = "本系统支持 Word、PDF、Excel 和图片的上传与检索。"
PARA_2 = "BM25 is the baseline for full-text retrieval."


@pytest.fixture
def plain_docx(tmp_path) -> Path:
    """段落序号：0 标题，1 正文，2 空段落，3 正文。"""
    document = docx.Document()
    document.add_heading(TITLE, level=1)
    document.add_paragraph(PARA_1)
    document.add_paragraph("")
    document.add_paragraph(PARA_2)
    path = tmp_path / "plain.docx"
    document.save(path)
    return path


@pytest.fixture
def table_docx(tmp_path) -> Path:
    """正文中间夹一张 2×3 的表格，第一行后两格横向合并。段落序号：

    0 “表格之前”
    表格第一行：1 “姓名”，2 “备注（合并）”
    表格第二行：3 “张三”，4 “李四”，5 “第一行” + 6 “第二行”（同一格里两个段落）
    7 “表格之后”
    """
    document = docx.Document()
    document.add_paragraph("表格之前")
    table = document.add_table(rows=2, cols=3)
    table.cell(0, 0).text = "姓名"
    table.cell(0, 1).merge(table.cell(0, 2)).text = "备注（合并）"
    table.cell(1, 0).text = "张三"
    table.cell(1, 1).text = "李四"
    table.cell(1, 2).text = "第一行"
    table.cell(1, 2).add_paragraph("第二行")
    document.add_paragraph("表格之后")
    path = tmp_path / "table.docx"
    document.save(path)
    return path


def parse(path: Path, **overrides) -> ParsedDocument:
    return parse_docx(path, **{**ZIP_LIMITS, **overrides})


def as_pairs(result: ParsedDocument) -> list[tuple[int, str]]:
    return [(b.locator.para_index, b.text) for b in result.blocks]


# ---- 纯段落 ----


def test_each_non_empty_paragraph_is_a_block_with_paragraph_locator(plain_docx):
    result = parse(plain_docx)

    assert result.parser_name == "python-docx"
    assert result.parser_version == docx.__version__
    # 空段落（序号 2）不产出文本块，但占着编号
    assert as_pairs(result) == [(0, TITLE), (1, PARA_1), (3, PARA_2)]
    assert all(isinstance(b.locator, DocxParaLocator) for b in result.blocks)


def test_word_never_produces_ocr_targets_or_page_numbers(plain_docx):
    result = parse(plain_docx)

    assert result.ocr_targets == []
    # 附录 A9：Word 只到段落级，定位里没有页码字段
    assert set(result.blocks[0].locator.model_dump()) == {"type", "para_index"}


def test_result_round_trips_through_the_contract(table_docx):
    result = parse(table_docx)

    assert ParsedDocument.model_validate_json(result.model_dump_json()) == result


def test_parsing_is_deterministic(table_docx):
    assert parse(table_docx) == parse(table_docx)


def test_text_is_cleaned(tmp_path):
    document = docx.Document()
    document.add_paragraph("  前后有空白  \t")
    document.add_paragraph(" \t ")
    paragraph = document.add_paragraph("第一行")
    paragraph.add_run().add_break()
    paragraph.add_run("第二行")
    path = tmp_path / "ws.docx"
    document.save(path)

    # 只有空白的段落（序号 1）视为空；段内换行保留
    assert as_pairs(parse(path)) == [(0, "前后有空白"), (2, "第一行\n第二行")]


def test_empty_document_yields_no_blocks(tmp_path):
    path = tmp_path / "empty.docx"
    docx.Document().save(path)

    result = parse(path)

    assert result.blocks == []
    assert result.ocr_targets == []


# ---- 表格 ----


def test_table_cells_are_read_in_document_order(table_docx):
    assert as_pairs(parse(table_docx)) == [
        (0, "表格之前"),
        (1, "姓名"),
        (2, "备注（合并）"),
        (3, "张三"),
        (4, "李四"),
        (5, "第一行"),
        (6, "第二行"),
        (7, "表格之后"),
    ]


def test_merged_cell_text_is_not_repeated(table_docx):
    texts = [b.text for b in parse(table_docx).blocks]

    assert texts.count("备注（合并）") == 1


def test_nested_table_is_expanded_in_place(tmp_path):
    document = docx.Document()
    outer = document.add_table(rows=1, cols=2)
    outer.cell(0, 0).text = "外层"
    inner = outer.cell(0, 1).add_table(rows=1, cols=1)
    inner.cell(0, 0).text = "内层"
    path = tmp_path / "nested.docx"
    document.save(path)

    assert [b.text for b in parse(path).blocks] == ["外层", "内层"]


# ---- 畸形文件 ----


def test_docx_zip_bomb_is_rejected_before_parsing(plain_docx, tmp_path):
    # 一个正常的 docx，里面多塞了一个解压后 8 MB 的条目
    bomb = rewrite_zip(
        plain_docx, tmp_path / "bomb.docx", add={"word/media/pad.bin": b"\x00" * (8 * 1024 * 1024)}
    )
    assert bomb.stat().st_size < 200 * 1024

    with pytest.raises(ParseError, match="超过上限") as excinfo:
        parse(bomb)
    assert excinfo.value.retryable is False


def test_docx_with_too_many_entries_is_rejected(plain_docx, tmp_path):
    crowded = rewrite_zip(
        plain_docx, tmp_path / "crowded.docx", add={f"junk/{i}.xml": b"" for i in range(300)}
    )

    with pytest.raises(ParseError, match="超过上限"):
        parse(crowded)


def test_limits_come_from_the_caller(plain_docx):
    with pytest.raises(ParseError, match="超过上限"):
        parse(plain_docx, zip_max_total_bytes=100)
    with pytest.raises(ParseError, match="超过上限"):
        parse(plain_docx, zip_max_entries=1)


def test_entry_lying_about_its_size_cannot_smuggle_data_past_the_limit(plain_docx, tmp_path):
    # 目录里谎报“解压后只有 10 字节”，总大小检查因此放行；
    # 但读取时最多只吐出声明的 10 字节，随后校验失败——多出来的数据进不了内存
    liar = rewrite_zip(plain_docx, tmp_path / "liar.docx")
    forge_declared_size(liar, "word/document.xml", 10)

    with pytest.raises(ParseError, match="无法打开"):
        parse(liar)


def test_truncated_docx_is_rejected(plain_docx, tmp_path):
    data = plain_docx.read_bytes()
    path = tmp_path / "cut.docx"
    path.write_bytes(data[: len(data) // 2])

    with pytest.raises(ParseError, match="不是完好的 zip"):
        parse(path)


def test_docx_with_broken_xml_is_rejected(plain_docx, tmp_path):
    broken = rewrite_zip(
        plain_docx, tmp_path / "badxml.docx", replace={"word/document.xml": b"<w:document><oops"}
    )

    with pytest.raises(ParseError, match="无法打开"):
        parse(broken)


def test_docx_missing_its_main_part_is_rejected(plain_docx, tmp_path):
    hollow = rewrite_zip(plain_docx, tmp_path / "hollow.docx", drop={"word/document.xml"})

    with pytest.raises(ParseError, match="无法打开"):
        parse(hollow)


def test_xlsx_passed_as_docx_is_rejected(tmp_path):
    path = tmp_path / "actually.xlsx"
    openpyxl.Workbook().save(path)

    with pytest.raises(ParseError, match="无法打开"):
        parse(path)


def test_error_message_does_not_leak_the_server_path(plain_docx, tmp_path):
    hollow = rewrite_zip(plain_docx, tmp_path / "hollow.docx", drop={"word/document.xml"})

    with pytest.raises(ParseError) as excinfo:
        parse(hollow)
    assert str(tmp_path) not in excinfo.value.message
    assert "hollow" not in excinfo.value.message
