"""venta_lineas gana referencia y producto: el ítem que vendió cada línea

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-07

La tarjeta «costos por producto» necesita saber **qué** se vendió, y hasta aquí
la línea solo decía dónde (punto de venta) y de qué categoría. La API ya
entrega el dato —`Referencia` y `DescItem` viajan en el CSV de
`costos-razon-social` desde el primer día—; lo que faltaba era conservarlo.

Las columnas nacen **anulables** por dos motivos que no se pueden confundir:

- El libro de Excel no trae ítem: quien cargue por ahí deja el producto en
  `NULL` y eso es un hecho del origen, no un dato que se pueda inventar.
- Las líneas ya cargadas no tienen ítem guardado. **No hay backfill** y no debe
  haberlo: el único dato verdadero está en SIESA y se recupera reingiriendo el
  rango, que es idempotente por día y punto de venta (§5). Mientras tanto, el
  reporte agrupa esas líneas en «SIN PRODUCTO», a la vista —la venta existe y
  cuadra con el consolidado; lo que no se sabe es de qué producto es—.

No se añade índice. La consulta del reporte filtra por `periodo_id` y `fecha`
—cubiertas por `ix_venta_periodo_pdv_categoria`— y agrupa lo que ese filtro deja
(unas 440 000 filas al mes); un índice extra encarecería cada inserción de la
ingesta sin acortar ese barrido ya acotado.

`op.batch_alter_table`: en SQLite —la base del arranque en desarrollo que
documenta el README— añadir columna con `ALTER TABLE` simple funciona, pero el
modo batch es el patrón de la casa (0003, 0005) y recrea la tabla conservando
sus índices, que `tests/test_migraciones.py` verifica.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("venta_lineas") as lote:
        lote.add_column(sa.Column("referencia", sa.String(length=60), nullable=True))
        lote.add_column(sa.Column("producto", sa.String(length=200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("venta_lineas") as lote:
        lote.drop_column("producto")
        lote.drop_column("referencia")
