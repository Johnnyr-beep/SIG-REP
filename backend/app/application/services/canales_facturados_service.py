"""Agregación mensual de ventas facturadas por canal."""

from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

import httpx

from app.core.config import Settings
from app.infrastructure.fuentes.ventas_canal_siesa import (
    ConfiguracionVentasCanal,
    consultar_ventas_por_canal,
)
from app.schemas.reportes import RespuestaCanalesFacturados

_CENTAVO = Decimal("0.01")
_FRACCION = Decimal("0.000001")
_MESES_BUSQUEDA = 12


def _periodo_anterior(periodo: str, meses: int) -> str:
    anio, mes = (int(parte) for parte in periodo.split("-"))
    indice = anio * 12 + mes - 1 - meses
    anio_encontrado, mes_cero = divmod(indice, 12)
    return f"{anio_encontrado:04d}-{mes_cero + 1:02d}"


def ventas_facturadas_por_canal(
    periodo: str,
    companias: tuple[int, ...],
    *,
    settings: Settings,
    cliente: httpx.Client | None = None,
) -> RespuestaCanalesFacturados:
    configuracion = ConfiguracionVentasCanal.desde_settings(settings)
    periodo_encontrado = periodo
    registros = []
    for diferencia in range(_MESES_BUSQUEDA):
        periodo_encontrado = _periodo_anterior(periodo, diferencia)
        registros = consultar_ventas_por_canal(
            periodo_encontrado.replace("-", ""),
            companias,
            configuracion=configuracion,
            cliente=cliente,
        )
        if registros:
            break
    else:
        periodo_encontrado = periodo
    ventas: dict[str, Decimal] = defaultdict(Decimal)
    for registro in registros:
        ventas[registro.canal] += registro.venta_neta

    total = sum(ventas.values(), Decimal("0"))
    filas = [
        {
            "canal": canal,
            "venta": format(venta.quantize(_CENTAVO, rounding=ROUND_HALF_UP), "f"),
            "participacion": (
                format((venta / total).quantize(_FRACCION, rounding=ROUND_HALF_UP), "f")
                if total
                else None
            ),
        }
        for canal, venta in sorted(ventas.items(), key=lambda item: (-item[1], item[0]))
    ]
    total_texto = format(total.quantize(_CENTAVO, rounding=ROUND_HALF_UP), "f")
    return RespuestaCanalesFacturados(
        periodo=periodo_encontrado,
        periodo_solicitado=periodo,
        total_venta=total_texto,
        filas=filas,
    )
