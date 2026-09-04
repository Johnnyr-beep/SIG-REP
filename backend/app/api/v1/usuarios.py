"""Administración de usuarios (`docs/API.md`, sección Usuarios).

Todos los endpoints de este router llevan `AdministracionDep`: **solo ADMIN**.
Es la única familia de rutas de la que GERENTE queda fuera, y ese es el punto —
quien reparte las llaves y quien mira dentro de la caja son cargos distintos—.

No existe `DELETE /usuarios/{id}` y no es un olvido: las acciones de un usuario
están referenciadas desde `presupuesto_historial` y `corridas_ingesta`, así que
las cuentas se desactivan (§3.3). Ver `UsuariosService.desactivar`.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request, status
from pydantic import BaseModel, Field

from app.api.v1 import AdministracionDep
from app.application.services.usuarios_service import UsuariosService
from app.core.deps import SesionDep, obtener_ip
from app.domain.enums import Rol
from app.schemas.usuarios import (
    AlcanceEntrada,
    AuditoriaSalida,
    ClaveProvisional,
    PermisoSalida,
    UsuarioCreado,
    UsuarioModificacion,
    UsuarioNuevo,
    UsuarioSalida,
)


class PermisoEntrada(BaseModel):
    codigo: str = Field(min_length=1, max_length=80)

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])


def _servicio(sesion: SesionDep, actor: AdministracionDep, request: Request) -> UsuariosService:
    """El servicio siempre sabe quién administra y desde dónde.

    La IP entra en el rastro de auditoría porque «quién» no siempre basta: una
    cuenta de Sistemas usada desde una dirección que no es la de la oficina es
    justo lo que una auditoría busca.
    """
    return UsuariosService(sesion, actor, ip_origen=obtener_ip(request))


@router.get("", response_model=list[UsuarioSalida], summary="Listar usuarios")
def listar(
    actor: AdministracionDep,
    sesion: SesionDep,
    request: Request,
    rol: Rol | None = None,
    activo: bool | None = Query(default=None, description="Sin indicar: activos e inactivos"),
) -> list[UsuarioSalida]:
    """RBAC: ADMIN. Devuelve rol, estado, último acceso y alcance de cada cuenta.

    Nunca devuelve el hash de la contraseña: `UsuarioSalida` no tiene ese campo.
    """
    return _servicio(sesion, actor, request).listar(rol=rol, activo=activo)


@router.get("/auditoria", response_model=list[AuditoriaSalida], summary="Rastro de administración")
def auditoria(
    actor: AdministracionDep,
    sesion: SesionDep,
    request: Request,
    usuario_id: int | None = None,
    limite: int = Query(default=100, ge=1, le=500),
) -> list[AuditoriaSalida]:
    """RBAC: ADMIN. Quién hizo qué, sobre quién y cuándo.

    La ruta se declara **antes** que cualquier `/{usuario_id}` a propósito:
    FastAPI resuelve por orden de declaración y el día que alguien añada un
    `GET /usuarios/{usuario_id}` por debajo, `/usuarios/auditoria` empezaría a
    entrar por ahí y devolvería un 422 pidiendo un entero. Es el clásico que no
    lo detecta ningún tipo y solo aparece en runtime.

    Nunca contiene claves: `RESTABLECER_CLAVE` deja constancia de que se
    restableció, no de qué se puso.
    """
    return _servicio(sesion, actor, request).auditoria(usuario_id=usuario_id, limite=limite)


@router.post(
    "",
    response_model=UsuarioCreado,
    status_code=status.HTTP_201_CREATED,
    summary="Crear usuario",
)
def crear(
    datos: UsuarioNuevo, actor: AdministracionDep, sesion: SesionDep, request: Request
) -> UsuarioCreado:
    """RBAC: ADMIN. Devuelve la clave provisional **una sola vez**.

    La clave la genera el servidor —no se envía en la petición—, se almacena
    solo como hash Argon2id y no vuelve a aparecer en ninguna otra respuesta ni
    en ningún log. Si el administrador la pierde antes de entregarla, el remedio
    es `POST /usuarios/{id}/restablecer-clave`, que genera otra.
    """
    usuario, clave = _servicio(sesion, actor, request).crear(datos)
    return UsuarioCreado(usuario=usuario, clave_provisional=clave)


@router.patch("/{usuario_id}", response_model=UsuarioSalida, summary="Modificar usuario")
def modificar(
    usuario_id: int,
    datos: UsuarioModificacion,
    actor: AdministracionDep,
    sesion: SesionDep,
    request: Request,
) -> UsuarioSalida:
    """RBAC: ADMIN, y **nunca sobre su propia cuenta** (403 `sin_autoadministracion`).

    409 `ultimo_admin_activo` si el cambio de rol dejaría el sistema sin ningún
    administrador activo.
    """
    return _servicio(sesion, actor, request).modificar(usuario_id, datos)


@router.put(
    "/{usuario_id}/puntos-venta",
    response_model=UsuarioSalida,
    summary="Fijar el alcance por punto de venta",
)
def fijar_alcance(
    usuario_id: int,
    datos: AlcanceEntrada,
    actor: AdministracionDep,
    sesion: SesionDep,
    request: Request,
) -> UsuarioSalida:
    """RBAC: ADMIN, y nunca sobre su propia cuenta.

    **Reemplaza** el alcance completo: lo que se envía es lo que queda. Asignar
    es mandar la lista con el código de más; quitar, mandarla con el código de
    menos; y `{"puntos_venta": []}` deja al usuario sin ninguno.
    """
    return _servicio(sesion, actor, request).fijar_alcance(usuario_id, datos)


@router.post("/{usuario_id}/permisos", response_model=UsuarioSalida, summary="Asignar permiso")
def asignar_permiso(
    usuario_id: int,
    datos: PermisoEntrada,
    actor: AdministracionDep,
    sesion: SesionDep,
    request: Request,
) -> UsuarioSalida:
    return _servicio(sesion, actor, request).asignar_permiso(usuario_id, datos.codigo)


@router.get("/{usuario_id}/permisos", response_model=list[PermisoSalida], summary="Listar permisos")
def listar_permisos(
    usuario_id: int,
    actor: AdministracionDep,
    sesion: SesionDep,
    request: Request,
) -> list[PermisoSalida]:
    return _servicio(sesion, actor, request).listar_permisos(usuario_id)


@router.delete(
    "/{usuario_id}/permisos/{codigo}",
    response_model=UsuarioSalida,
    summary="Retirar permiso",
)
def retirar_permiso(
    usuario_id: int,
    codigo: str,
    actor: AdministracionDep,
    sesion: SesionDep,
    request: Request,
) -> UsuarioSalida:
    return _servicio(sesion, actor, request).retirar_permiso(usuario_id, codigo)


@router.post("/{usuario_id}/activar", response_model=UsuarioSalida, summary="Activar usuario")
def activar(
    usuario_id: int, actor: AdministracionDep, sesion: SesionDep, request: Request
) -> UsuarioSalida:
    """RBAC: ADMIN, y nunca sobre su propia cuenta.

    Levanta además el bloqueo temporal por intentos fallidos, si lo hubiera.
    """
    return _servicio(sesion, actor, request).activar(usuario_id)


@router.post("/{usuario_id}/desactivar", response_model=UsuarioSalida, summary="Desactivar usuario")
def desactivar(
    usuario_id: int, actor: AdministracionDep, sesion: SesionDep, request: Request
) -> UsuarioSalida:
    """RBAC: ADMIN, y nunca sobre su propia cuenta.

    Es la baja: **no hay borrado**. 409 `ultimo_admin_activo` si dejaría el
    sistema sin ningún administrador activo.
    """
    return _servicio(sesion, actor, request).desactivar(usuario_id)


@router.post(
    "/{usuario_id}/restablecer-clave",
    response_model=ClaveProvisional,
    summary="Restablecer la clave",
)
def restablecer_clave(
    usuario_id: int, actor: AdministracionDep, sesion: SesionDep, request: Request
) -> ClaveProvisional:
    """RBAC: ADMIN, y nunca sobre su propia cuenta.

    Genera otra clave provisional, la muestra **una sola vez** y obliga a
    cambiarla en el siguiente acceso. Levanta el bloqueo por intentos fallidos:
    quien pide un restablecimiento suele haberse bloqueado intentando entrar.
    """
    usuario, clave = _servicio(sesion, actor, request).restablecer_clave(usuario_id)
    return ClaveProvisional(id=usuario.id, usuario=usuario.usuario, clave_provisional=clave)
