"""T24l：OCR Worker 启动时检查数据库里有没有它要读写的表和列。不需要数据库。"""

import pytest

from ocr_worker import store
from ocr_worker.store import REQUIRED_COLUMNS, PgStore, missing_columns

ALL_PRESENT = {(table, column) for table, columns in REQUIRED_COLUMNS.items() for column in columns}


def test_nothing_missing_when_every_column_exists():
    assert missing_columns(ALL_PRESENT | {("documents", "extra")}) == []


def test_missing_column_and_missing_table_are_listed():
    present = {
        pair
        for pair in ALL_PRESENT
        if pair != ("ocr_results", "params") and pair[0] != "document_chunks"
    }

    missing = missing_columns(present)

    assert "ocr_results.params" in missing
    assert "document_chunks.chunk_id" in missing
    assert len(missing) == 1 + len(REQUIRED_COLUMNS["document_chunks"])
    assert missing == sorted(missing)


def test_required_columns_exist_in_the_backend_models():
    # 迁移到最新版本的数据库一定满足检查（迁移与模型一致由 backend 的 test_migrations 保证）。
    # 只在装了 backend 的 main 环境里跑；ocr 环境没有 backend，跳过
    models = pytest.importorskip("app.db.models")
    for table, columns in REQUIRED_COLUMNS.items():
        actual = set(models.Base.metadata.tables[table].columns.keys())
        assert columns <= actual, (table, sorted(columns - actual))


def test_schema_problems_queries_information_schema(monkeypatch):
    executed = []

    class FakeConnection:
        closed = False

        def execute(self, sql, params=None):
            executed.append(params)
            return self

        def fetchall(self):
            return [pair for pair in ALL_PRESENT if pair != ("ocr_results", "params")]

    monkeypatch.setattr(store.psycopg, "connect", lambda *_a, **_k: FakeConnection())

    assert PgStore("postgresql://x").schema_problems() == ["ocr_results.params"]
    assert sorted(executed[0]["tables"]) == sorted(REQUIRED_COLUMNS)
