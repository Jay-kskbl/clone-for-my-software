"""T17：OCR Worker 主循环。队列和处理函数都是假的。"""

import uuid

import psycopg
from shared.tasks import Task

from ocr_worker.engine_process import EngineStartError
from ocr_worker.loop import run_worker
from ocr_worker.pipeline import OcrTaskError, Outcome


def make_task() -> Task:
    return Task(
        id=uuid.uuid4(),
        task_type="ocr",
        document_id=uuid.uuid4(),
        payload={},
        attempts=1,
        max_attempts=3,
    )


class FakeQueue:
    def __init__(self, items) -> None:
        self.items = list(items)
        self.claimed_types = []
        self.completed = []
        self.failed = []
        self.renewed = []
        self.resets = 0

    def claim(self, task_types):
        self.claimed_types.append(list(task_types))
        item = self.items.pop(0) if self.items else None
        if isinstance(item, Exception):
            raise item
        return item

    def renew(self, task_id):
        self.renewed.append(task_id)
        return True

    def complete(self, task_id):
        self.completed.append(task_id)
        return True

    def fail(self, task_id, error, *, retryable):
        self.failed.append((task_id, error, retryable))
        return "pending" if retryable else "failed"

    def reset(self):
        self.resets += 1


def run(queue, process, max_tasks=None):
    return run_worker(
        queue,
        process,
        max_tasks=max_tasks or len([i for i in queue.items if isinstance(i, Task)]),
        poll_seconds=0,
        sleep=lambda _: None,
    )


def test_only_ocr_tasks_are_claimed_and_success_is_recorded():
    task = make_task()
    queue = FakeQueue([task])

    assert run(queue, lambda t, tick: Outcome(ok=True, note="processed")) == 1

    assert queue.claimed_types == [["ocr"]]
    assert queue.completed == [task.id]


def test_on_tick_renews_the_lease():
    task = make_task()
    queue = FakeQueue([task])

    def process(t, on_tick):
        assert on_tick() is True
        return Outcome(ok=True)

    run(queue, process)

    assert queue.renewed == [task.id]


def test_failure_outcome_is_recorded_with_its_retryability():
    task = make_task()
    queue = FakeQueue([task])

    run(queue, lambda t, tick: Outcome(ok=False, error="识别超时", retryable=True))

    assert queue.failed == [(task.id, "识别超时", True)]


def test_lost_lease_writes_nothing():
    queue = FakeQueue([make_task()])

    run(queue, lambda t, tick: Outcome(ok=False, lease_lost=True))

    assert queue.completed == [] and queue.failed == []


def test_exceptions_become_failures_without_crashing_the_loop():
    tasks = [make_task() for _ in range(4)]
    queue = FakeQueue(tasks)
    errors = iter(
        [
            OcrTaskError("原始文件不存在"),
            EngineStartError("加载 OCR 模型超时"),
            psycopg.OperationalError("connection lost"),
            ValueError("意外"),
        ]
    )

    def process(t, tick):
        raise next(errors)

    assert run(queue, process) == 4

    assert [(error.split(":")[0], retryable) for _, error, retryable in queue.failed] == [
        ("OcrTaskError", False),
        ("EngineStartError", True),
        ("OperationalError", True),
        ("ValueError", True),
    ]


def test_claim_errors_reset_the_connection_and_the_loop_keeps_going():
    task = make_task()
    queue = FakeQueue([psycopg.OperationalError("down"), None, task])

    assert run(queue, lambda t, tick: Outcome(ok=True), max_tasks=1) == 1

    assert queue.resets == 1
    assert queue.completed == [task.id]


def test_stops_after_max_tasks():
    queue = FakeQueue([make_task() for _ in range(5)])

    assert run(queue, lambda t, tick: Outcome(ok=True), max_tasks=2) == 2
    assert len(queue.completed) == 2
