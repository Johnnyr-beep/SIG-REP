"""Esquemas de catálogos (`docs/API.md`, sección Catálogos)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import EsquemaBase


class GrupoSalida(EsquemaBase):
    id: int
    codigo: str
    nombre: str


class PuntoVentaSalida(EsquemaBase):
    id: int
    codigo_co: str
    nombre: str
    grupo: str | None = None
    zona: str | None = None
    activo: bool
    #: `False` para 432 EVENTOS BUCARAMANGA: vende y no se presupuesta (§3.1).
    presupuestado: bool


class CategoriaSalida(EsquemaBase):
    id: int
    codigo: str
    nombre: str
    orden: int


class ZonaSalida(EsquemaBase):
    id: int
    nombre: str
    #: Códigos C.O. de los puntos que comparten este calendario.
    puntos_venta: list[str] = Field(default_factory=list)


class MapeoCategoriaSalida(EsquemaBase):
    """Traducción de una categoría cruda de SIESA a categoría de negocio."""

    texto_siesa: str
    categoria: str


class MapeoCategoriaEntrada(BaseModel):
    """Alta o reclasificación de un mapeo.

    El texto se compara **exacto**: las dos variantes de `0006 - QUESO(S) Y
    LACTEOS` son dos filas distintas y así debe seguir siendo.
    """

    texto_siesa: str = Field(min_length=1, max_length=120)
    categoria: str = Field(min_length=1, max_length=40, description="Nombre de categoría SIGREP")
