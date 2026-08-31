"""Esquemas de la ingesta (`docs/API.md`, sección Ingesta).

Los esquemas están **completos y son estables**. La lógica que hay detrás no:
el servicio se detiene en `NotImplementedError` a la espera de que el agente de
ingesta la construya sobre el puerto `FuenteVenta` de `app/domain/puertos.py`
(§5). Esto es deliberado: el frontend puede integrarse contra un contrato firme
mientras la implementación llega.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from app.domain.enums import EstadoCorrida, FuenteIngesta
from app.schemas.common import EsquemaBase


class SolicitudIngesta(BaseModel):
    desde: date
    hasta: date
    fuente: FuenteIngesta = FuenteIngesta.EXCEL

    @model_validator(mode="after")
    def _rango_coherente(self) -> SolicitudIngesta:
        if self.hasta < self.desde:
            raise ValueError("La fecha final no puede ser anterior a la inicial.")
        return self


class CorridaSalida(EsquemaBase):
    id: int
    cuando: datetime
    quien: str | None = None
    fuente: str
    desde: date | None = None
    hasta: date | None = None
    estado: EstadoCorrida
    filas_leidas: int
    aceptadas: int
    rechazadas: int
    duracion_ms: int | None = None
    mensaje: str | None = None


class RechazoSalida(EsquemaBase):
    fila: int | None = None
    campo: str | None = None
    valor: str | None = None
    motivo: str = Field(description="Por qué no se pudo aceptar la fila")
