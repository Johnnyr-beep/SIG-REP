"""Endpoints de reportes — el núcleo (`docs/API.md`, sección Reportes).

Todos comparten los mismos filtros y todos devuelven `parametros_calculo`, para
que la pantalla pueda mostrar de dónde sale cada número (§4.2).

El alcance por punto de venta se aplica **aquí**, en la frontera: el servicio
recibe la lista de puntos permitidos y no vuelve a preguntarse quién consulta.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.api.v1 import LecturaDep
from app.application.services import exportacion_service
from app.application.services.reportes_service import FiltrosReporte, ReportesService
from app.core.deps import SesionDep, alcance_puntos_venta
from app.domain.enums import AgrupacionClientes, Medida
from app.schemas.reportes import (
    RespuestaClientes,
    RespuestaCumplimiento,
    RespuestaTablero,
    RespuestaVentaDiaria,
)

router = APIRouter(prefix="/reportes", tags=["Reportes"])

TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

PeriodoQuery = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", examples=["2026-08"])


def _filtros(
    usuario: LecturaDep,
    periodo: str,
    hasta: date | None,
    grupo: str | None,
    punto_venta: str | None,
    categoria: str | None,
    medida: Medida,
) -> FiltrosReporte:
    return FiltrosReporte(
        periodo=periodo,
        hasta=hasta,
        grupo=grupo,
        punto_venta=punto_venta,
        categoria=categoria,
        medida=medida,
        alcance=alcance_puntos_venta(usuario),
    )


@router.get("/tablero", response_model=RespuestaTablero, summary="Tablero gerencial")
def tablero(
    usuario: LecturaDep,
    sesion: SesionDep,
    periodo: str = PeriodoQuery,
    hasta: date | None = None,
    grupo: str | None = None,
    punto_venta: str | None = None,
    categoria: str | None = None,
    medida: Medida = Medida.VALOR,
) -> RespuestaTablero:
    """RBAC: cualquier rol autenticado; JEFE_PDV solo ve sus puntos."""
    return ReportesService(sesion).tablero(
        _filtros(usuario, periodo, hasta, grupo, punto_venta, categoria, medida)
    )


@router.get(
    "/cumplimiento", response_model=RespuestaCumplimiento, summary="Cumplimiento por punto de venta"
)
def cumplimiento(
    usuario: LecturaDep,
    sesion: SesionDep,
    periodo: str = PeriodoQuery,
    hasta: date | None = None,
    grupo: str | None = None,
    punto_venta: str | None = None,
    categoria: str | None = None,
    medida: Medida = Medida.VALOR,
) -> RespuestaCumplimiento:
    """RBAC: cualquier rol autenticado; JEFE_PDV solo ve sus puntos."""
    return ReportesService(sesion).cumplimiento(
        _filtros(usuario, periodo, hasta, grupo, punto_venta, categoria, medida)
    )


@router.get("/venta-diaria", response_model=RespuestaVentaDiaria, summary="Venta día por día")
def venta_diaria(
    usuario: LecturaDep,
    sesion: SesionDep,
    periodo: str = PeriodoQuery,
    hasta: date | None = None,
    grupo: str | None = None,
    punto_venta: str | None = None,
    categoria: str | None = None,
    medida: Medida = Medida.VALOR,
) -> RespuestaVentaDiaria:
    """RBAC: cualquier rol autenticado; JEFE_PDV solo ve sus puntos."""
    return ReportesService(sesion).venta_diaria(
        _filtros(usuario, periodo, hasta, grupo, punto_venta, categoria, medida)
    )


@router.get("/clientes", response_model=RespuestaClientes, summary="Clientes y vendedores")
def clientes(
    usuario: LecturaDep,
    sesion: SesionDep,
    periodo: str = PeriodoQuery,
    hasta: date | None = None,
    grupo: str | None = None,
    punto_venta: str | None = None,
    categoria: str | None = None,
    por: AgrupacionClientes = AgrupacionClientes.CLIENTE,
) -> RespuestaClientes:
    """RBAC: cualquier rol autenticado; JEFE_PDV solo ve sus puntos."""
    return ReportesService(sesion).clientes(
        _filtros(usuario, periodo, hasta, grupo, punto_venta, categoria, Medida.VALOR), por
    )


@router.get(
    "/{reporte}/exportar",
    summary="Exportar un reporte a Excel",
    response_class=Response,
    responses={200: {"content": {TIPO_XLSX: {}}, "description": "Libro .xlsx"}},
)
def exportar(
    reporte: Annotated[str, "tablero | cumplimiento | venta-diaria | clientes"],
    usuario: LecturaDep,
    sesion: SesionDep,
    periodo: str = PeriodoQuery,
    hasta: date | None = None,
    grupo: str | None = None,
    punto_venta: str | None = None,
    categoria: str | None = None,
    medida: Medida = Medida.VALOR,
    por: AgrupacionClientes = AgrupacionClientes.CLIENTE,
) -> Response:
    """RBAC: cualquier rol autenticado; JEFE_PDV solo ve sus puntos.

    Exporta **lo mismo que muestra la pantalla**, con los mismos filtros y a
    partir de la misma respuesta ya calculada.
    """
    from app.core.errors import ErrorNoEncontrado

    filtros = _filtros(usuario, periodo, hasta, grupo, punto_venta, categoria, medida)
    servicio = ReportesService(sesion)

    if reporte == "tablero":
        contenido = exportacion_service.exportar_tablero(servicio.tablero(filtros))
    elif reporte == "cumplimiento":
        contenido = exportacion_service.exportar_cumplimiento(servicio.cumplimiento(filtros))
    elif reporte == "venta-diaria":
        contenido = exportacion_service.exportar_venta_diaria(servicio.venta_diaria(filtros))
    elif reporte == "clientes":
        contenido = exportacion_service.exportar_clientes(servicio.clientes(filtros, por))
    else:
        raise ErrorNoEncontrado(f"No existe el reporte {reporte!r}.")

    nombre = f"sigrep-{reporte}-{periodo}.xlsx"
    return Response(
        content=contenido,
        media_type=TIPO_XLSX,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
