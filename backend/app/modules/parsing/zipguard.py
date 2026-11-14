"""M5：打开 docx / xlsx 之前的 zip 检查（GLOBAL §7.2：限制解压后总大小和文件数）。

docx 和 xlsx 本质是 zip。一个几十 KB 的压缩包可以声称解压出几十 GB（zip 炸弹），
解析库会把里面的 XML 整个读进内存。所以在交给解析库之前先看一眼目录，超限就拒绝。

为什么只看目录里声明的大小就够：python-docx 和 openpyxl 都通过标准库 zipfile 读取条目，
而 zipfile 读一个条目时最多只吐出目录里声明的字节数（声明小、实际大的条目会在声明处截断，
随后 CRC 校验失败）。因此“声明大小之和”就是解析库实际可能读入的上限。
多个目录项指向同一段数据的重叠式炸弹，每个目录项都要计一次，同样被这个总和拦住。
"""

import zipfile
from pathlib import Path

from app.modules.parsing.errors import ParseError

# 通用标志位的第 0 位：条目已加密
_FLAG_ENCRYPTED = 0x1


def check_zip_limits(path: Path, *, max_total_bytes: int, max_entries: int) -> None:
    """path 不是完好的 zip，或解压后的规模超过上限时抛 ParseError（不可重试）。"""
    try:
        with zipfile.ZipFile(path) as zf:
            entries = zf.infolist()
    except (zipfile.BadZipFile, OSError, EOFError, ValueError, NotImplementedError) as exc:
        raise ParseError(f"文件不是完好的 zip 压缩包，可能已损坏（{type(exc).__name__}）") from exc

    if len(entries) > max_entries:
        raise ParseError(f"压缩包内有 {len(entries)} 个文件，超过上限 {max_entries} 个，拒绝解析")
    if any(info.flag_bits & _FLAG_ENCRYPTED for info in entries):
        raise ParseError("压缩包内有加密的内容，无法解析")

    total = sum(info.file_size for info in entries)
    if total > max_total_bytes:
        raise ParseError(
            f"解压后共 {total} 字节，超过上限 {max_total_bytes} 字节，拒绝解析（可能是 zip 炸弹）"
        )
