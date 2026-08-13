"""Ampliar margen_siesa: el MARGEN de SIESA no esta acotado a +-100

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-13

`venta_lineas.margen_siesa` nacio como `Numeric(9, 6)` —tope 999,999999— por
suponer que un porcentaje de margen vive entre -100 y 100. No es cierto: una
venta por debajo del costo da un porcentaje arbitrariamente negativo, y el
archivo real de SIESA trae un **-1152,6997** entre 131 819 filas.

Consecuencia medida en PostgreSQL: esa unica fila hace fallar el `executemany`
del lote completo con `NumericValueOutOfRange`, la transaccion revierte y la
ingesta entera termina con 0 filas aceptadas. SQLite no valida la precision de
`Numeric`, asi que las pruebas pasaban y el defecto solo aparecia contra la
base real.

Se amplia a `Numeric(12, 6)`. La columna solo se conserva para conciliar con el
origen: el margen del reporte se recalcula sobre los totales (§4.4).

── Por que `batch_alter_table` y no `alter_column` ───────────────────────────

Esta migracion nacio con `op.alter_column`, que en SQLite se traduce a
`ALTER TABLE venta_lineas ALTER COLUMN ...`, sintaxis que SQLite **no soporta**:
`alembic upgrade head` sobre una base SQLite nueva moria aqui con
`OperationalError: near "ALTER": syntax error`. No lo detecto ninguna prueba
porque la suite monta el esquema con `Base.metadata.create_all`, que no pasa por
las migraciones; el arranque en desarrollo que documenta el README —SQLite mas
`alembic upgrade head`— estaba roto.

`op.batch_alter_table` emite el `ALTER` normal en PostgreSQL y en SQL Server, y
en SQLite recrea la tabla copiando los datos y sus indices. Toda migracion que
altere una columna de este proyecto tiene que usarlo: la base de desarrollo es
SQLite y la de produccion no, y las dos tienen que llegar a `head`. Lo fija
`tests/test_migraciones.py`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("venta_lineas") as lote:
        lote.alter_column(
            "margen_siesa",
            existing_type=sa.Numeric(9, 6),
            type_=sa.Numeric(12, 6),
            existing_nullable=True,
        )


def downgrade() -> None:
    # Estrecharla puede fallar si ya hay valores fuera de rango cargados, que es
    # exactamente el caso que esta migracion existe para admitir.
    with op.batch_alter_table("venta_lineas") as lote:
        lote.alter_column(
            "margen_siesa",
            existing_type=sa.Numeric(12, 6),
            type_=sa.Numeric(9, 6),
            existing_nullable=True,
        )
