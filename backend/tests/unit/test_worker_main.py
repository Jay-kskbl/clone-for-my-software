"""T24a：通用 Worker 启动时检查数据库——连不上就以退出码 1 结束，不进入领取循环。

不需要数据库：连不上的情况直接用真实的 PgTaskQueue 去连一个没有服务的本机端口；
连得上的情况用假的队列。领取循环中途断线的重试在 tests/unit/test_worker_loop.py。
"""

import re
import socket
from types import SimpleNamespace

import psycopg
import pytest
from shared.task_queue import PgTaskQueue

from app.worker import __main__ as worker_main

SECRET_PASSWORD = "do-not-print-this-password"


def free_port() -> int:
    """取一个此刻没有服务在监听的本机端口。"""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def fake_settings(database_url: str) -> SimpleNamespace:
    return SimpleNamespace(
        database_url=database_url,
        worker_lease_seconds=60.0,
        worker_max_tasks=5,
        worker_poll_seconds=0.01,
        worker_heartbeat_seconds=15.0,
        worker_task_timeout_seconds=600.0,
        worker_memory_limit_mb=None,
        worker_db_connect_timeout_seconds=10,
        retry_delays=(30.0, 120.0),
    )


@pytest.fixture
def run_worker_calls(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """替换领取循环和信号登记：记录是否进入了循环，且不改动 pytest 自己的信号处理。"""
    calls: list[object] = []

    def fake_run_worker(queue, handlers, options, *, should_stop):
        calls.append(queue)
        return 0

    monkeypatch.setattr(worker_main, "run_worker", fake_run_worker)
    monkeypatch.setattr(worker_main.signal, "signal", lambda *_args: None)
    # 结构检查默认通过；需要检查失败的测试自己再替换
    monkeypatch.setattr(worker_main, "check_schema", lambda *_args, **_kwargs: None)
    return calls


def test_unreachable_database_exits_1_without_entering_the_loop(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    run_worker_calls: list[object],
) -> None:
    url = f"postgresql://docmgr:{SECRET_PASSWORD}@127.0.0.1:{free_port()}/docmgr"
    monkeypatch.setattr(worker_main, "load_settings", lambda: fake_settings(url))

    assert worker_main.main() == 1
    assert run_worker_calls == []
    err = capsys.readouterr().err
    assert "无法连接数据库" in err
    # psycopg 可能抛出 OperationalError 的更具体子类；这里真正要固定的是启动失败
    # 会输出一个安全的异常类名，而不是随驱动版本改变的具体类名。
    assert re.search(r"Worker 无法连接数据库（[A-Za-z_][A-Za-z0-9_]*）", err)
    # 不把连接串里的密码、端口打到终端
    assert SECRET_PASSWORD not in err
    assert url not in err


class FakeQueue:
    def __init__(self, *, ping_error: Exception | None = None) -> None:
        self.ping_error = ping_error
        self.pinged = 0
        self.resets = 0

    def ping(self) -> None:
        self.pinged += 1
        if self.ping_error is not None:
            raise self.ping_error

    def reset(self) -> None:
        self.resets += 1


def test_reachable_database_enters_the_loop_with_the_same_queue(
    monkeypatch: pytest.MonkeyPatch, run_worker_calls: list[object]
) -> None:
    queue = FakeQueue()
    monkeypatch.setattr(worker_main, "load_settings", lambda: fake_settings("postgresql://x"))
    monkeypatch.setattr(worker_main, "PgTaskQueue", lambda *_args, **_kwargs: queue)

    assert worker_main.main() == 0
    assert queue.pinged == 1
    assert run_worker_calls == [queue]
    assert queue.resets == 1  # 退出时释放连接


def test_connect_timeout_from_settings_is_passed_to_the_queue(
    monkeypatch: pytest.MonkeyPatch, run_worker_calls: list[object]
) -> None:
    # T24k：主机不可达时启动检查在配置的时间内报错，而不是等操作系统的 TCP 超时
    created: list[dict[str, object]] = []
    queue = FakeQueue()

    def fake_queue(*_args, **kwargs):
        created.append(kwargs)
        return queue

    settings = fake_settings("postgresql://x")
    settings.worker_db_connect_timeout_seconds = 4
    monkeypatch.setattr(worker_main, "load_settings", lambda: settings)
    monkeypatch.setattr(worker_main, "PgTaskQueue", fake_queue)

    assert worker_main.main() == 0
    assert created[0]["connect_timeout_seconds"] == 4


def test_any_database_error_at_startup_exits_1(
    monkeypatch: pytest.MonkeyPatch, run_worker_calls: list[object]
) -> None:
    # 例如密码错误、库不存在：psycopg 都抛 psycopg.Error 的子类
    queue = FakeQueue(ping_error=psycopg.errors.InvalidPassword("bad password"))
    monkeypatch.setattr(worker_main, "load_settings", lambda: fake_settings("postgresql://x"))
    monkeypatch.setattr(worker_main, "PgTaskQueue", lambda *_args, **_kwargs: queue)

    assert worker_main.main() == 1
    assert run_worker_calls == []
    assert queue.resets == 1


def test_unmigrated_database_exits_1_with_the_upgrade_hint(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    run_worker_calls: list[object],
) -> None:
    # T24l：连得上，但数据库没有迁移到代码要求的版本
    queue = FakeQueue()
    monkeypatch.setattr(worker_main, "load_settings", lambda: fake_settings("postgresql://x"))
    monkeypatch.setattr(worker_main, "PgTaskQueue", lambda *_args, **_kwargs: queue)
    monkeypatch.setattr(
        worker_main,
        "check_schema",
        lambda *_a, **_k: "数据库还没有建表，先运行 alembic upgrade head",
    )

    assert worker_main.main() == 1
    assert run_worker_calls == []
    assert queue.resets == 1
    assert "Worker 无法启动：数据库还没有建表" in capsys.readouterr().err


def test_database_error_during_the_schema_check_is_a_connection_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    run_worker_calls: list[object],
) -> None:
    queue = FakeQueue()

    def broken(*_args, **_kwargs):
        raise psycopg.OperationalError("connection lost")

    monkeypatch.setattr(worker_main, "load_settings", lambda: fake_settings("postgresql://x"))
    monkeypatch.setattr(worker_main, "PgTaskQueue", lambda *_args, **_kwargs: queue)
    monkeypatch.setattr(worker_main, "check_schema", broken)

    assert worker_main.main() == 1
    assert run_worker_calls == []
    assert "Worker 无法连接数据库（OperationalError）" in capsys.readouterr().err


