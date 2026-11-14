"""M5：图片（PNG / JPEG）“解析器”。纯函数，不访问数据库和网络。

图片里的文字要靠 OCR（M6）才能读出来，所以这里不产出任何文本块，只做两件事：
1. 读出像素尺寸（写入 image_assets 表）；
2. 确认图片完整、能解码、尺寸在上限以内，然后把它登记为一个 OCR 对象。

先读文件头里的尺寸、检查上限，之后才解码：一张压缩后只有几 KB 的图片
可以声称有几十亿像素，直接解码会吃光内存（与 zip 炸弹同理）。
"""

import struct
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from shared.contracts import ImageLocator, ParsedDocument

from app.modules.parsing.errors import ParseError

PARSER_NAME = "pymupdf"

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8"
# JPEG 里记录图像尺寸的段（SOF0–SOF15）。0xC4、0xC8、0xCC 编号相邻但不是 SOF。
_JPEG_SOF_MARKERS = frozenset(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}
# 这些标记后面没有长度字段
_JPEG_STANDALONE_MARKERS = frozenset(range(0xD0, 0xDA)) | {0x01}
_JPEG_SOS = 0xDA  # 图像数据从这里开始
_JPEG_EOI = b"\xff\xd9"  # 图像结束


@dataclass(frozen=True)
class ImageInfo:
    width: int
    height: int


def _png_size(data: bytes) -> tuple[int, int]:
    # 8 字节魔数 + 4 字节长度 + "IHDR" + 宽 4 字节 + 高 4 字节
    if len(data) < 24 or data[12:16] != b"IHDR":
        raise ParseError("PNG 图片的文件头不完整")
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def _jpeg_scan(data: bytes) -> tuple[int, int, int]:
    """逐段走过 JPEG 的文件头，返回（宽，高，图像数据开始的位置）。

    按段长度跳着走，所以 EXIF 里内嵌的缩略图（它自己也是一个完整的 JPEG）会被整段跳过，
    不会把缩略图的尺寸和结束标记当成正图的。
    """
    size: tuple[int, int] | None = None
    pos = 2
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            raise ParseError("JPEG 图片的结构已损坏")
        marker = data[pos + 1]
        if marker == 0xFF:  # 填充字节
            pos += 1
            continue
        if marker in _JPEG_STANDALONE_MARKERS:
            pos += 2
            continue
        (length,) = struct.unpack(">H", data[pos + 2 : pos + 4])
        if length < 2:
            raise ParseError("JPEG 图片的结构已损坏")
        if marker in _JPEG_SOF_MARKERS and size is None:
            # 长度 2 字节 + 精度 1 字节 + 高 2 字节 + 宽 2 字节
            if pos + 9 > len(data):
                break
            height, width = struct.unpack(">HH", data[pos + 5 : pos + 9])
            size = (width, height)
        if marker == _JPEG_SOS:
            if size is None:
                break
            return size[0], size[1], pos
        pos += 2 + length
    raise ParseError("JPEG 图片的文件头不完整，文件可能已损坏或被截断")


def read_image_info(path: Path, *, max_pixels: int) -> ImageInfo:
    """读出图片的像素尺寸，并确认它完整、可解码、不超过 max_pixels。

    尺寸是文件里存储的宽和高，不考虑 EXIF 的旋转标记。
    不是 PNG / JPEG、文件不完整、无法解码或像素数超限时抛 ParseError。
    """
    data = path.read_bytes()
    if data.startswith(_PNG_MAGIC):
        width, height = _png_size(data)
        # 完整的 PNG 以 IEND 块结尾
        complete = b"IEND" in data[-16:]
    elif data.startswith(_JPEG_MAGIC):
        width, height, data_start = _jpeg_scan(data)
        # 完整的 JPEG 在图像数据之后有结束标记。有的相机会在它后面再附加数据，
        # 所以不要求它在文件最末尾；图像数据内部不会出现这两个字节（编码时已转义）。
        complete = data.find(_JPEG_EOI, data_start) != -1
    else:
        raise ParseError("文件不是 PNG 或 JPEG 图片")

    if width < 1 or height < 1:
        raise ParseError("图片的宽或高为 0")
    if width * height > max_pixels:
        raise ParseError(f"图片尺寸为 {width}×{height}，像素数超过上限 {max_pixels}，拒绝处理")
    # 解码器对截断的文件很宽容（缺的部分补成灰色），所以完整性要单独判断
    if not complete:
        raise ParseError("图片文件不完整（缺少结束标记），可能在传输中被截断")

    try:
        pixmap = pymupdf.Pixmap(data)
        decoded = (pixmap.width, pixmap.height)
    except Exception as exc:  # noqa: BLE001 —— 库对损坏文件抛出的异常类型不固定
        raise ParseError(f"图片无法解码，文件可能已损坏（{type(exc).__name__}）") from exc
    if decoded != (width, height):
        raise ParseError("图片文件头声明的尺寸与实际内容不一致")

    return ImageInfo(width=width, height=height)


def parse_image(path: Path, *, image_id: str, max_pixels: int) -> ParsedDocument:
    """“解析”一张独立上传的图片：检查它，然后整张交给 OCR。

    image_id：这张图片的 ID。独立图片的 image_id 就是它的 document_id
    （shared.ids.make_image_id），由调用方传入——解析器本身不知道文档 ID。
    max_pixels：像素数上限（来自配置 PARSE_IMAGE_MAX_PIXELS）。
    """
    read_image_info(path, max_pixels=max_pixels)
    return ParsedDocument(
        parser_name=PARSER_NAME,
        parser_version=pymupdf.__version__,
        ocr_targets=[ImageLocator(image_id=image_id)],
    )
