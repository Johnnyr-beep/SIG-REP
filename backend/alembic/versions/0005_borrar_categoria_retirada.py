"""OTROS deja de existir: se borra la categoria retirada por la revision 0004

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-13

La revision `0004` retiro `OTROS` y creo las cuatro categorias reales de SIESA
que vivian dentro de ese cajon. Para no perder nada, en vez de borrarla la
**renombro** a `OTROS (RETIRADA - REUBICAR)` y la desactivo: seguia teniendo
presupuesto capturado (616 000 000 de los 20 000 000 000 de la compania) y dos
lineas de venta, y borrar una categoria con eso colgando habria sido destruir
datos en silencio.

Hoy el negocio decidio el reparto —a prorrata de la venta real ya cargada, punto
de venta a punto de venta— y esta revision cierra la retirada. Hace cinco cosas:

1. **Se niega a correr si todavia queda presupuesto** contra la categoria
   retirada, y el mensaje dice el comando exacto que hay que ejecutar antes. Una
   migracion que borra 616 millones de presupuesto sin avisar es justo lo que no
   se quiere.
2. **Vuelve anulable `presupuesto_historial.categoria_id`** y desliga de la
   categoria las filas de historial que la apuntaban.
3. **Reubica la venta que entretanto si haya conseguido mapeo** y **borra las
   lineas que sigan sin categoria**.
4. Borra sus filas de `mapeo_categorias`, si quedara alguna.
5. Borra la categoria.

Los puntos 2 y 3 son los unicos donde hay una decision, y las dos merecen
explicacion porque en las dos se pierde algo.

── El historial (punto 2) ────────────────────────────────────────────────────

`presupuesto_historial` referencia `categorias.id` y esa clave foranea impide
borrar la categoria mientras existan las 30 filas de la carga inicial (15 puntos
de venta x 2 campos) mas las que escribe el reparto. Habia tres salidas:

- **Borrar esas filas de historial.** Inaceptable: §3.3 existe precisamente para
  que un presupuesto no cambie sin rastro, y el rastro de como llego ahi el
  presupuesto que se acaba de repartir es el mas valioso de todos.
- **Reapuntarlas a una de las cuatro categorias nuevas.** Falsifica. Ese cambio
  no ocurrio en VIVERES; ocurrio en un cajon que ya no existe.
- **Anular el vinculo y conservar todo lo demas.** Es lo que se hace.

Lo que se pierde es el vinculo con una fila borrada, no el hecho: cada renglon
conserva periodo, punto de venta, campo, valor anterior, valor nuevo, motivo,
autor e instante, y el motivo que escribe el reparto nombra la categoria
retirada con todas sus letras. La columna `presupuesto_id` ya era anulable desde
el primer dia por esta misma razon; `categoria_id` se le une aqui.

`op.batch_alter_table` y no `op.alter_column`: en SQLite —la base del arranque
en desarrollo que documenta el README— `ALTER TABLE ... ALTER COLUMN` no existe.
El modo batch recrea la tabla en SQLite y emite el `ALTER` normal en PostgreSQL.
Igual que en la revision `0003`; ver `tests/test_migraciones.py`, que comprueba
que la recreacion no se lleva por delante `ix_historial_periodo_pdv`.

── Las lineas de venta huerfanas (punto 3) ───────────────────────────────────

Quedan **2 lineas** (133 335 en total, ambas de 606 ALAMEDA2) que llegaron del
origen **sin categoria**: su `categoria_siesa` es nulo, asi que la revision
`0004` no pudo reubicarlas y se quedaron en el cajon. Tres opciones:

- **Reasignarlas a DOMICILIOS**, o a cualquier otra. Es inventar. Nadie sabe que
  eran; el origen no lo dijo. Meterlas en una categoria real corrompe la venta
  de esa categoria con producto que no le pertenece, y ademas lo hace de forma
  invisible: nunca mas se sabria que esas 2 lineas estaban mal.
- **Dejarlas donde estan.** Es honesto y es un callejon sin salida: mientras
  existan, la clave foranea impide borrar la categoria, y la categoria seguiria
  apareciendo en cada consulta de catalogo y en cada reporte con su nombre a
  gritos. La retirada no se cerraria nunca.
- **Borrarlas.** Es lo que se hace, y no es una perdida de informacion porque el
  dato no vive aqui: vive en SIESA. La ingesta es **idempotente por dia y punto
  de venta** (§5), asi que reingerir 2026-08-01 y 2026-08-03 para 606 las trae
  de vuelta. Y las trae de vuelta **mejor**: sin `OTROS` al que caer, una linea
  sin categoria se **rechaza con su motivo** y aparece en la bitacora de
  ingesta, que es donde le corresponde estar. Hoy estan escondidas dentro de una
  categoria fantasma, sumando 133 335 a un renglon que nadie mira; despues seran
  dos rechazos visibles con nombre y apellido.

Dicho de otro modo: la opcion 3 no borra un dato, **traslada un defecto de
calidad desde un sitio donde no se ve a uno donde si**. El log deja el detalle
exacto (id, fecha, punto de venta e importe) de cada linea borrada para que
quien lea el despliegue sepa que rango reingerir.

Antes de borrar nada, la revision **vuelve a intentar la reubicacion** contra la
tabla de mapeo: si entre la `0004` y hoy alguien dio de alta por
`POST /catalogos/mapeo-categorias` el texto de SIESA que faltaba, esas lineas se
salvan y no se borran. Solo se borra lo que de verdad no tiene a donde ir.

Todo el SQL es portable a SQLite y PostgreSQL a proposito.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa

import app.infrastructure.models.mixins
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

#: Nombre original del cajon y el nombre con el que la revision `0004` lo dejo
#: marcado. Se buscan los dos: una base que no llego a pasar por la `0004` con
#: referencias vivas puede conservar todavia el nombre original.
CAJON = "OTROS"
CAJON_RETIRADO = "OTROS (RETIRADA - REUBICAR)"

#: El comando que hay que ejecutar antes que esta migracion si todavia queda
#: presupuesto. Se escribe entero en el mensaje de error: un «reparta primero el
#: presupuesto» sin el comando obliga a quien despliega a ir a buscarlo.
COMANDO_REPARTO = (
    "python -m app.infrastructure.reparto_presupuesto --periodo {periodo} --usuario <cuenta>"
)


def _id_categoria(conexion: sa.Connection, nombre: str) -> int | None:
    return conexion.execute(
        sa.text("SELECT id FROM categorias WHERE nombre = :nombre"),
        {"nombre": nombre},
    ).scalar_one_or_none()


def _localizar_cajon(conexion: sa.Connection) -> tuple[int, str] | None:
    """La categoria retirada, con el nombre que tenga hoy en la base."""
    for nombre in (CAJON_RETIRADO, CAJON):
        identificador = _id_categoria(conexion, nombre)
        if identificador is not None:
            return identificador, nombre
    return None


def upgrade() -> None:
    conexion = op.get_bind()
    localizada = _localizar_cajon(conexion)

    # La comprobacion va **antes** de cualquier DDL: si hay que abortar, que se
    # aborte barato y sin haber tocado el esquema.
    if localizada is not None:
        _exigir_presupuesto_repartido(conexion, *localizada)

    _historial_admite_categoria_nula()

    if localizada is None:
        logger.info(
            "migracion_0005_sin_cajon: no habia categoria retirada que borrar. "
            "El esquema queda igualmente actualizado."
        )
        return

    cajon_id, nombre = localizada
    _reubicar_lo_que_ya_tiene_mapeo(conexion, cajon_id)
    _borrar_lineas_sin_categoria(conexion, cajon_id, nombre)
    _borrar_mapeo(conexion, cajon_id)
    _desligar_historial(conexion, cajon_id, nombre)
    _borrar_categoria(conexion, cajon_id, nombre)


def _exigir_presupuesto_repartido(conexion: sa.Connection, cajon_id: int, nombre: str) -> None:
    """Aborta si queda presupuesto, diciendo exactamente que ejecutar antes."""
    fila = conexion.execute(
        sa.text(
            "SELECT COUNT(*), COALESCE(SUM(monto), 0) FROM presupuestos WHERE categoria_id = :id"
        ),
        {"id": cajon_id},
    ).one()
    cuantas, total = int(fila[0]), fila[1]
    if not cuantas:
        return

    periodos = conexion.execute(
        sa.text(
            "SELECT DISTINCT p.anio, p.mes FROM presupuestos b "
            "JOIN periodos p ON p.id = b.periodo_id "
            "WHERE b.categoria_id = :id ORDER BY p.anio, p.mes"
        ),
        {"id": cajon_id},
    ).all()
    codigos = [f"{anio:04d}-{mes:02d}" for anio, mes in periodos] or ["<YYYY-MM>"]
    comandos = "\n    ".join(COMANDO_REPARTO.format(periodo=codigo) for codigo in codigos)

    raise RuntimeError(
        f"No se aplica la revision 0005: la categoria «{nombre}» todavia tiene {cuantas} filas "
        f"de presupuesto por un total de {total}. Borrar la categoria ahora borraria ese "
        "presupuesto en silencio y el consolidado de la compania saldria descuadrado sin que "
        "nadie sepa por que.\n\n"
        "Reparta primero ese presupuesto entre las categorias que sustituyen a la retirada "
        "(a prorrata de la venta ya cargada, punto de venta a punto de venta):\n\n"
        f"    {comandos}\n\n"
        "Anteponga --simular para ver los numeros sin escribir nada. Cuando la categoria se "
        "quede sin presupuesto, vuelva a ejecutar `alembic upgrade head`."
    )


def _historial_admite_categoria_nula() -> None:
    """`presupuesto_historial.categoria_id` pasa a anulable (ver la cabecera)."""
    with op.batch_alter_table("presupuesto_historial") as lote:
        lote.alter_column(
            "categoria_id",
            existing_type=sa.Integer(),
            nullable=True,
        )


def _reubicar_lo_que_ya_tiene_mapeo(conexion: sa.Connection, cajon_id: int) -> None:
    """Ultimo intento de salvar lineas antes de borrarlas.

    Identico al de la revision `0004` y repetido a proposito: entre aquella y
    esta pueden haber pasado semanas, y si alguien dio de alta el texto de SIESA
    que faltaba, esa linea no tiene por que morir.
    """
    resultado = conexion.execute(
        sa.text(
            "UPDATE venta_lineas SET categoria_id = ("
            "  SELECT m.categoria_id FROM mapeo_categorias m"
            "  WHERE m.texto_siesa = venta_lineas.categoria_siesa"
            ") "
            "WHERE categoria_id = :cajon "
            "  AND categoria_siesa IS NOT NULL "
            "  AND EXISTS ("
            "    SELECT 1 FROM mapeo_categorias m"
            "    WHERE m.texto_siesa = venta_lineas.categoria_siesa"
            "      AND m.categoria_id <> :cajon"
            "  )"
        ),
        {"cajon": cajon_id},
    )
    if resultado.rowcount:
        logger.info(
            "migracion_0005_lineas_reubicadas: %s lineas encontraron mapeo y se salvan del "
            "borrado.",
            resultado.rowcount,
        )


def _borrar_lineas_sin_categoria(conexion: sa.Connection, cajon_id: int, nombre: str) -> None:
    """Borra la venta que sigue sin categoria, dejando su detalle en el log."""
    lineas = conexion.execute(
        sa.text(
            "SELECT v.id, v.fecha, pv.codigo_co, v.valor_subtotal, v.categoria_siesa "
            "FROM venta_lineas v JOIN puntos_venta pv ON pv.id = v.punto_venta_id "
            "WHERE v.categoria_id = :cajon ORDER BY v.fecha, pv.codigo_co"
        ),
        {"cajon": cajon_id},
    ).all()
    if not lineas:
        return

    detalle = [
        {
            "id": fila[0],
            "fecha": str(fila[1]),
            "punto_venta": fila[2],
            "valor_subtotal": str(fila[3]),
            "categoria_siesa": fila[4],
        }
        for fila in lineas
    ]
    rangos = sorted({(fila[2], str(fila[1])) for fila in lineas})

    conexion.execute(
        sa.text("DELETE FROM venta_lineas WHERE categoria_id = :cajon"),
        {"cajon": cajon_id},
    )
    logger.warning(
        "migracion_0005_lineas_borradas: %s lineas de venta que seguian en «%s» sin categoria "
        "en el origen se han borrado. NO se han perdido: la ingesta es idempotente por dia y "
        "punto de venta (§5). Reingiera %s y volveran a entrar, esta vez RECHAZADAS con su "
        "motivo en la bitacora, que es donde les corresponde estar. Detalle: %s",
        len(lineas),
        nombre,
        rangos,
        detalle,
    )


def _borrar_mapeo(conexion: sa.Connection, cajon_id: int) -> None:
    resultado = conexion.execute(
        sa.text("DELETE FROM mapeo_categorias WHERE categoria_id = :cajon"),
        {"cajon": cajon_id},
    )
    if resultado.rowcount:
        logger.info(
            "migracion_0005_mapeo_borrado: %s textos de SIESA apuntaban todavia a la categoria "
            "retirada. Sin mapeo, esos textos pasan a rechazarse con su motivo (§7).",
            resultado.rowcount,
        )


def _desligar_historial(conexion: sa.Connection, cajon_id: int, nombre: str) -> None:
    """Anula el vinculo del historial con la categoria, conservando todo lo demas."""
    resultado = conexion.execute(
        sa.text("UPDATE presupuesto_historial SET categoria_id = NULL WHERE categoria_id = :cajon"),
        {"cajon": cajon_id},
    )
    if resultado.rowcount:
        logger.warning(
            "migracion_0005_historial_desligado: %s filas de presupuesto_historial pierden el "
            "vinculo con «%s». Conservan periodo, punto de venta, campo, valor anterior, valor "
            "nuevo, motivo, autor e instante: el rastro de §3.3 sigue intacto.",
            resultado.rowcount,
            nombre,
        )


def _borrar_categoria(conexion: sa.Connection, cajon_id: int, nombre: str) -> None:
    conexion.execute(sa.text("DELETE FROM categorias WHERE id = :id"), {"id": cajon_id})
    logger.info("migracion_0005_categoria_borrada: «%s» ya no existe.", nombre)


def downgrade() -> None:
    """Recrea la categoria retirada y devuelve `categoria_id` a obligatoria.

    Lo que **no** puede deshacer, y hay que decirlo: las lineas de venta que la
    revision borro. No se guardan en ninguna parte porque su sitio no es este:
    se recuperan reingiriendo el rango que dejo anotado el log (§5).

    Las filas de historial con `categoria_id` nulo se devuelven a la categoria
    recreada. Es una reconstruccion, no un dato guardado: bajo el esquema
    anterior a esta revision esa columna era obligatoria, asi que **todo** valor
    nulo que exista al bajar lo puso esta revision. Deja de ser exacto el dia en
    que otra cosa aprenda a escribir nulos ahi; mientras tanto, es la unica
    lectura posible y es la que permite restaurar el `NOT NULL`.
    """
    conexion = op.get_bind()

    cajon_id = _id_categoria(conexion, CAJON_RETIRADO)
    if cajon_id is None:
        instante = app.infrastructure.models.mixins.ahora_utc()
        op.bulk_insert(
            sa.table(
                "categorias",
                sa.column("codigo", sa.String),
                sa.column("nombre", sa.String),
                sa.column("orden", sa.Integer),
                sa.column("activa", sa.Boolean),
                sa.column("creado_en", app.infrastructure.models.mixins.UtcDateTime()),
                sa.column("actualizado_en", app.infrastructure.models.mixins.UtcDateTime()),
            ),
            [
                {
                    "codigo": CAJON,
                    "nombre": CAJON_RETIRADO,
                    "orden": 99,
                    "activa": False,
                    "creado_en": instante,
                    "actualizado_en": instante,
                }
            ],
        )
        cajon_id = _id_categoria(conexion, CAJON_RETIRADO)

    conexion.execute(
        sa.text("UPDATE presupuesto_historial SET categoria_id = :id WHERE categoria_id IS NULL"),
        {"id": cajon_id},
    )

    with op.batch_alter_table("presupuesto_historial") as lote:
        lote.alter_column(
            "categoria_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
