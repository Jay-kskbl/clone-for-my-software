from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker


def sqlalchemy_url(database_url: str) -> str:
    """把配置里的 postgresql://… 转成 SQLAlchemy 使用 psycopg 3 驱动的写法。

    配置只保留一种写法（标准的 postgresql://，psycopg 可直接使用），
    避免同一个数据库地址在 .env 里出现两个变量。
    """
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        raise ValueError("DATABASE_URL 必须是 PostgreSQL 连接串（postgresql://…）")
    return url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


def make_engine(database_url: str) -> Engine:
    # pool_pre_ping：数据库重启后，连接池里的旧连接会先被探测并丢弃，而不是让请求失败
    return create_engine(sqlalchemy_url(database_url), pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
