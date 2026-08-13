"""Las categorias de SIGREP pasan a ser las reales de SIESA y OTROS desaparece

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-13

SIGREP tenia ocho categorias y cuatro categorias reales de SIESA —`0006 QUESO Y
LACTEOS` (con sus dos ortografias), `0007 HUEVOS`, `0008 VIVERES` y `0014
DOMICILIOS`— vivian plegadas dentro de un cajon llamado `OTROS`. Ese cajon
llevaba 616 000 000 de los 20 000 000 000 del presupuesto de la compania: un
3 % sobre el que nadie podia decidir nada, porque mezclaba huevos con
domicilios y un renglon asi no se lee, solo se acepta.

El negocio decidio que `OTROS` desaparece. Quedan **once** categorias, una por
cada categoria real de SIESA. `0010 - RESTAURANTE` sigue llamandose ASADERO en
SIGREP porque es el nombre con el que el negocio captura y lee su presupuesto.

Esta migracion hace cuatro cosas y ninguna de ellas borra nada:

1. **Crea las cuatro categorias que faltaban** (QUESO Y LACTEOS, HUEVOS,
   VIVERES, DOMICILIOS), si no estaban ya.
2. **Reapunta el mapeo** de los cinco textos de SIESA que iban a `OTROS` hacia
   su categoria propia. Las dos ortografias de `0006` van a la **misma**
   categoria: es el mismo producto escrito de dos formas en el origen.
3. **Reubica la venta ya cargada** usando `venta_lineas.categoria_siesa`, que es
   el texto crudo con el que llego cada linea y que se conserva justo para
   esto. Sin esa columna esta migracion seria imposible y habria que reingerir
   meses enteros desde la API.
4. **Deja `OTROS` marcada, no borrada.** Si al terminar no le queda ninguna
   referencia, se elimina la fila y se acabo. Si le queda alguna —lineas cuyo
   `categoria_siesa` es nulo o desconocido, y sobre todo **presupuesto** que
   alguien capturo contra el cajon—, la fila se renombra a
   `OTROS (RETIRADA - REUBICAR)` y se desactiva.

El punto 4 merece explicacion porque es el unico donde hay una decision.
Borrar la fila con referencias vivas es imposible (las claves foraneas lo
impiden) y borrar tambien lo que la referencia seria destruir presupuesto
capturado. Renombrar y desactivar consigue las tres cosas que hacen falta a la
vez: `GET /catalogos/categorias` filtra por `activa` y deja de ofrecerla, asi
que nadie captura nada nuevo ahi; el presupuesto que ya existia **no se pierde
ni se mueve solo** y sigue sumando en el consolidado; y el nombre grita en cada
reporte donde aparezca, que es exactamente lo que hace falta para que alguien
lo reparta. Un reparto automatico —a partes iguales, a prorrata de la venta del
ano pasado— seria inventar un criterio y publicarlo como si el negocio lo
hubiera aprobado.

Lo que **no** se reubica y hay que mirar a mano tras aplicarla:

- Lineas de venta con `categoria_siesa` nulo o con un texto que sigue sin
  mapeo. Se quedan en la categoria retirada, contadas y registradas en el log
  (`migracion_0004_lineas_sin_reubicar`). Se recuperan dando de alta el mapeo
  en Catalogos y reingiriendo el rango, que es idempotente por dia y punto de
  venta (§5).
- Presupuesto capturado contra `OTROS`. No se reparte solo. Se registra en el
  log (`migracion_0004_presupuesto_sin_reubicar`) y se captura por pantalla.

Todo el SQL es portable a SQLite y PostgreSQL a proposito: el arranque en
desarrollo que documenta el README es SQLite + `alembic upgrade head`, y una
migracion que solo corre en PostgreSQL rompe ese arranque sin que la suite se
entere. Ver `tests/test_migraciones.py`.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa

import app.infrastructure.models.mixins
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

#: Nombre del cajon que desaparece.
CAJON = "OTROS"

#: Con el que queda marcada si no se la puede borrar. Cabe en `String(40)` y se
#: lee de un vistazo en cualquier reporte donde asome.
CAJON_RETIRADO = "OTROS (RETIRADA - REUBICAR)"

#: Las cuatro categorias nuevas, con el orden que ocupan en el reporte. Van
#: detras de las siete que ya existian para no reordenar una pantalla que la
#: gerencia ya tiene memorizada.
CATEGORIAS_NUEVAS: tuple[tuple[str, int], ...] = (
    ("QUESO Y LACTEOS", 8),
    ("HUEVOS", 9),
    ("VIVERES", 10),
    ("DOMICILIOS", 11),
)

#: Los cinco textos de SIESA que iban al cajon, con su destino real. Las dos
#: ortografias de `0006` caen en la misma categoria.
MAPEO_REAPUNTADO: tuple[tuple[str, str], ...] = (
    ("0006 - QUESO Y LACTEOS", "QUESO Y LACTEOS"),
    ("0006 - QUESOS Y LACTEOS", "QUESO Y LACTEOS"),
    ("0007 - HUEVOS", "HUEVOS"),
    ("0008 - VIVERES", "VIVERES"),
    ("0014 - DOMICILIOS", "DOMICILIOS"),
)

#: Las cuatro tablas que apuntan a `categorias.id`. Si aparece una quinta y no
#: se anade aqui, el recuento de referencias mentiria y el `DELETE` fallaria
#: por clave foranea en lugar de no intentarse.
TABLAS_QUE_REFERENCIAN: tuple[str, ...] = (
    "mapeo_categorias",
    "presupuestos",
    "presupuesto_historial",
    "venta_lineas",
)


def _tabla_categorias() -> sa.Table:
    """`categorias` declarada a mano: la migracion no depende del modelo ORM.

    Un `import` del modelo la ataria a la forma que la tabla tenga **hoy**, y
    una migracion tiene que seguir corriendo igual dentro de dos anos con el
    modelo ya cambiado.
    """
    return sa.table(
        "categorias",
        sa.column("codigo", sa.String),
        sa.column("nombre", sa.String),
        sa.column("orden", sa.Integer),
        sa.column("activa", sa.Boolean),
        sa.column("creado_en", app.infrastructure.models.mixins.UtcDateTime()),
        sa.column("actualizado_en", app.infrastructure.models.mixins.UtcDateTime()),
    )


def _id_categoria(conexion: sa.Connection, nombre: str) -> int | None:
    return conexion.execute(
        sa.text("SELECT id FROM categorias WHERE nombre = :nombre"),
        {"nombre": nombre},
    ).scalar_one_or_none()


def _referencias(conexion: sa.Connection, categoria_id: int) -> dict[str, int]:
    """Cuantas filas apuntan a esta categoria, tabla por tabla."""
    conteos: dict[str, int] = {}
    for tabla in TABLAS_QUE_REFERENCIAN:
        # `tabla` sale de una constante del modulo, nunca de una entrada; el
        # unico valor externo es `categoria_id` y viaja como parametro.
        cuantas = conexion.execute(
            sa.text(f"SELECT COUNT(*) FROM {tabla} WHERE categoria_id = :id"),  # noqa: S608
            {"id": categoria_id},
        ).scalar_one()
        if cuantas:
            conteos[tabla] = int(cuantas)
    return conteos


def upgrade() -> None:
    conexion = op.get_bind()

    _crear_categorias_nuevas(conexion)
    _reapuntar_mapeo(conexion)

    cajon_id = _id_categoria(conexion, CAJON)
    if cajon_id is None:
        # Base recien creada por `alembic upgrade head` sobre un archivo vacio:
        # no hay semilla, no hay cajon y no hay nada que reubicar. La semilla
        # sembrara directamente las once categorias.
        logger.info("migracion_0004_sin_cajon: no habia categoria %s que retirar", CAJON)
        return

    _reubicar_venta(conexion, cajon_id)
    _retirar_cajon(conexion, cajon_id)


def _crear_categorias_nuevas(conexion: sa.Connection) -> None:
    """Alta de las cuatro categorias, saltando las que ya estuvieran.

    Se comprueba antes de insertar y no se confia en el error del indice unico:
    una base que ya paso por la semilla nueva tiene que poder migrar igual.
    """
    existentes = {
        nombre for (nombre,) in conexion.execute(sa.text("SELECT nombre FROM categorias"))
    }
    faltantes = [(n, o) for n, o in CATEGORIAS_NUEVAS if n not in existentes]
    if not faltantes:
        return

    instante = app.infrastructure.models.mixins.ahora_utc()
    op.bulk_insert(
        _tabla_categorias(),
        [
            {
                "codigo": nombre,
                "nombre": nombre,
                "orden": orden,
                "activa": True,
                "creado_en": instante,
                "actualizado_en": instante,
            }
            for nombre, orden in faltantes
        ],
    )
    logger.info("migracion_0004_categorias_creadas: %s", [n for n, _ in faltantes])


def _reapuntar_mapeo(conexion: sa.Connection) -> None:
    """Los cinco textos de SIESA dejan de apuntar al cajon.

    Solo se **actualiza** lo que ya existe; no se da de alta ningun mapeo. Si la
    base nunca paso por la semilla, no hay nada que reapuntar y la semilla lo
    sembrara ya correcto. Y si alguien reclasifico un texto por pantalla a una
    categoria que no es el cajon, se respeta: la condicion incluye que el mapeo
    siguiera apuntando a `OTROS`.
    """
    cajon_id = _id_categoria(conexion, CAJON)
    if cajon_id is None:
        return

    reapuntados = 0
    for texto, destino in MAPEO_REAPUNTADO:
        destino_id = _id_categoria(conexion, destino)
        if destino_id is None:  # pragma: no cover - la creacion acaba de correr
            continue
        resultado = conexion.execute(
            sa.text(
                "UPDATE mapeo_categorias SET categoria_id = :destino "
                "WHERE texto_siesa = :texto AND categoria_id = :cajon"
            ),
            {"destino": destino_id, "texto": texto, "cajon": cajon_id},
        )
        reapuntados += resultado.rowcount or 0
    logger.info("migracion_0004_mapeo_reapuntado: %s filas", reapuntados)


def _reubicar_venta(conexion: sa.Connection, cajon_id: int) -> None:
    """Cada linea del cajon vuelve a su categoria por su `categoria_siesa`.

    El texto crudo con el que llego cada linea se conserva en la columna
    `categoria_siesa` precisamente para esto: sin el, la unica salida seria
    reingerir meses enteros desde la API.

    La reubicacion va **contra la tabla de mapeo ya reapuntada**, no contra una
    lista de este archivo. Asi, un texto que el negocio haya dado de alta a mano
    por `POST /catalogos/mapeo-categorias` —una categoria que SIESA anadio
    despues— tambien se reubica, sin que nadie tenga que acordarse de anadirlo
    aqui.
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
    logger.info("migracion_0004_lineas_reubicadas: %s", resultado.rowcount)

    sin_reubicar = conexion.execute(
        sa.text("SELECT COUNT(*) FROM venta_lineas WHERE categoria_id = :cajon"),
        {"cajon": cajon_id},
    ).scalar_one()
    if sin_reubicar:
        logger.warning(
            "migracion_0004_lineas_sin_reubicar: %s lineas se quedan en «%s» porque su "
            "categoria_siesa es nula o sigue sin mapeo. No se borran. De alta el mapeo en "
            "Catalogos y reingiera el rango: la ingesta es idempotente por dia y punto de "
            "venta.",
            sin_reubicar,
            CAJON_RETIRADO,
        )


