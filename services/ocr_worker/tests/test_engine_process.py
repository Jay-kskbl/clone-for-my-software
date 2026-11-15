"""T17：识别子进程。正常识别、模型只加载一次、超时、崩溃后重开、租约丢失、启动失败。

用假引擎（tests/fakes.py）在真实的 spawn 子进程里运行，不需要 PaddleOCR。
"""

import uuid

import fakes
import pymupdf
import pytest

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
