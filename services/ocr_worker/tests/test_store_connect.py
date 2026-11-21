"""T24k：OCR Worker 的数据库读写连接带上连接超时。不需要数据库：替换 psycopg.connect。"""

from ocr_worker import store
from ocr_worker.store import PgStore


def test_store_passes_the_timeout_to_psycopg(monkeypatch):
    calls = []

    class FakeConnection:
        closed = False

    def fake_connect(url, **kwargs):
        calls.append((url, kwargs))
        return FakeConnection()

    monkeypatch.setattr(store.psycopg, "connect", fake_connect)

    PgStore("postgresql://x", connect_timeout_seconds=5)._connection()
    PgStore("postgresql://x")._connection()

    assert calls == [
        ("postgresql://x", {"autocommit": True, "connect_timeout": 5}),
        ("postgresql://x", {"autocommit": True}),
    ]
