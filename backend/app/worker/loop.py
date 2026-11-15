"""通用 Worker 的主循环：领取 → 在子进程里执行 → 续租 → 回写结果。

崩溃恢复不靠这里的代码，而靠租约（shared/tasks.py）：本进程无论死在哪一步，
任务的租约都会过期，然后被别的 Worker 或重启后的自己重新领取。
"""

import logging
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

import psycopg
from shared import tasks

# PgTaskQueue 已移到 shared（OCR Worker 也要用）；__main__ 和测试仍从这里导入
from shared.task_queue import PgTaskQueue  # noqa: F401
from shared.tasks import Task

from app.worker.runner import Handler, RunResult, run_in_subprocess

logger = logging.getLogger(__name__)


class TaskQueue(Protocol):
    """主循环对任务队列的全部要求。测试用假实现替换，不需要数据库。"""

    def claim(self, task_types: Sequence[str]) -> Task | None: ...
    def renew(self, task_id: uuid.UUID) -> bool: ...
    def complete(self, task_id: uuid.UUID) -> bool: ...
    def fail(self, task_id: uuid.UUID, error: str, *, retryable: bool) -> str | None: ...
    def reset(self) -> None: ...


@dataclass(frozen=True)
class WorkerOptions:
    max_tasks: int
    poll_seconds: float
    heartbeat_seconds: float
    task_timeout_seconds: float
    memory_limit_mb: int | None


class _Runner(Protocol):
    def __call__(
        self,
        handler: Handler,
        task: Task,
        *,
        timeout_seconds: float,
        memory_limit_mb: int | None,
        tick_seconds: float,
        on_tick: Callable[[], bool],
    ) -> RunResult: ...


def _renew_or_report_lost(queue: TaskQueue, task: Task) -> bool:
    try:
        return queue.renew(task.id)
    except psycopg.Error as exc:
        # 续租时数据库出错：无法确认租约还在，按“已丢失”处理并停止任务。
        # 租约到期后任务会被回收重试，比冒着两个 Worker 同时处理同一任务的风险继续跑要安全。
        logger.error("任务 %s 续租失败（%s），停止处理", task.id, type(exc).__name__)
        queue.reset()
        return False


def _process(
    queue: TaskQueue, handler: Handler, task: Task, options: WorkerOptions, run: _Runner
) -> None:
    result = run(
        handler,
        task,
        timeout_seconds=options.task_timeout_seconds,
        memory_limit_mb=options.memory_limit_mb,
        tick_seconds=options.heartbeat_seconds,
        on_tick=lambda: _renew_or_report_lost(queue, task),
    )

    if result.lease_lost:
        logger.warning("任务 %s 的租约已丢失，不回写结果", task.id)
        return

    try:
        if result.ok:
            if queue.complete(task.id):
                pass
            elif task.task_type == tasks.TASK_CLEANUP:
                # 正常情况：清理任务的最后一步是硬删除文档，数据库的级联删除
                # 把这个任务自己的记录也删掉了，所以没有记录可以标记为成功
                logger.info("清理任务 %s 已完成，任务记录已随文档一并删除", task.id)
            else:
                logger.warning("任务 %s 已完成，但租约已不属于本 Worker，结果未被记录", task.id)
        else:
            status = queue.fail(task.id, result.error or "未知错误", retryable=result.retryable)
            logger.warning("任务 %s 失败（%s），新状态：%s", task.id, result.error, status)
    except psycopg.Error as exc:
        # 结果没写回去：不重试回写，让租约过期后由回收机制处理（处理函数是幂等的，重做是安全的）
        logger.error("任务 %s 回写结果失败（%s），等待租约过期后重试", task.id, type(exc).__name__)
        queue.reset()


def run_worker(
    queue: TaskQueue,
    handlers: Mapping[str, Handler],
    options: WorkerOptions,
    *,
    should_stop: Callable[[], bool] = lambda: False,
    sleep: Callable[[float], None] = time.sleep,
    run: _Runner = run_in_subprocess,
) -> int:
    """循环处理任务，直到处理满 options.max_tasks 个或 should_stop() 为真。返回处理的任务数。

    处理满 max_tasks 个后主动退出（附录 A3 的“定期重启”）：由外层的进程管理器或循环脚本
    重新拉起，避免长时间运行累积的内存增长。
    """
    task_types = list(handlers)
    processed = 0
    while processed < options.max_tasks and not should_stop():
        try:
            task = queue.claim(task_types)
        except psycopg.Error as exc:
            logger.error(
                "领取任务失败（%s），%g 秒后重试", type(exc).__name__, options.poll_seconds
            )
            queue.reset()
            sleep(options.poll_seconds)
            continue

        if task is None:
            sleep(options.poll_seconds)
            continue

        logger.info(
            "开始任务 %s（类型 %s，文档 %s，第 %d/%d 次尝试）",
            task.id,
            task.task_type,
            task.document_id,
            task.attempts,
            task.max_attempts,
        )
        _process(queue, handlers[task.task_type], task, options, run)
        processed += 1
    return processed
