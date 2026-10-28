"""Rentabilidad operativa de Carnes, separada por compañía, categoría y producto."""

from __future__ import annotations

from calendar import monthrange
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import obtener_settings
from app.core.errors import ErrorValidacion
from app.domain.puertos import LineaVenta
from app.infrastructure.fuentes.siesa import (
    COMPANIAS_CARNES,
    ConfiguracionSiesa,
    FuenteVentaSiesa,
)
from app.infrastructure.models.organizacion import PuntoVenta
from app.schemas.financiero import (
    FilaCategoriaCarnes,
    FilaCompaniaCarnes,
    FilaProductoCarnes,
    PuntoRentabilidadCarnes,
    RespuestaRentabilidadCarnes,
)

NOMBRES_COMPANIAS_CARNES = {
    4: "Carnes Santacruz",
    6: "Cristian Serrano",
    7: "Serueda",
}

_CERO = Decimal(0)


class FuenteCarnes(Protocol):
    def obtener_ventas(self, desde: date, hasta: date) -> Iterable[LineaVenta]: ...

    def cerrar(self) -> None: ...


@dataclass(slots=True)
class _Dia:
    venta: Decimal = _CERO
    kilos: Decimal = _CERO
    costo: Decimal = _CERO
    costo_completo: bool = True

    def agregar(self, venta: Decimal, kilos: Decimal, costo_total_linea: Decimal | None) -> None:
        self.venta += venta
        self.kilos += kilos
        if costo_total_linea is None:
            self.costo_completo = False
        else:
            self.costo += costo_total_linea


@dataclass(slots=True)
class _Acumulado:
    venta: Decimal = _CERO
    kilos: Decimal = _CERO
    costo: Decimal = _CERO
    costo_completo: bool = True
    lineas: int = 0
    por_dia: dict[date, _Dia] = field(default_factory=dict)

    def agregar(
        self,
        fecha: date,
        venta: Decimal,
        kilos: Decimal,
        costo_total_linea: Decimal | None,
    ) -> None:
        self.venta += venta
        self.kilos += kilos
        self.lineas += 1
        if costo_total_linea is None:
            self.costo_completo = False
        else:
            self.costo += costo_total_linea
        self.por_dia.setdefault(fecha, _Dia()).agregar(venta, kilos, costo_total_linea)

    @property
    def costo_total(self) -> Decimal | None:
        return self.costo if self.lineas > 0 and self.costo_completo else None

    @property
    def margen(self) -> Decimal | None:
        costo = self.costo_total
        return self.venta - costo if costo is not None else None

    @property
    def rentabilidad(self) -> Decimal | None:
        margen = self.margen
        return margen / self.venta if margen is not None and self.venta != 0 else None

    @property
    def costo_unitario_promedio(self) -> Decimal | None:
        costo = self.costo_total
        return costo / self.kilos if costo is not None and self.kilos != 0 else None


def _descripcion_centros(sesion: Session) -> dict[str, str]:
    filas = sesion.execute(
        select(PuntoVenta.descripcion_siesa, PuntoVenta.codigo_co).where(
            PuntoVenta.descripcion_siesa.is_not(None)
        )
    ).tuples()
    return {descripcion: codigo for descripcion, codigo in filas if descripcion}


def _producto(linea: LineaVenta) -> tuple[str, str | None]:
    referencia = linea.referencia
    descripcion = linea.desc_item
    etiqueta = (
        f"{referencia} · {descripcion}"
        if referencia and descripcion
        else referencia or descripcion or "SIN PRODUCTO"
    )
    return str(etiqueta), referencia


def _fila_base(etiqueta: str, acumulado: _Acumulado, fechas: list[date]) -> dict[str, object]:
    return {
        "etiqueta": etiqueta,
        "kilos": acumulado.kilos,
        "venta": acumulado.venta,
        "costo": acumulado.costo_total,
        "margen_bruto": acumulado.margen,
        "rentabilidad": acumulado.rentabilidad,
        "costo_unitario_promedio": acumulado.costo_unitario_promedio,
        "ventas_por_dia": [acumulado.por_dia.get(fecha, _Dia()).venta for fecha in fechas],
    }


