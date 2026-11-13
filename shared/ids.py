"""统一 ID 规则（GLOBAL §3.5，附录 A7）。

ID 都是确定性的：同样的输入永远得到同样的 ID，所以重新解析、重新索引时
新数据直接覆盖旧数据，不会产生重复（任务幂等依赖这一点）。
"""

import re
from typing import NamedTuple
from uuid import UUID

# parse_version 不能含 ":"，否则 chunk_id 无法可靠地拆回三段
PARSE_VERSION_PATTERN = r"^[A-Za-z0-9._-]+$"
_PARSE_VERSION_RE = re.compile(PARSE_VERSION_PATTERN)
_IMAGE_MARKER = "img"


class ChunkIdParts(NamedTuple):
    document_id: UUID
    parse_version: str
    seq: int


class ImageIdParts(NamedTuple):
    document_id: UUID
    # 独立上传的图片没有 page / idx（图片本身就是一个 document）
    page: int | None
    idx: int | None

    @property
    def is_embedded(self) -> bool:
        return self.page is not None


def validate_parse_version(parse_version: str) -> str:
    if not _PARSE_VERSION_RE.fullmatch(parse_version):
        raise ValueError(
            f"parse_version 只能包含字母、数字、'.'、'_'、'-'，且不能为空：{parse_version!r}"
        )
    return parse_version


def _non_negative_int(text: str, what: str, minimum: int = 0) -> int:
    # 只接受规范写法：拒绝 "+1"、" 1"、"01" 这类 int() 能解析但不是我们生成的形式
    if not text.isascii() or not text.isdigit() or (len(text) > 1 and text[0] == "0"):
        raise ValueError(f"{what} 不是合法的整数：{text!r}")
    value = int(text)
    if value < minimum:
        raise ValueError(f"{what} 不能小于 {minimum}：{value}")
    return value


def _canonical_uuid(text: str, source: str) -> UUID:
    try:
        value = UUID(text)
    except ValueError as exc:
        raise ValueError(f"{source} 中的 document_id 不是合法 UUID：{text!r}") from exc
    # UUID() 接受大写、带花括号等写法；ID 里只允许标准小写形式，保证一个文档只有一种写法
    if str(value) != text:
        raise ValueError(f"{source} 中的 document_id 不是标准小写 UUID 写法：{text!r}")
    return value


def make_chunk_id(document_id: UUID, parse_version: str, seq: int) -> str:
    """chunk_id = {document_id}:{parse_version}:{seq}"""
    validate_parse_version(parse_version)
    if seq < 0:
        raise ValueError(f"seq 不能为负数：{seq}")
    return f"{document_id}:{parse_version}:{seq}"


def parse_chunk_id(chunk_id: str) -> ChunkIdParts:
    parts = chunk_id.split(":")
    if len(parts) != 3:
        raise ValueError(f"chunk_id 应为 '{{document_id}}:{{parse_version}}:{{seq}}'：{chunk_id!r}")
    document_id = _canonical_uuid(parts[0], "chunk_id")
    parse_version = validate_parse_version(parts[1])
    seq = _non_negative_int(parts[2], "seq")
    return ChunkIdParts(document_id, parse_version, seq)


def make_image_id(document_id: UUID, page: int | None = None, idx: int | None = None) -> str:
    """独立图片：image_id 就是 document_id。
    文档内嵌图片（P4，目前只定义格式）：{document_id}:img:{page}:{idx}，
    其中 page 从 1 开始，idx 从 0 开始。
    """
    if page is None and idx is None:
        return str(document_id)
    if page is None or idx is None:
        raise ValueError("内嵌图片的 page 和 idx 必须同时提供")
    if page < 1:
        raise ValueError(f"page 从 1 开始：{page}")
    if idx < 0:
        raise ValueError(f"idx 不能为负数：{idx}")
    return f"{document_id}:{_IMAGE_MARKER}:{page}:{idx}"


def parse_image_id(image_id: str) -> ImageIdParts:
    parts = image_id.split(":")
    if len(parts) == 1:
        return ImageIdParts(_canonical_uuid(parts[0], "image_id"), None, None)
    if len(parts) == 4 and parts[1] == _IMAGE_MARKER:
        document_id = _canonical_uuid(parts[0], "image_id")
        page = _non_negative_int(parts[2], "page", minimum=1)
        idx = _non_negative_int(parts[3], "idx")
        return ImageIdParts(document_id, page, idx)
    raise ValueError(
        f"image_id 应为 '{{document_id}}' 或 '{{document_id}}:img:{{page}}:{{idx}}'：{image_id!r}"
    )
