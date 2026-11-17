"""识别子进程：模型只加载一次，一页一页地识别；超时、崩溃时杀掉，下次用到时重开。

为什么不像通用 Worker 那样每个任务开一个新子进程：加载 PP-OCR 模型要 10 秒以上，
每页都重新加载太慢。为什么不在 Worker 进程里直接识别：PaddleOCR 遇到畸形图片可能卡死、
吃光内存或让解释器崩溃，放在子进程里，最坏情况是这一页失败、子进程重开，Worker 不受影响
（GLOBAL §3.3 第 4 条）。

渲染（PDF 页 → 像素）也在子进程里做，理由相同。
"""

import logging
import multiprocessing
import time
from collections.abc import Callable
from dataclasses import dataclass
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter
from shared.contracts import OcrLocator

from ocr_worker.engine import Engine, RecognizedLine
from ocr_worker.rendering import render

try:
    import resource
except ImportError:  # Windows 没有这个模块；那里只受超时保护
    resource = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# spawn：子进程是全新的解释器，不继承父进程的数据库连接（与通用 Worker 相同）
_mp = multiprocessing.get_context("spawn")
_KILL_WAIT_SECONDS = 5.0
_LOCATOR = TypeAdapter(OcrLocator)


@dataclass(frozen=True)
class Job:
    path: str
    locator: dict[str, Any]
    dpi: int
    max_pixels: int


@dataclass(frozen=True)
class EngineResult:
    ok: bool
    lines: tuple[RecognizedLine, ...] = ()
    error: str | None = None
    # False：重试也不会成功（文件本身渲染不了）。超时、崩溃按可重试处理
    retryable: bool = True
    lease_lost: bool = False


class EngineStartError(Exception):
    """识别子进程没能启动（模型加载失败或超时）。"""


def _limit_memory(memory_limit_mb: int | None) -> None:
    if memory_limit_mb is None or resource is None:
        return
    limit = memory_limit_mb * 1024 * 1024
    try:
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except (ValueError, OSError) as exc:
        logger.warning("无法设置识别子进程的内存上限（%s），只受超时保护", exc)


def _child_main(
    factory: Callable[[], Engine], memory_limit_mb: int | None, conn: Connection
) -> None:
    """子进程入口：创建引擎，然后逐个处理父进程发来的任务，直到管道关闭。"""
    try:
        _limit_memory(memory_limit_mb)
        engine = factory()
    except BaseException as exc:  # noqa: BLE001 —— 任何失败都要告诉父进程
        conn.send(("start_failed", f"{type(exc).__name__}: {exc}"))
        conn.close()
        return
    conn.send(("ready", engine.library_version))

    while True:
        try:
            job: Job = conn.recv()
        except (EOFError, OSError):
            return  # 父进程关闭了管道
        try:
            image = render(
                Path(job.path),
                _LOCATOR.validate_python(job.locator),
                dpi=job.dpi,
                max_pixels=job.max_pixels,
            )
            lines = engine.recognize(image)
        except BaseException as exc:  # noqa: BLE001
            retryable = getattr(exc, "retryable", True) is not False
            conn.send(("failed", f"{type(exc).__name__}: {exc}", retryable))
        else:
            conn.send(("ok", tuple(lines)))


class EngineProcess:
    """父进程这一侧。不是线程安全的：一个 Worker 一次只识别一页。"""

    def __init__(
        self,
        factory: Callable[[], Engine],
        *,
        load_timeout_seconds: float,
        memory_limit_mb: int | None = None,
    ) -> None:
        """factory：在子进程里调用、返回识别引擎。必须能被 pickle（模块顶层函数或其 partial）。"""
        self._factory = factory
        self._load_timeout = load_timeout_seconds
        self._memory_limit_mb = memory_limit_mb
        self._process: multiprocessing.process.BaseProcess | None = None
        self._conn: Connection | None = None
        self.library_version: str | None = None

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.is_alive()

    def start(self) -> None:
        """启动子进程并等模型加载完。已在运行时什么也不做。失败抛 EngineStartError。"""
        if self.running:
            return
        self._stop()
        parent_conn, child_conn = _mp.Pipe(duplex=True)
        process = _mp.Process(
            target=_child_main,
            args=(self._factory, self._memory_limit_mb, child_conn),
            daemon=True,
        )
        process.start()
        child_conn.close()
        self._process, self._conn = process, parent_conn

        if not parent_conn.poll(self._load_timeout):
            self._stop()
            raise EngineStartError(f"加载 OCR 模型超时（超过 {self._load_timeout:g} 秒）")
        try:
            message = parent_conn.recv()
        except EOFError:
            process.join(_KILL_WAIT_SECONDS)
            exitcode = process.exitcode
            self._stop()
            raise EngineStartError(f"OCR 子进程启动时异常退出（退出码 {exitcode}）") from None
        if message[0] != "ready":
            self._stop()
            raise EngineStartError(f"OCR 模型加载失败：{message[1]}")
        self.library_version = message[1]

    def run(
        self,
        job: Job,
        *,
        timeout_seconds: float,
        tick_seconds: float,
        on_tick: Callable[[], bool] | None = None,
    ) -> EngineResult:
        """识别一页。每隔 tick_seconds 调用一次 on_tick（续租），它返回 False 时停止。

        子进程没在运行时先启动它；启动失败抛 EngineStartError（由调用方按可重试的失败处理）。
        """
        self.start()
        assert self._conn is not None and self._process is not None
        self._conn.send(job)

        deadline = time.monotonic() + timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._stop()
                return EngineResult(
                    ok=False, error=f"识别超时（超过 {timeout_seconds:g} 秒），已终止"
                )
            if self._conn.poll(min(tick_seconds, remaining)):
                try:
                    message = self._conn.recv()
                except EOFError:
                    self._process.join(_KILL_WAIT_SECONDS)
                    exitcode = self._process.exitcode
                    self._stop()
                    return EngineResult(ok=False, error=f"识别子进程异常退出（退出码 {exitcode}）")
                if message[0] == "ok":
                    return EngineResult(ok=True, lines=tuple(message[1]))
                return EngineResult(ok=False, error=message[1], retryable=message[2])
            if on_tick is not None and not on_tick():
                # 正在识别的这一页已不归本 Worker：子进程的结果作废，杀掉它
                self._stop()
                return EngineResult(ok=False, error="租约已丢失，停止处理", lease_lost=True)

    def _stop(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        if self._process is not None:
            if self._process.is_alive():
                self._process.kill()
            self._process.join(_KILL_WAIT_SECONDS)
            self._process.close()
            self._process = None

    def close(self) -> None:
        self._stop()