def calcular_rentabilidad_carnes_mes(
    periodo: str,
    sesion: Session,
    *,
    fabrica_fuente: Callable[[int], FuenteCarnes] | None = None,
) -> RespuestaRentabilidadCarnes:
    """Consulta 4/6/7 por separado y conserva el desglose de Carnes."""
    try:
        anio, mes = int(periodo[:4]), int(periodo[4:])
        desde = date(anio, mes, 1)
    except (ValueError, TypeError) as exc:
        raise ErrorValidacion("El período debe tener formato AAAAMM válido.") from exc
    hasta = date(anio, mes, monthrange(anio, mes)[1])
    fechas = [desde + timedelta(days=dia) for dia in range((hasta - desde).days + 1)]

    fuente_por_compania: Callable[[int], FuenteCarnes]
    if fabrica_fuente is None:
        configuracion_base = ConfiguracionSiesa.desde_settings(obtener_settings(), unidad="carnes")
        descripciones = _descripcion_centros(sesion)

        def crear_fuente(compania: int) -> FuenteCarnes:
            configuracion = replace(configuracion_base, companias=(compania,))
            return FuenteVentaSiesa(descripciones, configuracion=configuracion)

        fuente_por_compania = crear_fuente
    else:
        fuente_por_compania = fabrica_fuente

    total = _Acumulado()
    diario: dict[date, _Dia] = {}
    por_compania = {compania: _Acumulado() for compania in COMPANIAS_CARNES}
    por_categoria: dict[tuple[int, str], _Acumulado] = {}
    por_producto: dict[tuple[int, str, str], _Acumulado] = {}
    referencias: dict[tuple[int, str, str], str | None] = {}

    for compania in COMPANIAS_CARNES:
        fuente = fuente_por_compania(compania)
        try:
            for linea in fuente.obtener_ventas(desde, hasta):
                categoria = linea.categoria_siesa or "SIN CATEGORÍA"
                nombre_producto, referencia = _producto(linea)
                total.agregar(
                    linea.fecha,
                    linea.valor_subtotal,
                    linea.cantidad_inv,
                    linea.costo_promedio,
                )
                diario.setdefault(linea.fecha, _Dia()).agregar(
                    linea.valor_subtotal, linea.cantidad_inv, linea.costo_promedio
                )
                por_compania[compania].agregar(
                    linea.fecha, linea.valor_subtotal, linea.cantidad_inv, linea.costo_promedio
                )
                por_categoria.setdefault((compania, categoria), _Acumulado()).agregar(
                    linea.fecha, linea.valor_subtotal, linea.cantidad_inv, linea.costo_promedio
                )
                clave_producto = (compania, categoria, nombre_producto)
                por_producto.setdefault(clave_producto, _Acumulado()).agregar(
                    linea.fecha, linea.valor_subtotal, linea.cantidad_inv, linea.costo_promedio
                )
                referencias[clave_producto] = referencia
        finally:
            fuente.cerrar()

    detalle_companias = []
    for compania, acumulado_compania in sorted(por_compania.items(), key=lambda item: item[0]):
        categorias = []
        etiquetas_categoria = sorted(
            categoria for cia, categoria in por_categoria if cia == compania
        )
        for categoria in etiquetas_categoria:
            acumulado_categoria = por_categoria[(compania, categoria)]
            productos = []
            claves_producto = [
                clave for clave in por_producto if clave[0] == compania and clave[1] == categoria
            ]
            claves_producto_ordenadas = sorted(
                claves_producto,
                key=lambda clave_producto: por_producto[clave_producto].venta,
                reverse=True,
            )
            for clave in claves_producto_ordenadas:
                acumulado_producto = por_producto[clave]
                productos.append(
                    FilaProductoCarnes(
                        **_fila_base(clave[2], acumulado_producto, fechas),
                        referencia=referencias[clave],
                    )
                )
            categorias.append(
                FilaCategoriaCarnes(
                    **_fila_base(categoria, acumulado_categoria, fechas),
                    productos=productos,
                )
            )
        detalle_companias.append(
            FilaCompaniaCarnes(
                **_fila_base(
                    NOMBRES_COMPANIAS_CARNES.get(compania, f"Compañía {compania}"),
                    acumulado_compania,
                    fechas,
                ),
                compania=compania,
                categorias=categorias,
            )
        )

    puntos_diarios = []
    for fecha in fechas:
        acumulado_dia = diario.get(fecha, _Dia())
        margen = acumulado_dia.venta - acumulado_dia.costo if acumulado_dia.costo_completo else None
        puntos_diarios.append(
            PuntoRentabilidadCarnes(
                fecha=fecha,
                kilos=acumulado_dia.kilos,
                venta=acumulado_dia.venta,
                margen_bruto=margen,
                rentabilidad=(
                    margen / acumulado_dia.venta
                    if margen is not None and acumulado_dia.venta != 0
                    else None
                ),
                costo_unitario_promedio=(
                    acumulado_dia.costo / acumulado_dia.kilos
                    if acumulado_dia.costo_completo and acumulado_dia.kilos != 0
                    else None
                ),
            )
        )

    return RespuestaRentabilidadCarnes(
        periodo=periodo,
        companias=list(COMPANIAS_CARNES),
        fechas=fechas,
        venta=total.venta,
        kilos=total.kilos,
        costo=total.costo_total,
        margen_bruto=total.margen,
        rentabilidad=total.rentabilidad,
        costo_unitario_promedio=total.costo_unitario_promedio,
        lineas_facturadas=total.lineas,
        diario=puntos_diarios,
        detalle_companias=detalle_companias,
    )
