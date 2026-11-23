"""T17：识别子进程。正常识别、模型只加载一次、超时、崩溃后重开、租约丢失、启动失败。

用假引擎（tests/fakes.py）在真实的 spawn 子进程里运行，不需要 PaddleOCR。
"""

import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import fakes
import pymupdf
import pytest

from ocr_worker import engine_process
from ocr_worker.engine_process import EngineProcess, EngineStartError, Job

IMAGE_ID = str(uuid.UUID("11111111-2222-4333-8444-555555555555"))


@pytest.fixture
def image_job(tmp_path) -> Job:
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 20), False)
    pix.clear_with(200)
    path = tmp_path / "a.png"
    path.write_bytes(pix.tobytes("png"))
    return Job(
        path=str(path),
        locator={"type": "image", "image_id": IMAGE_ID},
        dpi=200,
        max_pixels=10**8,
    )


def engine(factory, **kwargs) -> EngineProcess:
    return EngineProcess(factory, load_timeout_seconds=kwargs.pop("load_timeout", 30.0), **kwargs)


def test_lines_come_back_from_the_child(image_job):
    process = engine(fakes.echo_engine)
    try:
        result = process.run(image_job, timeout_seconds=30, tick_seconds=0.2)

        assert result.ok
        assert [line.text for line in result.lines] == ["尺寸 40x20", "第二行文字"]
        assert process.library_version == "fake-1.0"
    finally:
        process.close()


def test_the_model_is_loaded_once_for_many_pages(image_job):
    process = engine(fakes.echo_engine)
    try:
        process.start()
        pid = process._process.pid
        for _ in range(3):
            assert process.run(image_job, timeout_seconds=30, tick_seconds=0.2).ok
        assert process._process.pid == pid
    finally:
        process.close()


def test_render_failure_is_reported_as_not_retryable(tmp_path):
    process = engine(fakes.echo_engine)
    try:
        job = Job(
            path=str(tmp_path / "missing.pdf"),
            locator={"type": "pdf_page", "page": 1},
            dpi=72,
            max_pixels=10**8,
        )
        result = process.run(job, timeout_seconds=30, tick_seconds=0.2)

        assert not result.ok and result.retryable is False
        assert "RenderError" in result.error
        # 子进程没有因此退出，下一页照常识别
        assert process.running
    finally:
        process.close()


def test_engine_exception_is_retryable_and_keeps_the_child(image_job):
    process = engine(fakes.raising_engine)
    try:
        result = process.run(image_job, timeout_seconds=30, tick_seconds=0.2)

        assert not result.ok and result.retryable is True
        assert "识别库内部错误" in result.error
        assert process.running
    finally:
        process.close()


def test_timeout_kills_the_child_and_the_next_run_starts_a_new_one(image_job):
    process = engine(fakes.slow_engine)
    try:
        process.start()
        first_pid = process._process.pid

        result = process.run(image_job, timeout_seconds=1, tick_seconds=0.2)

        assert not result.ok and result.retryable is True
        assert "超时" in result.error
        assert not process.running
        process.start()
        assert process._process.pid != first_pid
    finally:
        process.close()


def test_crash_is_reported_and_the_child_is_restarted(image_job):
    process = engine(fakes.crashing_engine)
    try:
        result = process.run(image_job, timeout_seconds=30, tick_seconds=0.2)

        assert not result.ok and result.retryable is True
        assert "退出码 3" in result.error
        assert not process.running
    finally:
        process.close()


def test_lost_lease_stops_the_child(image_job):
    process = engine(fakes.slow_engine)
    ticks = []

    def on_tick() -> bool:
        ticks.append(1)
        return len(ticks) < 2

    try:
        result = process.run(image_job, timeout_seconds=30, tick_seconds=0.1, on_tick=on_tick)

        assert result.lease_lost and not result.ok
        assert not process.running
    finally:
        process.close()


def test_model_load_failure_is_a_start_error():
    process = engine(fakes.broken_engine)
    try:
        with pytest.raises(EngineStartError, match="模型文件缺失"):
            process.start()
        assert not process.running
    finally:
        process.close()


def test_model_load_timeout_is_a_start_error():
    process = engine(fakes.slow_loading_engine, load_timeout=1.0)
    try:
        with pytest.raises(EngineStartError, match="超时"):
            process.start()
        assert not process.running
    finally:
        process.close()


# ---- T24aa：Ctrl-C 不打断正在识别的这一页 ----


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows 上 os.kill(pid, SIGINT) 会直接结束进程，模拟不了终端里的 Ctrl-C；"
    "Windows 的情况按 windows任务书.md 第 17.5 节手动验证",
)
def test_ctrl_c_reaching_the_child_does_not_fail_the_page(image_job):
    process = engine(fakes.ctrl_c_engine)
    try:
        result = process.run(image_job, timeout_seconds=30, tick_seconds=0.1)

        assert result.ok, result.error
        assert result.lines[0].text == "尺寸 40x20"
        assert process.running
    finally:
        process.close()


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

    assert engine_process._poll(Conn(), 5.0) is True
    assert Conn.calls == 2


def test_poll_gives_up_at_the_deadline_even_if_interrupted():
    class Conn:
        def poll(self, timeout: float) -> bool:
            raise InterruptedError(4, "Interrupted function call")

    started = time.monotonic()
    assert engine_process._poll(Conn(), 0.05) is False
    assert time.monotonic() - started < 5


def test_interrupted_wait_in_the_parent_still_returns_the_page(image_job):
    process = engine(fakes.echo_engine)
    try:
        process.start()
        flaky = _InterruptedOnce(process._conn)
        process._conn = flaky

        result = process.run(image_job, timeout_seconds=30, tick_seconds=0.1)

        assert result.ok, result.error
        assert flaky.interrupted == 1
        assert process.running
    finally:
        process.close()


# ---- T24ab：父进程被强制结束时，识别子进程跟着退出 ----


def _size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


def _wait_until(condition, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return condition()


def test_child_exits_when_the_parent_is_killed(image_job, tmp_path):
    # 另起一个进程当 OCR Worker 父进程，这样可以真的把它强制结束，不影响 pytest 自己
    code = (
        "import functools, sys\n"
        "import fakes\n"
        "from ocr_worker.engine_process import EngineProcess, Job\n"
        "job = Job(path=sys.argv[1], locator={'type': 'image', 'image_id': sys.argv[2]},"
        " dpi=200, max_pixels=10**8)\n"
        "factory = functools.partial(fakes.heartbeat_engine, sys.argv[3])\n"
        "process = EngineProcess(factory, load_timeout_seconds=30.0)\n"
        "process.run(job, timeout_seconds=60, tick_seconds=0.1)\n"
    )
    beat = tmp_path / "beat"
    parent = subprocess.Popen(
        [sys.executable, "-c", code, image_job.path, IMAGE_ID, str(beat)],
        env={**os.environ, "PYTHONPATH": os.pathsep.join(p for p in sys.path if p)},
    )
    try:
        assert _wait_until(lambda: _size(beat) > 0, 30), "识别子进程没有开始运行"
    finally:
        parent.kill()
        parent.wait(10)

    time.sleep(1.0)  # 给子进程退出的时间
    size = _size(beat)
    time.sleep(1.0)
    assert _size(beat) == size, "父进程已被强制结束，识别子进程还在运行"
