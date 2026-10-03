from collections.abc import Iterator
from datetime import date
from decimal import Decimal

from app.application.services.financiero_rentabilidad_dia_service import (
    calcular_rentabilidad_dia,
)
from app.infrastructure.fuentes.agropecuaria import LineaAgro


def _linea(
    dia: int,
    *,
    especie: str,
    tipo_comercial: str,
    codigo_vendedor: str,
    venta: str,
    costo: str | None,
    cantidad: str,
    referencia: str = "ITEM-01",
    descripcion: str = "Producto",
) -> LineaAgro:
    return LineaAgro(
        fecha=date(2026, 9, dia),
        co_id="301",
        centro_operacion="PLANTA",
        tipo_item_id=None,
        tipo_item="BIENES",
        especie_id=None,
        especie=especie,
        tipo_comercial_id=None,
        tipo_comercial=tipo_comercial,
        grupo_id=None,
        grupo=None,
        item_ref=referencia,
        item_desc=descripcion,
        cliente="CLIENTE",
        codigo_vendedor=codigo_vendedor,
        nombre_vendedor="Vendedor",
        cantidad_inv=Decimal(cantidad),
        kilos_total=Decimal(cantidad),
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


def test_rentabilidad_diaria_agrega_canal_especies_y_clases() -> None:
    fuente = _FuenteSimulada(
        [
            _linea(
                1,
                especie="CERDO",
                tipo_comercial="CANAL",
                codigo_vendedor="V1",
                venta="100",
                costo="60",
                cantidad="4",
            ),
            _linea(
                2,
                especie="RES",
                tipo_comercial="CORTE",
                codigo_vendedor="V2",
                venta="50",
                costo="30",
                cantidad="2",
                referencia="RES-CORTE-01",
                descripcion="Lomo",
            ),
            _linea(
                2,
                especie="RES",
                tipo_comercial="SUBPRODUCTO",
                codigo_vendedor="V2",
                venta="0",
                costo="0",
                cantidad="0",
                referencia="RES-SUB-01",
                descripcion="Hueso",
            ),
        ]
    )

    resultado = calcular_rentabilidad_dia(
        "202609",
        fuente=fuente,
        mapa_vendedores={"V1": "CCT", "V2": "MAY"},
    )

    assert resultado.venta == Decimal("150")
    assert resultado.rentabilidad == Decimal("0.4")
    assert resultado.canal_cerdo == Decimal("4")
    assert resultado.canal_res == Decimal("0")
    assert resultado.costo_kg_cerdo == Decimal("15")
    assert resultado.costo_kg_res == Decimal("15")
    assert len(resultado.diario) == 30
    assert resultado.diario[0].venta == Decimal("100")
    assert resultado.diario[1].venta == Decimal("50")
    filas_clase = {fila.etiqueta: fila for fila in resultado.vendedores_clases}
    assert filas_clase["CCT"].valores[0] == Decimal("100")
    assert filas_clase["CCT"].rentabilidad == Decimal("0.4")
    assert filas_clase["CCT"].productos[0].etiqueta == "ITEM-01 · Producto"
    assert filas_clase["CCT"].productos[0].valores[0] == Decimal("100")
    assert filas_clase["CCT"].productos[0].rentabilidad == Decimal("0.4")
    assert filas_clase["MAY"].valores[1] == Decimal("50")
    fila_cerdo = next(fila for fila in resultado.especies_bienes if fila.etiqueta == "CERDO")
    assert fila_cerdo.detalle[0].valores[0] == Decimal("100")
    fila_res = next(fila for fila in resultado.especies_bienes if fila.etiqueta == "RES")
    tipos_res = {fila.etiqueta: fila for fila in fila_res.detalle}
    assert tipos_res["CORTE"].productos[0].etiqueta == "RES-CORTE-01 · Lomo"
    assert tipos_res["CORTE"].productos[0].valores[1] == Decimal("50")
    assert tipos_res["SUBPRODUCTO"].productos[0].etiqueta == "RES-SUB-01 · Hueso"


def test_rentabilidad_diaria_no_calcula_margen_si_falta_costo() -> None:
    resultado = calcular_rentabilidad_dia(
        "202609",
        fuente=_FuenteSimulada(
            [
                _linea(
                    1,
                    especie="CERDO",
                    tipo_comercial="CANAL",
                    codigo_vendedor="V1",
                    venta="100",
                    costo=None,
                    cantidad="4",
                )
            ]
        ),
        mapa_vendedores={},
    )

    assert resultado.rentabilidad is None
    assert resultado.diario[0].rentabilidad is None
    assert resultado.costo_kg_cerdo is None
