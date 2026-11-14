"""T07：Worker 主循环——分发、回写、处理 N 个后退出、数据库出错时不崩溃。

用假的任务队列和假的执行器，不需要数据库，也不启动子进程。
领取、租约、回收的真实行为在 tests/integration/test_task_queue.py。
"""

import uuid

import psycopg
import pytest
from shared.tasks import Task

from app.config import Settings
from app.worker.loop import WorkerOptions, run_worker
from app.worker.runner import RunResult

OPTIONS = WorkerOptions(
    max_tasks=10,
    poll_seconds=2.0,
    heartbeat_seconds=15.0,
    task_timeout_seconds=600.0,
    memory_limit_mb=2048,
)


def make_task(task_type: str = "parse") -> Task:
    return Task(
        id=uuid.uuid4(),
        task_type=task_type,
        document_id=uuid.uuid4(),
        payload={},
        attempts=1,
        max_attempts=3,
    )


class FakeQueue:
    """按顺序吐出预设的任务；None 表示“此刻队列为空”，异常实例表示“这次领取时数据库出错”。"""

    def __init__(self, items):
        self.items = list(items)
        self.claimed_types = []
        self.completed = []
        self.failed = []
        self.fail_retryable = []
        self.renewed = []
        self.resets = 0
        self.renew_result = True
        self.complete_error = None

    def claim(self, task_types):
        self.claimed_types.append(list(task_types))
        if not self.items:
            return None
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def renew(self, task_id):
        self.renewed.append(task_id)
        if isinstance(self.renew_result, Exception):
            raise self.renew_result
        return self.renew_result

    def complete(self, task_id):
        if self.complete_error:
            raise self.complete_error
        self.completed.append(task_id)
        return True

    def fail(self, task_id, error, *, retryable):
        self.failed.append((task_id, error))
        self.fail_retryable.append(retryable)
        return "pending" if retryable else "failed"

    def reset(self):
        self.resets += 1


class FakeRunner:
    def __init__(self, results=None, ticks=0):
        self.results = list(results or [])
        self.ticks = ticks
        self.calls = []
        self.tick_results = []

    def __call__(self, handler, task, *, timeout_seconds, memory_limit_mb, tick_seconds, on_tick):
        self.calls.append(
            {
                "handler": handler,
                "task": task,
                "timeout_seconds": timeout_seconds,
                "memory_limit_mb": memory_limit_mb,
                "tick_seconds": tick_seconds,
            }
        )
        for _ in range(self.ticks):
            alive = on_tick()
            self.tick_results.append(alive)
            if not alive:
                return RunResult(ok=False, error="租约已丢失，停止处理", lease_lost=True)
        return self.results.pop(0) if self.results else RunResult(ok=True)


def stop_when_empty(queue):
    return lambda: not queue.items


def parse_handler(_task):
    pass


def cleanup_handler(_task):
    pass


HANDLERS = {"parse": parse_handler, "cleanup": cleanup_handler}


def run(queue, runner, options=OPTIONS, handlers=HANDLERS, sleeps=None):
    return run_worker(
        queue,
        handlers,
        options,
        should_stop=stop_when_empty(queue),
        sleep=(sleeps if sleeps is not None else []).append,
        run=runner,
    )


def test_dispatches_by_task_type_and_completes():
    parse, cleanup = make_task("parse"), make_task("cleanup")
    queue = FakeQueue([parse, cleanup])
    runner = FakeRunner()

    processed = run(queue, runner)

    assert processed == 2
    assert [c["handler"] for c in runner.calls] == [parse_handler, cleanup_handler]
    assert [c["task"] for c in runner.calls] == [parse, cleanup]
    assert queue.completed == [parse.id, cleanup.id]
    assert queue.failed == []


def test_only_claims_types_it_has_handlers_for():
    queue = FakeQueue([make_task("parse")])

    run(queue, FakeRunner())

    # ocr、embed 没有登记处理函数，通用 Worker 不会去领
    assert queue.claimed_types[0] == ["parse", "cleanup"]


def test_options_are_passed_to_the_runner():
    queue = FakeQueue([make_task()])
    runner = FakeRunner()

    run(queue, runner)

    call = runner.calls[0]
    assert call["timeout_seconds"] == 600.0
    assert call["memory_limit_mb"] == 2048
    assert call["tick_seconds"] == 15.0


