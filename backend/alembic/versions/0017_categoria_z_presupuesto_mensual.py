"""Permite la categoría Z en el presupuesto mensual comercial.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-13 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLAS = (
    ("agro_ppto_mensual_mapeo", "ck_agro_ppto_mensual_mapeo_categoria"),
    ("agro_ppto_mensual_detalle", "ck_agro_ppto_mensual_detalle_categoria"),
    ("agro_ppto_mensual_canal_mapeo", "ck_agro_ppto_mensual_canal_mapeo_categoria"),
)
_CATEGORIAS = "categoria IS NULL OR categoria IN ('A', 'B', 'C', 'D', 'E', 'F', 'Z')"
_CATEGORIAS_SIN_Z = "categoria IS NULL OR categoria IN ('A', 'B', 'C', 'D', 'E', 'F')"


def upgrade() -> None:
    for tabla, restriccion in _TABLAS:
        with op.batch_alter_table(tabla) as batch:
            batch.drop_constraint(restriccion, type_="check")
            batch.create_check_constraint(restriccion, _CATEGORIAS)


def downgrade() -> None:
    conexion = op.get_bind()
    for tabla, _restriccion in _TABLAS:
        tiene_z = conexion.execute(
            sa.text(f"SELECT 1 FROM {tabla} WHERE categoria = 'Z' LIMIT 1")
        ).first()
        if tiene_z:
            raise RuntimeError(
                f"No se puede retirar la categoría Z: hay filas en {tabla} que la usan."
            )

    for tabla, restriccion in _TABLAS:
        with op.batch_alter_table(tabla) as batch:
            batch.drop_constraint(restriccion, type_="check")
            batch.create_check_constraint(restriccion, _CATEGORIAS_SIN_Z)