def _retirar_cajon(conexion: sa.Connection, cajon_id: int) -> None:
    """Borra `OTROS` si ya no la referencia nadie; si no, la marca y la apaga."""
    referencias = _referencias(conexion, cajon_id)
    if not referencias:
        conexion.execute(
            sa.text("DELETE FROM categorias WHERE id = :id"),
            {"id": cajon_id},
        )
        logger.info("migracion_0004_cajon_borrado: no quedaban referencias a %s", CAJON)
        return

    conexion.execute(
        sa.text(
            "UPDATE categorias SET nombre = :nombre, activa = :apagada, orden = :orden "
            "WHERE id = :id"
        ),
        {"nombre": CAJON_RETIRADO, "apagada": False, "orden": 99, "id": cajon_id},
    )
    logger.warning(
        "migracion_0004_cajon_marcado: %s queda como «%s», desactivada y con referencias "
        "vivas: %s. Nada se ha borrado.",
        CAJON,
        CAJON_RETIRADO,
        referencias,
    )
    presupuestos = referencias.get("presupuestos", 0)
    if presupuestos:
        logger.warning(
            "migracion_0004_presupuesto_sin_reubicar: %s filas de presupuesto siguen "
            "capturadas contra la categoria retirada. El sistema **no** las reparte: el "
            "criterio lo decide el negocio. Repartalas por pantalla entre VIVERES, HUEVOS, "
            "QUESO Y LACTEOS y DOMICILIOS.",
            presupuestos,
        )


