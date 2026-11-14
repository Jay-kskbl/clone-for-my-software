"""M5：Excel（.xlsx）解析器。文件路径 → ParsedDocument，纯函数，不访问数据库和网络。

每个有内容的行产出一个文本块：这一行的非空单元格从左到右用制表符连接，
来源定位到工作表和单元格范围（这一行第一个到最后一个非空单元格，如 B3:F3）。
按行组合并成检索片段是切分模块（M7）的事。

取值规则：
- 公式取 Excel 上次保存时缓存的计算结果，不取公式本身。文件如果不是由 Excel
  保存的（例如程序生成后从未用 Excel 打开过），公式单元格没有缓存值，会被当成空单元格。
- 数字、日期按值转成文本，不套用单元格的显示格式（“0.5” 不会变成 “50%”）。
- 合并单元格的内容只出现在左上角那一格。
- 隐藏的工作表照常提取；图表工作表没有单元格，不提取。
"""

import datetime
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter
from shared.contracts import ParsedDocument, TextBlock, XlsxRangeLocator

from app.modules.parsing.errors import ParseError
from app.modules.parsing.text import clean_text
from app.modules.parsing.zipguard import check_zip_limits

PARSER_NAME = "openpyxl"


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    # bool 是 int 的子类，必须先判断
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        # 2.0 写成 "2"；其余用最短的、能还原出同一个数的写法
        return str(int(value)) if value.is_integer() else repr(value)
    if isinstance(value, datetime.datetime):
        # 只有日期的单元格读出来是零点整的 datetime，不显示多余的 00:00:00
        if value.time() == datetime.time(0):
            return value.date().isoformat()
        return value.isoformat(sep=" ")
    if isinstance(value, datetime.date | datetime.time):
        return value.isoformat()
    return clean_text(str(value))


def _row_block(sheet: str, row_number: int, row) -> TextBlock | None:
    cells = [
        (col, text) for col, cell in enumerate(row, start=1) if (text := _cell_text(cell.value))
    ]
    if not cells:
        return None
    first = f"{get_column_letter(cells[0][0])}{row_number}"
    last = f"{get_column_letter(cells[-1][0])}{row_number}"
    return TextBlock(
        text="\t".join(text for _, text in cells),
        locator=XlsxRangeLocator(sheet=sheet, range=first if first == last else f"{first}:{last}"),
    )


def parse_xlsx(path: Path, *, zip_max_total_bytes: int, zip_max_entries: int) -> ParsedDocument:
    """解析一个 .xlsx。

    zip_max_total_bytes / zip_max_entries：解压后总大小和文件数的上限
    （来自配置 PARSE_ZIP_MAX_TOTAL_BYTES、PARSE_ZIP_MAX_ENTRIES）。

    文件损坏、不是 Excel 工作簿或超过上限时抛 ParseError。
    """
    check_zip_limits(path, max_total_bytes=zip_max_total_bytes, max_entries=zip_max_entries)

    blocks: list[TextBlock] = []
    try:
        # 传文件对象而不是路径：openpyxl 拿到路径时会先检查扩展名
        with path.open("rb") as f:
            # read_only：逐行流式读取，不把整张表建成对象放进内存
            workbook = openpyxl.load_workbook(f, read_only=True, data_only=True)
            try:
                for sheet in workbook.worksheets:
                    # 不采用文件里声明的表格范围：它可以被伪造成 A1:XFD1048576，
                    # 让每一行都被补齐到一万六千多个空单元格。重置后按实际存在的单元格读。
                    sheet.reset_dimensions()
                    for row_number, row in enumerate(sheet.iter_rows(), start=1):
                        block = _row_block(sheet.title, row_number, row)
                        if block is not None:
                            blocks.append(block)
            finally:
                workbook.close()
    except ParseError:
        raise
    except Exception as exc:  # noqa: BLE001 —— 库对损坏文件抛出的异常类型不固定
        # 读到一半才出错也整个按失败处理，不返回部分结果
        raise ParseError(
            f"Excel 工作簿无法读取，文件可能已损坏或不是 .xlsx（{type(exc).__name__}）"
        ) from exc

    return ParsedDocument(
        parser_name=PARSER_NAME, parser_version=openpyxl.__version__, blocks=blocks
    )
