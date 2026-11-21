"""通用 Worker 启动时检查数据库结构是否已迁移到代码要求的版本（T24l）。

空库（没运行过 alembic）或没升级到最新迁移时，Worker 原来要到第一次领取任务、
或第一次写入新列时才报错，而且报的是 SQL 错误。这里在启动时就比对 alembic_version
和代码里迁移脚本的最新版本，不一致就给出可以照做的提示。
"""

from pathlib import Path

import psycopg
from alembic.script import ScriptDirectory
from shared.task_queue import connect_kwargs

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "db" / "migrations"

_UPGRADE_HINT = "在 backend/ 目录运行 alembic upgrade head"


def expected_heads() -> set[str]:
    """代码里迁移脚本的最新版本（正常只有一个）。只读脚本文件，不连数据库。"""
    return set(ScriptDirectory(str(MIGRATIONS_DIR)).get_heads())


def schema_problem(conn: psycopg.Connection, heads: set[str]) -> str | None:
    """数据库结构与代码不一致时返回提示，一致时返回 None。conn 须为 autocommit 连接。"""
    try:
        rows = conn.execute("SELECT version_num FROM alembic_version").fetchall()
    except psycopg.errors.UndefinedTable:
        return f"数据库还没有建表（没有 alembic_version），先{_UPGRADE_HINT}"
    current = {row[0] for row in rows}
    if current == heads:
        return None
    return (
        f"数据库结构版本为 {sorted(current) or '（空）'}，代码要求 {sorted(heads)}："
        f"数据库落后时先{_UPGRADE_HINT}；数据库比代码新时请更新代码"
    )


def check_schema(database_url: str, *, connect_timeout_seconds: int | None) -> str | None:
    """连一次数据库做 schema_problem 检查，用完即关。连不上时抛 psycopg.Error。"""
    with psycopg.connect(
        database_url, autocommit=True, **connect_kwargs(connect_timeout_seconds)
    ) as conn:
        return schema_problem(conn, expected_heads())
