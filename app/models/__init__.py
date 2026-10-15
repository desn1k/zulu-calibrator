"""ORM models. Every table is declared on `Base` so Alembic autogenerate sees it."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Project(Base):
    """«Расчёт ЦТП» = CTP + measurement date. The CTP address is never stored."""

    __tablename__ = "project"

    id: Mapped[int] = mapped_column(primary_key=True)
    ctp_name: Mapped[str] = mapped_column(String(200))
    measured_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(40), default="в работе")
    current_step: Mapped[str] = mapped_column(String(20), default="fact")
    fact: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    iterations: Mapped[list["Iteration"]] = relationship(
        back_populates="project", order_by="Iteration.number", cascade="all, delete-orphan"
    )
    step_states: Mapped[list["StepState"]] = relationship(cascade="all, delete-orphan")
    edits: Mapped[list["ConsumerEditRow"]] = relationship(cascade="all, delete-orphan")


class Iteration(Base):
    """One imported export (a verification run), attached to the step that was open."""

    __tablename__ = "iteration"
    __table_args__ = (UniqueConstraint("project_id", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"))
    number: Mapped[int]
    step: Mapped[str] = mapped_column(String(20))
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)  # private fields already removed
    identical_to_previous: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="iterations")


class StepState(Base):
    __tablename__ = "step_state"
    __table_args__ = (UniqueConstraint("project_id", "step"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"))
    step: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))  # "passed" | "accepted"
    comment: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class ConsumerEditRow(Base):
    """Manual fact edit of one consumer (by Sys); survives every re-import."""

    __tablename__ = "consumer_edit"
    __table_args__ = (UniqueConstraint("project_id", "sys"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"))
    sys: Mapped[int]
    block: Mapped[str | None] = mapped_column(String(4))
    overrides: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    distrust: Mapped[bool] = mapped_column(default=False)


class SchemeStatus(Base):
    """«Статус схем»: a scheme without a row is «не отлажена». «Откалибрована» is set by migration
    0003 for the initial schemes and otherwise only by «подтвердить» on a finished project."""

    __tablename__ = "scheme_status"
    __table_args__ = (UniqueConstraint("kind", "n"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(10))  # "ctp" | "consumer"
    n: Mapped[int]
    status: Mapped[str] = mapped_column(String(20))  # "in_check" | "calibrated"
    calibrated_on: Mapped[date | None] = mapped_column(Date)
    project: Mapped[str] = mapped_column(String(200), default="")
