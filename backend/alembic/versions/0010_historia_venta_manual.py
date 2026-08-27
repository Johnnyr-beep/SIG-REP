"""historia manual de venta por punto de venta

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

import app.infrastructure.models.mixins
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "historia_venta_manual",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("periodo_id", sa.Integer(), nullable=False),
        sa.Column("punto_venta_id", sa.Integer(), nullable=False),
        sa.Column("monto", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("kilos", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("motivo", sa.String(length=400), nullable=False),
        sa.Column("actualizado_por_id", sa.Integer(), nullable=True),
        sa.Column(
            "creado_en", app.infrastructure.models.mixins.UtcDateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "actualizado_en",
            app.infrastructure.models.mixins.UtcDateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint("monto >= 0", name="ck_historia_venta_manual_monto_no_negativo"),
        sa.CheckConstraint("kilos >= 0", name="ck_historia_venta_manual_kilos_no_negativo"),
        sa.ForeignKeyConstraint(["periodo_id"], ["periodos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["punto_venta_id"], ["puntos_venta.id"]),
        sa.ForeignKeyConstraint(["actualizado_por_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "periodo_id", "punto_venta_id", name="uq_historia_venta_manual_periodo_pdv"
        ),
    )
    op.create_index(
        "ix_historia_venta_manual_periodo_pdv",
        "historia_venta_manual",
        ["periodo_id", "punto_venta_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_historia_venta_manual_periodo_pdv",
        table_name="historia_venta_manual",
    )
    op.drop_table("historia_venta_manual")
