from datetime import date

import httpx
from pydantic import BaseModel

from app.application.services.tpv_service import RegistroTpv
from app.core.config import Settings
from app.infrastructure.fuentes.siesa import ErrorFuenteSiesa, token_efectivo


class PaginaTpv(BaseModel):
    data: list[RegistroTpv]
    has_more: bool
    next_offset: int | None = None


def leer_paginas_tpv(
    cliente: httpx.Client, companias: tuple[int, ...], inicio: date, corte: date
) -> list[RegistroTpv]:
    registros: list[RegistroTpv] = []
    for compania in companias:
        offset = 0
        while True:
            try:
                respuesta = cliente.get("/ventas/tpv-no-acumuladas", params={
                    "cia": compania, "fecha_inicio": inicio.isoformat(),
                    "fecha_fin": corte.isoformat(), "limit": 5000, "offset": offset,
                })
                respuesta.raise_for_status()
                pagina = PaginaTpv.model_validate_json(respuesta.content)
            except (httpx.HTTPError, ValueError):
                raise ErrorFuenteSiesa(
                    "No se pudieron consultar los registros de TPV en SIESA."
                ) from None

            if any(registro.compania != compania for registro in pagina.data):
                raise ErrorFuenteSiesa("SIESA devolvió registros de una compañía distinta.")
            registros.extend(pagina.data)
            if not pagina.has_more:
                break
            if pagina.next_offset is None or pagina.next_offset <= offset or not pagina.data:
                raise ErrorFuenteSiesa("SIESA devolvió una paginación de TPV inválida.")
            offset = pagina.next_offset
    return registros


def consultar_registros_tpv(
    settings: Settings, unidad: str, inicio: date, corte: date
) -> list[RegistroTpv]:
    token = token_efectivo(settings.siesa_token.get_secret_value())
    companias = settings.companias_siesa_de(unidad)
    if not token or not companias:
        raise ErrorFuenteSiesa("La consulta de TPV no está configurada en SIGREP.")
    with httpx.Client(
        base_url=settings.siesa_url_base,
        headers={"Authorization": token, "Accept": "application/json"},
        timeout=httpx.Timeout(20.0, connect=settings.siesa_timeout_conexion_seg),
    ) as cliente:
        return leer_paginas_tpv(cliente, companias, inicio, corte)