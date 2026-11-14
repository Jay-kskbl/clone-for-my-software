"""T07：在子进程里执行任务——正常、抛异常、超时、崩溃、租约丢失。

这些测试启动真实的子进程，不需要数据库。
"""

import os
import time
import uuid

from shared.tasks import Task

from app.worker.runner import run_in_subprocess

TASK = Task(
    id=uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001"),
    task_type="parse",
    document_id=uuid.UUID("bbbbbbbb-0000-4000-8000-000000000002"),
    payload={"marker_dir": None},
    attempts=1,
    max_attempts=3,
)


# 处理函数必须定义在模块顶层：子进程按名字重新导入它们


def handler_ok(task: Task) -> None:
    marker_dir = task.payload["marker_dir"]
    if marker_dir:
        # 证明函数确实执行了，并且是在另一个进程里执行的
        with open(os.path.join(marker_dir, "ran"), "w") as f:
            f.write(f"{task.document_id}:{os.getpid()}")


def handler_raises(_task: Task) -> None:
    raise ValueError("文件已损坏")


class PermanentError(Exception):
    """和 parsing.ParseError 一样的约定：带 retryable=False 表示重试也没用。"""

    retryable = False


def handler_permanent_failure(_task: Task) -> None:
    raise PermanentError("文件已加密")


def handler_parse_error(_task: Task) -> None:
    from app.modules.parsing import ParseError

    raise ParseError("PDF 已加密，需要口令才能读取，无法解析")


def handler_sleeps_forever(_task: Task) -> None:
    time.sleep(600)


def handler_hard_crash(_task: Task) -> None:
    # 模拟解释器崩溃或被系统杀掉：不抛异常、不做任何清理，直接消失
    os._exit(7)


def handler_out_of_memory(_task: Task) -> None:
    raise MemoryError()


def test_successful_handler_runs_in_another_process(tmp_path):
    task = Task(**{**TASK.__dict__, "payload": {"marker_dir": str(tmp_path)}})

    result = run_in_subprocess(handler_ok, task, timeout_seconds=30)

    assert result.ok is True
    assert result.error is None
    assert result.lease_lost is False
    document_id, pid = (tmp_path / "ran").read_text().split(":")
    assert document_id == str(TASK.document_id)
    assert int(pid) != os.getpid()


def test_exception_becomes_error_message():
    result = run_in_subprocess(handler_raises, TASK, timeout_seconds=30)

    assert result.ok is False
    assert result.error == "ValueError: 文件已损坏"
    assert result.lease_lost is False


def test_ordinary_exception_is_retryable():
    assert run_in_subprocess(handler_raises, TASK, timeout_seconds=30).retryable is True


def test_non_retryable_exception_is_flagged_across_the_process_boundary():
    result = run_in_subprocess(handler_permanent_failure, TASK, timeout_seconds=30)

    assert result.ok is False
    assert result.error == "PermanentError: 文件已加密"
    assert result.retryable is False


def test_parse_error_from_the_parsing_module_is_not_retried():
    # T07 与 T09 的衔接：解析器报告“文件本身有问题”时，任务框架不应浪费重试次数
    result = run_in_subprocess(handler_parse_error, TASK, timeout_seconds=30)

    assert result.ok is False
    assert "已加密" in result.error
    assert result.retryable is False


def test_memory_error_is_reported_not_fatal_to_parent():
    result = run_in_subprocess(handler_out_of_memory, TASK, timeout_seconds=30)

    assert result.ok is False
    assert result.error.startswith("MemoryError")


def test_timeout_kills_the_subprocess():
    started = time.monotonic()

    result = run_in_subprocess(handler_sleeps_forever, TASK, timeout_seconds=1.5, tick_seconds=0.2)

    assert result.ok is False
    assert "超时" in result.error
    assert result.lease_lost is False
    assert result.retryable is True  # 超时可能是机器一时繁忙，值得再试
    # 远小于处理函数想睡的 600 秒：子进程确实被杀掉了，而不是等它自己结束
    assert time.monotonic() - started < 20


def test_hard_crash_is_reported_with_exit_code():
    result = run_in_subprocess(handler_hard_crash, TASK, timeout_seconds=30)

    assert result.ok is False
    assert "异常退出" in result.error
    assert "7" in result.error


def test_on_tick_is_called_while_running_and_lost_lease_stops_the_task():
    calls = []

    def on_tick() -> bool:
        calls.append(time.monotonic())
        # 前两次续租成功，第三次发现租约已丢失
        return len(calls) < 3

    started = time.monotonic()
    result = run_in_subprocess(
        handler_sleeps_forever, TASK, timeout_seconds=60, tick_seconds=0.2, on_tick=on_tick
    )

    assert len(calls) == 3
    assert result.ok is False
    assert result.lease_lost is True
    assert time.monotonic() - started < 20


def test_on_tick_not_needed_for_fast_task():
    calls = []

    result = run_in_subprocess(
        handler_ok, TASK, timeout_seconds=30, tick_seconds=30, on_tick=lambda: calls.append(1)
    )

    assert result.ok is True
    assert calls == []
