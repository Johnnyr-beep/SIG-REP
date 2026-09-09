"""Kilos, venta por kilo y costo %: las tres lecturas físicas del corte de costos.

`GET /reportes/costos` siempre sumó kilos (`Σ cantidad_inv`) para sus adentros;
esta revisión los **publica** junto con dos derivados que el negocio lee a diario:

- `venta_por_kilo` = `Σ valor_subtotal / Σ cantidad_inv`, el precio promedio
  **ponderado** del conjunto. No es el promedio de los precios de línea:
  ponderar por kilo es lo que hace que la cifra del grupo cuadre con la de
  sus puntos. Sin kilos vendidos es `None` —división protegida, nunca cero—
  y la pantalla pinta «—».
- `costo_porcentaje` = `Σ costo_promedio / Σ valor_subtotal`, el complemento
  del margen. Obedece la misma regla de §4.4: basta una línea sin costo para
  que el conjunto entero deje de tener cifra calculable y publique `None`.

Los kilos viajan en los cuatro desgloses —consolidado, grupo, punto de venta,
categoría y producto— porque todos heredan `FilaCostos`, y cada desglose se
calcula de su propia agregación: la suma de los kilos del desglose cuadra con
el consolidado, kilo a kilo, igual que la venta.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.application.services.reportes_service import FiltrosReporte, ReportesService
from app.schemas.reportes import RespuestaCostos
from tests.conftest import PERIODO, dar_venta

D = Decimal
CORTE = date(2026, 8, 15)


def _costos(sesion: Session, **filtros: object) -> RespuestaCostos:
    return ReportesService(sesion).costos(
        FiltrosReporte(periodo=PERIODO, hasta=CORTE, **filtros)  # type: ignore[arg-type]
    )


# ── Los kilos ─────────────────────────────────────────────────────────────────


def test_los_kilos_cuadran_en_todos_los_desgloses(sesion: Session, estructura: None) -> None:
    """La suma de cada desglose es el consolidado, kilo a kilo."""
    dar_venta(sesion, "402", "RES", 1, "100000", costo="60000", kilos="10")
    dar_venta(sesion, "413", "RES", 2, "50000", costo="30000", kilos="5")
    dar_venta(sesion, "402", "CERDO", 3, "20000", costo="14000", kilos="2")

    respuesta = _costos(sesion)

    assert D(respuesta.consolidado.kilos) == D("17.00")
    for desglose in ("grupos", "puntos_venta", "categorias", "productos"):
        filas = getattr(respuesta, desglose)
        assert sum(D(fila.kilos) for fila in filas) == D("17.00"), (
            f"los kilos del desglose por {desglose} tienen que cuadrar con el consolidado"
        )


def test_los_kilos_de_un_punto_son_los_suyos(sesion: Session, estructura: None) -> None:
    dar_venta(sesion, "402", "RES", 1, "100000", costo="60000", kilos="10")
    dar_venta(sesion, "413", "RES", 2, "50000", costo="30000", kilos="5")

    respuesta = _costos(sesion)

    por_punto = {fila.punto_venta: fila for fila in respuesta.puntos_venta}
    assert D(por_punto["402"].kilos) == D("10.00")
    assert D(por_punto["413"].kilos) == D("5.00")


# ── Venta por kilo ────────────────────────────────────────────────────────────


def test_la_venta_por_kilo_es_el_precio_promedio_ponderado(
    sesion: Session, estructura: None
) -> None:
    """`Σ valor / Σ kilos` del conjunto, no el promedio de precios de línea."""
    dar_venta(sesion, "402", "RES", 1, "100000", costo="60000", kilos="8")
    dar_venta(sesion, "402", "RES", 2, "20000", costo="12000", kilos="2")

    respuesta = _costos(sesion)

    assert D(respuesta.consolidado.venta_por_kilo) == D("12000.00"), (
        "120000 / 10 kg: el precio del conjunto pondera por kilo, no por línea"
    )


def test_sin_kilos_no_hay_venta_por_kilo(sesion: Session, estructura: None) -> None:
    """División protegida: sin kilos la pantalla pinta «—», nunca un cero falso."""
    dar_venta(sesion, "402", "RES", 1, "100000", costo="60000", kilos="0")

    respuesta = _costos(sesion)

    assert respuesta.consolidado.venta_por_kilo is None
    assert D(respuesta.consolidado.kilos) == D("0.00"), (
        "los kilos sí se publican: cero kilos vendidos es un dato, no una ausencia"
    )


# ── Costo % ───────────────────────────────────────────────────────────────────


def test_el_costo_porcentaje_es_el_complemento_del_margen(
    sesion: Session, estructura: None
) -> None:
    dar_venta(sesion, "402", "RES", 1, "100000", costo="70000", kilos="8")

    respuesta = _costos(sesion)

    consolidado = respuesta.consolidado
    assert D(consolidado.costo_porcentaje) == D("0.7000")
    assert D(consolidado.margen_porcentaje) + D(consolidado.costo_porcentaje) == D("1.0000")


def test_una_linea_sin_costo_tumba_el_costo_porcentaje_del_conjunto(
    sesion: Session, estructura: None
) -> None:
    """La misma regla del margen (§4.4): costo incompleto ⇒ «—», no una cifra a medias."""
    dar_venta(sesion, "402", "RES", 1, "100000", costo="70000", kilos="8")
    dar_venta(sesion, "402", "RES", 2, "50000", costo=None, kilos="4")

    respuesta = _costos(sesion)

    consolidado = respuesta.consolidado
    assert consolidado.costo is None
    assert consolidado.costo_porcentaje is None
    assert consolidado.margen_porcentaje is None
    assert D(consolidado.kilos) == D("12.00"), (
        "el costo se pierde; los kilos y la venta por kilo, no"
    )
    assert D(consolidado.venta_por_kilo) == D("12500.00")
