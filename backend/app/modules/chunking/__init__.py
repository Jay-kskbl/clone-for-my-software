"""M7 切分：ParsedDocument → Chunk[]（纯函数）。"""

from app.modules.chunking.chunker import (
    CHUNKER_VERSION,
    ChunkingParams,
    chunk_blocks,
    chunk_document,
    make_parse_version,
)
from app.modules.chunking.splitter import split_spans

__all__ = [
    "CHUNKER_VERSION",
    "ChunkingParams",
    "chunk_blocks",
    "chunk_document",
    "make_parse_version",
    "split_spans",
]
