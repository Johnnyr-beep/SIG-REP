"""Primitivas de seguridad: hashing de contraseñas y emisión/verificación de JWT.

Portado de GSC ONE. Decisiones:
- Argon2id como función de derivación (ganadora del Password Hashing Competition
  y recomendación actual de OWASP), no bcrypt ni SHA.
- Tokens de acceso cortos + refresco separado, con `tipo` embebido para que un
  token de refresco nunca sea aceptado como token de acceso.
- `jti` en cada token para permitir revocación futura sin cambiar el contrato.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from jose import JWTError, jwt

from app.core.config import obtener_settings
from app.core.errors import ErrorAutenticacion

TipoToken = Literal["acceso", "refresco"]

#: Emisor de los tokens. Va firmado y se verifica al decodificar, de modo que un
#: token de GSC ONE no vale en SIGREP aunque compartieran la clave.
EMISOR = "sigrep"

# Parámetros conforme a OWASP Password Storage Cheat Sheet (perfil equilibrado).
_hasher = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=4)


# ── Contraseñas ───────────────────────────────────────────────────────────────


def hashear_password(password: str) -> str:
    """Deriva el hash Argon2id de una contraseña en claro."""
    return _hasher.hash(password)


def verificar_password(password: str, hash_almacenado: str) -> bool:
    """Compara en tiempo constante. Nunca lanza por hash corrupto."""
    try:
        return _hasher.verify(hash_almacenado, password)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def requiere_rehash(hash_almacenado: str) -> bool:
    """True si el hash usa parámetros obsoletos y conviene recalcularlo."""
    try:
        return _hasher.check_needs_rehash(hash_almacenado)
    except (InvalidHashError, ValueError):
        return True


def generar_password_temporal(longitud: int = 16) -> str:
    """Contraseña aleatoria criptográficamente segura para altas de usuario."""
    return secrets.token_urlsafe(longitud)


# ── Tokens ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class DatosToken:
    """Contenido verificado de un JWT."""

    usuario_id: int
    usuario: str
    rol: str
    tipo: TipoToken
    jti: str
    #: Unidad de negocio contra cuya base se autentico este token, y la unica
    #: cuya base va a poder leer. Es el mecanismo que separa a las dos
    #: companias: no es una preferencia que el cliente pueda cambiar mandando
    #: otra cabecera, porque va firmada dentro del token.
    #:
    #: Los tokens emitidos antes de este campo lo traen vacio y se leen como
    #: `carnes`, que es contra lo que se autenticaron: una sesion abierta no
    #: tiene por que caerse al desplegar.
    unidad: str = "carnes"


def _crear_token(
    *,
    usuario_id: int,
    usuario: str,
    rol: str,
    tipo: TipoToken,
    expira_en: timedelta,
    unidad: str = "carnes",
) -> str:
    settings = obtener_settings()
    ahora = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(usuario_id),
        "usuario": usuario,
        "rol": rol,
        "unidad": unidad,
        "tipo": tipo,
        "jti": str(uuid.uuid4()),
        "iat": int(ahora.timestamp()),
        "exp": int((ahora + expira_en).timestamp()),
        "iss": EMISOR,
    }
    return jwt.encode(
        payload,
        settings.secret_key.get_secret_value(),
        algorithm=settings.jwt_algoritmo,
    )


def crear_token_acceso(usuario_id: int, usuario: str, rol: str, unidad: str = "carnes") -> str:
    settings = obtener_settings()
    return _crear_token(
        usuario_id=usuario_id,
        usuario=usuario,
        rol=rol,
        unidad=unidad,
        tipo="acceso",
        expira_en=timedelta(minutes=settings.access_token_minutos),
    )


def crear_token_refresco(usuario_id: int, usuario: str, rol: str, unidad: str = "carnes") -> str:
    settings = obtener_settings()
    return _crear_token(
        usuario_id=usuario_id,
        usuario=usuario,
        rol=rol,
        unidad=unidad,
        tipo="refresco",
        expira_en=timedelta(days=settings.refresh_token_dias),
    )


def decodificar_token(token: str, *, tipo_esperado: TipoToken = "acceso") -> DatosToken:
    """Verifica firma, vigencia y tipo. Lanza `ErrorAutenticacion` si falla."""
    settings = obtener_settings()
    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.jwt_algoritmo],
            issuer=EMISOR,
        )
    except JWTError as exc:
        raise ErrorAutenticacion("Token inválido o expirado.") from exc

    if payload.get("tipo") != tipo_esperado:
        raise ErrorAutenticacion("El tipo de token no corresponde a esta operación.")

    subject = payload.get("sub")
    if subject is None:
        raise ErrorAutenticacion("Token sin sujeto.")

    try:
        usuario_id = int(subject)
    except (TypeError, ValueError) as exc:
        raise ErrorAutenticacion("Token con sujeto malformado.") from exc

    return DatosToken(
        usuario_id=usuario_id,
        usuario=str(payload.get("usuario", "")),
        rol=str(payload.get("rol", "")),
        unidad=str(payload.get("unidad") or "carnes"),
        tipo=tipo_esperado,
        jti=str(payload.get("jti", "")),
    )
