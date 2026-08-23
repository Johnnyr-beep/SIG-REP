"""Endpoints de autenticación (`docs/API.md`, sección Autenticación)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.application.services.auth_service import AuthService
from app.core.db import sesion_ambito
from app.core.deps import SesionDep, UnidadDep, UsuarioDep, obtener_ip, unidad_de_refresco
from app.domain.enums import Rol
from app.infrastructure.models.organizacion import PuntoVenta
from app.schemas.auth import (
    CambioClave,
    PerfilUsuario,
    RespuestaAcceso,
    RespuestaRefresco,
    SolicitudAcceso,
    SolicitudRefresco,
)
from app.schemas.common import Mensaje

router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.post("/acceso", response_model=RespuestaAcceso, summary="Iniciar sesión")
def acceso(
    datos: SolicitudAcceso, sesion: SesionDep, unidad: UnidadDep, request: Request
) -> RespuestaAcceso:
    """Valida credenciales y devuelve el par de tokens. Público.

    `sesion` ya viene de la base de `unidad` —lo resuelve la dependencia—, asi
    que las credenciales se comprueban contra la compania correcta. La unidad
    queda sellada en el token para que las siguientes peticiones vuelvan sola.
    """
    _, credenciales = AuthService(sesion, unidad).autenticar(
        datos.usuario,
        datos.clave,
        ip_origen=obtener_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return RespuestaAcceso(
        token_acceso=credenciales.token_acceso,
        token_refresco=credenciales.token_refresco,
        tipo=credenciales.tipo,
        expira_en=credenciales.expira_en,
    )


@router.post("/refrescar", response_model=RespuestaRefresco, summary="Renovar token de acceso")
def refrescar(datos: SolicitudRefresco) -> RespuestaRefresco:
    """Público: la autorización la da el propio token de refresco.

    **No usa `SesionDep`, y ese es el punto.** El refresco viaja en el cuerpo,
    no en `Authorization`, así que la dependencia de sesión no lo ve: resolvía
    la unidad por la cabecera —o por el valor por defecto— y renovaba una sesión
    de agropecuaria contra la base de carnes. Allí el mismo `id` de usuario es
    otra persona, de modo que la comprobación de «la cuenta sigue habilitada» se
    hacía sobre una cuenta ajena y el token salía a nombre de un desconocido:
    desactivar a alguien en su compañía no le cerraba la renovación, y un
    usuario cuyo `id` no existiera en carnes se quedaba sin poder renovar.

    Aquí la unidad se saca del propio refresco, que es donde va firmada, y la
    sesión se abre contra **esa** base.
    """
    with sesion_ambito(unidad_de_refresco(datos.token_refresco)) as sesion:
        credenciales = AuthService(sesion).refrescar(datos.token_refresco)
    return RespuestaRefresco(
        token_acceso=credenciales.token_acceso,
        tipo=credenciales.tipo,
        expira_en=credenciales.expira_en,
    )


@router.get("/yo", response_model=PerfilUsuario, summary="Perfil del usuario autenticado")
def perfil(usuario: UsuarioDep, sesion: SesionDep) -> PerfilUsuario:
    """Cualquier usuario autenticado, sea cual sea su rol."""
    codigos: list[str] = []
    if usuario.puntos_venta_ids:
        codigos = list(
            sesion.execute(
                select(PuntoVenta.codigo_co)
                .where(PuntoVenta.id.in_(usuario.puntos_venta_ids))
                .order_by(PuntoVenta.codigo_co)
            ).scalars()
        )
    return PerfilUsuario(
        id=usuario.id,
        usuario=usuario.usuario,
        nombre=usuario.nombre,
        rol=Rol(usuario.rol),
        puntos_venta=codigos,
        debe_cambiar_password=usuario.debe_cambiar_password,
    )


@router.post("/cambiar-clave", response_model=Mensaje, summary="Cambiar la clave propia")
def cambiar_clave(datos: CambioClave, usuario: UsuarioDep, sesion: SesionDep) -> Mensaje:
    """Cualquier usuario autenticado, sobre su propia cuenta."""
    AuthService(sesion).cambiar_clave(usuario, datos.clave_actual, datos.clave_nueva)
    return Mensaje(mensaje="Clave actualizada correctamente.")
