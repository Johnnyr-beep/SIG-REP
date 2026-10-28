"""Movimientos paginados de inventario de Agropecuaria, compañía 3."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.infrastructure.fuentes.existencias_bodega_agro import FuenteExistenciasBodegaAgroSiesa
from app.infrastructure.fuentes.siesa import ESTADOS_REINTENTABLES, ErrorFuenteSiesa, token_efectivo
from app.schemas.inventario import RespuestaMovimientosInventario

RUTA_MOVIMIENTOS = "/ventas/movimientos-inventario"


class _PaginaMovimientos(BaseModel):
    model_config = ConfigDict(strict=True)

    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    count: int = Field(ge=0)
    has_more: bool
    next_offset: int | None = Field(default=None, ge=0)
    data: list[dict[str, str | int | Decimal | None]]


class FuenteMovimientosInventarioSiesa(FuenteExistenciasBodegaAgroSiesa):
    def leer_pagina(
        self,
        desde: date,
        hasta: date,
        *,
        limit: int = 100,
        offset: int = 0,
        instalacion: Literal["planta", "monteria"] | None = None,
    ) -> RespuestaMovimientosInventario:
        if instalacion is None:
            return self._leer_pagina_origen(desde, hasta, limit=limit, offset=offset)

        prefijo = "301" if instalacion == "planta" else "302"
        filas: list[dict[str, str | None]] = []
        columnas: dict[str, None] = {}
        total = 0
        offset_origen = 0
        while True:
            pagina = self._leer_pagina_origen(desde, hasta, limit=5000, offset=offset_origen)
            columnas.update(dict.fromkeys(pagina.columnas))
            for fila in pagina.filas:
                codigo_bodega = (fila.get("Bodega") or "").strip()
                if codigo_bodega[:3] != prefijo:
                    continue
                if offset <= total < offset + limit:
                    filas.append(fila)
                total += 1
            if not pagina.has_more or pagina.next_offset is None:
                break
            offset_origen = pagina.next_offset
        siguiente = offset + len(filas)
        return RespuestaMovimientosInventario(
            columnas=list(columnas),
            filas=filas,
            total=total,
            limit=limit,
            offset=offset,
            count=len(filas),
            has_more=siguiente < total,
            next_offset=siguiente if siguiente < total else None,
        )

    def _leer_pagina_origen(
        self, desde: date, hasta: date, *, limit: int, offset: int
    ) -> RespuestaMovimientosInventario:
        configuracion = self._configuracion
        parametros = {
            "fecha_inicio": desde.isoformat(),
            "fecha_fin": hasta.isoformat(),
            "compania": "3",
            "limit": str(limit),
            "offset": str(offset),
        }
        intentos = max(configuracion.reintentos, 1)
        for intento in range(1, intentos + 1):
            try:
                respuesta = self._cliente().get(
                    configuracion.url_base + RUTA_MOVIMIENTOS,
                    params=parametros,
                    headers={
                        "X-API-Key": token_efectivo(configuracion.token.get_secret_value()),
                        "Accept": "application/json",
                    },
                )
                if respuesta.status_code >= 400:
                    if respuesta.status_code in ESTADOS_REINTENTABLES and intento < intentos:
                        self._esperar(intento)
                        continue
                    raise ErrorFuenteSiesa(
                        f"La API de SIESA respondió {respuesta.status_code} en {RUTA_MOVIMIENTOS}."
                    )
                try:
                    pagina = _PaginaMovimientos.model_validate(
                        json.loads(respuesta.text, parse_float=Decimal)
                    )
                except (ValueError, ValidationError):
                    raise ErrorFuenteSiesa(
                        f"La respuesta de {RUTA_MOVIMIENTOS} no cumple el contrato JSON paginado."
                    ) from None
                if (
                    pagina.offset != offset
                    or pagina.limit != limit
                    or pagina.count != len(pagina.data)
                    or pagina.count > limit
                    or pagina.total < offset + pagina.count
                    or (
                        pagina.has_more
                        and (
                            pagina.count == 0
                            or pagina.next_offset != offset + pagina.count
                            or pagina.next_offset >= pagina.total
                        )
                    )
                ):
                    raise ErrorFuenteSiesa(
                        "SIESA devolvió una paginación de inventario inconsistente."
                    )
                columnas = list(dict.fromkeys(clave for fila in pagina.data for clave in fila))
                return RespuestaMovimientosInventario(
                    columnas=columnas,
                    filas=[
                        {
                            clave: None if valor is None else str(valor)
                            for clave, valor in fila.items()
                        }
                        for fila in pagina.data
                    ],
                    total=pagina.total,
                    limit=pagina.limit,
                    offset=pagina.offset,
                    count=pagina.count,
                    has_more=pagina.has_more,
                    next_offset=pagina.next_offset if pagina.has_more else None,
                )
            except httpx.HTTPError as exc:
                if intento == intentos:
                    raise ErrorFuenteSiesa(
                        f"No se pudo leer {RUTA_MOVIMIENTOS} ({type(exc).__name__})."
                    ) from None
                self._esperar(intento)
        raise ErrorFuenteSiesa(f"No se pudo leer {RUTA_MOVIMIENTOS}.")
