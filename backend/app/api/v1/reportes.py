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

#: `punto_venta` admite **varios códigos separados por coma**. Es el mismo
#: control de la misma barra de filtros en las cuatro pantallas, así que se
#: declara una vez y se reutiliza: que un reporte lo entendiera distinto que
#: otro sería exactamente la incoherencia que este parámetro viene a evitar.
PuntoVentaQuery = Query(
    default=None,
    description=(
        "Código C.O., o **varios separados por coma** (`402,405,603`). "
        "Estrecha el reporte; nunca amplía el alcance de quien consulta."
    ),
    examples=["405", "402,405,603"],
)

DesdeQuery = Query(
    default=None,
    description=(
        "Solo en venta diaria: primer día del rango. Sin él manda `periodo` y "
        "el reporte va del día 1 a la fecha de corte, como siempre."
    ),
    examples=["2026-07-25"],
)


def _puntos_venta(valor: str | None) -> tuple[str, ...] | None:
    """`"402, 405,,603"` → `("402", "405", "603")`.

    Tres decisiones pequeñas y deliberadas:

    - **Los vacíos se descartan.** `?punto_venta=` y `?punto_venta=,,` se
      comportan como no enviar el filtro, que es lo que hacían antes de admitir
      la lista: una barra de filtros que se vacía no puede acabar pidiendo el
      punto de venta de código «».
    - **Se quitan los repetidos** conservando el orden. Pedir `402,402` no es
      pedir MALAMBO dos veces.
    - **No se valida que los códigos existan.** Un código inventado
      sencillamente no casa con ninguna fila, igual que hoy. Fallar aquí
      convertiría el filtro en un validador de catálogo y le diría, a quien no
      tiene alcance sobre un punto, si ese punto existe o no.
    """
    if not valor:
        return None
    codigos = list(dict.fromkeys(parte.strip() for parte in valor.split(",") if parte.strip()))
    return tuple(codigos) or None


def _filtros(
    usuario: LecturaDep,
    periodo: str,
    hasta: date | None,
    grupo: str | None,
    punto_venta: str | None,
    categoria: str | None,
    medida: Medida,
    desde: date | None = None,
) -> FiltrosReporte:
    return FiltrosReporte(
        periodo=periodo,
        hasta=hasta,
        grupo=grupo,
        puntos_venta=_puntos_venta(punto_venta),
        categoria=categoria,
        medida=medida,
        alcance=alcance_puntos_venta(usuario),
        desde=desde,
    )


@router.get("/tablero", response_model=RespuestaTablero, summary="Tablero gerencial")
def tablero(
    usuario: LecturaDep,
    sesion: SesionDep,
    periodo: str = PeriodoQuery,
    hasta: date | None = None,
    grupo: str | None = None,
    punto_venta: str | None = PuntoVentaQuery,
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
    punto_venta: str | None = PuntoVentaQuery,
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
    desde: date | None = DesdeQuery,
    grupo: str | None = None,
    punto_venta: str | None = PuntoVentaQuery,
    categoria: str | None = None,
    medida: Medida = Medida.VALOR,
) -> RespuestaVentaDiaria:
    """RBAC: cualquier rol autenticado; JEFE_PDV solo ve sus puntos.

    Con `desde`, `hasta` deja de ser la fecha de corte del mes y pasa a ser el
    último día del rango; sin él, todo se comporta como siempre. El rango se
    valida en el servicio —invertido o desmedido se rechazan con su motivo—
    porque es una regla del reporte y no de la frontera HTTP: la misma regla
    tiene que valer cuando el rango llega por la exportación.
    """
    return ReportesService(sesion).venta_diaria(
        _filtros(usuario, periodo, hasta, grupo, punto_venta, categoria, medida, desde)
    )


@router.get("/clientes", response_model=RespuestaClientes, summary="Clientes y vendedores")
def clientes(
    usuario: LecturaDep,
    sesion: SesionDep,
    periodo: str = PeriodoQuery,
    hasta: date | None = None,
    grupo: str | None = None,
    punto_venta: str | None = PuntoVentaQuery,
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
    desde: date | None = DesdeQuery,
    grupo: str | None = None,
    punto_venta: str | None = PuntoVentaQuery,
    categoria: str | None = None,
    medida: Medida = Medida.VALOR,
    por: AgrupacionClientes = AgrupacionClientes.CLIENTE,
) -> Response:
    """RBAC: cualquier rol autenticado; JEFE_PDV solo ve sus puntos.

    Exporta **lo mismo que muestra la pantalla**, con los mismos filtros y a
    partir de la misma respuesta ya calculada. `desde` incluido: exportar un
    rango que la pantalla no puede exportar sería otra manera de tener dos
    verdades.
    """
    from app.core.errors import ErrorNoEncontrado

    filtros = _filtros(usuario, periodo, hasta, grupo, punto_venta, categoria, medida, desde)
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
