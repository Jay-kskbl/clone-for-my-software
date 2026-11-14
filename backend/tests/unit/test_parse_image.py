"""T11 🧪：图片解析器（只做元数据，交给 OCR）。

fixtures：PNG、JPEG、畸形文件（截断、损坏、像素炸弹）。

测试用的图片在运行时用 PyMuPDF 现场生成，不依赖外部文件。
"""

import struct
import uuid
import zlib
from pathlib import Path

import pymupdf
import pytest
from shared.contracts import ImageLocator, ParsedDocument
from shared.ids import make_image_id

from app.modules.parsing import ImageInfo, ParseError, parse_image, read_image_info

MAX_PIXELS = 1_000_000
DOCUMENT_ID = uuid.UUID("11111111-2222-4333-8444-555555555555")
IMAGE_ID = make_image_id(DOCUMENT_ID)


def image_bytes(width: int, height: int, fmt: str) -> bytes:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, width, height))
    pixmap.clear_with(180)
    return pixmap.tobytes(fmt)


@pytest.fixture
def png(tmp_path) -> Path:
    path = tmp_path / "picture.png"
    path.write_bytes(image_bytes(320, 200, "png"))
    return path


@pytest.fixture
def jpeg(tmp_path) -> Path:
    path = tmp_path / "photo.jpg"
    path.write_bytes(image_bytes(640, 480, "jpeg"))
    return path


def write(tmp_path, data: bytes, name: str = "bad.bin") -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def png_chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))


# ---- 正常图片 ----


def test_png_size_is_read(png):
    assert read_image_info(png, max_pixels=MAX_PIXELS) == ImageInfo(width=320, height=200)


def test_jpeg_size_is_read(jpeg):
    assert read_image_info(jpeg, max_pixels=MAX_PIXELS) == ImageInfo(width=640, height=480)


@pytest.mark.parametrize("fixture", ["png", "jpeg"])
def test_image_yields_no_text_and_is_handed_to_ocr_as_a_whole(fixture, request):
    path = request.getfixturevalue(fixture)

    result = parse_image(path, image_id=IMAGE_ID, max_pixels=MAX_PIXELS)

    assert result.parser_name == "pymupdf"
    assert result.parser_version == pymupdf.__version__
    assert result.blocks == []
    # 独立图片的 image_id 就是它的 document_id
    assert result.ocr_targets == [ImageLocator(image_id=str(DOCUMENT_ID))]
    assert ParsedDocument.model_validate_json(result.model_dump_json()) == result


def test_jpeg_with_embedded_thumbnail_reports_the_main_image(tmp_path):
    # 相机拍的 JPEG 常在 EXIF 段里内嵌一张缩略图，它自己也是一个完整的 JPEG。
    # 读到的应是正图的尺寸，不是缩略图的
    main = image_bytes(640, 480, "jpeg")
    thumbnail = image_bytes(16, 12, "jpeg")
    app1 = b"\xff\xe1" + struct.pack(">H", len(thumbnail) + 2) + thumbnail
    path = write(tmp_path, main[:2] + app1 + main[2:], "exif.jpg")

    assert read_image_info(path, max_pixels=MAX_PIXELS) == ImageInfo(width=640, height=480)


def test_trailing_bytes_after_the_end_marker_are_tolerated(jpeg, tmp_path):
    path = write(tmp_path, jpeg.read_bytes() + b"\x00" * 200, "padded.jpg")

    assert read_image_info(path, max_pixels=MAX_PIXELS) == ImageInfo(width=640, height=480)


def test_extension_is_not_trusted(png, tmp_path):
    # 内容是 PNG、名字是 .jpg：按内容处理
    path = write(tmp_path, png.read_bytes(), "misnamed.jpg")

    assert read_image_info(path, max_pixels=MAX_PIXELS) == ImageInfo(width=320, height=200)


# ---- 畸形文件 ----


