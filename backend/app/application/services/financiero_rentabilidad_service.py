"""Agregados operativos mensuales para el módulo Rentabilidad de Grupo."""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal

from app.core.config import obtener_settings
from app.core.errors import ErrorValidacion
from app.infrastructure.fuentes.agropecuaria import (
    COMPANIA_AGROPECUARIA,
    ConfiguracionAgro,
    FuenteVentaAgro,
    FuenteVentaAgropecuaria,
    LineaAgro,
)
from app.infrastructure.models.agro_vocabulario import es_impuesto
from app.schemas.financiero import (
    FilaEspecieRentabilidadMes,
    FilaRentabilidadMes,
    FilaTipoItemRentabilidadMes,
    PuntoRentabilidadMes,
    RespuestaRentabilidadMes,
)


@dataclass(slots=True)
class _Acumulado:
    venta: Decimal = Decimal(0)
    costo: Decimal = Decimal(0)
    kilos: Decimal = Decimal(0)
    lineas: int = 0
    costo_completo: bool = True

    def agregar(self, fila: LineaAgro) -> None:
        self.venta += fila.total_neto
        self.kilos += fila.kilos_total
        self.lineas += fila.lineas_facturadas
        if fila.total_costo is None:
            self.costo_completo = False
        else:
            self.costo += fila.total_costo

    @property
    def costo_conocido(self) -> Decimal | None:
        return self.costo if self.costo_completo else None

    @property
    def margen(self) -> Decimal | None:
        return self.venta - self.costo if self.costo_completo else None

    @property
    def porcentaje(self) -> Decimal | None:
        margen = self.margen
        if margen is None or self.venta == 0:
            return None
        return margen / self.venta


def _acumular(diccionario: dict[str, _Acumulado], clave: str, fila: LineaAgro) -> None:
    diccionario.setdefault(clave, _Acumulado()).agregar(fila)


def _fila(
    etiqueta: str, acumulado: _Acumulado, venta_total: Decimal | None = None
) -> FilaRentabilidadMes:
    participacion = (
        acumulado.venta / venta_total if venta_total is not None and venta_total != 0 else None
    )
    return FilaRentabilidadMes(
        etiqueta=etiqueta,
        venta=acumulado.venta,
        costo=acumulado.costo_conocido,
        margen_bruto=acumulado.margen,
        rentabilidad=acumulado.porcentaje,
        kilos=acumulado.kilos,
        participacion=participacion,
    )


def calcular_rentabilidad_mes(
    periodo: str, fuente: FuenteVentaAgro | None = None
) -> RespuestaRentabilidadMes:
    """Consulta cia 3 y agrega las métricas operativas del mes solicitado."""
    try:
        anio, mes = int(periodo[:4]), int(periodo[4:])
        desde = date(anio, mes, 1)
    except (ValueError, TypeError) as exc:
        raise ErrorValidacion("El período debe tener formato AAAAMM válido.") from exc
    hasta = date(anio, mes, monthrange(anio, mes)[1])

    fuente_creada: FuenteVentaAgropecuaria | None = None
    if fuente is None:
        configuracion = replace(
            ConfiguracionAgro.desde_settings(obtener_settings()),
            compania=COMPANIA_AGROPECUARIA,
        )
        fuente_creada = FuenteVentaAgropecuaria(configuracion=configuracion)
        origen: FuenteVentaAgro = fuente_creada
    else:
        origen = fuente

    total = _Acumulado()
    diario = {desde + timedelta(days=dia): _Acumulado() for dia in range((hasta - desde).days + 1)}
    tipos_item: dict[str, _Acumulado] = {}
    centros_por_tipo_item: dict[tuple[str, str], _Acumulado] = {}
    especies: dict[str, _Acumulado] = {}
    ventas_comerciales: dict[tuple[str, str], _Acumulado] = {}
    clientes: dict[str, _Acumulado] = {}
    productos: dict[str, _Acumulado] = {}

    try:
        for fila in origen.obtener_ventas(desde, hasta):
            if es_impuesto(fila.tipo_item):
                continue
            total.agregar(fila)
            diario[fila.fecha].agregar(fila)
            tipo_item = fila.tipo_item or "SIN TIPO DE ITEM"
            _acumular(tipos_item, tipo_item, fila)
            clave_centro = (tipo_item, fila.co_id or "SIN CENTRO")
            centros_por_tipo_item.setdefault(clave_centro, _Acumulado()).agregar(fila)
            if "BIENES" in (fila.tipo_item or "").upper():
                _acumular(especies, fila.especie or "SIN ESPECIE", fila)
                clave_comercial = (
                    fila.especie or "SIN ESPECIE",
                    fila.tipo_comercial or "SIN TIPO COMERCIAL",
                )
                ventas_comerciales.setdefault(clave_comercial, _Acumulado()).agregar(fila)
            _acumular(clientes, fila.cliente or "SIN CLIENTE", fila)
            etiqueta_producto = (
                f"{fila.item_ref} · {fila.item_desc}"
                if fila.item_ref and fila.item_desc
                else fila.item_ref or fila.item_desc or "SIN PRODUCTO"
            )
            _acumular(productos, etiqueta_producto, fila)
    finally:
        if fuente_creada is not None:
            fuente_creada.cerrar()

    tipos_salida = []
    for etiqueta, acumulado in sorted(
        tipos_item.items(), key=lambda par: par[1].venta, reverse=True
    ):
        centros = [
            _fila(centro, acumulado_centro, total.venta)
            for (tipo, centro), acumulado_centro in centros_por_tipo_item.items()
            if tipo == etiqueta
        ]
        centros.sort(key=lambda fila: fila.venta, reverse=True)
        tipos_salida.append(
            FilaTipoItemRentabilidadMes(
                **_fila(etiqueta, acumulado, total.venta).model_dump(),
                centros_operacion=centros,
            )
        )
    especies_salida: list[FilaEspecieRentabilidadMes] = []
    for especie, acumulado in sorted(especies.items(), key=lambda par: par[1].venta, reverse=True):
        comerciales = [
            _fila(tipo, valor, acumulado.venta)
            for (nombre_especie, tipo), valor in ventas_comerciales.items()
            if nombre_especie == especie
        ]
        comerciales.sort(key=lambda fila: fila.venta, reverse=True)
        especies_salida.append(
            FilaEspecieRentabilidadMes(
                **_fila(especie, acumulado, total.venta).model_dump(),
                comerciales=comerciales,
            )
        )

    ranking_clientes = sorted(
        (_fila(etiqueta, acumulado, total.venta) for etiqueta, acumulado in clientes.items()),
        key=lambda fila: fila.venta,
        reverse=True,
    )[:10]
    ranking_productos = sorted(
        (_fila(etiqueta, acumulado, total.venta) for etiqueta, acumulado in productos.items()),
        key=lambda fila: fila.venta,
        reverse=True,
    )[:10]

    return RespuestaRentabilidadMes(
        periodo=periodo,
        cia=COMPANIA_AGROPECUARIA,
        fecha_inicio=desde,
        fecha_fin=hasta,
        venta=total.venta,
        costo=total.costo_conocido,
        margen_bruto=total.margen,
        rentabilidad=total.porcentaje,
        kilos=total.kilos,
        lineas_facturadas=total.lineas,
        diario=[
            PuntoRentabilidadMes(
                fecha=dia,
                venta=acumulado.venta,
                rentabilidad=acumulado.porcentaje,
            )
            for dia, acumulado in diario.items()
        ],
        tipos_item=tipos_salida,
        especies=especies_salida,
        clientes=ranking_clientes,
        productos=ranking_productos,
    )
