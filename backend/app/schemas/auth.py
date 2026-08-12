"""Esquemas de autenticación (`docs/API.md`, sección Autenticación)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.enums import Rol
from app.schemas.common import EsquemaBase


class SolicitudAcceso(BaseModel):
    usuario: str = Field(min_length=3, max_length=50)
    clave: str = Field(min_length=1, max_length=200)


class SolicitudRefresco(BaseModel):
    token_refresco: str


class RespuestaAcceso(BaseModel):
    """Par de tokens emitido tras un acceso válido."""

    token_acceso: str
    token_refresco: str
    tipo: str = "bearer"
    expira_en: int = Field(description="Vigencia del token de acceso en segundos")


class RespuestaRefresco(BaseModel):
    token_acceso: str
    tipo: str = "bearer"
    expira_en: int


class PerfilUsuario(EsquemaBase):
    """Lo que devuelve `GET /auth/yo`.

    `puntos_venta` son los **códigos C.O.** de los puntos a los que el usuario
    tiene alcance, en el mismo formato con el que el frontend filtra los
    reportes (`?punto_venta=405`). Lista vacía en los roles que ven todo.
    """

    id: int
    usuario: str
    nombre: str
    rol: Rol
    puntos_venta: list[str] = Field(default_factory=list)


class CambioClave(BaseModel):
    clave_actual: str = Field(min_length=1, max_length=200)
    clave_nueva: str = Field(min_length=12, max_length=200)
