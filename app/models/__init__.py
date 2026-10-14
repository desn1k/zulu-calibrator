"""ORM models. Every table is declared on `Base` so Alembic autogenerate sees it."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
