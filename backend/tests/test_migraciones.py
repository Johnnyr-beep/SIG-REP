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
    for revision in ("0001", "0002", "0003"):
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
