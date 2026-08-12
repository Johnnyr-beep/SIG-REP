"""Esquemas y tipos transversales.

Aquí vive la decisión más importante del contrato: **los importes y las
cantidades viajan como `string`**.

    "presupuesto": "20000000000.00"

No es una manía. `Decimal` no sobrevive a un `float` de JavaScript: un
presupuesto de veinte mil millones con dos decimales necesita 14 cifras
significativas y `Number` de ECMAScript garantiza 15, de modo que basta un
céntimo más para que el frontend empiece a mostrar totales que no cuadran con
la base. El frontend formatea y nunca opera aritmética sobre estos campos.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

#: `Decimal` que se serializa como cadena. Se aplica al tipo interno, así que
#: `DecimalStr | None` sigue emitiendo `null` para lo indefinido, tal como pide
#: el contrato: «un indicador indefinido viaja como `null` y se pinta «—».
#: Nunca `0`».
DecimalStr = Annotated[Decimal, PlainSerializer(str, return_type=str, when_used="json")]


class EsquemaBase(BaseModel):
    """Base de todos los esquemas de salida."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class DetalleError(BaseModel):
    """Formato único de error de toda la API (`docs/API.md`)."""

    detalle: str = Field(description="Mensaje legible para el usuario final")
    codigo: str = Field(description="Código estable para que el frontend decida qué hacer")
    detalles: dict[str, object] = Field(default_factory=dict)


class Mensaje(BaseModel):
    """Respuesta simple de confirmación."""

    mensaje: str
