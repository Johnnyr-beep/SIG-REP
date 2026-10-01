"""guardar hora de las facturas TAT

Revision ID: 0016
Revises: 0015
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agro_tat_ventas",
        sa.Column("hora_documento", sa.Time(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agro_tat_ventas", "hora_documento")
