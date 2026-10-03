from collections.abc import Iterator
from datetime import date
from decimal import Decimal

from app.application.services.financiero_rentabilidad_service import calcular_rentabilidad_mes
from app.infrastructure.fuentes.agropecuaria import LineaAgro


def _linea(
    *,
    tipo_item: str,
    co_id: str = "301",
    especie: str | None,
    tipo_comercial: str | None,
    cliente: str | None,
    referencia: str | None,
    venta: str,
    costo: str | None,
    kilos: str,
) -> LineaAgro:
    return LineaAgro(
        fecha=date(2026, 9, 1),
        co_id=co_id,
        centro_operacion="PLANTA",
        tipo_item_id=None,
        tipo_item=tipo_item,
        especie_id=None,
        especie=especie,
        tipo_comercial_id=None,
        tipo_comercial=tipo_comercial,
        grupo_id=None,
        grupo=None,
        item_ref=referencia,
        item_desc=f"Producto {referencia}" if referencia else None,
        cliente=cliente,
        codigo_vendedor=None,
        nombre_vendedor=None,
        cantidad_inv=Decimal(kilos),
        kilos_total=Decimal(kilos),
        valor_bruto=Decimal(venta),
        descuentos=Decimal(0),
        valor_subtotal=Decimal(venta),
        total_neto=Decimal(venta),
        total_costo=Decimal(costo) if costo is not None else None,
        utilidad_bruta=None,
        lineas_facturadas=1,
    )


class _FuenteSimulada:
    def __init__(self, filas: list[LineaAgro]) -> None:
        self.filas = filas

    def obtener_ventas(self, desde: date, hasta: date) -> Iterator[LineaAgro]:
        assert desde == date(2026, 9, 1)
        assert hasta == date(2026, 9, 30)
        yield from self.filas


def test_rentabilidad_mensual_agrega_dimensiones_y_no_inventa_costo() -> None:
    fuente = _FuenteSimulada(
        [
            _linea(
                tipo_item="0001 - BIENES",
                especie="RES",
                tipo_comercial="CORTE",
                cliente="CLIENTE UNO",
                referencia="RES-01",
                venta="100",
                costo="60",
                kilos="10",
            ),
            _linea(
                tipo_item="0002 - SERVICIOS",
                co_id="302",
                especie=None,
                tipo_comercial="SERVICIO",
                cliente="CLIENTE DOS",
                referencia="SER-01",
                venta="50",
                costo=None,
                kilos="5",
            ),
            _linea(
                tipo_item="IMPUESTO",
                especie="RES",
                tipo_comercial="IMPUESTO",
                cliente="CLIENTE UNO",
                referencia="IMP-01",
                venta="999",
                costo="0",
                kilos="1",
            ),
        ]
    )

    resultado = calcular_rentabilidad_mes("202609", fuente=fuente)

    assert resultado.cia == 3
    assert resultado.fecha_inicio == date(2026, 9, 1)
    assert resultado.fecha_fin == date(2026, 9, 30)
    assert resultado.venta == Decimal("150")
    assert resultado.costo is None
    assert resultado.margen_bruto is None
    assert resultado.lineas_facturadas == 2
    assert [fila.etiqueta for fila in resultado.tipos_item] == [
        "0001 - BIENES",
        "0002 - SERVICIOS",
    ]
    assert resultado.tipos_item[0].rentabilidad == Decimal("0.4")
    assert resultado.tipos_item[1].rentabilidad is None
    assert [fila.etiqueta for fila in resultado.especies] == ["RES"]
    assert [
        (centro.etiqueta, centro.venta) for centro in resultado.tipos_item[0].centros_operacion
    ] == [("301", Decimal("100"))]
    assert [
        (centro.etiqueta, centro.venta) for centro in resultado.tipos_item[1].centros_operacion
    ] == [("302", Decimal("50"))]
    assert len(resultado.diario) == 30
    assert resultado.diario[0].venta == Decimal("150")
    assert [fila.etiqueta for fila in resultado.clientes] == ["CLIENTE UNO", "CLIENTE DOS"]
    assert [fila.etiqueta for fila in resultado.productos] == [
        "RES-01 · Producto RES-01",
        "SER-01 · Producto SER-01",
    ]


def test_rentabilidad_mensual_anida_productos_bajo_su_tipo_comercial() -> None:
    fuente = _FuenteSimulada(
        [
            _linea(
                tipo_item="0001 - BIENES",
                especie="RES",
                tipo_comercial="CORTE",
                cliente="CLIENTE",
                referencia="RES-01",
                venta="100",
                costo="60",
                kilos="10",
            ),
            _linea(
                tipo_item="0001 - BIENES",
                especie="RES",
                tipo_comercial="SUBPRODUCTO",
                cliente="CLIENTE",
                referencia="RES-02",
                venta="25",
                costo="10",
                kilos="5",
            ),
        ]
    )

    resultado = calcular_rentabilidad_mes("202609", fuente=fuente)

    comerciales = {fila.etiqueta: fila for fila in resultado.especies[0].comerciales}
    assert [fila.etiqueta for fila in comerciales["CORTE"].productos] == [
        "RES-01 · Producto RES-01"
    ]
    assert comerciales["CORTE"].productos[0].venta == Decimal("100")
    assert [fila.etiqueta for fila in comerciales["SUBPRODUCTO"].productos] == [
        "RES-02 · Producto RES-02"
    ]
