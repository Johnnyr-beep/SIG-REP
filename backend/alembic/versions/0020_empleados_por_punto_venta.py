"""Número de empleados vigente por punto de venta.

Revision ID: 0020
Revises: 0019
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("puntos_venta") as tabla:
        tabla.add_column(sa.Column("numero_empleados", sa.Integer(), nullable=True))
        tabla.create_check_constraint(
            "ck_pdv_numero_empleados_no_negativo",
            "numero_empleados IS NULL OR numero_empleados >= 0",
        )


def downgrade() -> None:
    with op.batch_alter_table("puntos_venta") as tabla:
        tabla.drop_constraint("ck_pdv_numero_empleados_no_negativo", type_="check")
        tabla.drop_column("numero_empleados")
