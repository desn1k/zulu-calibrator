from pathlib import Path

from sqlalchemy import text

from app.db import make_engine


def test_sqlite_connections_use_wal_and_foreign_keys(db_url: str) -> None:
    engine = make_engine(db_url)
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
    engine.dispose()


def test_missing_database_directory_is_created(tmp_path: Path) -> None:
    db_file = tmp_path / "nested" / "dir" / "app.db"
    engine = make_engine(f"sqlite:///{db_file.as_posix()}")
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    engine.dispose()
    assert db_file.exists()