def test_failed_task_is_reported_with_reason_and_worker_continues():
    bad, good = make_task(), make_task()
    queue = FakeQueue([bad, good])
    runner = FakeRunner([RunResult(ok=False, error="ValueError: 文件已损坏"), RunResult(ok=True)])

    processed = run(queue, runner)

    # 一个文件失败不影响下一个文件
    assert processed == 2
    assert queue.failed == [(bad.id, "ValueError: 文件已损坏")]
    assert queue.completed == [good.id]


def test_retryable_flag_reaches_the_queue():
    # 文件本身损坏这类失败，重试没有意义：处理函数标记的 retryable=False 必须一路传到队列
    corrupt, flaky = make_task(), make_task()
    queue = FakeQueue([corrupt, flaky])
    runner = FakeRunner(
        [
            RunResult(ok=False, error="ParseError: PDF 已加密", retryable=False),
            RunResult(ok=False, error="处理超时"),
        ]
    )

    run(queue, runner)

    assert queue.fail_retryable == [False, True]


def test_exits_after_max_tasks():
    queue = FakeQueue([make_task() for _ in range(5)])
    runner = FakeRunner()
    options = WorkerOptions(**{**OPTIONS.__dict__, "max_tasks": 3})

    processed = run(queue, runner, options=options)

    assert processed == 3
    assert len(queue.completed) == 3
    assert len(queue.items) == 2  # 剩下的留给重启后的 Worker


def test_empty_queue_sleeps_then_polls_again():
    task = make_task()
    queue = FakeQueue([None, None, task])
    sleeps = []

    processed = run(queue, FakeRunner(), sleeps=sleeps)

    assert processed == 1
    assert sleeps == [2.0, 2.0]


def test_should_stop_ends_the_loop_without_claiming():
    queue = FakeQueue([make_task()])

    processed = run_worker(
        queue, HANDLERS, OPTIONS, should_stop=lambda: True, sleep=lambda _s: None, run=FakeRunner()
    )

    assert processed == 0
    assert queue.claimed_types == []


def test_lease_is_renewed_while_the_task_runs():
    task = make_task()
    queue = FakeQueue([task])
    runner = FakeRunner(ticks=3)

    run(queue, runner)

    assert queue.renewed == [task.id] * 3
    assert queue.completed == [task.id]


def test_lost_lease_writes_nothing_back():
    task = make_task()
    queue = FakeQueue([task])
    queue.renew_result = False
    runner = FakeRunner(ticks=1)

    processed = run(queue, runner)

    # 任务已归别人：既不标成功也不标失败，否则会覆盖别人的结果
    assert processed == 1
    assert queue.completed == []
    assert queue.failed == []


def test_database_error_during_renew_is_treated_as_lost_lease():
    task = make_task()
    queue = FakeQueue([task])
    queue.renew_result = psycopg.OperationalError("connection lost")
    runner = FakeRunner(ticks=1)

    run(queue, runner)

    assert runner.tick_results == [False]
    assert queue.completed == []
    assert queue.failed == []
    assert queue.resets == 1


def test_database_error_during_claim_does_not_kill_the_worker():
    task = make_task()
    queue = FakeQueue([psycopg.OperationalError("connection refused"), task])
    sleeps = []

    processed = run(queue, FakeRunner(), sleeps=sleeps)

    assert processed == 1
    assert queue.resets == 1
    assert sleeps == [2.0]
    assert queue.completed == [task.id]


def test_database_error_during_write_back_does_not_kill_the_worker():
    first, second = make_task(), make_task()
    queue = FakeQueue([first, second])
    queue.complete_error = psycopg.OperationalError("connection lost")

    processed = run(queue, FakeRunner())

    # 没写回去的结果靠租约过期后重做来弥补；Worker 自己继续运行
    assert processed == 2
    assert queue.resets == 2


# ---- 配置 ----

BASE = {
    "_env_file": None,
    "database_url": "postgresql://u:p@localhost:5432/db",
    "opensearch_url": "http://localhost:9200",
    "clip_service_url": "http://localhost:8001",
    "jwt_secret": "unit-test-secret-not-used-anywhere-else-0123456789",
}


def test_worker_defaults():
    settings = Settings(**BASE)

    assert settings.worker_lease_seconds == 60.0
    assert settings.worker_heartbeat_seconds == 15.0
    assert settings.worker_max_tasks == 50


def test_heartbeat_must_leave_room_for_a_missed_renewal():
    with pytest.raises(ValueError, match="WORKER_HEARTBEAT_SECONDS"):
        Settings(**BASE, worker_lease_seconds=20, worker_heartbeat_seconds=15)

    assert Settings(**BASE, worker_lease_seconds=30, worker_heartbeat_seconds=15)
