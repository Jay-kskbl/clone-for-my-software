"""T09 🧪：PDF 解析器。fixtures：文本型、扫描型、混合型、加密、损坏。

测试用的 PDF 在运行时用 PyMuPDF 现场生成（见下面的 make_* 函数），不依赖外部文件，
每种文件长什么样在代码里一目了然。
"""

from pathlib import Path

import pymupdf
import pytest
from shared.contracts import ParsedDocument, PdfPageLocator

from app.modules.parsing import ParseError, parse_pdf
from app.modules.parsing.pdf import effective_char_count

OCR_MIN_CHARS = 20

PAGE_1 = "第一页：智能文档管理系统的设计目标是让扫描件和图片中的文字也能被检索。"
PAGE_2 = "Second page: BM25 is the baseline for full-text retrieval in this project."


def add_text_page(doc: pymupdf.Document, text: str) -> None:
    page = doc.new_page()
    # china-s 是 PyMuPDF 内置的简体中文字体，不需要系统字体或网络
    page.insert_textbox(pymupdf.Rect(50, 50, 550, 300), text, fontname="china-s", fontsize=12)


def add_scanned_page(doc: pymupdf.Document, caption: str | None = None) -> None:
    """整页是一张图片的页：扫描件就是这个结构。

    caption：有的扫描件带一点文本层，比如扫描软件加上的页码。
    """
    page = doc.new_page()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 100))
    pix.clear_with(200)
    page.insert_image(pymupdf.Rect(50, 50, 450, 250), pixmap=pix)
    if caption:
        page.insert_textbox(
            pymupdf.Rect(50, 700, 550, 750), caption, fontname="china-s", fontsize=12
        )


def save(doc: pymupdf.Document, path: Path, **kwargs) -> Path:
    doc.save(path, **kwargs)
    doc.close()
    return path


@pytest.fixture
def text_pdf(tmp_path) -> Path:
    doc = pymupdf.open()
    add_text_page(doc, PAGE_1)
    add_text_page(doc, PAGE_2)
    return save(doc, tmp_path / "text.pdf")


@pytest.fixture
def scanned_pdf(tmp_path) -> Path:
    doc = pymupdf.open()
    add_scanned_page(doc)
    add_scanned_page(doc)
    return save(doc, tmp_path / "scanned.pdf")


@pytest.fixture
def mixed_pdf(tmp_path) -> Path:
    """六页，每页一种情况：

    1 文本页；2 扫描页；3 带页码的扫描页（文本层只有“第3页”三个字）；
    4 只有一行短标题、没有图片的页；5 空白页；6 文本页。
    """
    doc = pymupdf.open()
    add_text_page(doc, PAGE_1)
    add_scanned_page(doc)
    add_scanned_page(doc, caption="第3页")
    add_text_page(doc, "附录")
    doc.new_page()
    add_text_page(doc, PAGE_2)
    return save(doc, tmp_path / "mixed.pdf")


def parse(path: Path, ocr_min_chars: int = OCR_MIN_CHARS) -> ParsedDocument:
    return parse_pdf(path, ocr_min_chars=ocr_min_chars)


def pages(locators) -> list[int]:
    return [loc.page for loc in locators]


# ---- 文本型 ----


def test_text_pdf_yields_one_block_per_page_with_page_locator(text_pdf):
    result = parse(text_pdf)

    assert result.parser_name == "pymupdf"
    assert result.parser_version == pymupdf.__version__
    assert [b.locator for b in result.blocks] == [PdfPageLocator(page=1), PdfPageLocator(page=2)]
    assert result.ocr_targets == []
    # 换行位置由排版决定，比较时去掉空白
    assert "".join(result.blocks[0].text.split()) == PAGE_1
    assert " ".join(result.blocks[1].text.split()) == PAGE_2


def test_result_round_trips_through_the_contract(text_pdf):
    result = parse(text_pdf)

    assert ParsedDocument.model_validate_json(result.model_dump_json()) == result


def test_parsing_is_deterministic(text_pdf):
    assert parse(text_pdf) == parse(text_pdf)


def test_text_has_no_nul_or_trailing_whitespace(text_pdf):
    for block in parse(text_pdf).blocks:
        assert "\x00" not in block.text
        assert block.text == block.text.strip()
        assert all(line == line.rstrip() for line in block.text.splitlines())


# ---- 扫描型 ----


def test_scanned_pdf_has_no_text_and_every_page_goes_to_ocr(scanned_pdf):
    result = parse(scanned_pdf)

    assert result.blocks == []
    assert result.ocr_targets == [PdfPageLocator(page=1), PdfPageLocator(page=2)]


# ---- 混合型 ----


def test_mixed_pdf_decides_page_by_page(mixed_pdf):
    result = parse(mixed_pdf)

    # 1、6：文本足够。4：只有两个字，但页面上没有别的东西，文本层就是全部内容，保留。
    # 2：扫描页。3：扫描页带页码，三个字低于阈值，不采用文本层，整页交给 OCR。
    # 5：空白页，两边都不进。
    assert pages(b.locator for b in result.blocks) == [1, 4, 6]
    assert pages(result.ocr_targets) == [2, 3]
    assert result.blocks[1].text == "附录"


