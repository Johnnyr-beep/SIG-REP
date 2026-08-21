"""Autenticación, bloqueo de cuentas y gestión de usuarios.

Portado de GSC ONE. Se conserva íntegra la defensa contra fuerza bruta y la
política de contraseñas; se simplifica el modelo de roles a uno por usuario,
que es lo que declara `docs/API.md`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import obtener_settings
from app.core.errors import ErrorAutenticacion, ErrorConflicto, ErrorNoEncontrado, ErrorValidacion
from app.core.logging import obtener_logger
from app.core.security import (
    crear_token_acceso,
    crear_token_refresco,
    decodificar_token,
    hashear_password,
    requiere_rehash,
    verificar_password,
)
from app.domain.enums import Rol
from app.infrastructure.models.mixins import ahora_utc
from app.infrastructure.models.organizacion import PuntoVenta
from app.infrastructure.models.usuario import IntentoAcceso, Usuario, UsuarioPuntoVenta

logger = obtener_logger(__name__)

#: Longitud mínima de contraseña. OWASP ASVS 2.1.1 exige 12 para cuentas de
#: aplicaciones de negocio.
LONGITUD_MINIMA_CLAVE = 12


@dataclass(frozen=True, slots=True)
class Credenciales:
    """Par de tokens emitido tras un acceso válido."""

    token_acceso: str
    token_refresco: str
    expira_en: int
    tipo: str = "bearer"


class AuthService:
    """Casos de uso de identidad."""

    def __init__(self, sesion: Session, unidad: str = "carnes") -> None:
        self._sesion = sesion
        self._settings = obtener_settings()
        # La unidad de la sesión que llega, no una elección del servicio: quien
        # la resolvió fue la dependencia, y aquí solo se sella en el token para
        # que las siguientes peticiones vuelvan a la misma base sin depender de
        # que el cliente lo recuerde.
        self._unidad = unidad

    # ── Autenticación ─────────────────────────────────────────────────────────

    def autenticar(
        self,
        usuario_nombre: str,
        clave: str,
        *,
        ip_origen: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[Usuario, Credenciales]:
        """Valida credenciales y emite tokens.

        El mensaje de error es idéntico para «usuario inexistente» y «clave
        incorrecta»: revelar cuál de los dos falló permite enumerar usuarios
        válidos (OWASP A07).
        """
        usuario = self._sesion.execute(
            select(Usuario).where(Usuario.usuario == usuario_nombre)
        ).scalar_one_or_none()

        if usuario is None:
            # Se gasta el mismo tiempo que en una verificación real para no
            # filtrar la existencia del usuario por diferencia de latencia.
            verificar_password(clave, _HASH_SEÑUELO)
            self._registrar_intento(
                usuario_nombre, False, ip_origen, user_agent, "usuario_inexistente"
            )
            raise ErrorAutenticacion("Usuario o clave incorrectos.")

        if usuario.esta_bloqueado:
            self._registrar_intento(
                usuario_nombre, False, ip_origen, user_agent, "cuenta_bloqueada"
            )
            raise ErrorAutenticacion(
                "La cuenta está bloqueada temporalmente por intentos fallidos. "
                f"Reintente en {self._settings.minutos_bloqueo_cuenta} minutos."
            )

        if not usuario.activo:
            self._registrar_intento(usuario_nombre, False, ip_origen, user_agent, "cuenta_inactiva")
            raise ErrorAutenticacion("La cuenta está desactivada. Contacte al administrador.")

        if not verificar_password(clave, usuario.password_hash):
            self._contar_fallo(usuario)
            self._registrar_intento(
                usuario_nombre, False, ip_origen, user_agent, "clave_incorrecta"
            )
            raise ErrorAutenticacion("Usuario o clave incorrectos.")

        # Éxito: se limpia el contador y se actualiza el hash si envejeció.
        usuario.intentos_fallidos = 0
        usuario.bloqueado_hasta = None
        usuario.ultimo_acceso = ahora_utc()
        if requiere_rehash(usuario.password_hash):
            usuario.password_hash = hashear_password(clave)

        self._registrar_intento(usuario_nombre, True, ip_origen, user_agent, None)
        self._sesion.flush()

        logger.info("acceso_exitoso", usuario=usuario.usuario, rol=usuario.rol)
        return usuario, self._emitir_credenciales(usuario)

    def refrescar(self, token_refresco: str) -> Credenciales:
        """Emite un nuevo par de tokens a partir de un refresco válido.

        La unidad sale del **token que se presenta**, no de la petición: renovar
        no puede cambiar de compañía. Si saliera de la cabecera, un refresco de
        carnes serviría para obtener un acceso a agropecuaria, que es justo lo
        que la separación impide.
        """
        datos = decodificar_token(token_refresco, tipo_esperado="refresco")
        usuario = self._sesion.get(Usuario, datos.usuario_id)

        if usuario is None or not usuario.activo:
            raise ErrorAutenticacion("La cuenta ya no está habilitada.")

        return self._emitir_credenciales(usuario, unidad=datos.unidad)

    def _emitir_credenciales(self, usuario: Usuario, unidad: str | None = None) -> Credenciales:
        sello = unidad or self._unidad
        return Credenciales(
            token_acceso=crear_token_acceso(usuario.id, usuario.usuario, usuario.rol, sello),
            token_refresco=crear_token_refresco(usuario.id, usuario.usuario, usuario.rol, sello),
            expira_en=self._settings.access_token_minutos * 60,
        )

    def _contar_fallo(self, usuario: Usuario) -> None:
        usuario.intentos_fallidos += 1
        if usuario.intentos_fallidos >= self._settings.max_intentos_login:
            usuario.bloqueado_hasta = ahora_utc() + timedelta(
                minutes=self._settings.minutos_bloqueo_cuenta
            )
            logger.warning(
                "cuenta_bloqueada",
                usuario=usuario.usuario,
                intentos=usuario.intentos_fallidos,
            )
        self._sesion.flush()

    def _registrar_intento(
        self,
        usuario_nombre: str,
        exitoso: bool,
        ip: str | None,
        user_agent: str | None,
        motivo: str | None,
    ) -> None:
        self._sesion.add(
            IntentoAcceso(
                usuario=usuario_nombre[:50],
                exitoso=exitoso,
                ip_origen=ip,
                user_agent=(user_agent or "")[:300] or None,
                motivo=motivo,
            )
        )
        self._sesion.flush()

    # ── Gestión de usuarios ───────────────────────────────────────────────────

    def crear_usuario(
        self,
        *,
        usuario_nombre: str,
        nombre: str,
        clave: str,
        rol: Rol,
        email: str | None = None,
        codigos_punto_venta: list[str] | None = None,
    ) -> Usuario:
        """Alta de usuario con su rol y, si es JEFE_PDV, su alcance."""
        self.validar_fortaleza_clave(clave, usuario_nombre=usuario_nombre)

        existente = self._sesion.execute(
            select(Usuario).where(Usuario.usuario == usuario_nombre)
        ).scalar_one_or_none()
        if existente is not None:
            raise ErrorConflicto("Ya existe un usuario con ese nombre.")

        usuario = Usuario(
            usuario=usuario_nombre,
            nombre=nombre,
            email=email,
            rol=rol.value,
            password_hash=hashear_password(clave),
            debe_cambiar_password=True,
            activo=True,
        )
        self._sesion.add(usuario)
        self._sesion.flush()

        for codigo in codigos_punto_venta or []:
            punto = self._sesion.execute(
                select(PuntoVenta).where(PuntoVenta.codigo_co == codigo)
            ).scalar_one_or_none()
            if punto is None:
                raise ErrorNoEncontrado(f"No existe el punto de venta {codigo}.")
            self._sesion.add(UsuarioPuntoVenta(usuario_id=usuario.id, punto_venta_id=punto.id))
        self._sesion.flush()
        return usuario

    def cambiar_clave(self, usuario: Usuario, clave_actual: str, clave_nueva: str) -> None:
        """Cambio de clave por el propio usuario."""
        if not verificar_password(clave_actual, usuario.password_hash):
            raise ErrorAutenticacion("La clave actual no es correcta.")
        if clave_actual == clave_nueva:
            raise ErrorValidacion("La clave nueva debe ser distinta de la actual.")

        self.validar_fortaleza_clave(clave_nueva, usuario_nombre=usuario.usuario)

        usuario.password_hash = hashear_password(clave_nueva)
        usuario.debe_cambiar_password = False
        self._sesion.flush()

        logger.info("clave_cambiada", usuario=usuario.usuario)

    @staticmethod
    def validar_fortaleza_clave(clave: str, *, usuario_nombre: str | None = None) -> None:
        """Política de contraseñas alineada con OWASP ASVS 2.1."""
        if len(clave) < LONGITUD_MINIMA_CLAVE:
            raise ErrorValidacion(
                f"La clave debe tener al menos {LONGITUD_MINIMA_CLAVE} caracteres."
            )
        if clave.lower() == (usuario_nombre or "").lower():
            raise ErrorValidacion("La clave no puede ser igual al nombre de usuario.")
        clases = [
            any(c.islower() for c in clave),
            any(c.isupper() for c in clave),
            any(c.isdigit() for c in clave),
            any(not c.isalnum() for c in clave),
        ]
        if sum(clases) < 3:
            raise ErrorValidacion(
                "La clave debe combinar al menos tres de estos grupos: "
                "minúsculas, mayúsculas, dígitos y símbolos."
            )


#: Hash real de una clave aleatoria, usado como señuelo temporal.
_HASH_SEÑUELO = hashear_password("señuelo-para-igualar-tiempos-de-respuesta")
