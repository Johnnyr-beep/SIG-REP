"""mapeo de canal para importacion comercial del presupuesto mensual

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-26 00:00:00.000000

Añade la tabla `agro_ppto_mensual_canal_mapeo`, que configura a qué vendedor,
cliente y categoría (A–F) del bloque **commercial** pertenece cada canal del
Excel anual de agropecuaria (`SUPER MAYORISTA`, `MAYORISTA`, `TAT`, `Call
Center`…). Es la configuración que hace que la importación del libro sea
configurable en lugar de codificada: la importación normaliza el nombre del
canal que lee del Excel y lo busca aquí; lo que no encuentra se rechaza con su
motivo.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

import app.infrastructure.models.mixins
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agro_ppto_mensual_canal_mapeo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("canal", sa.String(length=120), nullable=False),
        sa.Column("vendedor_clave", sa.String(length=60), nullable=True),
        sa.Column("cliente_clave", sa.String(length=60), nullable=True),
        sa.Column("categoria", sa.String(length=1), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column(
            "creado_en", app.infrastructure.models.mixins.UtcDateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "actualizado_en",
            app.infrastructure.models.mixins.UtcDateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "categoria IS NULL OR categoria = 'A' OR categoria = 'B' OR categoria = 'C' "
            "OR categoria = 'D' OR categoria = 'E' OR categoria = 'F'",
            name="ck_agro_ppto_mensual_canal_mapeo_categoria",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canal", name="uq_agro_ppto_mensual_canal_mapeo_canal"),
    )
    op.create_index(
        "ix_agro_ppto_mensual_canal_mapeo_activo",
        "agro_ppto_mensual_canal_mapeo",
        ["activo"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agro_ppto_mensual_canal_mapeo_activo",
        table_name="agro_ppto_mensual_canal_mapeo",
    )
    op.drop_table("agro_ppto_mensual_canal_mapeo")
