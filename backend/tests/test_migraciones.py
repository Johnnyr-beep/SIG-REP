"""Las migraciones tienen que correr sobre **SQLite** además de PostgreSQL.

El arranque en desarrollo que documenta el README es SQLite + `alembic upgrade
head`. Las demás pruebas montan el esquema con `Base.metadata.create_all`, que
no pasa por ninguna migración: por eso una migración rota podía convivir con la
suite en verde mientras el arranque documentado estaba muerto.

Esta prueba recorre las migraciones **de cero a `head`** sobre un archivo SQLite
recién creado, en un proceso aparte y con la CLI real —el mismo comando que
teclea quien monta su entorno—, y comprueba tres cosas:

1. que se llega hasta la revisión cabeza, sin fallar por el camino;
2. que `venta_lineas.costo_promedio` quedó **anulable** (§4.4: PEREIRA no trae
   costo y un costo que no existe es `NULL`, nunca cero);
3. que los índices de `venta_lineas` **sobrevivieron**. En SQLite,
   `op.batch_alter_table` no altera la columna: recrea la tabla entera. Si esa
   recreación se lleva por delante `ix_venta_periodo_pdv_categoria`, la consulta
   caliente del reporte pasa a barrer millones de filas y nadie se entera hasta
   que el tablero tarda medio minuto.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

#: `backend/`, que es donde viven `alembic.ini` y el paquete `app`.
RAIZ = Path(__file__).resolve().parents[1]

#: Los índices que `venta_lineas` declara en el modelo y que una recreación de
#: tabla mal hecha se llevaría en silencio.
INDICES_ESPERADOS = {
    "ix_venta_periodo_pdv_categoria",
    "ix_venta_fecha_pdv",
    "ix_venta_periodo_cliente",
    "ix_venta_corrida",
}

#: Lo mismo para `presupuesto_historial`, que la revisión `0005` recrea en
#: SQLite al volver anulable `categoria_id`. `ix_historial_periodo_pdv` es el
#: índice que sirve la consulta del historial por período y punto de venta.
INDICES_HISTORIAL_ESPERADOS = {"ix_historial_periodo_pdv"}

#: Nombre con el que la revisión `0004` marcó la categoría retirada.
CAJON_RETIRADO = "OTROS (RETIRADA - REUBICAR)"


def _alembic(entorno: dict[str, str], *argumentos: str) -> subprocess.CompletedProcess[str]:
    """La CLI real, en un proceso aparte y contra la base que diga `entorno`.

    Se invoca por CLI y no con `alembic.command` a propósito: lo que hay que
    probar es el comando que teclea quien monta su entorno, `alembic.ini` y
    `env.py` incluidos.
    """
    return subprocess.run(  # noqa: S603 - comando fijo, sin entrada del usuario
        [sys.executable, "-m", "alembic", *argumentos],
        cwd=RAIZ,
        env=entorno,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def test_alembic_upgrade_head_recorre_todas_las_migraciones_sobre_sqlite(tmp_path: Path) -> None:
    """`alembic upgrade head` sobre una base SQLite **nueva**, no sobre una ya migrada."""
    archivo = tmp_path / "migraciones.db"
    assert not archivo.exists(), (
        "la base tiene que nacer aquí; si no, no se prueban las migraciones"
    )

    entorno = dict(os.environ)
    entorno["SIGREP_DB_URL_OVERRIDE"] = f"sqlite:///{archivo.as_posix()}"

    proceso = _alembic(entorno, "upgrade", "head")

    assert proceso.returncode == 0, (
        "`alembic upgrade head` falló sobre SQLite; el arranque en desarrollo que "
        f"documenta el README está roto.\n{proceso.stdout[-2000:]}\n{proceso.stderr[-4000:]}"
    )
    assert archivo.exists(), "la migración no creó la base"

    # Se recorrieron **todas** las revisiones, no solo la primera.
    aplicadas = proceso.stderr + proceso.stdout
    for revision in ("0001", "0002", "0003", "0004", "0005", "0009"):
        assert f"-> {revision}" in aplicadas, f"la revisión {revision} no llegó a ejecutarse"

    actual = _alembic(entorno, "current")
    assert actual.returncode == 0, actual.stderr[-2000:]
    assert "(head)" in actual.stdout + actual.stderr, (
        f"la base no quedó en la revisión cabeza: {actual.stdout!r}"
    )

    conexion = sqlite3.connect(archivo)
    try:
        columnas = {fila[1]: fila for fila in conexion.execute("PRAGMA table_info(venta_lineas)")}
        indices = {fila[1] for fila in conexion.execute("PRAGMA index_list(venta_lineas)")}
        historial = {
            fila[1]: fila for fila in conexion.execute("PRAGMA table_info(presupuesto_historial)")
        }
        indices_historial = {
            fila[1] for fila in conexion.execute("PRAGMA index_list(presupuesto_historial)")
        }
    finally:
        conexion.close()

    # `PRAGMA table_info` devuelve (cid, name, type, notnull, default, pk).
    assert columnas["costo_promedio"][3] == 0, (
        "`costo_promedio` sigue siendo NOT NULL: las líneas sin costo volverían a "
        "entrar en cero y PEREIRA publicaría 100 % de margen (§4.4)"
    )
    assert columnas["valor_subtotal"][3] == 1, "la venta sí es obligatoria y debe seguir siéndolo"

    faltantes = INDICES_ESPERADOS - indices
    assert not faltantes, f"la recreación de la tabla en SQLite perdió índices: {sorted(faltantes)}"

    assert historial["categoria_id"][3] == 0, (
        "`presupuesto_historial.categoria_id` sigue siendo NOT NULL: la revisión 0005 no "
        "podría borrar la categoría retirada sin destruir el rastro de §3.3"
    )
    assert historial["motivo"][3] == 1, "el motivo del cambio sigue siendo obligatorio (§3.3)"

    faltantes_historial = INDICES_HISTORIAL_ESPERADOS - indices_historial
    assert not faltantes_historial, (
        "la recreación de `presupuesto_historial` en SQLite perdió índices: "
        f"{sorted(faltantes_historial)}"
    )


def _base_en_0004(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """Una base SQLite migrada hasta la `0004`, justo antes de la que se prueba."""
    archivo = tmp_path / "cajon.db"
    entorno = dict(os.environ)
    entorno["SIGREP_DB_URL_OVERRIDE"] = f"sqlite:///{archivo.as_posix()}"
    proceso = _alembic(entorno, "upgrade", "0004")
    assert proceso.returncode == 0, proceso.stderr[-4000:]
    return archivo, entorno


def _sembrar_cajon_con_presupuesto(archivo: Path, monto: str) -> None:
    """Reconstruye el escenario real: categoría retirada con presupuesto colgando.

    Se escribe con `sqlite3` a pelo y no con el ORM a propósito: lo que se
    prueba es la migración contra un esquema construido por migraciones, y meter
    los modelos por medio introduciría justo la diferencia entre `create_all` y
    `upgrade` que estas pruebas existen para vigilar.
    """
    conexion = sqlite3.connect(archivo)
    try:
        conexion.execute(
            "INSERT INTO periodos (anio, mes, cerrado, creado_en, actualizado_en) "
            "VALUES (2026, 8, 0, '2026-08-01 00:00:00', '2026-08-01 00:00:00')"
        )
        conexion.execute(
            "INSERT INTO puntos_venta (codigo_co, nombre, activo, presupuestado, creado_en, "
            "actualizado_en) VALUES ('402', 'MALAMBO', 1, 1, '2026-08-01 00:00:00', "
            "'2026-08-01 00:00:00')"
        )
        conexion.execute(
            "INSERT INTO categorias (codigo, nombre, orden, activa, creado_en, actualizado_en) "
            "VALUES ('OTROS', ?, 99, 0, '2026-08-01 00:00:00', '2026-08-01 00:00:00')",
            (CAJON_RETIRADO,),
        )
        conexion.execute(
            "INSERT INTO presupuestos (periodo_id, punto_venta_id, categoria_id, monto, kilos, "
            "creado_en, actualizado_en) SELECT p.id, pv.id, c.id, ?, 0, "
            "'2026-08-01 00:00:00', '2026-08-01 00:00:00' "
            "FROM periodos p, puntos_venta pv, categorias c WHERE c.nombre = ?",
            (monto, CAJON_RETIRADO),
        )
        conexion.commit()
    finally:
        conexion.close()


def test_la_revision_0005_se_niega_a_borrar_una_categoria_con_presupuesto(
    tmp_path: Path,
) -> None:
    """616 millones no desaparecen en silencio: la migración aborta y dice qué hacer.

    Es la salvaguarda entera de la revisión `0005`. Si algún día alguien la
    relaja «porque estorba en el despliegue», esta prueba se pone en rojo antes
    de que el presupuesto de la compañía se quede corto sin explicación.
    """
    archivo, entorno = _base_en_0004(tmp_path)
    _sembrar_cajon_con_presupuesto(archivo, "616000000.00")

    proceso = _alembic(entorno, "upgrade", "head")
    salida = proceso.stdout + proceso.stderr

    print()
    print(f"  alembic upgrade head → código {proceso.returncode}")

    assert proceso.returncode != 0, (
        "la revisión 0005 borró una categoría que todavía tenía presupuesto capturado"
    )
    assert "reparto_presupuesto" in salida, (
        f"el mensaje no dice qué comando ejecutar antes:\n{salida[-3000:]}"
    )
    assert "2026-08" in salida, "el mensaje no nombra el período que hay que repartir"

    # Y no dejó la base a medias: la categoría y su presupuesto siguen ahí.
    conexion = sqlite3.connect(archivo)
    try:
        cuantas = conexion.execute("SELECT COUNT(*) FROM presupuestos").fetchone()[0]
        categorias = conexion.execute(
            "SELECT COUNT(*) FROM categorias WHERE nombre = ?", (CAJON_RETIRADO,)
        ).fetchone()[0]
    finally:
        conexion.close()
    assert (cuantas, categorias) == (1, 1), "la migración abortada dejó la base a medias"


def test_la_revision_0005_borra_la_categoria_cuando_ya_no_tiene_presupuesto(
    tmp_path: Path,
) -> None:
    """Con el presupuesto ya repartido, la retirada se cierra: se borra la categoría.

    Se comprueba además lo que se decidió con las dos líneas de venta huérfanas
    —las que llegaron sin categoría del origen—: **se borran**, y el historial de
    presupuesto que apuntaba a la categoría **no**, se desliga.
    """
    archivo, entorno = _base_en_0004(tmp_path)
    _sembrar_cajon_con_presupuesto(archivo, "616000000.00")

    conexion = sqlite3.connect(archivo)
    try:
        # El reparto ya pasó: la fila de presupuesto no está, pero su historial sí.
        conexion.execute("DELETE FROM presupuestos")
        conexion.execute(
            "INSERT INTO presupuesto_historial (presupuesto_id, periodo_id, punto_venta_id, "
            "categoria_id, campo, valor_anterior, valor_nuevo, motivo, cuando) "
            "SELECT NULL, p.id, pv.id, c.id, 'monto', 616000000, 0, "
            "'Reparto proporcional a la venta del período 2026-08', '2026-08-13 00:00:00' "
            "FROM periodos p, puntos_venta pv, categorias c WHERE c.nombre = ?",
            (CAJON_RETIRADO,),
        )
        # Las dos líneas huérfanas: sin `categoria_siesa`, imposibles de reubicar.
        conexion.execute(
            "INSERT INTO venta_lineas (periodo_id, fecha, punto_venta_id, categoria_id, "
            "valor_subtotal, cantidad_inv, categoria_siesa) "
            "SELECT p.id, '2026-08-01', pv.id, c.id, 74075, 5, NULL "
            "FROM periodos p, puntos_venta pv, categorias c WHERE c.nombre = ?",
            (CAJON_RETIRADO,),
        )
        conexion.execute(
            "INSERT INTO mapeo_categorias (texto_siesa, categoria_id, creado_en, actualizado_en) "
            "SELECT '9999 - LO QUE SEA', c.id, '2026-08-01 00:00:00', '2026-08-01 00:00:00' "
            "FROM categorias c WHERE c.nombre = ?",
            (CAJON_RETIRADO,),
        )
        conexion.commit()
    finally:
        conexion.close()

    proceso = _alembic(entorno, "upgrade", "head")
    assert proceso.returncode == 0, f"{proceso.stdout[-2000:]}\n{proceso.stderr[-4000:]}"

    conexion = sqlite3.connect(archivo)
    try:
        categorias = conexion.execute(
            "SELECT COUNT(*) FROM categorias WHERE nombre = ?", (CAJON_RETIRADO,)
        ).fetchone()[0]
        lineas = conexion.execute("SELECT COUNT(*) FROM venta_lineas").fetchone()[0]
        mapeos = conexion.execute("SELECT COUNT(*) FROM mapeo_categorias").fetchone()[0]
        historial = conexion.execute(
            "SELECT categoria_id, motivo FROM presupuesto_historial"
        ).fetchall()
    finally:
        conexion.close()

    print()
    print(f"  categorías retiradas: {categorias} · líneas: {lineas} · mapeos: {mapeos}")
    print(f"  historial conservado: {historial}")

    assert categorias == 0, "la categoría retirada sigue existiendo"
    assert lineas == 0, "las líneas huérfanas siguen ahí y la categoría no se podría borrar"
    assert mapeos == 0, "quedó mapeo apuntando a una categoría inexistente"
    assert len(historial) == 1, "el historial se borró: §3.3 exige que el rastro sobreviva"
    assert historial[0][0] is None, "el vínculo con la categoría borrada no se anuló"
    assert "Reparto proporcional" in historial[0][1], "el motivo del cambio se perdió"
