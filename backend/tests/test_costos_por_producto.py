"""Costos y margen por producto: el cuarto desglose de `GET /reportes/costos`.

El ítem llega de la API de SIESA (`Referencia` + `DescItem`) desde la revisión
`0013`. Antes de ella la línea decía dónde se vendió y de qué categoría era,
pero no **qué** se vendió, y sin eso no hay tarjeta de costos por producto que
valga.

Tres reglas que este archivo fija:

1. **Cuadra con el consolidado.** La consulta del corte usa el mismo `WHERE`
   que la consulta caliente —período, corte y el perímetro de puntos
   visibles—, así que la suma de los productos es la venta consolidada, peso
   a peso. Un desglose que no cuadra es peor que ninguno.
2. **«SIN PRODUCTO» se publica, no se esconde.** Las líneas cargadas por Excel
   —que no trae ítem— o antes de que existiera la columna no tienen producto,
   y esa venta es real. Agruparla en un grupo a la vista mantiene la
   cuadratura y dice la verdad: se vendió, y no se sabe qué. Repartirla entre
   los productos conocidos sería inventar margen ajeno.
3. **El margen por producto obedece §4.4.** Un producto con alguna línea sin
   costo no tiene margen calculable: publica «—», no el margen de las líneas
   que sí lo traen.
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


# ── La agregación ─────────────────────────────────────────────────────────────


def test_el_desglose_por_producto_cuadra_con_el_consolidado(
    sesion: Session, estructura: None
) -> None:
    """La suma de los productos es el consolidado, aunque el ítem cruce puntos."""
    dar_venta(
        sesion,
        "402",
        "RES",
        1,
        "100000",
        costo="60000",
        referencia="1039",
        producto="HUESO SUSTANCIA CARNUDO",
    )
    dar_venta(
        sesion,
        "413",
        "RES",
        2,
        "50000",
        costo="30000",
        referencia="1039",
        producto="HUESO SUSTANCIA CARNUDO",
    )
    dar_venta(
        sesion, "402", "RES", 3, "30000", costo="18000", referencia="2050", producto="PUNTA DE ANCA"
    )

    respuesta = _costos(sesion)

    suma_productos = sum(D(fila.venta) for fila in respuesta.productos)
    assert suma_productos == D(respuesta.consolidado.venta)
    assert len(respuesta.productos) == 2


def test_el_mismo_item_en_dos_puntos_es_un_solo_producto(sesion: Session, estructura: None) -> None:
    """El corte es por referencia, no por pareja (punto, referencia)."""
    dar_venta(
        sesion,
        "402",
        "RES",
        1,
        "100",
        costo="60",
        referencia="1039",
        producto="HUESO SUSTANCIA CARNUDO",
    )
    dar_venta(
        sesion,
        "413",
        "RES",
        2,
        "50",
        costo="30",
        referencia="1039",
        producto="HUESO SUSTANCIA CARNUDO",
    )

    respuesta = _costos(sesion)

    assert len(respuesta.productos) == 1
    producto = respuesta.productos[0]
    assert producto.referencia == "1039"
    assert producto.nombre == "HUESO SUSTANCIA CARNUDO"
    assert D(producto.venta) == D("150")
    assert producto.lineas == 2


def test_los_productos_se_ordenan_de_mayor_a_menor_venta(sesion: Session, estructura: None) -> None:
    dar_venta(
        sesion, "402", "RES", 1, "30000", costo="18000", referencia="2050", producto="PUNTA DE ANCA"
    )
    dar_venta(
        sesion,
        "402",
        "RES",
        2,
        "100000",
        costo="60000",
        referencia="1039",
        producto="HUESO SUSTANCIA CARNUDO",
    )

    respuesta = _costos(sesion)

    assert [fila.referencia for fila in respuesta.productos] == ["1039", "2050"]


def test_la_venta_sin_item_se_agrupa_en_sin_producto_a_la_vista(
    sesion: Session, estructura: None
) -> None:
    """El Excel no trae ítem: su venta no desaparece ni se reparte."""
    dar_venta(sesion, "402", "RES", 1, "40000", costo="24000")  # sin ítem: el Excel
    dar_venta(
        sesion,
        "402",
        "RES",
        2,
        "10000",
        costo="6000",
        referencia="1039",
        producto="HUESO SUSTANCIA CARNUDO",
    )

    respuesta = _costos(sesion)

    sin_producto = [fila for fila in respuesta.productos if fila.referencia is None]
    assert len(sin_producto) == 1
    assert sin_producto[0].nombre == "SIN PRODUCTO"
    assert D(sin_producto[0].venta) == D("40000")
    suma_productos = sum(D(fila.venta) for fila in respuesta.productos)
    assert suma_productos == D(respuesta.consolidado.venta), (
        "la venta sin ítem tiene que cuadrar con el consolidado, no esconderse"
    )


def test_un_producto_con_lineas_sin_costo_no_tiene_margen(
    sesion: Session, estructura: None
) -> None:
    """§4.4 por ítem: basta una línea sin costo y el margen del producto es «—»."""
    dar_venta(
        sesion,
        "402",
        "RES",
        1,
        "100",
        costo="60",
        referencia="1039",
        producto="HUESO SUSTANCIA CARNUDO",
    )
    dar_venta(
        sesion,
        "402",
        "RES",
        2,
        "50",
        costo=None,
        referencia="1039",
        producto="HUESO SUSTANCIA CARNUDO",
    )

    respuesta = _costos(sesion)

    assert len(respuesta.productos) == 1
    producto = respuesta.productos[0]
    assert producto.costo is None
    assert producto.margen_valor is None
    assert producto.margen_porcentaje is None
    assert D(producto.venta) == D("150"), "el margen se pierde; la venta, no"


def test_el_desglose_respeta_el_filtro_de_categoria(sesion: Session, estructura: None) -> None:
    dar_venta(
        sesion,
        "402",
        "RES",
        1,
        "100",
        costo="60",
        referencia="1039",
        producto="HUESO SUSTANCIA CARNUDO",
    )
    dar_venta(
        sesion,
        "402",
        "CERDO",
        1,
        "200",
        costo="120",
        referencia="3055",
        producto="COSTILLA DE CERDO",
    )

    respuesta = _costos(sesion, categoria="CERDO")

    assert [fila.referencia for fila in respuesta.productos] == ["3055"]
