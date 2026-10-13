"""Captura directa de presupuesto ejecutivo mensual Agro.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-13 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import app.infrastructure.models.mixins
import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agro_ppto_mensual_ejecutivo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("periodo_id", sa.Integer(), nullable=False),
        sa.Column("gerencia_comercial", sa.Numeric(18, 2), nullable=False),
        sa.Column("oficina", sa.Numeric(18, 2), nullable=False),
        sa.Column("servicios", sa.Numeric(18, 2), nullable=False),
        sa.Column("negocios_especiales", sa.Numeric(18, 2), nullable=False),
        sa.Column("actualizado_por_id", sa.Integer(), nullable=True),
        sa.Column(
            "creado_en", app.infrastructure.models.mixins.UtcDateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "actualizado_en",
            app.infrastructure.models.mixins.UtcDateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "gerencia_comercial >= 0",
            name="ck_agro_ppto_mensual_ejecutivo_gerencia_no_negativa",
        ),
        sa.CheckConstraint("oficina >= 0", name="ck_agro_ppto_mensual_ejecutivo_oficina_no_negativa"),
        sa.CheckConstraint(
            "servicios >= 0", name="ck_agro_ppto_mensual_ejecutivo_servicios_no_negativos"
        ),
        sa.CheckConstraint(
            "negocios_especiales >= 0",
            name="ck_agro_ppto_mensual_ejecutivo_especiales_no_negativos",
        ),
        sa.ForeignKeyConstraint(["actualizado_por_id"], ["usuarios.id"]),
        sa.ForeignKeyConstraint(["periodo_id"], ["periodos.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("periodo_id", name="uq_agro_ppto_mensual_ejecutivo_periodo"),
    )
    op.create_index(
        op.f("ix_agro_ppto_mensual_ejecutivo_periodo_id"),
        "agro_ppto_mensual_ejecutivo",
        ["periodo_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_agro_ppto_mensual_ejecutivo_periodo_id"),
        table_name="agro_ppto_mensual_ejecutivo",
    )
    op.drop_table("agro_ppto_mensual_ejecutivo")