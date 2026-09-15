"""movimientos_contables: libro mayor del tablero financiero de Grupo Santacruz

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-15

Tabla nueva y **exclusiva de la base `grupo-santacruz`**. Aunque vive en la
misma metadata declarativa que el resto del esquema (`app.core.db.Base`), esta
revisión no debe tocar las bases de Carnes, Agropecuaria ni Carnes Frías: son
compañías operativas ajenas al tablero financiero consolidado, y no deben
ganar ni siquiera una tabla vacía por el hecho de compartir `Base`.

`alembic/env.py` hace cumplir esto sin que el resto del esquema tenga que
imitarlo: `_migrar` guarda en `context.config.attributes["sigrep_unidad"]` qué
base se está migrando, y esta revisión se convierte en no-operación cuando esa
unidad no es `grupo-santacruz`. El `alembic_version` de las otras tres bases
sigue avanzando hasta `0014` con normalidad —lo que no ocurre ahí es la
creación de la tabla—, así que las cuatro bases quedan sincronizadas en
revisión aunque su esquema físico ya no sea idéntico.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

import app.infrastructure.models.mixins
from alembic import context, op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _es_grupo_santacruz() -> bool:
    """`False` en cualquier base que no sea la de la instancia corporativa.

    Ausente (`None`) también cuenta como `False`: es lo que pasa si alguien
    corre `alembic upgrade head` a mano contra una conexión suelta, sin pasar
    por `env.py`. Ante la duda, no crear la tabla es la opción segura — quien
    de verdad necesite la tabla puede volver a migrar declarando la unidad.
    """
    return context.config.attributes.get("sigrep_unidad") == "grupo-santacruz"


def upgrade() -> None:
    if not _es_grupo_santacruz():
        return
    op.create_table(
        "movimientos_contables",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cia", sa.Integer(), nullable=False),
        sa.Column("co", sa.String(length=10), nullable=False),
        sa.Column("periodo", sa.Integer(), nullable=False),
        sa.Column("auxiliar", sa.String(length=30), nullable=False),
        sa.Column("descripcion", sa.String(length=200), nullable=True),
        sa.Column("id_tercero", sa.String(length=30), nullable=True),
        sa.Column("razon_social", sa.String(length=200), nullable=True),
        sa.Column("id_centro_costo", sa.String(length=30), nullable=True),
        sa.Column("centro_costo", sa.String(length=120), nullable=True),
        sa.Column("mayor", sa.String(length=30), nullable=True),
        sa.Column("mayor_iv", sa.String(length=30), nullable=True),
        sa.Column("mayor_iii", sa.String(length=10), nullable=False),
        sa.Column("saldo_inicial", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("debitos", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("creditos", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("final", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("origen", sa.String(length=300), nullable=True),
        sa.Column(
            "creado_en", app.infrastructure.models.mixins.UtcDateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "actualizado_en",
            app.infrastructure.models.mixins.UtcDateTime(timezone=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_movcont_cia_periodo", "movimientos_contables", ["cia", "periodo"], unique=False
    )
    op.create_index("ix_movcont_mayor_iii", "movimientos_contables", ["mayor_iii"], unique=False)
    op.create_index("ix_movcont_tercero", "movimientos_contables", ["id_tercero"], unique=False)
    op.create_index("ix_movcont_co", "movimientos_contables", ["co"], unique=False)


def downgrade() -> None:
    if not _es_grupo_santacruz():
        return
    op.drop_index("ix_movcont_co", table_name="movimientos_contables")
    op.drop_index("ix_movcont_tercero", table_name="movimientos_contables")
    op.drop_index("ix_movcont_mayor_iii", table_name="movimientos_contables")
    op.drop_index("ix_movcont_cia_periodo", table_name="movimientos_contables")
    op.drop_table("movimientos_contables")