def downgrade() -> None:
    """Devuelve la taxonomia a las ocho categorias con `OTROS` de cajon.

    Se **niega** si ya hay presupuesto capturado contra alguna de las cuatro
    categorias nuevas. Devolverlo al cajon exigiria sumar varias filas en una
    —la clave unica es `(periodo, punto de venta, categoria)` y un PDV puede
    tener presupuesto en VIVERES y en HUEVOS a la vez— y esa suma es una
    decision de negocio, no una operacion de esquema. Un `downgrade` que
    destruye la parametrizacion que alguien capturo es peor que uno que no
    corre: negarse deja el problema a la vista y los datos intactos.
    """
    conexion = op.get_bind()

    nuevas_ids = [
        identificador
        for identificador in (_id_categoria(conexion, n) for n, _ in CATEGORIAS_NUEVAS)
        if identificador is not None
    ]
    if nuevas_ids:
        capturado = conexion.execute(
            sa.text("SELECT COUNT(*) FROM presupuestos WHERE categoria_id IN :ids").bindparams(
                sa.bindparam("ids", value=nuevas_ids, expanding=True)
            )
        ).scalar_one()
        if capturado:
            raise RuntimeError(
                f"No se revierte la revision 0004: hay {capturado} filas de presupuesto "
                "capturadas contra QUESO Y LACTEOS, HUEVOS, VIVERES o DOMICILIOS. "
                "Devolverlas al cajon OTROS exigiria sumarlas, y esa suma la decide el "
                "negocio. Vacie o traslade ese presupuesto por pantalla y vuelva a intentarlo."
            )

    cajon_id = _restaurar_cajon(conexion)

    for texto, _destino in MAPEO_REAPUNTADO:
        conexion.execute(
            sa.text("UPDATE mapeo_categorias SET categoria_id = :cajon WHERE texto_siesa = :texto"),
            {"cajon": cajon_id, "texto": texto},
        )

    if nuevas_ids:
        parametros = sa.bindparam("ids", value=nuevas_ids, expanding=True)
        conexion.execute(
            sa.text(
                "UPDATE venta_lineas SET categoria_id = :cajon WHERE categoria_id IN :ids"
            ).bindparams(parametros, sa.bindparam("cajon", value=cajon_id))
        )
        conexion.execute(
            sa.text(
                "UPDATE presupuesto_historial SET categoria_id = :cajon WHERE categoria_id IN :ids"
            ).bindparams(parametros, sa.bindparam("cajon", value=cajon_id))
        )
        conexion.execute(sa.text("DELETE FROM categorias WHERE id IN :ids").bindparams(parametros))


def _restaurar_cajon(conexion: sa.Connection) -> int:
    """Devuelve `OTROS` a la vida: la reactiva si estaba marcada, o la recrea."""
    marcada = _id_categoria(conexion, CAJON_RETIRADO)
    if marcada is not None:
        conexion.execute(
            sa.text(
                "UPDATE categorias SET nombre = :nombre, activa = :activa, orden = :orden "
                "WHERE id = :id"
            ),
            {"nombre": CAJON, "activa": True, "orden": 8, "id": marcada},
        )
        return marcada

    existente = _id_categoria(conexion, CAJON)
    if existente is not None:
        return existente

    instante = app.infrastructure.models.mixins.ahora_utc()
    op.bulk_insert(
        _tabla_categorias(),
        [
            {
                "codigo": CAJON,
                "nombre": CAJON,
                "orden": 8,
                "activa": True,
                "creado_en": instante,
                "actualizado_en": instante,
            }
        ],
    )
    identificador = _id_categoria(conexion, CAJON)
    assert identificador is not None
    return identificador
