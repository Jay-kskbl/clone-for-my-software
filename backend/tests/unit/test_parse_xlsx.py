"""T11 🧪：Excel 解析器。fixtures：单表工作簿、多表工作簿、畸形文件（损坏、炸弹、伪造范围、冒充）。

测试用的 .xlsx 在运行时用 openpyxl 现场生成，不依赖外部文件。
"""

import datetime
import re
import zipfile
from pathlib import Path

import docx
import openpyxl
import pytest
from parsing_helpers import ZIP_LIMITS, rewrite_zip
from shared.contracts import ParsedDocument, XlsxRangeLocator

from app.modules.parsing import ParseError, parse_xlsx

SHEET_XML = "xl/worksheets/sheet1.xml"


@pytest.fixture
def grades_xlsx(tmp_path) -> Path:
    """一张表，数据不从 A1 开始，中间有空行，有一格离得很远。"""
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "成绩"
    sheet["B2"], sheet["C2"] = "姓名", "分数"
    sheet["B3"], sheet["C3"] = "张三", 95
    sheet["B5"], sheet["C5"] = "李四", 88.5
    sheet["AB10"] = "备注"
    path = tmp_path / "grades.xlsx"
    workbook.save(path)
    return path


@pytest.fixture
def multi_sheet_xlsx(tmp_path) -> Path:
    """三张表：有数据的、空的、隐藏的。"""
    workbook = openpyxl.Workbook()
    first = workbook.active
    first.title = "一月"
    first.append(["项目", "金额"])
    first.append(["房租", 3000])
    workbook.create_sheet("空表")
    hidden = workbook.create_sheet("隐藏表")
    hidden["A1"] = "隐藏的内容"
    hidden.sheet_state = "hidden"
    path = tmp_path / "multi.xlsx"
    workbook.save(path)
    return path


def parse(path: Path, **overrides) -> ParsedDocument:
    return parse_xlsx(path, **{**ZIP_LIMITS, **overrides})


def as_triples(result: ParsedDocument) -> list[tuple[str, str, str]]:
    return [(b.locator.sheet, b.locator.range, b.text) for b in result.blocks]


def single_row(tmp_path, values: list) -> str:
    workbook = openpyxl.Workbook()
    workbook.active.append(values)
    path = tmp_path / "row.xlsx"
    workbook.save(path)
    (block,) = parse(path).blocks
    return block.text


# ---- 单表 ----


def test_each_non_empty_row_is_a_block_with_sheet_and_range(grades_xlsx):
    result = parse(grades_xlsx)

    assert result.parser_name == "openpyxl"
    assert result.parser_version == openpyxl.__version__
    # 范围是这一行第一个到最后一个非空单元格；空行（1、4、6–9）不产出文本块；
    # 只有一个单元格的行，范围就是那一格
    assert as_triples(result) == [
        ("成绩", "B2:C2", "姓名\t分数"),
        ("成绩", "B3:C3", "张三\t95"),
        ("成绩", "B5:C5", "李四\t88.5"),
        ("成绩", "AB10", "备注"),
    ]
    assert all(isinstance(b.locator, XlsxRangeLocator) for b in result.blocks)
    assert result.ocr_targets == []


def test_result_round_trips_through_the_contract(grades_xlsx):
    result = parse(grades_xlsx)

    assert ParsedDocument.model_validate_json(result.model_dump_json()) == result


def test_parsing_is_deterministic(grades_xlsx):
    assert parse(grades_xlsx) == parse(grades_xlsx)


def test_cell_values_are_rendered_as_text(tmp_path):
    text = single_row(
        tmp_path,
        [
            "文字",
            7,
            2.0,
            0.5,
            True,
            False,
            datetime.datetime(2026, 1, 2),
            datetime.datetime(2026, 1, 2, 8, 30),
            datetime.time(8, 30),
        ],
    )

    assert text.split("\t") == [
        "文字",
        "7",
        "2",
        "0.5",
        "TRUE",
        "FALSE",
        "2026-01-02",
        "2026-01-02 08:30:00",
        "08:30:00",
    ]


def test_blank_and_whitespace_cells_are_skipped(tmp_path):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet["A1"], sheet["B1"], sheet["C1"], sheet["D1"] = "左", "  ", None, " 右 "
    sheet["A2"] = " \n "
    path = tmp_path / "blank.xlsx"
    workbook.save(path)

    # B1 只有空白，视为空；范围仍然从 A1 到 D1。第 2 行只有空白，整行跳过
    assert as_triples(parse(path)) == [("Sheet", "A1:D1", "左\t右")]


def test_merged_cell_appears_once(tmp_path):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet["B2"] = "合并的标题"
    sheet.merge_cells("B2:D3")
    path = tmp_path / "merged.xlsx"
    workbook.save(path)

    assert as_triples(parse(path)) == [("Sheet", "B2", "合并的标题")]


def test_formula_without_cached_value_is_treated_as_empty(tmp_path):
    # openpyxl 写出的公式没有缓存结果（只有 Excel 保存时才会写入）。
    # 解析器取值不取公式，所以这一格为空，而不是把 "=A1*2" 当正文
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet["A1"], sheet["B1"] = 21, "=A1*2"
    path = tmp_path / "formula.xlsx"
    workbook.save(path)

    assert as_triples(parse(path)) == [("Sheet", "A1", "21")]


