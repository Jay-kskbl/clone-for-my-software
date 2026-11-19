"""M10 图片向量索引（T21）：image_vectors 索引的创建、写入、删除和精确检索。

附录 A12：不建 HNSW 等近似索引，检索时用 script_score 对候选向量逐一计算相似度；
用户可访问的 document_id 集合作为检索前的过滤条件。
权限信息不进索引（附录 A10），返回前仍由 M11 用数据库再校验一次。

向量本体以数据库的 image_embeddings 为准（D10），本索引丢失时可以从数据库重建。
"""

from app.modules.vector_index.index import (
    VECTOR_DIM,
    VectorHit,
    delete_document_vectors,
    ensure_vector_index,
    index_image_vector,
    load_vector_index_definition,
    search_vectors,
)

__all__ = [
    "VECTOR_DIM",
    "VectorHit",
    "delete_document_vectors",
    "ensure_vector_index",
    "index_image_vector",
    "load_vector_index_definition",
    "search_vectors",
]
