"""T24e：文本预览的排序键（D44）。只检查生成的 SQL；真实排序结果在
tests/integration/test_document_text.py（需要 PostgreSQL）。"""

from sqlalchemy import func, select, tuple_
from sqlalchemy.dialects import postgresql

from app.api.document_text import _PREVIEW_ORDER
from app.db.models import DocumentChunk


def compiled(statement) -> str:
    return str(
        statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )


def test_list_is_ordered_by_page_then_body_before_ocr_then_seq():
    sql = compiled(select(DocumentChunk.chunk_id).order_by(*_PREVIEW_ORDER))
    order_by = sql.split("ORDER BY", 1)[1]

    page = order_by.index("locator ->> 'page'")
    source = order_by.index("CASE WHEN (document_chunks.source_type = 'body') THEN 0 ELSE 1 END")
    seq = order_by.rindex("document_chunks.seq")
    assert page < source < seq
    # 没有页码的定位（Word、Excel、图片）按 0 算，不会因为 NULL 排到别处
    assert "coalesce(CAST(document_chunks.locator ->> 'page' AS INTEGER), 0)" in order_by


def test_jump_counts_rows_before_the_target_in_the_same_order():
    sql = compiled(
        select(func.count())
        .select_from(DocumentChunk)
        .where(tuple_(*_PREVIEW_ORDER) < tuple_(3, 1, 7))
    )

    assert ", document_chunks.seq) < (3, 1, 7)" in sql
