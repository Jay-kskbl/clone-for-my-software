"""M7：ParsedDocument（或 OCR 得到的文本块）→ Chunk 列表。纯函数，不访问数据库和网络。

本模块只依赖 shared 和标准库，不依赖 backend 的其他部分：OCR Worker（ocr 环境）
将来也要切分 OCR 文字，需要时可以把它原样移到 shared 下（见 DEVPLAN §4）。

规则（docs/decisions.md D25）：

1. 能否合并由来源定位的类型决定：
   - PDF 页、图片：不与任何块合并。一页或一张图片的文字只出现在指向它自己的片段里。
   - Word 段落：相邻段落可以合并。合并后的定位是片段起始段落（契约里 Word 只有段落序号）。
   - Excel 行：同一工作表的相邻行可以合并（按行组切分）。合并后的定位是这些行的外接矩形。
2. 合并时按整块累加，不超过 max_chars；开始下一个片段时，从上一个片段末尾带过来若干整块，
   总长不超过 overlap_chars（整块重叠，定位仍然准确）。
3. 单独一块就超过 max_chars 的（长段落、长页、OCR 出的长文字）按字符窗口拆开，
   相邻两段重叠 overlap_chars 个字符，每段都用这一块的定位。
"""

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

from shared.contracts import (
    Chunk,
    DocxParaLocator,
    ParsedDocument,
    SourceLocator,
    SourceType,
    TextBlock,
    XlsxRangeLocator,
)

from app.modules.chunking.splitter import split_spans

# 切分算法的版本。改动切分规则（不是参数）时加一，parse_version 随之变化，旧片段被整体替换
CHUNKER_VERSION = 1

# 合并的块之间用换行隔开。Excel 一行之内的单元格已经用制表符隔开（D24）
_JOINER = "\n"

ParamValue = str | int | float | bool


@dataclass(frozen=True)
class ChunkingParams:
    """切分参数，来自配置 CHUNK_MAX_CHARS、CHUNK_OVERLAP_CHARS。属于实验参数（GLOBAL §8.2）。"""

    max_chars: int
    overlap_chars: int

    def __post_init__(self) -> None:
        if self.max_chars < 1:
            raise ValueError("max_chars 必须大于 0")
        if not 0 <= self.overlap_chars < self.max_chars:
            raise ValueError("overlap_chars 必须不小于 0 且小于 max_chars")


def make_parse_version(
    *,
    parser_name: str,
    parser_version: str,
    params: ChunkingParams,
    parser_options: Mapping[str, ParamValue] | None = None,
) -> str:
    """由“会影响片段内容的一切”确定性地算出 parse_version。

    包括：切分算法版本、切分参数、解析器名称和版本、影响解析结果的解析参数
    （parser_options，例如 PDF 的 OCR 阈值 pdf_ocr_min_chars，由调用方传入）。
    任何一项变化，parse_version 都会变化，旧版本的片段随之整体删除（附录 A7）。

    形如 c1-m500-o50-1a2b3c4d5e6f：前面是便于肉眼辨认的算法版本和参数，后面是全部输入的哈希。
    只含字母、数字和连字符，满足 shared.ids 的字符集要求，长度固定在 64 以内。
    """
    payload = {
        "chunker": CHUNKER_VERSION,
        "max_chars": params.max_chars,
        "overlap_chars": params.overlap_chars,
        "parser_name": parser_name,
        "parser_version": parser_version,
        "parser_options": dict(parser_options or {}),
    }
    # sort_keys：同样的内容不论字典顺序如何都得到同一个哈希
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return f"c{CHUNKER_VERSION}-m{params.max_chars}-o{params.overlap_chars}-{digest[:12]}"


# ---- Excel 单元格范围 ----

_CELL_RE = re.compile(r"^([A-Z]{1,3})([1-9][0-9]*)$")


def _col_to_number(letters: str) -> int:
    number = 0
    for ch in letters:
        number = number * 26 + (ord(ch) - ord("A") + 1)
    return number


def _number_to_col(number: int) -> str:
    letters = ""
    while number:
        number, rest = divmod(number - 1, 26)
        letters = chr(ord("A") + rest) + letters
    return letters


def _parse_cell(cell: str) -> tuple[int, int]:
    match = _CELL_RE.fullmatch(cell)
    if match is None:  # 契约的正则已经保证了格式，这里只是防御
        raise ValueError(f"不是合法的单元格地址：{cell!r}")
    return _col_to_number(match.group(1)), int(match.group(2))


def _range_bounds(cell_range: str) -> tuple[int, int, int, int]:
    """'B3:F3' → (左列, 上行, 右列, 下行)。"""
    first, _, last = cell_range.partition(":")
    c1, r1 = _parse_cell(first)
    c2, r2 = _parse_cell(last or first)
    return min(c1, c2), min(r1, r2), max(c1, c2), max(r1, r2)


