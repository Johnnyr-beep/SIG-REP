"""presupuesto mensual configurable: mapeos, detalle y servicio

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-25 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

# `UtcDateTime` es un tipo propio (`TypeDecorator`). Alembic lo referencia por su
# ruta completa al autogenerar, asi que el modulo tiene que estar importado aqui.
import app.infrastructure.models.mixins
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Tabla de mapeos (configuración de asignaciones) ──────────────────────
    op.create_table(
        "agro_ppto_mensual_mapeo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bloque", sa.String(length=30), nullable=False),
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
            nullable=False
        ),
        sa.CheckConstraint(
            "bloque = 'commercial' OR bloque = 'agro_distribucion' "
            "OR bloque = 'servicio' OR bloque = 'nacional'",
            name="ck_agro_ppto_mensual_mapeo_bloque",
        ),
        sa.CheckConstraint(
            "categoria IS NULL OR categoria = 'A' OR categoria = 'B' OR categoria = 'C' "
            "OR categoria = 'D' OR categoria = 'E' OR categoria = 'F'",
            name="ck_agro_ppto_mensual_mapeo_categoria",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "bloque",
            "vendedor_clave",
            "cliente_clave",
            "categoria",
            name="uq_agro_ppto_mensual_mapeo_bloque_asignacion",
        ),
    )
    op.create_index(
        "ix_agro_ppto_mensual_mapeo_bloque",
        "agro_ppto_mensual_mapeo",
        ["bloque", "activo"],
        unique=False,
    )

    # ── Tabla de detalle (filas por bloque/cliente/vendedor/categoría) ────────
    op.create_table(
        "agro_ppto_mensual_detalle",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("periodo_id", sa.Integer(), nullable=False),
        sa.Column("bloque", sa.String(length=30), nullable=False),
        sa.Column("cliente_clave", sa.String(length=60), nullable=True),
        sa.Column("vendedor_clave", sa.String(length=60), nullable=True),
        sa.Column("categoria", sa.String(length=1), nullable=True),
        sa.Column("cliente_etiqueta", sa.String(length=200), nullable=True),
        sa.Column("vendedor_etiqueta", sa.String(length=200), nullable=True),
        sa.Column("monto", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("kilos", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("actualizado_por_id", sa.Integer(), nullable=True),
        sa.Column(
            "creado_en", app.infrastructure.models.mixins.UtcDateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "actualizado_en",
            app.infrastructure.models.mixins.UtcDateTime(timezone=True),
            nullable=False
        ),
        sa.CheckConstraint(
            "bloque = 'commercial' OR bloque = 'agro_distribucion' "
            "OR bloque = 'servicio' OR bloque = 'nacional'",
            name="ck_agro_ppto_mensual_detalle_bloque",
        ),
        sa.CheckConstraint(
            "categoria IS NULL OR categoria = 'A' OR categoria = 'B' OR categoria = 'C' "
            "OR categoria = 'D' OR categoria = 'E' OR categoria = 'F'",
            name="ck_agro_ppto_mensual_detalle_categoria",
        ),
        sa.CheckConstraint("kilos >= 0", name="ck_agro_ppto_mensual_detalle_kilos_no_negativo"),
        sa.CheckConstraint("monto >= 0", name="ck_agro_ppto_mensual_detalle_monto_no_negativo"),
        sa.ForeignKeyConstraint(
            ["actualizado_por_id"],
            ["usuarios.id"],
        ),
        sa.ForeignKeyConstraint(
            ["periodo_id"],
            ["periodos.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "periodo_id",
            "bloque",
            "cliente_clave",
            "vendedor_clave",
            "categoria",
            name="uq_agro_ppto_mensual_detalle_periodo_bloque_asignacion",
        ),
    )
    op.create_index(
        op.f("ix_agro_ppto_mensual_detalle_periodo_id"),
        "agro_ppto_mensual_detalle",
        ["periodo_id"],
        unique=False,
    )
    op.create_index(
        "ix_agro_ppto_mensual_detalle_periodo_bloque",
        "agro_ppto_mensual_detalle",
        ["periodo_id", "bloque"],
        unique=False,
    )

    # ── Tabla de servicio (un solo valor mensual por período) ─────────────────
    op.create_table(
        "agro_ppto_mensual_servicio",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("periodo_id", sa.Integer(), nullable=False),
        sa.Column("monto", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("kilos", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("actualizado_por_id", sa.Integer(), nullable=True),
        sa.Column(
            "creado_en", app.infrastructure.models.mixins.UtcDateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "actualizado_en",
            app.infrastructure.models.mixins.UtcDateTime(timezone=True),
            nullable=False
        ),
        sa.CheckConstraint("kilos >= 0", name="ck_agro_ppto_mensual_servicio_kilos_no_negativo"),
        sa.CheckConstraint("monto >= 0", name="ck_agro_ppto_mensual_servicio_monto_no_negativo"),
        sa.ForeignKeyConstraint(
            ["actualizado_por_id"],
            ["usuarios.id"],
        ),
        sa.ForeignKeyConstraint(
            ["periodo_id"],
            ["periodos.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("periodo_id", name="uq_agro_ppto_mensual_servicio_periodo"),
    )
    op.create_index(
        op.f("ix_agro_ppto_mensual_servicio_periodo_id"),
        "agro_ppto_mensual_servicio",
        ["periodo_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_agro_ppto_mensual_servicio_periodo_id"),
        table_name="agro_ppto_mensual_servicio",
    )
    op.drop_table("agro_ppto_mensual_servicio")
    op.drop_index(
        "ix_agro_ppto_mensual_detalle_periodo_bloque",
        table_name="agro_ppto_mensual_detalle",
    )
    op.drop_index(
        op.f("ix_agro_ppto_mensual_detalle_periodo_id"),
        table_name="agro_ppto_mensual_detalle",
    )
    op.drop_table("agro_ppto_mensual_detalle")
    op.drop_index(
        "ix_agro_ppto_mensual_mapeo_bloque",
        table_name="agro_ppto_mensual_mapeo",
    )
    op.drop_table("agro_ppto_mensual_mapeo")
