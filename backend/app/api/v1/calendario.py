"""Endpoints del calendario de días hábiles (`docs/API.md`).

Una zona **no es** un punto de venta: agrupa puntos de varios responsables
(`BUCARAMANGA Y CENTRO` cubre 412 y 414, de grupos distintos). De ahí las dos
reglas de este router:

- En lectura, un JEFE_PDV ve el calendario de las zonas donde tiene puntos, no
  el de la compañía. Los días hábiles son la vara con la que se calcula el
  ideal de cada punto, y la de una zona ajena no es asunto suyo.
- En escritura, quien parametriza una zona está fijando el ideal de todos sus
  puntos. Eso solo lo hace quien tiene alcance sobre la compañía entera.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.v1 import AnalistaDep, LecturaDep
from app.application.services.calendario_service import CalendarioService
from app.core.deps import SesionDep, alcance_escritura, alcance_puntos_venta
from app.core.errors import ErrorAutorizacion
from app.infrastructure.models.organizacion import PuntoVenta
from app.schemas.calendario import CalendarioEntrada, CalendarioSalida

router = APIRouter(prefix="/calendario", tags=["Calendario"])

PeriodoQuery = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", examples=["2026-08"])


@router.get("", response_model=list[CalendarioSalida], summary="Días hábiles por zona")
def listar(
    usuario: LecturaDep,
    sesion: SesionDep,
    periodo: str = PeriodoQuery,
    hasta: date | None = None,
) -> list[CalendarioSalida]:
    """RBAC: cualquier rol autenticado; JEFE_PDV solo ve las zonas de sus puntos."""
    zonas = CalendarioService(sesion).listar(periodo, hasta)

    alcance = alcance_puntos_venta(usuario)
    if alcance is None:
        return zonas

    permitidas = set(
        sesion.execute(
            select(PuntoVenta.zona_id).where(PuntoVenta.id.in_(alcance or [-1]))
        ).scalars()
    )
    return [zona for zona in zonas if zona.zona_id in permitidas]


@router.put("/{zona_id}", response_model=CalendarioSalida, summary="Parametrizar una zona")
def actualizar(
    zona_id: int,
    datos: CalendarioEntrada,
    usuario: AnalistaDep,
    sesion: SesionDep,
    periodo: str = PeriodoQuery,
    hasta: date | None = None,
) -> CalendarioSalida:
    """RBAC: ANALISTA (y GERENTE), y solo con alcance sobre toda la compañía.

    `dias_trabajados` nulo devuelve la zona al cálculo derivado de la fecha de
    corte; un valor explícito es una afirmación del usuario y manda.

    Una zona agrupa puntos de venta de varios responsables, así que no hay
    forma de «parametrizar solo la parte propia» de una zona: o se tiene
    alcance sobre toda la compañía o no se toca.
    """
    if alcance_escritura(usuario) is not None:
        raise ErrorAutorizacion(
            "El calendario de una zona fija el ideal de todos sus puntos de venta, que son "
            "de varios responsables. Solo se parametriza con alcance sobre toda la compañía."
        )

    return CalendarioService(sesion).actualizar(
        zona_id,
        periodo,
        datos.dias_habiles,
        datos.dias_trabajados,
        usuario_id=usuario.id,
        hasta=hasta,
    )