def _bounding_range(ranges: Sequence[str]) -> str:
    bounds = [_range_bounds(r) for r in ranges]
    left = min(b[0] for b in bounds)
    top = min(b[1] for b in bounds)
    right = max(b[2] for b in bounds)
    bottom = max(b[3] for b in bounds)
    first = f"{_number_to_col(left)}{top}"
    last = f"{_number_to_col(right)}{bottom}"
    return first if first == last else f"{first}:{last}"


# ---- 合并 ----


def _merge_key(locator: SourceLocator) -> tuple[str, ...] | None:
    """定位类型相同、merge_key 相同的相邻块可以合并；None 表示这一块不与任何块合并。"""
    if isinstance(locator, DocxParaLocator):
        return ("docx",)
    if isinstance(locator, XlsxRangeLocator):
        return ("xlsx", locator.sheet)
    return None


def _merged_locator(blocks: Sequence[TextBlock]) -> SourceLocator:
    first = blocks[0].locator
    if isinstance(first, XlsxRangeLocator):
        ranges = [b.locator.range for b in blocks]  # type: ignore[union-attr]
        return XlsxRangeLocator(sheet=first.sheet, range=_bounding_range(ranges))
    # Word：片段从哪一段开始，就定位到哪一段
    return first


def _joined_length(blocks: Sequence[TextBlock]) -> int:
    if not blocks:
        return 0
    return sum(len(b.text) for b in blocks) + len(_JOINER) * (len(blocks) - 1)


def _overlap_tail(blocks: Sequence[TextBlock], overlap_chars: int) -> list[TextBlock]:
    """从 blocks 末尾取若干整块作为下一个片段的开头，总长不超过 overlap_chars。

    不会取走全部块，否则下一个片段与这一个完全重复、切分不前进。
    """
    tail: list[TextBlock] = []
    for block in reversed(blocks[1:]):
        if _joined_length([block, *tail]) > overlap_chars:
            break
        tail.insert(0, block)
    return tail


@dataclass(frozen=True)
class _Piece:
    text: str
    locator: SourceLocator


def _pieces(blocks: Sequence[TextBlock], params: ChunkingParams) -> list[_Piece]:
    pieces: list[_Piece] = []
    group: list[TextBlock] = []  # 正在累加的一组可合并的块
    group_key: tuple[str, ...] | None = None
    fresh = 0  # group 里不是从上一个片段带过来的块数；为 0 时不必输出

    def flush() -> None:
        nonlocal group, group_key, fresh
        if group and fresh:
            pieces.append(_Piece(_JOINER.join(b.text for b in group), _merged_locator(group)))
        group, group_key, fresh = [], None, 0

    for block in blocks:
        text = block.text.strip()
        if not text:
            continue
        if text != block.text:
            block = TextBlock(text=text, locator=block.locator)

        key = _merge_key(block.locator)
        if key is None or len(text) > params.max_chars:
            # 不合并的块，或单独就超长的块：结束当前组，自己拆成若干段
            flush()
            for start, end in split_spans(
                text, max_chars=params.max_chars, overlap_chars=params.overlap_chars
            ):
                piece_text = text[start:end].strip()
                if piece_text:
                    pieces.append(_Piece(piece_text, block.locator))
            continue

        if key != group_key:
            flush()
            group_key = key
        elif _joined_length([*group, block]) > params.max_chars:
            # 当前组放不下了：输出它，带着末尾的重叠块开始下一组
            tail = _overlap_tail(group, params.overlap_chars)
            flush()
            group_key = key
            # 重叠块加上新块仍然放不下时，放弃重叠
            group = tail if _joined_length([*tail, block]) <= params.max_chars else []
        group.append(block)
        fresh += 1

    flush()
    return pieces


def chunk_blocks(
    blocks: Sequence[TextBlock],
    *,
    document_id: UUID,
    parse_version: str,
    source_type: SourceType,
    params: ChunkingParams,
    seq_start: int = 0,
) -> list[Chunk]:
    """把一串文本块切成片段。seq 从 seq_start 开始连续编号，顺序与 blocks 一致。

    同样的输入永远得到同样的输出（chunk_id 是确定性的，重复索引直接覆盖，附录 A7）。
    seq_start：同一个文档、同一个 parse_version 下分几次切分时（例如正文和各页 OCR 文字），
    调用方要保证各次的 seq 区间不重叠。
    """
    return [
        Chunk.build(
            document_id=document_id,
            parse_version=parse_version,
            seq=seq_start + i,
            source_type=source_type,
            text=piece.text,
            locator=piece.locator,
        )
        for i, piece in enumerate(_pieces(blocks, params))
    ]


def chunk_document(
    parsed: ParsedDocument,
    *,
    document_id: UUID,
    parse_version: str,
    params: ChunkingParams,
) -> list[Chunk]:
    """切分解析结果中的文本层（source_type=body）。ocr_targets 不在这里处理，由 OCR 之后再切分。"""
    return chunk_blocks(
        parsed.blocks,
        document_id=document_id,
        parse_version=parse_version,
        source_type="body",
        params=params,
    )
