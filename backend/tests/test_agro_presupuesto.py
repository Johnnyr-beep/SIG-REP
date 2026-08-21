"""La regla que sostiene el presupuesto agropecuario.

El negocio fija la meta en **cuatro descomposiciones del mismo total**:
vendedor, centro de operacion, especie y tipo comercial. No son cuatro metas
distintas —es la misma plata repartida de cuatro formas—, y de ahi sale el unico
error que este modelo existe para hacer imposible:

    Sumar el presupuesto por vendedor con el presupuesto por especie da el doble
    de la meta. Con las cuatro, el cuadruple.

Estas pruebas fijan que la suma no se pueda escribir, no que este desaconsejada.
Una restriccion que solo advierte se ignora el dia que alguien tiene prisa.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.application.services.agro_presupuesto_service import (
    AgroPresupuestoService,
    ErrorDimensionesIncompatibles,
)
from app.application.services.periodos import obtener_o_crear_periodo
from app.infrastructure.models.agro_vocabulario import DimensionPresupuesto
from tests.conftest import PERIODO

VENDEDOR = DimensionPresupuesto.VENDEDOR
ESPECIE = DimensionPresupuesto.ESPECIE


def _plan(sesion: Session, dimension: DimensionPresupuesto):
    """`plan()` recibe el periodo resuelto, no su codigo."""
    periodo = obtener_o_crear_periodo(sesion, PERIODO)
    return AgroPresupuestoService(sesion).plan(periodo, dimension)


def _fijar(sesion: Session, dimension: DimensionPresupuesto, clave: str, monto: str) -> None:
    AgroPresupuestoService(sesion).guardar(
        codigo_periodo=PERIODO,
        dimension=dimension,
        clave=clave,
        monto=Decimal(monto),
        kilos=Decimal("0"),
        motivo="Meta inicial de la prueba",
    )


def test_dos_planes_de_dimensiones_distintas_no_se_pueden_sumar(
    estructura: None,
    sesion: Session,
) -> None:
    """Es el corazon del modelo: la suma prohibida no compila ni en ejecucion."""
    _fijar(sesion, VENDEDOR, "V-01", "1000000")
    _fijar(sesion, ESPECIE, "RES", "1000000")

    por_vendedor = _plan(sesion, VENDEDOR)
    por_especie = _plan(sesion, ESPECIE)

    with pytest.raises(ErrorDimensionesIncompatibles):
        _ = por_vendedor + por_especie


def test_dos_planes_de_la_misma_dimension_si_se_suman(
    estructura: None,
    sesion: Session,
) -> None:
    """Lo que se prohibe es cruzar descomposiciones, no agregar dentro de una."""
    _fijar(sesion, VENDEDOR, "V-01", "600000")
    _fijar(sesion, VENDEDOR, "V-02", "400000")

    plan = _plan(sesion, VENDEDOR)
    assert plan.total_monto == Decimal("1000000")


def test_el_plan_lleva_su_dimension_pegada(
    estructura: None,
    sesion: Session,
) -> None:
    """Un total suelto se puede sumar con cualquier cosa; uno con dimension, no."""
    _fijar(sesion, VENDEDOR, "V-01", "1000000")
    plan = _plan(sesion, VENDEDOR)

    assert plan.dimension is VENDEDOR
    assert plan.definido


def test_una_dimension_sin_capturar_no_finge_estar_en_cero(
    estructura: None,
    sesion: Session,
) -> None:
    """«Nadie la ha capturado» y «la meta es cero» son afirmaciones distintas."""
    plan = _plan(sesion, ESPECIE)
    assert not plan.definido


def test_el_cuadre_delata_cuando_dos_dimensiones_no_coinciden(
    estructura: None,
    sesion: Session,
) -> None:
    """Con cuatro descomposiciones del mismo total, tarde o temprano alguien
    actualiza una y olvida las otras. El sistema lo hace visible; no lo corrige,
    porque cual de las dos esta bien lo sabe el negocio y no el programa."""
    _fijar(sesion, VENDEDOR, "V-01", "1000000")
    _fijar(sesion, ESPECIE, "RES", "750000")

    cuadre = AgroPresupuestoService(sesion).cuadre(PERIODO)
    assert not cuadre.cuadra
