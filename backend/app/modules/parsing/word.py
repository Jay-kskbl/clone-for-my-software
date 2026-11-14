"""M5：Word（.docx）解析器。文件路径 → ParsedDocument，纯函数，不访问数据库和网络。

每个非空段落产出一个文本块，来源定位到段落（附录 A9）。python-docx 读不到页码
——Word 的分页是排版时才算出来的——所以不提供页码，也不伪造。

para_index 的定义（从 0 开始）：按文档顺序给正文里的每一个段落编号，
表格单元格里的段落也算在内（逐行、逐格、格内从上到下；嵌套表格同样展开）。
空段落占一个编号但不产出文本块，这样编号只取决于文档结构，不取决于哪些段落有字。

不提取的内容：页眉、页脚、脚注、批注、文本框，以及内容控件（sdt）里的段落。
内嵌图片的抽取属于 P4（附录 A17），所以 ocr_targets 永远为空。
"""

from pathlib import Path

import docx
from docx.document import Document
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph
from shared.contracts import DocxParaLocator, ParsedDocument, TextBlock

from app.modules.parsing.errors import ParseError
from app.modules.parsing.text import clean_text
from app.modules.parsing.zipguard import check_zip_limits

PARSER_NAME = "python-docx"


def _iter_paragraphs(container: Document | _Cell):
    """按文档顺序产出 container 里的全部段落，表格就地展开。"""
    for item in container.iter_inner_content():
        if isinstance(item, Paragraph):
            yield item
        elif isinstance(item, Table):
            for row in item.rows:
                # 直接取这一行在 XML 里真实存在的单元格。row.cells 会把横向合并的
                # 单元格按它跨的列数重复返回，同一段文字会被读出多遍。
                for tc in row._tr.tc_lst:
                    yield from _iter_paragraphs(_Cell(tc, item))


def parse_docx(path: Path, *, zip_max_total_bytes: int, zip_max_entries: int) -> ParsedDocument:
    """解析一个 .docx。

    zip_max_total_bytes / zip_max_entries：解压后总大小和文件数的上限
    （来自配置 PARSE_ZIP_MAX_TOTAL_BYTES、PARSE_ZIP_MAX_ENTRIES）。

    文件损坏、不是 Word 文档或超过上限时抛 ParseError。
    """
    check_zip_limits(path, max_total_bytes=zip_max_total_bytes, max_entries=zip_max_entries)

    try:
        # 传文件对象而不是路径：不让库根据文件名判断类型（存储层已按内容确认过）
        with path.open("rb") as f:
            document = docx.Document(f)
    except Exception as exc:  # noqa: BLE001 —— 库对损坏文件抛出的异常类型不固定
        raise ParseError(
            f"Word 文档无法打开，文件可能已损坏或不是 .docx（{type(exc).__name__}）"
        ) from exc

    blocks: list[TextBlock] = []
    try:
        for index, paragraph in enumerate(_iter_paragraphs(document)):
            text = clean_text(paragraph.text)
            if text:
                blocks.append(TextBlock(text=text, locator=DocxParaLocator(para_index=index)))
    except Exception as exc:  # noqa: BLE001
        # 结构损坏（包括表格嵌套过深导致的 RecursionError）：整个文件按失败处理，
        # 不返回读到一半的结果，否则用户会以为全文都已经可以检索。
        raise ParseError(f"Word 文档内容无法读取（{type(exc).__name__}）") from exc

    return ParsedDocument(parser_name=PARSER_NAME, parser_version=docx.__version__, blocks=blocks)
