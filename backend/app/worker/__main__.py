"""通用 Worker 入口（backend/ 目录，main 环境）：

    python -m app.worker

处理满 WORKER_MAX_TASKS 个任务后以退出码 0 退出，需要由外层重新拉起，例如：

    while true; do python -m app.worker || break; done

收到 SIGTERM / Ctrl-C 时，做完手头的任务再退出（退出码 130，上面的循环随之结束）。

退出码：0 处理满任务数后正常退出；1 配置有问题或启动时连不上数据库（重新拉起也没用，
外层循环应当停下）；130 收到停止信号。
"""

import logging
import os
import signal
import socket
import sys
import uuid

import psycopg

from app.config import load_settings
from app.core.errors import ConfigError
from app.worker.loop import PgTaskQueue, WorkerOptions, run_worker
from app.worker.registry import HANDLERS

logger = logging.getLogger("app.worker")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1

    if not HANDLERS:
        logger.warning("没有登记任何任务处理函数，Worker 不会领取任务")

    # 每次启动都是新的标识：重启后的 Worker 不会被当成崩溃前的那个，旧租约只能等过期回收
    worker_id = f"{socket.gethostname()[:64]}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
    stop_requested = False

    def request_stop(signum: int, _frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True
        logger.info("收到信号 %s，完成当前任务后退出", signal.Signals(signum).name)

    queue = PgTaskQueue(
        settings.database_url, worker_id=worker_id, lease_seconds=settings.worker_lease_seconds
    )
    try:
        queue.ping()
    except psycopg.Error as exc:
        # GLOBAL §12：数据库连接失败时启动就给出清楚的错误，不进入“看起来在运行”的状态
        # （与 OCR Worker 一致，D30）。运行中数据库短暂中断则不退出，主循环会重试。
        # 只输出异常类型：异常文本里可能带主机、端口和数据库用户名
        queue.reset()
        print(
            f"Worker 无法连接数据库（{type(exc).__name__}），请确认数据库已启动、DATABASE_URL 正确",
            file=sys.stderr,
        )
        return 1

    # 在连上数据库之后才接管信号：启动检查期间按 Ctrl-C 照常中断
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    options = WorkerOptions(
        max_tasks=settings.worker_max_tasks,
        poll_seconds=settings.worker_poll_seconds,
        heartbeat_seconds=settings.worker_heartbeat_seconds,
        task_timeout_seconds=settings.worker_task_timeout_seconds,
        memory_limit_mb=settings.worker_memory_limit_mb,
    )
    logger.info("Worker %s 启动，可处理的任务类型：%s", worker_id, sorted(HANDLERS) or "无")
    try:
        processed = run_worker(queue, HANDLERS, options, should_stop=lambda: stop_requested)
    finally:
        queue.reset()

    logger.info("Worker %s 退出，共处理 %d 个任务", worker_id, processed)
    return 130 if stop_requested else 0


if __name__ == "__main__":
    sys.exit(main())
