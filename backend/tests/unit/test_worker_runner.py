"""T07：在子进程里执行任务——正常、抛异常、超时、崩溃、租约丢失。

这些测试启动真实的子进程，不需要数据库。
"""

import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
from shared.tasks import Task

from app.worker import runner
from app.worker.runner import run_in_subprocess

TASK = Task(
    id=uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001"),
    task_type="parse",
    document_id=uuid.UUID("bbbbbbbb-0000-4000-8000-000000000002"),
    payload={"marker_dir": None},
    attempts=1,
    max_attempts=3,
)


# 处理函数必须定义在模块顶层：子进程按名字重新导入它们


def handler_ok(task: Task) -> None:
    marker_dir = task.payload["marker_dir"]
    if marker_dir:
        # 证明函数确实执行了，并且是在另一个进程里执行的
        with open(os.path.join(marker_dir, "ran"), "w") as f:
            f.write(f"{task.document_id}:{os.getpid()}")


def handler_raises(_task: Task) -> None:
    raise ValueError("文件已损坏")


class PermanentError(Exception):
    """和 parsing.ParseError 一样的约定：带 retryable=False 表示重试也没用。"""

    retryable = False


def handler_permanent_failure(_task: Task) -> None:
    raise PermanentError("文件已加密")


def handler_parse_error(_task: Task) -> None:
    from app.modules.parsing import ParseError

    raise ParseError("PDF 已加密，需要口令才能读取，无法解析")


def handler_sleeps_forever(_task: Task) -> None:
    time.sleep(600)


def handler_hard_crash(_task: Task) -> None:
    # 模拟解释器崩溃或被系统杀掉：不抛异常、不做任何清理，直接消失
    os._exit(7)


def handler_out_of_memory(_task: Task) -> None:
    raise MemoryError()


def handler_heartbeat(task: Task) -> None:
    # 每 0.05 秒写一个字节，最多 60 秒：文件停止变长就说明子进程已经不在了
    with open(os.path.join(task.payload["marker_dir"], "beat"), "ab", buffering=0) as f:
        for _ in range(1200):
            f.write(b".")
            time.sleep(0.05)


def handler_gets_ctrl_c(task: Task) -> None:
    # 模拟在终端里按 Ctrl-C：信号也会发到子进程。子进程应当忽略它，把任务做完
    os.kill(os.getpid(), signal.SIGINT)
    time.sleep(0.2)
    handler_ok(task)


def test_successful_handler_runs_in_another_process(tmp_path):
    task = Task(**{**TASK.__dict__, "payload": {"marker_dir": str(tmp_path)}})

    result = run_in_subprocess(handler_ok, task, timeout_seconds=30)

    assert result.ok is True
    assert result.error is None
    assert result.lease_lost is False
    document_id, pid = (tmp_path / "ran").read_text().split(":")
    assert document_id == str(TASK.document_id)
    assert int(pid) != os.getpid()


def test_exception_becomes_error_message():
    result = run_in_subprocess(handler_raises, TASK, timeout_seconds=30)

    assert result.ok is False
    assert result.error == "ValueError: 文件已损坏"
    assert result.lease_lost is False


def test_ordinary_exception_is_retryable():
    assert run_in_subprocess(handler_raises, TASK, timeout_seconds=30).retryable is True


def test_non_retryable_exception_is_flagged_across_the_process_boundary():
    result = run_in_subprocess(handler_permanent_failure, TASK, timeout_seconds=30)

    assert result.ok is False
    assert result.error == "PermanentError: 文件已加密"
    assert result.retryable is False


def test_parse_error_from_the_parsing_module_is_not_retried():
    # T07 与 T09 的衔接：解析器报告“文件本身有问题”时，任务框架不应浪费重试次数
    result = run_in_subprocess(handler_parse_error, TASK, timeout_seconds=30)

    assert result.ok is False
    assert "已加密" in result.error
    assert result.retryable is False


def test_memory_error_is_reported_not_fatal_to_parent():
    result = run_in_subprocess(handler_out_of_memory, TASK, timeout_seconds=30)

    assert result.ok is False
    assert result.error.startswith("MemoryError")


def test_timeout_kills_the_subprocess():
    started = time.monotonic()

    result = run_in_subprocess(handler_sleeps_forever, TASK, timeout_seconds=1.5, tick_seconds=0.2)

    assert result.ok is False
    assert "超时" in result.error
    assert result.lease_lost is False
    assert result.retryable is True  # 超时可能是机器一时繁忙，值得再试
    # 远小于处理函数想睡的 600 秒：子进程确实被杀掉了，而不是等它自己结束
    assert time.monotonic() - started < 20


def test_hard_crash_is_reported_with_exit_code():
    result = run_in_subprocess(handler_hard_crash, TASK, timeout_seconds=30)

    assert result.ok is False
    assert "异常退出" in result.error
    assert "7" in result.error


def test_on_tick_is_called_while_running_and_lost_lease_stops_the_task():
    calls = []

    def on_tick() -> bool:
        calls.append(time.monotonic())
        # 前两次续租成功，第三次发现租约已丢失
        return len(calls) < 3

    started = time.monotonic()
    result = run_in_subprocess(
        handler_sleeps_forever, TASK, timeout_seconds=60, tick_seconds=0.2, on_tick=on_tick
    )

    assert len(calls) == 3
    assert result.ok is False
    assert result.lease_lost is True
    assert time.monotonic() - started < 20


def test_on_tick_not_needed_for_fast_task():
    calls = []

    result = run_in_subprocess(
        handler_ok, TASK, timeout_seconds=30, tick_seconds=30, on_tick=lambda: calls.append(1)
    )

    assert result.ok is True
    assert calls == []


