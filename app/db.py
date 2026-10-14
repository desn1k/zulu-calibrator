"""Database engine. All DB access goes through SQLAlchemy; only the pragmas are SQLite-specific."""

from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url


def make_engine(url: str) -> Engine:
    parsed = make_url(url)
    connect_args: dict[str, object] = {}

    if parsed.get_backend_name() == "sqlite":
        connect_args["check_same_thread"] = False
        if parsed.database and parsed.database != ":memory:":
            Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(url, connect_args=connect_args)

    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record) -> None:
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.close()

    return engine
