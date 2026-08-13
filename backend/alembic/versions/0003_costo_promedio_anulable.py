"""venta_lineas.costo_promedio pasa a anulable: hay una fuente que no da costo

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-13

409 PEREIRA —el segundo punto de venta de la compañia— registra en el modulo de
POS que llega marcado como `Origen = SIN ACUMULAR`, y ese modulo **no
entrega el costo**: llega vacio en el 100 % de sus filas. Con la columna
`NOT NULL`, esas lineas entraban con costo cero y §4.4 calculaba

    margen = (Σ subtotal - 0) / Σ subtotal = 100 %

Un 100 % de margen para PEREIRA no es una cifra alta: es una cifra falsa
publicada en la pantalla de la gerencia.

Esta migracion hace posible la unica respuesta correcta: el costo que la fuente
no entrega se persiste como `NULL` —«no se sabe»—, distinto de `0` —«costo
cero»—, y el reporte publica el margen de todo agregado que contenga una linea
sin costo como `None`, que la interfaz pinta «—» (§4 y §7). El resto de los
indicadores del punto de venta no dependen del costo y siguen calculandose.

**No hay backfill y no debe haberlo.** Las filas ya cargadas conservan su cero:
son las que entraron mientras la columna era obligatoria y no hay forma de
distinguir, a posteriori, cual de esos ceros era un costo real y cual el relleno
de una fila sin costo. Se recuperan reingiriendo el rango desde la API, que es
idempotente por dia y punto de venta (§5). Hasta entonces, PEREIRA seguira
publicando su margen de 100 % sobre lo ya cargado; lo que esta migracion
garantiza es que **lo que se cargue desde ahora** diga la verdad.

`op.batch_alter_table` y no `op.alter_column`: en SQLite —la base del arranque
en desarrollo que documenta el README— `ALTER TABLE ... ALTER COLUMN` no existe.
El modo batch recrea la tabla en SQLite y emite el `ALTER` normal en PostgreSQL.
Ver la cabecera de la revision 0002 y `tests/test_migraciones.py`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("venta_lineas") as lote:
        lote.alter_column(
            "costo_promedio",
            existing_type=sa.Numeric(18, 2),
            nullable=True,
        )


def downgrade() -> None:
    # Falla si ya hay costos nulos cargados, y esta bien que falle: volver atras
    # exige decidir que se hace con esas lineas, y la unica alternativa
    # automatica —convertirlas en cero— es justo el 100 % de margen inventado
    # que esta revision existe para eliminar.
    with op.batch_alter_table("venta_lineas") as lote:
        lote.alter_column(
            "costo_promedio",
            existing_type=sa.Numeric(18, 2),
            nullable=False,
        )
