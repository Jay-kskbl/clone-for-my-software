"""OCR Worker 入口（ocr 环境）。在 services/ocr_worker/ 目录下运行：

    ../../env_check/.venv-ocr/bin/python -m ocr_worker

处理满 OCR_WORKER_MAX_TASKS 个任务后退出，长期运行时由外层循环重新拉起：

    while true; do ../../env_check/.venv-ocr/bin/python -m ocr_worker || break; done

退出码：0 正常退出；1 配置或模型有问题（重新拉起也没用，外层循环应当停下）。
"""

import functools
import logging
import os
import signal
import socket
import sys
import uuid

import psycopg
from shared.task_queue import PgTaskQueue
from shared.text_index import client_from_settings

from ocr_worker.config import ConfigError, load_settings
from ocr_worker.engine import make_paddle_engine
from ocr_worker.engine_process import EngineProcess, EngineStartError
from ocr_worker.loop import run_worker
from ocr_worker.models import check_models
from ocr_worker.pipeline import OcrOptions, process_task
from ocr_worker.store import PgStore

logger = logging.getLogger("ocr_worker")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        settings = load_settings()
        model = check_models(settings.ocr_det_model_dir, settings.ocr_rec_model_dir)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1

    engine = EngineProcess(
        functools.partial(
            make_paddle_engine,
            str(model.det_dir),
            str(model.rec_dir),
            settings.ocr_device,
        ),
        load_timeout_seconds=settings.ocr_worker_load_timeout_seconds,
        memory_limit_mb=settings.ocr_worker_memory_limit_mb,
    )
    try:
        # 启动时就加载模型：模型有问题在启动时暴露，而不是等到第一个任务
        engine.start()
    except EngineStartError as exc:
        print(f"OCR Worker 无法启动：{exc}", file=sys.stderr)
        return 1
    logger.info(
        "OCR 模型已加载：%s，%s",
        model.model_name,
        model.model_version(engine.library_version or ""),
    )

    stop_requested = False

    def request_stop(signum, _frame) -> None:
        nonlocal stop_requested
        stop_requested = True
        logger.info("收到信号 %s，处理完当前任务后退出", signum)

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    worker_id = f"ocr-{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
    connect_timeout = settings.ocr_worker_db_connect_timeout_seconds
    queue = PgTaskQueue(
        settings.database_url,
        worker_id=worker_id,
        lease_seconds=settings.ocr_worker_lease_seconds,
        connect_timeout_seconds=connect_timeout,
    )
    store = PgStore(settings.database_url, connect_timeout_seconds=connect_timeout)
    try:
        store.ping()
        # T24l：空库或没升级时启动就说清楚，而不是等到第一次写入时报 SQL 错误
        missing = store.schema_problems()
    except psycopg.Error as exc:
        # GLOBAL §12：数据库连接失败时启动就给出清楚的错误，不进入“看起来在运行”的状态。
        # 运行中数据库短暂中断则不退出，主循环会重试
        engine.close()
        print(
            f"OCR Worker 无法连接数据库（{type(exc).__name__}），请确认数据库已启动",
            file=sys.stderr,
        )
        return 1
    if missing:
        engine.close()
        store.reset()
        shown = "、".join(missing[:5]) + ("等" if len(missing) > 5 else "")
        print(
            f"OCR Worker 无法启动：数据库缺少 {len(missing)} 个需要的列（{shown}），"
            "先在 backend/ 目录运行 alembic upgrade head",
            file=sys.stderr,
        )
        return 1
    options = OcrOptions(
        dpi=settings.ocr_pdf_dpi,
        max_pixels=settings.ocr_max_pixels,
        min_confidence=settings.ocr_min_confidence,
        task_timeout_seconds=settings.ocr_worker_task_timeout_seconds,
        heartbeat_seconds=settings.ocr_worker_heartbeat_seconds,
    )

    try:
        with client_from_settings(settings) as index:

            def process(task, on_tick):
                try:
                    return process_task(
                        task,
                        store=store,
                        engine=engine,
                        index=index,
                        model=model,
                        storage_root=settings.storage_root,
                        options=options,
                        on_tick=on_tick,
                    )
                except Exception:
                    # 数据库出错后丢弃连接，下一个任务重新连接；异常交给主循环记为失败
                    store.reset()
                    raise

            processed = run_worker(
                queue,
                process,
                max_tasks=settings.ocr_worker_max_tasks,
                poll_seconds=settings.ocr_worker_poll_seconds,
                should_stop=lambda: stop_requested,
            )
        logger.info("已处理 %d 个任务，退出", processed)
    finally:
        engine.close()
        queue.reset()
        store.reset()
    return 0


if __name__ == "__main__":
    sys.exit(main())
