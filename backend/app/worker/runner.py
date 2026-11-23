"""在子进程里执行一个任务（附录 A3：子进程隔离、超时、内存上限）。

为什么用子进程：解析库遇到畸形文件可能卡死、吃光内存或直接让解释器崩溃。
放在子进程里，最坏情况是这一个任务失败，Worker 本身和其他文件不受影响。

本模块不访问数据库：续租通过 on_tick 回调交给调用方。
"""

import logging
import multiprocessing
import signal
import time
from collections.abc import Callable
from dataclasses import dataclass
from multiprocessing.connection import Connection

from shared.parent_watch import exit_when_parent_dies
from shared.tasks import Task

try:
    import resource
except ImportError:  # Windows 没有这个模块；那里单个任务只受超时保护
    resource = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# 任务处理函数：接收任务，成功则正常返回，失败则抛异常。
# 必须是模块顶层的函数：子进程用 spawn 方式启动，要按“模块名 + 函数名”重新导入它。
Handler = Callable[[Task], None]

# spawn：子进程是一个全新的解释器，不继承父进程的数据库连接和锁（fork 会继承，容易出问题），
# 并且在 macOS、Linux、Windows 上行为一致。
_mp = multiprocessing.get_context("spawn")

# 杀掉子进程后等它退出的时间
_KILL_WAIT_SECONDS = 5.0


@dataclass(frozen=True)
class RunResult:
    ok: bool
    # 失败原因；成功时为 None
    error: str | None = None
    # True：处理过程中发现租约已不属于本 Worker，子进程已被终止。
    # 此时任务已归别人或已被回收，调用方不应再回写结果。
    lease_lost: bool = False
    # False：重试也不会成功（处理函数抛出的异常带有 retryable=False，例如文件本身已损坏），
    # 调用方应直接把任务标记为 failed。超时、崩溃等情况都按可重试处理。
    retryable: bool = True


def _limit_memory(memory_limit_mb: int) -> None:
    """限制本进程（子进程）的地址空间。

    局限：这个限制在 Linux 上有效；macOS 的内核基本不执行 RLIMIT_AS，设置可能失败或不起作用。
    设置失败只记录警告，不让任务因此失败——超时仍然是有效的兜底。
    """
    if resource is None:
        logger.warning("当前系统不支持设置内存上限，本任务只受超时保护")
        return
    limit = memory_limit_mb * 1024 * 1024
    try:
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except (ValueError, OSError) as exc:
        logger.warning("无法设置内存上限（%s），本任务只受超时保护", exc)


def _child_main(
    handler: Handler, task: Task, memory_limit_mb: int | None, conn: Connection
) -> None:
    """子进程入口：执行处理函数，把结果通过管道告诉父进程。"""
    # 在终端里按 Ctrl-C 时，信号会同时发给父进程和本进程。父进程的约定是“完成当前任务后
    # 退出”；本进程若也响应，KeyboardInterrupt 会被下面当作一次可重试的失败，正在处理的
    # 文件白白记一次失败。所以这里忽略它，由父进程决定何时结束（与 OCR 识别子进程相同，
    # D34；T24aa 补上）
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    # 父进程被强制结束时跟着退出，不留下没有超时、没有续租的孤儿（T24ab）
    exit_when_parent_dies()
    try:
        if memory_limit_mb is not None:
            _limit_memory(memory_limit_mb)
        handler(task)
    except BaseException as exc:  # noqa: BLE001 —— 任何失败（含 MemoryError）都要报告给父进程
        # 异常对象本身不一定能跨进程传递，只传失败原因和“是否值得重试”这两样。
        # 约定：异常带有 retryable 属性且为 False 时不再重试（例如 parsing.ParseError）。
        retryable = getattr(exc, "retryable", True) is not False
        conn.send((f"{type(exc).__name__}: {exc}", retryable))
    else:
        conn.send(None)
    finally:
        conn.close()


def _poll(conn: Connection, timeout: float) -> bool:
    """等管道里有数据，最多 timeout 秒；返回是否有数据。

    Windows 上主线程在 Connection.poll() 里等待时，按下 Ctrl-C 会让它直接抛 InterruptedError
    （等待会同时等 Ctrl-C 事件，PEP 475 的自动重试不覆盖这条路径；macOS、Linux 上信号处理
    函数返回后系统会自动接着等）。此时信号处理函数已经记下“完成当前任务后退出”，
    这里只需接着等，不能让正在处理的任务被当成失败（T24aa）。
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            return conn.poll(max(0.0, deadline - time.monotonic()))
        except InterruptedError:
            if time.monotonic() >= deadline:
                return False


def _kill(process: multiprocessing.process.BaseProcess) -> None:
    process.kill()
    process.join(_KILL_WAIT_SECONDS)


def run_in_subprocess(
    handler: Handler,
    task: Task,
    *,
    timeout_seconds: float,
    memory_limit_mb: int | None = None,
    tick_seconds: float = 1.0,
    on_tick: Callable[[], bool] | None = None,
) -> RunResult:
    """在子进程里执行 handler(task)，等待它结束、超时或崩溃。

    每隔 tick_seconds 调用一次 on_tick（用于续租）；on_tick 返回 False 表示租约已丢失，
    此时终止子进程并返回 lease_lost=True。
    """
    parent_conn, child_conn = _mp.Pipe(duplex=False)
    process = _mp.Process(
        target=_child_main, args=(handler, task, memory_limit_mb, child_conn), daemon=True
    )
    process.start()
    # 父进程关掉自己手里的写端：这样子进程一旦退出，读端就能立刻得到“已关闭”的通知
    child_conn.close()

    deadline = time.monotonic() + timeout_seconds
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _kill(process)
                return RunResult(ok=False, error=f"处理超时（超过 {timeout_seconds:g} 秒），已终止")

            if _poll(parent_conn, min(tick_seconds, remaining)):
                try:
                    failure = parent_conn.recv()
                except EOFError:
                    # 管道关闭但没有收到结果：子进程没来得及报告就死了
                    # （被系统杀掉、解释器崩溃、os._exit 等）
                    process.join(_KILL_WAIT_SECONDS)
                    return RunResult(ok=False, error=f"子进程异常退出（退出码 {process.exitcode}）")
                process.join(_KILL_WAIT_SECONDS)
                if failure is None:
                    return RunResult(ok=True)
                error, retryable = failure
                return RunResult(ok=False, error=error, retryable=retryable)

            if on_tick is not None and not on_tick():
                _kill(process)
                return RunResult(ok=False, error="租约已丢失，停止处理", lease_lost=True)
    finally:
        if process.is_alive():
            _kill(process)
        parent_conn.close()
        process.close()
