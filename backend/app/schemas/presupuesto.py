"""Esquemas de presupuesto, historial y períodos (`docs/API.md`)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import DecimalStr, EsquemaBase


class PresupuestoSalida(EsquemaBase):
    punto_venta: str = Field(description="Código C.O.")
    categoria: str
    monto: DecimalStr
    kilos: DecimalStr
    actualizado_en: datetime
    actualizado_por: str | None = None


class PresupuestoEntrada(BaseModel):
    """Alta o modificación de un presupuesto.

    `motivo` es obligatorio y no admite una palabra suelta: todo cambio de
    presupuesto queda con autor, fecha y motivo (§7), y «ajuste» no es un
    motivo que sirva para evaluar a nadie seis meses después.
    """

    periodo: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", examples=["2026-08"])
    punto_venta_id: int
    categoria_id: int
    monto: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    kilos: Decimal = Field(ge=0, max_digits=18, decimal_places=3)
    motivo: str = Field(min_length=5, max_length=400)


class ErrorFila(BaseModel):
    fila: int
    motivo: str


class ResultadoCargaMasiva(BaseModel):
    aceptadas: int
    rechazadas: int
    errores: list[ErrorFila] = Field(default_factory=list)


class HistorialSalida(EsquemaBase):
    cuando: datetime
    quien: str | None = None
    campo: str
    valor_anterior: DecimalStr | None = None
    valor_nuevo: DecimalStr | None = None
    motivo: str


class PeriodoSalida(EsquemaBase):
    periodo: str
    cerrado: bool
    cerrado_por: str | None = None
    cerrado_en: datetime | None = None
