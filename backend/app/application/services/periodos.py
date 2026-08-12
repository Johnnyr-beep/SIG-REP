"""Resolución de períodos `YYYY-MM`.

Vive aparte porque lo necesitan el calendario, el presupuesto y los reportes, y
porque convertir «2026-08» en una fila de `periodos` es la clase de detalle que,
repetido en tres servicios, acaba divergiendo.
"""

from __future__ import annotations

import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ErrorNoEncontrado, ErrorValidacion
from app.infrastructure.models.periodo import Periodo

_PATRON_PERIODO = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def parsear_periodo(codigo: str) -> tuple[int, int]:
    """«2026-08» → `(2026, 8)`. Lanza `ErrorValidacion` si no encaja."""
    coincidencia = _PATRON_PERIODO.match(codigo.strip())
    if coincidencia is None:
        raise ErrorValidacion(f"Período inválido: {codigo!r}. Se espera el formato YYYY-MM.")
    return int(coincidencia.group(1)), int(coincidencia.group(2))


def buscar_periodo(sesion: Session, codigo: str) -> Periodo | None:
    """Devuelve el período o `None`. No lo crea."""
    anio, mes = parsear_periodo(codigo)
    return sesion.execute(
        select(Periodo).where(Periodo.anio == anio, Periodo.mes == mes)
    ).scalar_one_or_none()


def obtener_periodo(sesion: Session, codigo: str) -> Periodo:
    """Devuelve el período o falla con 404."""
    periodo = buscar_periodo(sesion, codigo)
    if periodo is None:
        raise ErrorNoEncontrado(f"El período {codigo} no está abierto en el sistema.")
    return periodo


def obtener_o_crear_periodo(sesion: Session, codigo: str) -> Periodo:
    """Abre el período si aún no existe.

    Se crean bajo demanda —al parametrizar el primer presupuesto o el primer
    calendario— en lugar de sembrar años completos por adelantado: un período
    vacío en la lista es ruido que induce a pensar que hay algo que mirar.
    """
    periodo = buscar_periodo(sesion, codigo)
    if periodo is not None:
        return periodo

    anio, mes = parsear_periodo(codigo)
    periodo = Periodo(anio=anio, mes=mes, cerrado=False)
    sesion.add(periodo)
    sesion.flush()
    return periodo


def periodo_anterior(codigo: str) -> str:
    """Mismo mes del año anterior, para el indicador de crecimiento (§4.3)."""
    anio, mes = parsear_periodo(codigo)
    return f"{anio - 1:04d}-{mes:02d}"


def fecha_corte_efectiva(periodo: Periodo, hasta: date | None) -> date:
    """Fecha de corte saneada contra el período.

    Sin `hasta` se toma hoy. Y se satura contra el mes del período: un corte
    heredado de otro período —el caso clásico del usuario que deja el filtro de
    ayer y cambia de mes— produciría un ideal absurdo. Al saturar, consultar un
    mes ya cerrado devuelve el mes completo, que es lo que cualquiera espera.
    """
    from app.domain.calendario import dias_del_mes

    ultimo_dia = date(periodo.anio, periodo.mes, dias_del_mes(periodo.anio, periodo.mes))
    corte = hasta or date.today()
    if corte < periodo.primer_dia:
        return periodo.primer_dia
    return min(corte, ultimo_dia)
