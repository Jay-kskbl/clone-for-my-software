"""OCR Worker 对数据库的读写。直接用 psycopg 写 SQL，不依赖 backend 的 ORM 模型。

表结构以 backend/app/db/models.py 为准（docs/data-model.md），这里只用到其中几列。
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

import psycopg
from psycopg.types.json import Jsonb
from shared.contracts import Chunk, OCRResult


@dataclass(frozen=True)
class DocumentState:
    parse_version: str | None
    deleted_at: datetime | None
    storage_key: str
    mime_type: str

    @property
    def deleted(self) -> bool:
        return self.deleted_at is not None


class Store(Protocol):
    """流水线对数据库的全部要求。测试用假实现替换。"""

    def document(self, document_id: uuid.UUID) -> DocumentState | None: ...

    def save(
        self,
        result: OCRResult,
        chunks: Sequence[Chunk],
        *,
        parse_version: str,
        seq_range: tuple[int, int],
        params: Mapping[str, Any],
    ) -> bool: ...

    def ping(self) -> None: ...


_DOCUMENT_SQL = """
SELECT parse_version, deleted_at, storage_key, mime_type FROM documents WHERE id = %(id)s
"""

# 同一文档、同一对象（同一页或同一张图片）的旧识别结果。jsonb 按值比较，键的顺序无关
# 在保存的事务里锁住文档行（共享锁）：事务结束前，文档不会被硬删除，parse_version
# 也不会被重新解析改掉，所以版本复查的结论在写入时仍然成立
_LOCK_DOCUMENT_SQL = """
SELECT parse_version, deleted_at FROM documents WHERE id = %(id)s FOR SHARE
"""

_DELETE_OCR_RESULTS_SQL = """
DELETE FROM ocr_results WHERE document_id = %(document_id)s AND locator = %(locator)s
"""

_INSERT_OCR_RESULT_SQL = """
INSERT INTO ocr_results (id, document_id, locator, lines, model_name, model_version, params)
VALUES (%(id)s, %(document_id)s, %(locator)s, %(lines)s, %(model_name)s, %(model_version)s,
        %(params)s)
"""

# 只删这一页（这张图片）预留的序号区间里的 OCR 片段：别的页、正文片段都不动
_DELETE_CHUNKS_SQL = """
DELETE FROM document_chunks
WHERE document_id = %(document_id)s AND parse_version = %(parse_version)s
  AND source_type = 'ocr' AND seq >= %(seq_from)s AND seq < %(seq_to)s
"""

_INSERT_CHUNK_SQL = """
INSERT INTO document_chunks
    (chunk_id, document_id, parse_version, seq, source_type, text, locator)
VALUES
    (%(chunk_id)s, %(document_id)s, %(parse_version)s, %(seq)s, %(source_type)s,
     %(text)s, %(locator)s)
"""


class PgStore:
    """每个操作自己开一个事务。连接出错后丢弃，下次重新连接。"""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._conn: psycopg.Connection | None = None

    def _connection(self) -> psycopg.Connection:
        if self._conn is None or self._conn.closed:
            self._conn = psycopg.connect(self._database_url, autocommit=True)
        return self._conn

    def reset(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except psycopg.Error:
                pass
            self._conn = None

    def document(self, document_id: uuid.UUID) -> DocumentState | None:
        row = self._connection().execute(_DOCUMENT_SQL, {"id": document_id}).fetchone()
        if row is None:
            return None
        return DocumentState(
            parse_version=row[0], deleted_at=row[1], storage_key=row[2], mime_type=row[3]
        )

    def save(
        self,
        result: OCRResult,
        chunks: Sequence[Chunk],
        *,
        parse_version: str,
        seq_range: tuple[int, int],
        params: Mapping[str, Any],
    ) -> bool:
        """在一个事务里：换掉这个对象的识别结果和 OCR 片段。重复执行结果相同。

        params 是识别这一条实际用的 OCR 参数，原样写进 ocr_results.params（T24c）。

        返回 False 表示什么都没写：文档已不存在、已删除，或已被重新解析成别的版本
        （识别期间发生的变化）。
        """
        conn = self._connection()
        locator = Jsonb(result.locator.model_dump(mode="json"))
        with conn.transaction():
            row = conn.execute(_LOCK_DOCUMENT_SQL, {"id": result.document_id}).fetchone()
            if row is None or row[1] is not None or row[0] != parse_version:
                return False
            conn.execute(
                _DELETE_OCR_RESULTS_SQL, {"document_id": result.document_id, "locator": locator}
            )
            conn.execute(
                _INSERT_OCR_RESULT_SQL,
                {
                    "id": uuid.uuid4(),
                    "document_id": result.document_id,
                    "locator": locator,
                    "lines": Jsonb([line.model_dump(mode="json") for line in result.lines]),
                    "model_name": result.model_name,
                    "model_version": result.model_version,
                    "params": Jsonb(dict(params)),
                },
            )
            conn.execute(
                _DELETE_CHUNKS_SQL,
                {
                    "document_id": result.document_id,
                    "parse_version": parse_version,
                    "seq_from": seq_range[0],
                    "seq_to": seq_range[1],
                },
            )
            rows: list[dict[str, Any]] = [
                {
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "parse_version": chunk.parse_version,
                    "seq": chunk.seq,
                    "source_type": chunk.source_type,
                    "text": chunk.text,
                    "locator": Jsonb(chunk.locator.model_dump(mode="json")),
                }
                for chunk in chunks
            ]
            if rows:
                with conn.cursor() as cur:
                    cur.executemany(_INSERT_CHUNK_SQL, rows)
        return True

    def ping(self) -> None:
        """确认数据库连得上。启动时调用：连不上就报错退出，不进入“看起来在运行”的状态。"""
        self._connection().execute("SELECT 1")
