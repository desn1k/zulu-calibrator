"""scheme status registry with the initially calibrated schemes

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-15 21:00:00
"""

from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# docs/algorithm.md «Статус схем»: initially calibrated (same list as app/engine/schemes.py).
INITIAL = [
    ("ctp", 2, date(2026, 10, 14), "Огородная, 87"),
    ("consumer", 4, date(2026, 10, 14), "Огородная, 87"),
    ("consumer", 26, date(2026, 10, 14), "Огородная, 87"),
    ("ctp", 12, date(2026, 10, 15), "Чернышевского, 8"),
    ("ctp", 3, date(2026, 10, 15), "Береговая, 1/15"),
    ("ctp", 5, date(2026, 10, 15), "Верхняя, 24"),
    ("ctp", 6, date(2026, 10, 15), "2-я Пионерская, 30/36"),
    ("consumer", 2, date(2026, 10, 15), "Верхняя, 24"),
]


def upgrade() -> None:
    table = op.create_table(
        "scheme_status",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("calibrated_on", sa.Date(), nullable=True),
        sa.Column("project", sa.String(length=200), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "n"),
    )
    op.bulk_insert(
        table,
        [
            {"kind": k, "n": n, "status": "calibrated", "calibrated_on": d, "project": p}
            for k, n, d, p in INITIAL
        ],
    )


def downgrade() -> None:
    op.drop_table("scheme_status")
