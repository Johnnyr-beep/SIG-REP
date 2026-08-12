"""Esquemas del calendario de días hábiles (`docs/API.md`)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import DecimalStr, EsquemaBase


class CalendarioSalida(EsquemaBase):
    """Parámetros de una zona en un período.

    `dias_habiles` y `dias_trabajados` son decimales con un decimal (`"27.5"`):
    los días admiten media jornada (§3.2). `derivado` dice si los trabajados los
    calculó el sistema o los escribió el usuario, porque de eso depende si un
    cambio de fecha de corte los va a mover.
    """

    zona_id: int
    zona: str
    dias_habiles: DecimalStr
    dias_trabajados: DecimalStr | None = None
    ideal: DecimalStr | None = None
    fecha_corte: date | None = None
    derivado: bool = True


class CalendarioEntrada(BaseModel):
    """`dias_trabajados` nulo significa **derivado** de la fecha de corte."""

    dias_habiles: Decimal = Field(gt=0, le=31, max_digits=5, decimal_places=2)
    dias_trabajados: Decimal | None = Field(default=None, ge=0, le=31, max_digits=5)
