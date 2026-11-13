"""M5：PDF 解析器。文件路径 → ParsedDocument，纯函数，不访问数据库和网络。

每一页产出至多一个文本块，来源定位到页（附录 A9）。

按页判断是否需要 OCR（GLOBAL §2 P1）。一页的有效字符数记为 n，阈值记为 ocr_min_chars：

    n ≥ 阈值                      → 采用文本层
    n < 阈值，页面上有图片或图形  → 这一页交给 OCR，不采用文本层
    n < 阈值，页面上没有图片和图形 → n > 0 时采用文本层；n = 0 是空白页，跳过

第二种情况是扫描件（整页是一张图，文本层为空或只有页码之类的零星字符）。
OCR 会把整页渲染成图片再识别，页面上原有的少量文字不会丢。
第三种情况是只有一行标题之类的短页：页面上除了这点文字什么都没有，
OCR 不会比文本层读到更多，所以直接用文本层，不能因为字数少就把它丢掉。
"""

from pathlib import Path

import pymupdf
from shared.contracts import ParsedDocument, PdfPageLocator, TextBlock

from app.modules.parsing.errors import ParseError

PARSER_NAME = "pymupdf"


def effective_char_count(text: str) -> int:
    """有效字符数：不计空白字符。扫描件的文本层常常只有零星的空格和换行。"""
    return sum(1 for ch in text if not ch.isspace())


def _clean(text: str) -> str:
    # 去掉空字符（PostgreSQL 的 text 类型不能保存它）和每行末尾的空白
    lines = [line.rstrip() for line in text.replace("\x00", "").splitlines()]
    return "\n".join(lines).strip()


def _has_graphics(page: pymupdf.Page) -> bool:
    """页面上有图片或矢量图形：可能有文本层之外、只有 OCR 才能读到的内容。"""
    return bool(page.get_images()) or bool(page.get_drawings())


def _open(path: Path) -> pymupdf.Document:
    try:
        # filetype="pdf"：按 PDF 打开，不让库根据扩展名去猜（存储层已按魔数确认过类型）
        doc = pymupdf.open(path, filetype="pdf")
    except Exception as exc:  # noqa: BLE001 —— 库对损坏文件抛出的异常类型不固定
        raise ParseError(f"PDF 无法打开，文件可能已损坏（{type(exc).__name__}）") from exc

    # 库会按内容再判断一次格式：一张图片即使被当作 PDF 传进来，也会被它当成图片打开。
    # 本函数只解析 PDF，其他格式一律拒绝。
    if not doc.is_pdf:
        doc.close()
        raise ParseError("文件不是 PDF")

    # needs_pass：需要口令才能读取内容。只设了“所有者口令”（限制打印、复制）的 PDF
    # 不需要口令就能读，needs_pass 为假，照常解析。
    if doc.needs_pass:
        doc.close()
        raise ParseError("PDF 已加密，需要口令才能读取，无法解析")
    return doc


def parse_pdf(path: Path, *, ocr_min_chars: int) -> ParsedDocument:
    """解析一个 PDF。

    ocr_min_chars：一页的有效字符数低于它时，这一页走 OCR（来自配置 PDF_OCR_MIN_CHARS，
    是需要随实验结果一起记录的参数）。

    文件损坏、加密或没有任何页时抛 ParseError。
    """
    doc = _open(path)
    try:
        if doc.page_count == 0:
            raise ParseError("PDF 中没有任何页")

        blocks: list[TextBlock] = []
        ocr_targets: list[PdfPageLocator] = []
        for index in range(doc.page_count):
            locator = PdfPageLocator(page=index + 1)
            try:
                page = doc.load_page(index)
                text = _clean(page.get_text("text"))
                chars = effective_char_count(text)
                if chars >= ocr_min_chars:
                    blocks.append(TextBlock(text=text, locator=locator))
                elif _has_graphics(page):
                    ocr_targets.append(locator)
                elif chars > 0:
                    blocks.append(TextBlock(text=text, locator=locator))
            except ParseError:
                raise
            except Exception as exc:  # noqa: BLE001
                # 某一页的结构坏了：整个文件按失败处理，原因里写明是哪一页。
                # 不悄悄跳过这一页，否则用户会以为全文都已经可以检索。
                raise ParseError(f"PDF 第 {index + 1} 页无法解析（{type(exc).__name__}）") from exc

        return ParsedDocument(
            parser_name=PARSER_NAME,
            parser_version=pymupdf.__version__,
            blocks=blocks,
            ocr_targets=ocr_targets,
        )
    finally:
        doc.close()
