from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory

from app.db import make_engine
from app.models import Base

ROOT = Path(__file__).resolve().parent.parent


def alembic_config(db_url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_upgrade_head_on_empty_database(db_url: str) -> None:
    cfg = alembic_config(db_url)
    command.upgrade(cfg, "head")

    head = ScriptDirectory.from_config(cfg).get_current_head()
    engine = make_engine(db_url)
    with engine.connect() as conn:
        assert MigrationContext.configure(conn).get_current_revision() == head
    engine.dispose()


def test_models_match_migrations(db_url: str) -> None:
    command.upgrade(alembic_config(db_url), "head")

    engine = make_engine(db_url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()
    assert diff == [], f"models differ from migrations, add a migration: {diff}"


def test_downgrade_to_base_and_back(db_url: str) -> None:
    cfg = alembic_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
