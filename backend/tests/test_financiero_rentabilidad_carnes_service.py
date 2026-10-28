from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.application.services.financiero_rentabilidad_carnes_service import (
    calcular_rentabilidad_carnes_mes,
)
from app.domain.puertos import LineaVenta


def _linea(
    *,
    fecha: date,
    venta: str,
    kilos: str,
    costo_linea: str | None,
    categoria: str,
    referencia: str,
    producto: str,
) -> LineaVenta:
    return LineaVenta(
        centro_operacion="402",
        fecha=fecha,
        valor_subtotal=Decimal(venta),
        costo_promedio=(Decimal(costo_linea) if costo_linea is not None else None),
        cantidad_inv=Decimal(kilos),
        categoria_siesa=categoria,
        referencia=referencia,
        desc_item=producto,
    )


class _FuenteFalsa:
    def __init__(self, filas: list[LineaVenta]) -> None:
        self._filas = filas

    def obtener_ventas(self, desde: date, hasta: date):
        assert desde == date(2026, 9, 1)
        assert hasta == date(2026, 9, 30)
        yield from self._filas

    def cerrar(self) -> None:
        return None


def test_consolida_carnes_con_detalle_por_compania_categoria_y_producto() -> None:
    filas_por_compania = {
        4: [
            _linea(
                fecha=date(2026, 9, 2),
                venta="100",
                kilos="10",
                costo_linea="6",
                categoria="RES",
                referencia="R-1",
                producto="Corte uno",
            ),
            _linea(
                fecha=date(2026, 9, 20),
                venta="50",
                kilos="5",
                costo_linea="6",
                categoria="RES",
                referencia="R-1",
                producto="Corte uno",
            ),
        ],
        6: [
            _linea(
                fecha=date(2026, 9, 3),
                venta="100",
                kilos="5",
                costo_linea=None,
                categoria="CERDO",
                referencia="C-1",
                producto="Producto sin costo",
            ),
        ],
        7: [],
    }
    llamadas: list[int] = []

    def crear_fuente(compania: int) -> _FuenteFalsa:
        llamadas.append(compania)
        return _FuenteFalsa(filas_por_compania[compania])

    resultado = calcular_rentabilidad_carnes_mes("202609", Session(), fabrica_fuente=crear_fuente)

    assert llamadas == [4, 6, 7]
    assert resultado.venta == Decimal("250")
    assert resultado.kilos == Decimal("20")
    assert resultado.costo is None
    assert len(resultado.detalle_companias) == 3

    por_cia = {fila.compania: fila for fila in resultado.detalle_companias}
    assert por_cia[4].venta == Decimal("150")
    assert por_cia[4].costo == Decimal("12")
    assert por_cia[4].costo_unitario_promedio == Decimal("0.8")
    assert por_cia[4].margen_bruto == Decimal("138")
    producto = por_cia[4].categorias[0].productos[0]
    assert producto.referencia == "R-1"
    assert producto.kilos == Decimal("15")
    assert producto.costo == Decimal("12")
    assert producto.costo_unitario_promedio == Decimal("0.8")
    assert producto.margen_bruto == Decimal("138")
    assert producto.ventas_por_dia[1] == Decimal("100")
    assert producto.ventas_por_dia[19] == Decimal("50")

    assert por_cia[6].categorias[0].productos[0].costo is None
    assert por_cia[6].categorias[0].productos[0].rentabilidad is None
    assert por_cia[7].venta == Decimal("0")
    assert por_cia[7].costo is None
