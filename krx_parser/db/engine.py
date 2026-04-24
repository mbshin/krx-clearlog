"""SQLAlchemy engine + session factory.

The first connection to a SQLite file enables WAL journaling and
foreign-key enforcement (design §9). In-memory SQLite skips WAL
since it's a no-op for `:memory:`.
"""

from __future__ import annotations

from functools import lru_cache

import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from krx_parser.settings import get_settings


def create_engine_from_url(url: str, *, echo: bool = False) -> Engine:
    connect_args: dict[str, object] = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    engine = sa.create_engine(url, echo=echo, future=True, connect_args=connect_args)
    if url.startswith("sqlite") and ":memory:" not in url:
        _install_sqlite_pragmas(engine)
    return engine


def _install_sqlite_pragmas(engine: Engine) -> None:
    @sa.event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, connection_record):  # noqa: ANN001
        cur = dbapi_connection.cursor()
        try:
            cur.execute("PRAGMA journal_mode = WAL")
            cur.execute("PRAGMA foreign_keys = ON")
            cur.execute("PRAGMA synchronous = NORMAL")
        finally:
            cur.close()


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine_from_url(get_settings().database_url)


def get_sessionmaker(engine: Engine | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=engine or get_engine(), expire_on_commit=False, future=True)