def test_ping_on_the_real_queue_raises_when_nothing_listens() -> None:
    queue = PgTaskQueue(
        f"postgresql://docmgr:x@127.0.0.1:{free_port()}/docmgr",
        worker_id="t",
        lease_seconds=60,
    )
    with pytest.raises(psycopg.OperationalError):
        queue.ping()
    queue.reset()


def test_worker_passes_retry_delays_to_the_queue(
    monkeypatch: pytest.MonkeyPatch, run_worker_calls: list[object]
) -> None:
    created: list[dict] = []

    class FakeQueue:
        def __init__(self, _url: str, **kwargs: object) -> None:
            created.append(kwargs)

        def ping(self) -> None:
            pass

        def reset(self) -> None:
            pass

    monkeypatch.setattr(worker_main, "load_settings", lambda: fake_settings("postgresql://x"))
    monkeypatch.setattr(worker_main, "PgTaskQueue", FakeQueue)

    assert worker_main.main() == 0
    assert created[0]["retry_delays"] == (30.0, 120.0)


@pytest.mark.parametrize(("supported", "expected"), [(False, 1), (True, 0)])
def test_unsupported_memory_limit_is_reported_once_at_startup(
    monkeypatch: pytest.MonkeyPatch,
    run_worker_calls: list[object],
    caplog: pytest.LogCaptureFixture,
    supported: bool,
    expected: int,
) -> None:
    # T24ag：原来每个任务的子进程各打一次
    monkeypatch.setattr(worker_main, "load_settings", lambda: fake_settings("postgresql://x"))
    monkeypatch.setattr(worker_main, "PgTaskQueue", lambda *_args, **_kwargs: FakeQueue())
    monkeypatch.setattr(worker_main, "memory_limit_supported", lambda: supported)

    assert worker_main.main() == 0
    assert caplog.text.count("不支持限制子进程的内存") == expected
