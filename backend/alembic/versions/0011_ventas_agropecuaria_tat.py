"""ventas TAT de Agropecuaria

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agro_tat_corridas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("desde", sa.Date(), nullable=False),
        sa.Column("hasta", sa.Date(), nullable=False),
        sa.Column("filas_leidas", sa.Integer(), nullable=False),
        sa.Column("filas_insertadas", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "agro_tat_ventas",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            nullable=False,
        ),
        sa.Column("corrida_id", sa.Integer(), nullable=False),
        sa.Column("fecha_documento", sa.Date(), nullable=False),
        sa.Column("nro_documento", sa.String(length=80), nullable=False),
        sa.Column("tipo_comercial", sa.String(length=120), nullable=True),
        sa.Column("cliente_factura", sa.String(length=80), nullable=True),
        sa.Column("razon_social_cliente", sa.String(length=240), nullable=True),
        sa.Column("codigo_sucursal", sa.String(length=80), nullable=True),
        sa.Column("descripcion_sucursal", sa.String(length=240), nullable=True),
        sa.Column("direccion_sucursal", sa.String(length=300), nullable=True),
        sa.Column("cantidad_inv", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("valor_subtotal", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.ForeignKeyConstraint(["corrida_id"], ["agro_tat_corridas.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agro_tat_fecha_sucursal", "agro_tat_ventas", ["fecha_documento", "codigo_sucursal"])
    op.create_index("ix_agro_tat_documento", "agro_tat_ventas", ["nro_documento"])


def downgrade() -> None:
    op.drop_index("ix_agro_tat_documento", table_name="agro_tat_ventas")
    op.drop_index("ix_agro_tat_fecha_sucursal", table_name="agro_tat_ventas")
    op.drop_table("agro_tat_ventas")
    op.drop_table("agro_tat_corridas")