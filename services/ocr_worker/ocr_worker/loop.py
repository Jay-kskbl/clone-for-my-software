"""OCR Worker 的主循环：领取 ocr 任务 → 处理（识别期间续租）→ 回写结果。

与通用 Worker（backend/app/worker/loop.py）的规则相同：
- 处理满 max_tasks 个后主动退出，由外层重新拉起（附录 A3 的定期重启）；
- 续租失败按“租约已丢失”处理，不回写结果；
- 数据库出错不让进程崩溃，丢弃连接，稍后重试；
- 崩溃恢复靠租约：本进程死在哪一步，任务的租约都会过期并被重新领取。
"""

import logging
import time
import uuid
from collections.abc import Callable, Sequence
from typing import Protocol

import psycopg
from shared.tasks import TASK_OCR, Task
from shared.text_index import TextIndexError

from ocr_worker.engine_process import EngineStartError
from ocr_worker.pipeline import OcrTaskError, Outcome

logger = logging.getLogger(__name__)


class TaskQueue(Protocol):
    def claim(self, task_types: Sequence[str]) -> Task | None: ...
    def renew(self, task_id: uuid.UUID) -> bool: ...
    def complete(self, task_id: uuid.UUID) -> bool: ...
    def fail(self, task_id: uuid.UUID, error: str, *, retryable: bool) -> str | None: ...
    def reset(self) -> None: ...


# 处理一个任务：传入任务和续租回调，返回结果
Processor = Callable[[Task, Callable[[], bool]], Outcome]


def _renew_or_report_lost(queue: TaskQueue, task: Task) -> bool:
    try:
        return queue.renew(task.id)
    except psycopg.Error as exc:
        logger.error("任务 %s 续租失败（%s），停止处理", task.id, type(exc).__name__)
        queue.reset()
        return False


def _run_one(process: Processor, queue: TaskQueue, task: Task) -> Outcome:
    """执行处理函数，把预期之外的异常也变成 Outcome，不让主循环崩溃。"""
    try:
        return process(task, lambda: _renew_or_report_lost(queue, task))
    except OcrTaskError as exc:
        return Outcome(ok=False, error=f"OcrTaskError: {exc.message}", retryable=False)
    except (EngineStartError, TextIndexError, psycopg.Error) as exc:
        # 模型加载失败、检索服务或数据库故障：稍后重试可能成功
        retryable = getattr(exc, "retryable", True) is not False
        return Outcome(ok=False, error=f"{type(exc).__name__}: {exc}", retryable=retryable)
    except Exception as exc:  # noqa: BLE001 —— 记下原因，按可重试处理
        logger.exception("任务 %s 处理时出现未预期的错误", task.id)
        return Outcome(ok=False, error=f"{type(exc).__name__}: {exc}", retryable=True)


def run_worker(
    queue: TaskQueue,
    process: Processor,
    *,
    max_tasks: int,
    poll_seconds: float,
    should_stop: Callable[[], bool] = lambda: False,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """循环处理 ocr 任务，直到处理满 max_tasks 个或 should_stop() 为真。返回处理的任务数。"""
    processed = 0
    while processed < max_tasks and not should_stop():
        try:
            task = queue.claim([TASK_OCR])
        except psycopg.Error as exc:
            logger.error("领取任务失败（%s），%g 秒后重试", type(exc).__name__, poll_seconds)
            queue.reset()
            sleep(poll_seconds)
            continue
        if task is None:
            sleep(poll_seconds)
            continue

        logger.info(
            "开始 OCR 任务 %s（文档 %s，第 %d/%d 次尝试）",
            task.id,
            task.document_id,
            task.attempts,
            task.max_attempts,
        )
        outcome = _run_one(process, queue, task)
        processed += 1

        if outcome.lease_lost:
            logger.warning("任务 %s 的租约已丢失，不回写结果", task.id)
            continue
        try:
            if outcome.ok:
                if not queue.complete(task.id):
                    logger.warning("任务 %s 已完成，但租约已不属于本 Worker，结果未被记录", task.id)
                else:
                    logger.info("任务 %s 完成（%s）", task.id, outcome.note)
            else:
                status = queue.fail(
                    task.id, outcome.error or "未知错误", retryable=outcome.retryable
                )
                logger.warning("任务 %s 失败（%s），新状态：%s", task.id, outcome.error, status)
        except psycopg.Error as exc:
            logger.error(
                "任务 %s 回写结果失败（%s），等待租约过期后重试", task.id, type(exc).__name__
            )
            queue.reset()
    return processed