def test_formula_with_cached_value_yields_the_value(tmp_path):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet["A1"], sheet["B1"] = 21, "=A1*2"
    plain = tmp_path / "formula.xlsx"
    workbook.save(plain)
    # 模拟 Excel 保存后的样子：公式旁边带着上次算出的结果 <v>42</v>
    with zipfile.ZipFile(plain) as zf:
        xml = zf.read(SHEET_XML)
    assert xml.count(b"<f>A1*2</f><v></v>") == 1
    patched = xml.replace(b"<f>A1*2</f><v></v>", b"<f>A1*2</f><v>42</v>")
    cached = rewrite_zip(plain, tmp_path / "cached.xlsx", replace={SHEET_XML: patched})

    assert as_triples(parse(cached)) == [("Sheet", "A1:B1", "21\t42")]


def test_empty_workbook_yields_no_blocks(tmp_path):
    path = tmp_path / "empty.xlsx"
    openpyxl.Workbook().save(path)

    assert parse(path).blocks == []


# ---- 多表 ----


def test_sheets_are_read_in_workbook_order_including_hidden_ones(multi_sheet_xlsx):
    assert as_triples(parse(multi_sheet_xlsx)) == [
        ("一月", "A1:B1", "项目\t金额"),
        ("一月", "A2:B2", "房租\t3000"),
        ("隐藏表", "A1", "隐藏的内容"),
    ]


# ---- 畸形文件 ----


def test_xlsx_zip_bomb_is_rejected_before_parsing(grades_xlsx, tmp_path):
    bomb = rewrite_zip(
        grades_xlsx, tmp_path / "bomb.xlsx", add={"xl/media/pad.bin": b"\x00" * (8 * 1024 * 1024)}
    )
    assert bomb.stat().st_size < 200 * 1024

    with pytest.raises(ParseError, match="超过上限") as excinfo:
        parse(bomb)
    assert excinfo.value.retryable is False


def test_limits_come_from_the_caller(grades_xlsx):
    with pytest.raises(ParseError, match="超过上限"):
        parse(grades_xlsx, zip_max_total_bytes=100)
    with pytest.raises(ParseError, match="超过上限"):
        parse(grades_xlsx, zip_max_entries=1)


def test_forged_sheet_dimension_does_not_blow_up_the_row_width(grades_xlsx, tmp_path):
    # 声明的范围被改成整张表（16384 列 × 1048576 行），并在最右下角放一个单元格。
    # 如果照声明的范围补空单元格，每一行都要造一万六千多个对象
    with zipfile.ZipFile(grades_xlsx) as zf:
        xml = zf.read(SHEET_XML)
    xml, count = re.subn(rb'<dimension ref="[^"]*"', b'<dimension ref="A1:XFD1048576"', xml)
    assert count == 1
    xml = xml.replace(
        b"</sheetData>",
        b'<row r="1048576"><c r="XFD1048576" t="inlineStr"><is><t>END</t></is></c></row>'
        b"</sheetData>",
    )
    forged = rewrite_zip(grades_xlsx, tmp_path / "forged.xlsx", replace={SHEET_XML: xml})

    result = parse(forged)

    assert len(result.blocks) == 5
    assert as_triples(result)[-1] == ("成绩", "XFD1048576", "END")


def test_truncated_xlsx_is_rejected(grades_xlsx, tmp_path):
    data = grades_xlsx.read_bytes()
    path = tmp_path / "cut.xlsx"
    path.write_bytes(data[: len(data) // 2])

    with pytest.raises(ParseError, match="不是完好的 zip"):
        parse(path)


def test_xlsx_with_broken_sheet_xml_is_rejected(grades_xlsx, tmp_path):
    broken = rewrite_zip(
        grades_xlsx, tmp_path / "badxml.xlsx", replace={SHEET_XML: b"<worksheet><sheetData><row"}
    )

    with pytest.raises(ParseError, match="无法读取"):
        parse(broken)


def test_xlsx_missing_its_workbook_part_is_rejected(grades_xlsx, tmp_path):
    hollow = rewrite_zip(grades_xlsx, tmp_path / "hollow.xlsx", drop={"xl/workbook.xml"})

    with pytest.raises(ParseError, match="无法读取"):
        parse(hollow)


def test_docx_passed_as_xlsx_is_rejected(tmp_path):
    path = tmp_path / "actually.docx"
    docx.Document().save(path)

    with pytest.raises(ParseError, match="无法读取"):
        parse(path)


def test_file_name_and_extension_are_not_trusted_or_required(grades_xlsx, tmp_path):
    # 存储层按内容识别类型，解析器不应依赖扩展名
    renamed = tmp_path / "no_extension"
    renamed.write_bytes(grades_xlsx.read_bytes())

    assert parse(renamed) == parse(grades_xlsx)


def test_error_message_does_not_leak_the_server_path(grades_xlsx, tmp_path):
    hollow = rewrite_zip(grades_xlsx, tmp_path / "hollow.xlsx", drop={"xl/workbook.xml"})

    with pytest.raises(ParseError) as excinfo:
        parse(hollow)
    assert str(tmp_path) not in excinfo.value.message
    assert "hollow" not in excinfo.value.message