def test_no_page_is_both_text_and_ocr(mixed_pdf):
    result = parse(mixed_pdf)

    assert set(pages(b.locator for b in result.blocks)).isdisjoint(pages(result.ocr_targets))


def test_short_text_only_page_is_never_dropped(tmp_path):
    # 回归：字数低于阈值、又没有图片的页曾被当成空白页整页丢掉
    doc = pymupdf.open()
    add_text_page(doc, "目录")
    path = save(doc, tmp_path / "title.pdf")

    result = parse(path, ocr_min_chars=10_000)

    assert [b.text for b in result.blocks] == ["目录"]
    assert result.ocr_targets == []


def test_blank_pdf_yields_nothing(tmp_path):
    doc = pymupdf.open()
    doc.new_page()
    doc.new_page()
    path = save(doc, tmp_path / "blank.pdf")

    result = parse(path)

    assert result.blocks == []
    assert result.ocr_targets == []


def test_threshold_comes_from_the_caller(mixed_pdf):
    # 阈值降到 3：带页码的扫描页（“第3页”恰好 3 个字）被当成有文本层
    lenient = parse(mixed_pdf, ocr_min_chars=3)
    assert pages(b.locator for b in lenient.blocks) == [1, 3, 4, 6]
    assert pages(lenient.ocr_targets) == [2]

    # 阈值再高一点：它回到 OCR
    assert pages(parse(mixed_pdf, ocr_min_chars=4).ocr_targets) == [2, 3]


def test_page_with_image_and_full_text_keeps_its_text_layer(tmp_path):
    # 图文混排的普通页：有图片，但文本层足够，不做 OCR
    doc = pymupdf.open()
    add_scanned_page(doc, caption=PAGE_1)
    path = save(doc, tmp_path / "illustrated.pdf")

    result = parse(path)

    assert pages(b.locator for b in result.blocks) == [1]
    assert result.ocr_targets == []


def test_effective_char_count_ignores_whitespace():
    assert effective_char_count("") == 0
    assert effective_char_count(" \n\t　 ") == 0
    assert effective_char_count("a b\n中 文") == 4


# ---- 加密 ----


def test_password_protected_pdf_is_rejected_with_clear_reason(tmp_path):
    doc = pymupdf.open()
    add_text_page(doc, PAGE_1)
    path = save(
        doc,
        tmp_path / "locked.pdf",
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        user_pw="secret",
        owner_pw="owner",
    )

    with pytest.raises(ParseError) as excinfo:
        parse(path)

    assert "加密" in excinfo.value.message
    assert excinfo.value.retryable is False


def test_owner_password_only_pdf_is_still_readable(tmp_path):
    # 只限制打印、复制等权限，没有设置打开口令：内容可以正常读取
    doc = pymupdf.open()
    add_text_page(doc, PAGE_1)
    path = save(
        doc,
        tmp_path / "restricted.pdf",
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw="owner",
        user_pw="",
    )

    result = parse(path)

    assert "".join(result.blocks[0].text.split()) == PAGE_1


# ---- 损坏 ----


@pytest.mark.parametrize(
    "content",
    [
        b"%PDF-1.7\nthis is not really a pdf\n",
        b"%PDF-1.7\n" + bytes(range(256)) * 20,
        b"",
    ],
    ids=["header-only", "binary-garbage", "empty"],
)
def test_corrupt_pdf_raises_parse_error(tmp_path, content):
    path = tmp_path / "broken.pdf"
    path.write_bytes(content)

    with pytest.raises(ParseError) as excinfo:
        parse(path)

    assert excinfo.value.retryable is False
    # 失败原因会展示给用户：不能带服务器上的路径
    assert str(tmp_path) not in excinfo.value.message


def test_truncated_pdf_either_parses_or_fails_cleanly(text_pdf, tmp_path):
    # 截掉后半个文件（丢了交叉引用表）。PyMuPDF 有时能修复、有时不能，
    # 两种结果都可以接受；不能接受的是抛出 ParseError 以外的异常或卡死
    data = text_pdf.read_bytes()
    path = tmp_path / "truncated.pdf"
    path.write_bytes(data[: len(data) // 2])

    try:
        result = parse(path)
    except ParseError:
        return
    assert isinstance(result, ParsedDocument)


def test_missing_file_raises_parse_error(tmp_path):
    with pytest.raises(ParseError):
        parse(tmp_path / "does-not-exist.pdf")


def test_non_pdf_content_is_not_parsed_as_something_else(tmp_path):
    # 一张 PNG 被当成 PDF 传进来：按 PDF 打开失败，而不是被库悄悄当成图片处理
    path = tmp_path / "image.pdf"
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 10, 10))
    pix.clear_with(255)
    path.write_bytes(pix.tobytes("png"))

    with pytest.raises(ParseError):
        parse(path)
