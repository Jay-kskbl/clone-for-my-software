"""T24l：通用 Worker 启动时比对数据库的迁移版本。不需要数据库：用假的连接。"""

from pathlib import Path

import psycopg
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.worker.schema import expected_heads, schema_problem

BACKEND_DIR = Path(__file__).resolve().parents[2]


class FakeConnection:
    def __init__(self, versions=None, missing_table=False):
        self.versions = versions or []
        self.missing_table = missing_table

    def execute(self, sql):
        if self.missing_table:
            raise psycopg.errors.UndefinedTable('relation "alembic_version" does not exist')
        return self

    def fetchall(self):
        return [(v,) for v in self.versions]


def test_expected_heads_match_alembic_ini():
    # 直接读迁移目录得到的最新版本，与 alembic 命令按 alembic.ini 找到的一致
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    heads = set(ScriptDirectory.from_config(config).get_heads())
    assert expected_heads() == heads
    assert len(heads) == 1


def test_up_to_date_database_has_no_problem():
    assert schema_problem(FakeConnection(["0002"]), {"0002"}) is None


def test_empty_database_says_to_run_the_migration():
    problem = schema_problem(FakeConnection(missing_table=True), {"0002"})
    assert "还没有建表" in problem and "alembic upgrade head" in problem


def test_outdated_database_names_both_versions():
    problem = schema_problem(FakeConnection(["0001"]), {"0002"})
    assert "['0001']" in problem and "['0002']" in problem
    assert "alembic upgrade head" in problem


def test_empty_version_table_is_reported():
    assert "（空）" in schema_problem(FakeConnection([]), {"0002"})
