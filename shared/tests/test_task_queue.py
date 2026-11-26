"""T24k：连接超时；T24ad：重试间隔的解析与传递。不需要数据库：替换 psycopg.connect 或连接。"""

import contextlib
import re

import pytest

from shared import task_queue, tasks
from shared.task_queue import PgTaskQueue, connect_kwargs, parse_retry_delays


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


# ---- T24ad：重试间隔 ----


@pytest.mark.parametrize(
    ("value", "expected"),
    [("30,120", (30.0, 120.0)), (" 30 , 120 ", (30.0, 120.0)), ("0", (0.0,)), ("1.5", (1.5,))],
)
def test_parse_retry_delays(value, expected):
    assert parse_retry_delays(value) == expected


@pytest.mark.parametrize("value", ["", "abc", "30,", ",30", "-1", "3601", "nan", "inf", "30;120"])
def test_parse_retry_delays_rejects_bad_values(value):
    with pytest.raises(ValueError):
        parse_retry_delays(value)


@pytest.mark.parametrize(
    ("kwargs", "expected"), [({}, []), ({"retry_delays": (30, 120)}, [30.0, 120.0])]
)
def test_queue_passes_retry_delays_to_the_claim_query(monkeypatch, kwargs, expected):
    executed = []

    class Cursor:
        rowcount = 0

        def fetchall(self):
            return []

        def fetchone(self):
            return None

    class FakeConnection:
        closed = False

        def transaction(self):
            return contextlib.nullcontext()

        def execute(self, sql, params=None):
            executed.append((sql, params))
            return Cursor()

    monkeypatch.setattr(task_queue.psycopg, "connect", lambda *_a, **_k: FakeConnection())
    queue = PgTaskQueue("postgresql://x", worker_id="t", lease_seconds=60, **kwargs)

    assert queue.claim(["ocr"]) is None

    sql, params = executed[-1]
    assert params["retry_delays"] == expected
    assert params["lease_expired_error"] == tasks.LEASE_EXPIRED_ERROR
    # SQL 用到的每个参数都传了（少传一个，psycopg 要到真正执行时才报错）
    assert set(re.findall(r"%\((\w+)\)s", sql)) == set(params)
