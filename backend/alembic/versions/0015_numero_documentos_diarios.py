"""numero_documentos_diarios: conteo de facturas por PDV y dia (§4.4)

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

import app.infrastructure.models.mixins
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "numero_documentos_diarios",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("punto_venta_id", sa.Integer(), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("origen", sa.String(length=20), nullable=False),
        sa.Column(
            "creado_en", app.infrastructure.models.mixins.UtcDateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "actualizado_en",
            app.infrastructure.models.mixins.UtcDateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["punto_venta_id"], ["puntos_venta.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("punto_venta_id", "fecha", name="uq_documentos_pdv_fecha"),
    )
    op.create_index("ix_documentos_fecha", "numero_documentos_diarios", ["fecha"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_documentos_fecha", table_name="numero_documentos_diarios")
    op.drop_table("numero_documentos_diarios")
