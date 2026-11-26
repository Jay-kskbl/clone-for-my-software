"""绑定了 worker_id 和租约时长的 PostgreSQL 任务队列（附录 A2、A3）。

通用 Worker（main 环境）和 OCR Worker（ocr 环境）共用。只依赖 psycopg 和 shared.tasks。
"""

import math
import uuid
from collections.abc import Sequence

import psycopg

from shared import tasks
from shared.tasks import Task


def connect_kwargs(connect_timeout_seconds: int | None) -> dict[str, int]:
    """psycopg.connect 的额外参数。关键字参数会覆盖连接串里同名的 connect_timeout。"""
    if connect_timeout_seconds is None:
        return {}
    return {"connect_timeout": connect_timeout_seconds}


def parse_retry_delays(value: str) -> tuple[float, ...]:
    """解析 TASK_RETRY_DELAYS_SECONDS，例如 "30,120"。不合法时抛 ValueError。

    写 0 表示失败后马上重试。两个 Worker 的配置共用，保证含义相同（T24ad）。
    """
    try:
        delays = tuple(float(part) for part in value.split(","))
    except ValueError:
        raise ValueError("应为用逗号分隔的秒数，例如 30,120") from None
    if any(not math.isfinite(delay) or not 0 <= delay <= 3600 for delay in delays):
        raise ValueError("每个重试间隔应在 0 到 3600 秒之间")
    return delays


class PgTaskQueue:
    def __init__(
        self,
        database_url: str,
        *,
        worker_id: str,
        lease_seconds: float,
        connect_timeout_seconds: int | None = None,
        retry_delays: Sequence[float] = (),
    ) -> None:
        """connect_timeout_seconds：建立连接最多等多久（libpq 的 connect_timeout，整数秒）。

        None 表示用 libpq 的默认行为（不设上限，主机不可达时要等操作系统的 TCP 超时，
        可能一两分钟）。Worker 传配置里的值，启动检查才能及时报错（T24k）。
        retry_delays：失败任务的重试间隔（秒），见 shared.tasks 约定 4；空表示不等。
        """
        self._database_url = database_url
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._connect_timeout_seconds = connect_timeout_seconds
        self._retry_delays = tuple(retry_delays)
        self._conn: psycopg.Connection | None = None

    @property
    def worker_id(self) -> str:
        return self._worker_id

    def _connection(self) -> psycopg.Connection:
        if self._conn is None or self._conn.closed:
            # autocommit：shared.tasks 的每个操作自己开事务、自己提交
            self._conn = psycopg.connect(
                self._database_url, autocommit=True, **connect_kwargs(self._connect_timeout_seconds)
            )
        return self._conn

    def ping(self) -> None:
        """确认数据库连得上，连不上时抛出 psycopg.Error。Worker 启动时调用（GLOBAL §12）。

        成功后连接留着给后面的领取用。
        """
        self._connection().execute("SELECT 1")

    def reclaim_expired(self) -> int:
        return tasks.reclaim_expired(self._connection())

    def claim(self, task_types: Sequence[str]) -> Task | None:
        return tasks.claim(
            self._connection(),
            worker_id=self._worker_id,
            task_types=task_types,
            lease_seconds=self._lease_seconds,
            retry_delays=self._retry_delays,
        )

    def renew(self, task_id: uuid.UUID) -> bool:
        return tasks.renew(
            self._connection(),
            task_id=task_id,
            worker_id=self._worker_id,
            lease_seconds=self._lease_seconds,
        )

    def complete(self, task_id: uuid.UUID) -> bool:
        return tasks.complete(self._connection(), task_id=task_id, worker_id=self._worker_id)

    def fail(self, task_id: uuid.UUID, error: str, *, retryable: bool) -> str | None:
        return tasks.fail(
            self._connection(),
            task_id=task_id,
            worker_id=self._worker_id,
            error=error,
            retryable=retryable,
        )

    def reset(self) -> None:
        """丢弃当前连接；下次操作时重新连接。数据库出错后调用。"""
        if self._conn is not None:
            try:
                self._conn.close()
            except psycopg.Error:
                pass
            self._conn = None
