"""T24ac：OCR Worker 入口的退出码。外层循环靠它决定要不要重新拉起。

不加载模型、不连数据库：入口用到的外部对象全部换成假的，只看退出码。
"""

import contextlib
import signal
from types import SimpleNamespace

import pytest

from ocr_worker import __main__ as ocr_main


class FakeEngine:
    library_version = "fake-1.0"

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def start(self) -> None:
        pass

    def close(self) -> None:
        pass


class FakeQueue:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def reset(self) -> None:
        pass


class FakeStore(FakeQueue):
    def ping(self) -> None:
        pass

    def schema_problems(self) -> list[str]:
        return []


class AnySettings:
    """任何配置项都有值：入口只是把它们转交给（假的）对象。"""

    def __getattr__(self, _name: str) -> int:
        return 1


@pytest.fixture
def handlers(monkeypatch) -> dict:
    """换掉外部对象，返回入口登记的信号处理函数（不真的改动 pytest 进程的信号设置）。"""
    registered: dict = {}
    model = SimpleNamespace(
        det_dir="det", rec_dir="rec", model_name="fake", model_version=lambda version: version
    )
    monkeypatch.setattr(ocr_main, "load_settings", AnySettings)
    monkeypatch.setattr(ocr_main, "check_models", lambda *_args: model)
    monkeypatch.setattr(ocr_main, "EngineProcess", FakeEngine)
    monkeypatch.setattr(ocr_main, "PgTaskQueue", FakeQueue)
    monkeypatch.setattr(ocr_main, "PgStore", FakeStore)
    monkeypatch.setattr(
        ocr_main, "client_from_settings", lambda _settings: contextlib.nullcontext(object())
    )
    monkeypatch.setattr(ocr_main.signal, "signal", registered.__setitem__)
    return registered


def test_exits_0_after_reaching_max_tasks(handlers, monkeypatch):
    monkeypatch.setattr(ocr_main, "run_worker", lambda *_args, **_kwargs: 200)

    # 0：做满任务数，外层循环应当重新拉起（附录 A3 的定期重启）
    assert ocr_main.main() == 0


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
def test_exits_130_after_a_stop_signal(handlers, monkeypatch, signum):
    def fake_run_worker(*_args, should_stop, **_kwargs) -> int:
        assert not should_stop()
        handlers[signum](signum, None)  # 处理任务途中收到停止信号
        assert should_stop()
        return 1

    monkeypatch.setattr(ocr_main, "run_worker", fake_run_worker)

    # 130：收到停止信号，外层循环应当停下（与通用 Worker 相同）。返回 0 会被马上重新拉起
    assert ocr_main.main() == 130


def test_stop_signal_wins_when_max_tasks_is_reached_at_the_same_time(handlers, monkeypatch):
    def fake_run_worker(*_args, max_tasks, **_kwargs) -> int:
        handlers[signal.SIGINT](signal.SIGINT, None)
        return max_tasks

    monkeypatch.setattr(ocr_main, "run_worker", fake_run_worker)

    assert ocr_main.main() == 130
