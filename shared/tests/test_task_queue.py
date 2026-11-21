"""T24k：任务队列连接数据库时带上连接超时。不需要数据库：替换 psycopg.connect。"""

import pytest

from shared import task_queue
from shared.task_queue import PgTaskQueue, connect_kwargs


def test_connect_kwargs():
    assert connect_kwargs(None) == {}
    assert connect_kwargs(10) == {"connect_timeout": 10}


@pytest.mark.parametrize(("timeout", "expected"), [(None, {}), (7, {"connect_timeout": 7})])
def test_queue_passes_the_timeout_to_psycopg(monkeypatch, timeout, expected):
    calls = []

    class FakeConnection:
        closed = False

    def fake_connect(url, **kwargs):
        calls.append((url, kwargs))
        return FakeConnection()

    monkeypatch.setattr(task_queue.psycopg, "connect", fake_connect)
    queue = PgTaskQueue(
        "postgresql://x", worker_id="t", lease_seconds=60, connect_timeout_seconds=timeout
    )

    connection = queue._connection()

    assert calls == [("postgresql://x", {"autocommit": True, **expected})]
    # 连接复用：第二次不再新建
    assert queue._connection() is connection and len(calls) == 1