@pytest.mark.parametrize("fixture", ["png", "jpeg"])
def test_truncated_image_is_rejected(fixture, request, tmp_path):
    # 解码器对截断的图片很宽容（缺的部分补成灰色），所以必须由解析器自己发现
    data = request.getfixturevalue(fixture).read_bytes()
    path = write(tmp_path, data[: len(data) // 2])

    with pytest.raises(ParseError, match="不完整") as excinfo:
        read_image_info(path, max_pixels=MAX_PIXELS)
    assert excinfo.value.retryable is False


def test_truncated_jpeg_with_thumbnail_is_still_detected(tmp_path):
    # 缩略图自带结束标记；不能因为它就把截断的正图当成完整的
    main = image_bytes(640, 480, "jpeg")
    thumbnail = image_bytes(16, 12, "jpeg")
    app1 = b"\xff\xe1" + struct.pack(">H", len(thumbnail) + 2) + thumbnail
    whole = main[:2] + app1 + main[2:]
    path = write(tmp_path, whole[: len(whole) - 200])

    with pytest.raises(ParseError, match="不完整"):
        read_image_info(path, max_pixels=MAX_PIXELS)


def test_pixel_bomb_is_rejected_from_the_header_without_decoding(tmp_path):
    # 文件头声称 60000×60000（36 亿像素），文件本身不到 100 字节
    header = struct.pack(">IIBBBBB", 60000, 60000, 8, 2, 0, 0, 0)
    bomb = b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", header) + png_chunk(b"IEND", b"")
    path = write(tmp_path, bomb)

    with pytest.raises(ParseError, match="像素数超过上限"):
        read_image_info(path, max_pixels=MAX_PIXELS)


def test_pixel_limit_comes_from_the_caller(png):
    assert read_image_info(png, max_pixels=320 * 200) == ImageInfo(width=320, height=200)
    with pytest.raises(ParseError, match="像素数超过上限"):
        read_image_info(png, max_pixels=320 * 200 - 1)
    with pytest.raises(ParseError, match="像素数超过上限"):
        parse_image(png, image_id=IMAGE_ID, max_pixels=10)


def test_png_with_corrupt_pixel_data_is_rejected(tmp_path):
    header = struct.pack(">IIBBBBB", 32, 32, 8, 2, 0, 0, 0)
    data = (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", header)
        + png_chunk(b"IDAT", b"this is not zlib data")
        + png_chunk(b"IEND", b"")
    )

    with pytest.raises(ParseError, match="无法解码"):
        read_image_info(write(tmp_path, data), max_pixels=MAX_PIXELS)


def test_zero_sized_image_is_rejected(tmp_path):
    header = struct.pack(">IIBBBBB", 0, 32, 8, 2, 0, 0, 0)
    data = b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", header) + png_chunk(b"IEND", b"")

    with pytest.raises(ParseError, match="为 0"):
        read_image_info(write(tmp_path, data), max_pixels=MAX_PIXELS)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"\x89PNG\r\n\x1a\n",  # 只有魔数
        b"\xff\xd8\xff",  # 只有魔数
        b"\xff\xd8\xff\xe0\x00\x10" + b"\x00" * 14,  # 有一个段，之后什么都没有
        b"\xff\xd8\x00\x00\x00\x00",  # 魔数之后不是段标记
        b"GIF89a" + b"\x00" * 20,  # 不支持的格式
        b"%PDF-1.7\n",
    ],
)
def test_garbage_is_rejected_with_parse_error(tmp_path, data):
    with pytest.raises(ParseError):
        read_image_info(write(tmp_path, data), max_pixels=MAX_PIXELS)


def test_image_id_must_be_a_valid_id(png):
    with pytest.raises(ValueError):
        parse_image(png, image_id="not-an-id", max_pixels=MAX_PIXELS)


def test_error_message_does_not_leak_the_server_path(tmp_path):
    path = write(tmp_path, b"junk", "secret-name.png")

    with pytest.raises(ParseError) as excinfo:
        read_image_info(path, max_pixels=MAX_PIXELS)
    assert str(tmp_path) not in excinfo.value.message
    assert "secret-name" not in excinfo.value.message