# ---- T24aa：Ctrl-C 不打断当前任务 ----


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows 上 os.kill(pid, SIGINT) 会直接结束进程，模拟不了终端里的 Ctrl-C；"
    "Windows 的情况按 windows任务书.md 第 17.5 节手动验证",
)
def test_ctrl_c_reaching_the_child_does_not_fail_the_task(tmp_path):
    task = Task(**{**TASK.__dict__, "payload": {"marker_dir": str(tmp_path)}})

    result = run_in_subprocess(handler_gets_ctrl_c, task, timeout_seconds=30)

    assert result.ok is True, result.error
    assert (tmp_path / "ran").exists()


class _InterruptedOnce:
    """第一次 poll() 抛 InterruptedError，模拟 Windows 上等待时按下 Ctrl-C；之后照常。"""

    def __init__(self, conn) -> None:
        self._conn = conn
        self.interrupted = 0

    def poll(self, timeout: float) -> bool:
        if self.interrupted == 0:
            self.interrupted = 1
            raise InterruptedError(4, "Interrupted function call")
        return self._conn.poll(timeout)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def test_poll_keeps_waiting_after_an_interruption():
    class Conn:
        calls = 0

        def poll(self, timeout: float) -> bool:
            Conn.calls += 1
            if Conn.calls == 1:
                raise InterruptedError(4, "Interrupted function call")
            return True

    assert runner._poll(Conn(), 5.0) is True
    assert Conn.calls == 2


def test_poll_gives_up_at_the_deadline_even_if_interrupted():
    class Conn:
        def poll(self, timeout: float) -> bool:
            raise InterruptedError(4, "Interrupted function call")

    started = time.monotonic()
    assert runner._poll(Conn(), 0.05) is False
    assert time.monotonic() - started < 5


def test_interrupted_wait_in_the_parent_still_finishes_the_task(tmp_path, monkeypatch):
    task = Task(**{**TASK.__dict__, "payload": {"marker_dir": str(tmp_path)}})
    real_mp = runner._mp
    wrapped = []

    class Context:
        def Pipe(self, duplex: bool = True):  # noqa: N802 —— 与 multiprocessing 的名字一致
            parent, child = real_mp.Pipe(duplex=duplex)
            wrapped.append(_InterruptedOnce(parent))
            return wrapped[-1], child

        def __getattr__(self, name):
            return getattr(real_mp, name)

    monkeypatch.setattr(runner, "_mp", Context())

    result = run_in_subprocess(handler_ok, task, timeout_seconds=30, tick_seconds=0.2)

    assert result.ok is True, result.error
    assert wrapped[0].interrupted == 1
    assert (tmp_path / "ran").exists()


# ---- T24ab：父进程被强制结束时，子进程跟着退出 ----


def _size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


def _wait_until(condition, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return condition()


def test_child_exits_when_the_parent_is_killed(tmp_path):
    # 另起一个进程当 Worker 父进程，这样可以真的把它强制结束（kill：POSIX 上是 SIGKILL，
    # Windows 上是 TerminateProcess，等同于 Stop-Process -Force），不影响 pytest 自己
    code = (
        "import dataclasses, sys\n"
        "import test_worker_runner as t\n"
        "task = dataclasses.replace(t.TASK, payload={'marker_dir': sys.argv[1]})\n"
        "t.run_in_subprocess(t.handler_heartbeat, task, timeout_seconds=60)\n"
    )
    beat = tmp_path / "beat"
    parent = subprocess.Popen(
        [sys.executable, "-c", code, str(tmp_path)],
        env={**os.environ, "PYTHONPATH": os.pathsep.join(p for p in sys.path if p)},
    )
    try:
        assert _wait_until(lambda: _size(beat) > 0, 30), "子进程没有开始运行"
    finally:
        parent.kill()
        parent.wait(10)

    time.sleep(1.0)  # 给子进程退出的时间
    size = _size(beat)
    time.sleep(1.0)
    assert _size(beat) == size, "父进程已被强制结束，子进程还在运行"


# ---- T24ag：不支持限制内存的系统上，子进程不再每个任务打印一次 ----


def test_child_is_silent_when_memory_limits_are_not_supported(capfd):
    for _ in range(2):
        assert run_in_subprocess(handler_ok, TASK, timeout_seconds=30, memory_limit_mb=2048).ok

    # 子进程的输出直接进终端，所以用 capfd（抓文件描述符）而不是 capsys
    assert "内存上限" not in capfd.readouterr().err


@pytest.mark.parametrize(
    ("platform", "has_resource", "expected"),
    [
        ("linux", True, True),
        ("linux", False, False),
        ("darwin", True, False),
        ("win32", False, False),
    ],
)
def test_memory_limit_is_only_supported_on_linux(monkeypatch, platform, has_resource, expected):
    monkeypatch.setattr(runner.sys, "platform", platform)
    monkeypatch.setattr(runner, "resource", object() if has_resource else None)

    assert runner.memory_limit_supported() is expected


class _FakeResource:
    RLIMIT_AS = 9

    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list = []
        self._error = error

    def setrlimit(self, which, limits) -> None:
        self.calls.append((which, limits))
        if self._error:
            raise self._error


def test_limit_is_set_on_linux(monkeypatch):
    fake = _FakeResource()
    monkeypatch.setattr(runner, "resource", fake)
    monkeypatch.setattr(runner.sys, "platform", "linux")

    runner._limit_memory(256)

    assert fake.calls == [(9, (256 * 1024 * 1024,) * 2)]


def test_a_real_failure_on_linux_is_still_reported(monkeypatch, caplog):
    monkeypatch.setattr(runner, "resource", _FakeResource(ValueError("over the hard limit")))
    monkeypatch.setattr(runner.sys, "platform", "linux")

    runner._limit_memory(256)

    assert "无法设置内存上限（over the hard limit）" in caplog.text
