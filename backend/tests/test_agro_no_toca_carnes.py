"""Agropecuaria no lee ni una tabla de carnes, y no puede empezar a hacerlo.

Son dos compañías distintas: la 3 por un lado y la 4, la 6 y la 7 por otro, con
API de origen propia cada una. Que sus cifras no se mezclen no es una cuestión
de disciplina al escribir consultas —eso se rompe el primer día que alguien
tenga prisa—, así que se comprueba.

Lo que se fija aquí es la lectura. La separación en bases distintas está
pendiente; mientras las dos convivan en la misma, esta prueba es lo que impide
que una consulta de agro empiece a sumar venta de carnes sin que nadie lo note.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.application.services.agro_presupuesto_service import AgroPresupuestoService
from app.application.services.agro_reportes_service import AgroReportesService, FiltrosAgro
from app.application.services.periodos import obtener_o_crear_periodo
from app.domain.enums import Medida
from app.infrastructure.models.agro_vocabulario import DimensionPresupuesto, EjeCruce, EjeResumen
from tests.conftest import PERIODO as PERIODO_PRUEBAS
from tests.conftest import id_categoria, id_punto_venta

#: Las tablas de carnes. `periodos`, `usuarios` y las suyas quedan fuera a
#: propósito: el mes y el autor son del sistema, no de una compañía, y agro los
#: comparte legítimamente.
TABLAS_DE_CARNES = frozenset(
    {
        "venta_lineas",
        "presupuestos",
        "presupuesto_historial",
        "puntos_venta",
        "categorias",
        "grupos",
        "zonas",
        "calendario_zona",
        "clientes",
        "mapeo_categorias",
        "corridas_ingesta",
        "rechazos_ingesta",
    }
)

PERIODO = PERIODO_PRUEBAS
ANIO, MES = (int(parte) for parte in PERIODO.split("-"))
FILTROS = FiltrosAgro(
    periodo=PERIODO,
    hasta=date(ANIO, MES, 28),
    desde=date(ANIO, MES, 1),
    centros=None,
    medida=Medida.VALOR,
)


@pytest.fixture(autouse=True)
def periodo_abierto(sesion: Session) -> None:
    """Los reportes exigen un período abierto; sin él no llegan ni a consultar."""
    obtener_o_crear_periodo(sesion, PERIODO)
    sesion.flush()


def _sentencias(sesion: Session) -> list[str]:
    """Recoge el SQL que se emita mientras dure el bloque."""
    emitidas: list[str] = []

    def escuchar(_conn, _cursor, sentencia: str, *_resto: object) -> None:
        emitidas.append(sentencia)

    event.listen(sesion.bind, "before_cursor_execute", escuchar)
    sesion.info["_escucha"] = escuchar
    return emitidas


def _soltar(sesion: Session, emitidas: list[str]) -> set[str]:
    event.remove(sesion.bind, "before_cursor_execute", sesion.info.pop("_escucha"))

    referidas: set[str] = set()
    for sentencia in emitidas:
        # Basta con mirar los nombres que aparecen tras FROM y JOIN: es donde una
        # consulta declara de dónde saca las filas.
        for nombre in re.findall(r"\b(?:FROM|JOIN)\s+\"?([a-z_]+)\"?", sentencia, re.IGNORECASE):
            referidas.add(nombre.lower())
    return referidas


@pytest.mark.parametrize("eje", list(EjeResumen))
def test_el_resumen_no_consulta_ninguna_tabla_de_carnes(sesion: Session, eje: EjeResumen) -> None:
    emitidas = _sentencias(sesion)
    AgroReportesService(sesion).resumen(FILTROS, eje)
    intrusas = _soltar(sesion, emitidas) & TABLAS_DE_CARNES

    assert not intrusas, f"el resumen por {eje.value} leyó tablas de carnes: {sorted(intrusas)}"


@pytest.mark.parametrize("cruce", list(EjeCruce))
def test_el_cruce_no_consulta_ninguna_tabla_de_carnes(sesion: Session, cruce: EjeCruce) -> None:
    emitidas = _sentencias(sesion)
    AgroReportesService(sesion).cruce(FILTROS, cruce)
    intrusas = _soltar(sesion, emitidas) & TABLAS_DE_CARNES

    assert not intrusas, f"el cruce {cruce.value} leyó tablas de carnes: {sorted(intrusas)}"


def test_la_venta_diaria_no_consulta_ninguna_tabla_de_carnes(sesion: Session) -> None:
    emitidas = _sentencias(sesion)
    AgroReportesService(sesion).venta_diaria(FILTROS)
    intrusas = _soltar(sesion, emitidas) & TABLAS_DE_CARNES

    assert not intrusas, f"la venta diaria leyó tablas de carnes: {sorted(intrusas)}"


@pytest.mark.parametrize("dimension", list(DimensionPresupuesto))
def test_el_presupuesto_no_consulta_el_de_carnes(
    sesion: Session, dimension: DimensionPresupuesto
) -> None:
    """`presupuestos` y `agro_presupuestos` se llaman casi igual y no son lo mismo.

    Confundirlas mediría la venta de una compañía contra la meta de la otra, y el
    resultado tendría toda la pinta de un cumplimiento normal.
    """
    emitidas = _sentencias(sesion)
    AgroPresupuestoService(sesion).listar(PERIODO, dimension)
    intrusas = _soltar(sesion, emitidas) & TABLAS_DE_CARNES

    assert not intrusas, f"el presupuesto por {dimension.value} leyó: {sorted(intrusas)}"


def test_las_companias_de_origen_no_se_solapan() -> None:
    """La 3 es de agropecuaria; la 4, la 6 y la 7 son de carnes.

    Poner una compañía de carnes en `agro_compania` cargaría en el módulo de
    agropecuaria venta que se reporta en el otro, y las dos cifras dejarían de
    significar nada. Al revés igual.
    """
    from app.core.config import Settings

    ajustes = Settings(secret_key="c" * 40)

    assert ajustes.agro_compania not in ajustes.siesa_companias
    assert ajustes.agro_compania == 3
    assert sorted(ajustes.siesa_companias) == [4, 6, 7]


def test_el_cuadre_del_presupuesto_de_agro_ignora_lo_de_carnes(
    sesion: Session, estructura: None
) -> None:
    """Un presupuesto de carnes en el mismo período no altera el cuadre de agro.

    Es la prueba con datos, no con SQL: hay novecientos millones de meta de
    carnes en la misma base y el mismo mes, y el cuadre de agropecuaria tiene que
    seguir viendo cero.
    """
    from app.infrastructure.models.presupuesto import Presupuesto

    periodo = obtener_o_crear_periodo(sesion, PERIODO)
    sesion.add(
        Presupuesto(
            periodo_id=periodo.id,
            punto_venta_id=id_punto_venta(sesion, "402"),
            categoria_id=id_categoria(sesion, "RES"),
            monto=Decimal("999999999.00"),
            kilos=Decimal("0"),
        )
    )
    sesion.flush()

    salida = AgroPresupuestoService(sesion).cuadre_salida(PERIODO)

    for bloque in salida.dimensiones:
        assert Decimal(bloque.total_monto) == Decimal("0"), (
            f"la dimensión {bloque.dimension} recogió el presupuesto de carnes"
        )
