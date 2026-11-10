"""Traslado de Pereira al C.O. 411, sin separar su historial ni presupuesto.

Revision ID: 0019
Revises: 0018
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _trasladar(origen: str, destino: str, descripcion: str) -> None:
    puntos = sa.table(
        "puntos_venta",
        sa.column("id", sa.Integer),
        sa.column("codigo_co", sa.String),
        sa.column("nombre", sa.String),
        sa.column("descripcion_siesa", sa.String),
    )
    conexion = op.get_bind()
    punto_id = conexion.scalar(
        sa.select(puntos.c.id).where(
            puntos.c.codigo_co == origen,
            puntos.c.nombre == "PEREIRA",
        )
    )
    if punto_id is None:
        return
    ocupado = conexion.scalar(sa.select(puntos.c.id).where(puntos.c.codigo_co == destino))
    if ocupado is not None:
        raise RuntimeError(
            f"No se puede trasladar PEREIRA de {origen} a {destino}: "
            "el C.O. de destino ya existe. Concilie ambos puntos antes de migrar; "
            "no se fusionan ventas ni presupuestos automaticamente."
        )
    conexion.execute(
        puntos.update()
        .where(puntos.c.id == punto_id)
        .values(codigo_co=destino, descripcion_siesa=descripcion)
    )


def upgrade() -> None:
    _trasladar("409", "411", "PDV PEREIRA DOSQUEBRADAS")


def downgrade() -> None:
    _trasladar("411", "409", "PDV PEREIRA")
