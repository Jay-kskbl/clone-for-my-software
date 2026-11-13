"""在子进程里执行一个任务（附录 A3：子进程隔离、超时、内存上限）。

为什么用子进程：解析库遇到畸形文件可能卡死、吃光内存或直接让解释器崩溃。
放在子进程里，最坏情况是这一个任务失败，Worker 本身和其他文件不受影响。

本模块不访问数据库：续租通过 on_tick 回调交给调用方。
"""

import logging
import multiprocessing
import resource
import time
from collections.abc import Callable
from dataclasses import dataclass
from multiprocessing.connection import Connection

from shared.tasks import Task

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


def _limit_memory(memory_limit_mb: int) -> None:
    """限制本进程（子进程）的地址空间。

    局限：这个限制在 Linux 上有效；macOS 的内核基本不执行 RLIMIT_AS，设置可能失败或不起作用。
    设置失败只记录警告，不让任务因此失败——超时仍然是有效的兜底。
    """
    limit = memory_limit_mb * 1024 * 1024
    try:
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except (ValueError, OSError) as exc:
        logger.warning("无法设置内存上限（%s），本任务只受超时保护", exc)


def _child_main(
    handler: Handler, task: Task, memory_limit_mb: int | None, conn: Connection
) -> None:
    """子进程入口：执行处理函数，把结果通过管道告诉父进程。"""
    try:
        if memory_limit_mb is not None:
            _limit_memory(memory_limit_mb)
        handler(task)
    except BaseException as exc:  # noqa: BLE001 —— 任何失败（含 MemoryError）都要报告给父进程
        conn.send(f"{type(exc).__name__}: {exc}")
    else:
        conn.send(None)
    finally:
        conn.close()


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

            if parent_conn.poll(min(tick_seconds, remaining)):
                try:
                    error = parent_conn.recv()
                except EOFError:
                    # 管道关闭但没有收到结果：子进程没来得及报告就死了
                    # （被系统杀掉、解释器崩溃、os._exit 等）
                    process.join(_KILL_WAIT_SECONDS)
                    return RunResult(ok=False, error=f"子进程异常退出（退出码 {process.exitcode}）")
                process.join(_KILL_WAIT_SECONDS)
                return RunResult(ok=error is None, error=error)

            if on_tick is not None and not on_tick():
                _kill(process)
                return RunResult(ok=False, error="租约已丢失，停止处理", lease_lost=True)
    finally:
        if process.is_alive():
            _kill(process)
        parent_conn.close()
        process.close()
