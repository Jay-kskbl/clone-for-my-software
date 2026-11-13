import pytest

from app.db.session import sqlalchemy_url


def test_plain_postgresql_url_gets_psycopg_driver():
    assert (
        sqlalchemy_url("postgresql://u:p%40ss@localhost:5432/db")
        == "postgresql+psycopg://u:p%40ss@localhost:5432/db"
    )


def test_already_qualified_url_is_normalised():
    assert sqlalchemy_url("postgresql+psycopg2://u@h/db") == "postgresql+psycopg://u@h/db"


def test_non_postgresql_url_rejected():
    with pytest.raises(ValueError, match="PostgreSQL"):
        sqlalchemy_url("sqlite:///x.db")
