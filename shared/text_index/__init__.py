"""M8 文本索引：doc_meta（文件级）与 chunks（片段级）两个索引的创建、写入和删除。

BM25 查询在 M11（T15）里实现。
"""

from shared.text_index.client import (
    CHUNKS,
    DOC_META,
    IMAGE_VECTORS,
    INDEX_NAMES,
    OpenSearchClient,
    client_from_settings,
)
from shared.text_index.errors import TextIndexError, TextIndexUnavailable
from shared.text_index.indexer import (
    delete_chunk_range,
    delete_document,
    index_doc_meta,
    index_document,
    write_chunks,
)
from shared.text_index.indices import ensure_indices, load_index_definition

__all__ = [
    "CHUNKS",
    "DOC_META",
    "IMAGE_VECTORS",
    "INDEX_NAMES",
    "OpenSearchClient",
    "TextIndexError",
    "TextIndexUnavailable",
    "client_from_settings",
    "delete_chunk_range",
    "delete_document",
    "ensure_indices",
    "index_doc_meta",
    "index_document",
    "load_index_definition",
    "write_chunks",
]
