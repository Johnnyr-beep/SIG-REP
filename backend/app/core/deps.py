"""Dependencias de FastAPI: sesión, usuario autenticado y control de rol.

Portado de GSC ONE. Se añade `alcance_puntos_venta`, que es la regla que hace
cumplir el rol JEFE_PDV: consulta solo sus propios puntos de venta (§8.4).

Aquí viven también las guardas que la frontera HTTP aplica antes de dejar pasar
nada al dominio: el alcance de escritura (`alcance_escritura`), la clave
provisional pendiente de cambio (`ErrorClavePendiente`) y la lectura validada
de un archivo subido (`leer_subida`). Están en este módulo, y no duplicadas en
cada router, porque una validación de frontera que existe en dos sitios acaba
corregida en uno solo.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import obtener_sesion
from app.core.errors import ErrorAutenticacion, ErrorAutorizacion, ErrorValidacion
from app.core.security import decodificar_token
from app.domain.enums import Rol
from app.infrastructure.models.usuario import Usuario

# `auto_error=False` para devolver nuestro formato de error uniforme en lugar
# del que impone Starlette.
_esquema_bearer = HTTPBearer(auto_error=False, description="Token JWT de acceso")

SesionDep = Annotated[Session, Depends(obtener_sesion)]


def obtener_usuario_actual(
    sesion: SesionDep,
    credenciales: Annotated[HTTPAuthorizationCredentials | None, Depends(_esquema_bearer)],
) -> Usuario:
    """Resuelve el usuario del token y comprueba que siga habilitado.

    Se relee de la base en cada petición a propósito: si a alguien se le cambia
    el rol o se le desactiva la cuenta, el cambio surte efecto de inmediato y no
    cuando expire su token.
    """
    if credenciales is None:
        raise ErrorAutenticacion("Se requiere autenticación para acceder a este recurso.")

    datos = decodificar_token(credenciales.credentials, tipo_esperado="acceso")

    usuario = sesion.get(Usuario, datos.usuario_id)
    if usuario is None or not usuario.activo:
        raise ErrorAutenticacion("La cuenta ya no está habilitada.")
    if usuario.esta_bloqueado:
        raise ErrorAutenticacion("La cuenta está bloqueada temporalmente.")

    return usuario


UsuarioDep = Annotated[Usuario, Depends(obtener_usuario_actual)]


class ErrorClavePendiente(ErrorAutorizacion):
    """La cuenta arrastra una clave provisional sin cambiar.

    Vive aquí, en la frontera, y no en `core/errors.py`, porque no es una regla
    del dominio: es la puerta que `exigir_roles` cierra mientras la cuenta no
    haya estrenado su clave definitiva.

    Tiene código propio —`clave_pendiente`, no `no_autorizado`— porque el
    frontend necesita distinguirlos: uno significa «no es su sitio» y el otro
    «vaya a cambiar la clave y vuelva». Con el mismo código, la pantalla solo
    podría enseñar un 403 anónimo a alguien que sí tiene permisos.
    """

    codigo = "clave_pendiente"


def exigir_roles(*roles: Rol) -> Callable[[Usuario], Usuario]:
    """Dependencia que restringe un endpoint a ciertos roles.

    Ningún rol se incluye automáticamente: si un endpoint debe estar abierto a
    GERENTE, se declara. Los permisos implícitos son la principal fuente de
    sorpresas en las auditorías. `ADMIN` no es la excepción: donde entra, entra
    porque el endpoint lo declara.

    Aquí se cierra además la puerta de la clave provisional. Es el sitio
    correcto y no `obtener_usuario_actual`: por `exigir_roles` pasan **todos**
    los endpoints con RBAC y no pasan los dos que el usuario necesita
    justamente para salir del atolladero —`GET /auth/yo`, que le dice a la
    pantalla qué mostrar, y `POST /auth/cambiar-clave`, que resuelve el
    problema—. Ponerla en `obtener_usuario_actual` habría dejado a quien
    estrena cuenta sin forma de estrenarla.

    El rol se comprueba **antes** que la clave: quien no tiene permisos recibe
    403 sin llegar a saber si la cuenta que usó tiene o no una clave pendiente.
    """
    permitidos = {rol.value for rol in roles}

    def _verificar(usuario: UsuarioDep) -> Usuario:
        if usuario.rol not in permitidos:
            raise ErrorAutorizacion(
                "No tiene permisos para esta operación.",
                detalles={"roles_requeridos": sorted(permitidos)},
            )
        if usuario.debe_cambiar_password:
            raise ErrorClavePendiente(
                "Debe cambiar la clave provisional antes de usar el sistema.",
                detalles={"debe_cambiar_password": True},
            )
        return usuario

    return _verificar


def alcance_puntos_venta(usuario: Usuario) -> list[int] | None:
    """Puntos de venta que el usuario puede ver. `None` significa todos.

    Solo JEFE_PDV queda restringido. Un JEFE_PDV sin puntos asignados no ve
    nada —lista vacía—, que es lo correcto: dar acceso total «porque no le
    configuraron el alcance» es cómo se filtran los reportes de toda la
    compañía.

    `ADMIN` va como GERENTE: `None`, la compañía entera. Es superusuario y
    tiene que poder diagnosticar cualquier punto de venta sin pedir prestada
    una cuenta ajena.
    """
    if usuario.rol != Rol.JEFE_PDV.value:
        return None
    return usuario.puntos_venta_ids


def alcance_escritura(usuario: Usuario) -> list[int] | None:
    """Puntos de venta que el usuario puede **modificar**. `None` = todos.

    No es lo mismo que `alcance_puntos_venta` y la diferencia es deliberada:

    - En **lectura** solo se restringe a JEFE_PDV, porque ANALISTA y GERENTE
      parametrizan el reporte de toda la compañía y necesitan verlo entero.
    - En **escritura** manda la asignación explícita, la tenga el rol que la
      tenga. Asignarle puntos a alguien es afirmar «este es su ámbito»; que esa
      afirmación no valga para escribir es la clase de sorpresa que se descubre
      cuando un analista ya cargó el presupuesto de un punto ajeno desde su
      propio archivo.

    Un JEFE_PDV queda restringido siempre, aunque no tenga ningún punto
    asignado: su lista vacía significa «ninguno», nunca «todos».

    `ADMIN` no se exceptúa de la segunda regla, y es deliberado: si alguien le
    asigna puntos a un ADMIN, esa asignación limita lo que ese ADMIN escribe,
    igual que limitaría a un GERENTE. Un ADMIN recién creado no tiene ninguno,
    así que su alcance natural es la compañía entera.
    """
    if usuario.rol == Rol.JEFE_PDV.value or usuario.puntos_venta_ids:
        return usuario.puntos_venta_ids
    return None


def obtener_ip(request: Request) -> str | None:
    """IP de origen, respetando el proxy inverso cuando lo hay."""
    reenviada = request.headers.get("x-forwarded-for")
    if reenviada:
        return reenviada.split(",")[0].strip()
    return request.client.host if request.client else None


# ── Subida de archivos ────────────────────────────────────────────────────────

#: Firma de un archivo ZIP. Un `.xlsx` es un ZIP: si no empieza por aquí, no es
#: un libro de Excel por mucho que el nombre lo diga.
_FIRMA_ZIP = b"PK\x03\x04"

#: Trozo de lectura. El tamaño se comprueba **mientras** se lee, no después:
#: comprobarlo al final obliga a materializar entero lo que se quería rechazar.
_TROZO = 1024 * 1024

#: Relación máxima entre lo que el ZIP declara descomprimido y lo que ocupa.
#: El XML de un `.xlsx` real comprime entre 10 y 25 veces; 200 deja margen de
#: sobra y sigue muy por debajo de las 1 000 de una bomba de descompresión.
MAX_RATIO_COMPRESION = 200


async def leer_subida(
    archivo: UploadFile,
    *,
    extensiones: tuple[str, ...],
    max_bytes: int,
    max_descomprimido: int,
) -> bytes:
    """Lee un archivo subido validando extensión, tamaño y bomba ZIP.

    El orden importa: primero la extensión —descartar por el nombre no cuesta
    nada—, después el tamaño **durante** la lectura, y solo sobre lo que ya
    pasó las dos se mira el interior del ZIP. Un `.xlsx` es un ZIP y un ZIP de
    50 KB puede declarar 4 GB descomprimidos; abrirlo con `openpyxl` sin haber
    mirado antes lo que declara es entregarle la memoria del servidor a quien
    suba el archivo.

    El `Content-Type` que manda el cliente no se usa para nada: lo elige él.
    """
    nombre = (archivo.filename or "").strip().lower()
    if not nombre.endswith(extensiones):
        raise ErrorValidacion(f"Formato no admitido. Use {' o '.join(extensiones)}.")

    trozos: list[bytes] = []
    leidos = 0
    while True:
        trozo = await archivo.read(_TROZO)
        if not trozo:
            break
        leidos += len(trozo)
        if leidos > max_bytes:
            raise ErrorValidacion(
                f"El archivo supera el tamaño máximo admitido ({max_bytes // (1024 * 1024)} MB)."
            )
        trozos.append(trozo)

    contenido = b"".join(trozos)
    if not contenido:
        raise ErrorValidacion("El archivo está vacío.")

    if nombre.endswith((".xlsx", ".xlsm")):
        _verificar_zip(contenido, max_descomprimido)
    return contenido


def _verificar_zip(contenido: bytes, max_descomprimido: int) -> None:
    """Rechaza lo que no es un ZIP y lo que declara descomprimirse de más."""
    if not contenido.startswith(_FIRMA_ZIP):
        raise ErrorValidacion("El archivo no es un libro de Excel: no tiene formato ZIP.")

    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as libro:
            declarado = sum(entrada.file_size for entrada in libro.infolist())
    except zipfile.BadZipFile as exc:
        raise ErrorValidacion("El archivo no es un libro de Excel legible.") from exc

    if declarado > max_descomprimido:
        raise ErrorValidacion(
            f"El archivo declara {declarado // (1024 * 1024)} MB descomprimidos, por encima "
            f"del máximo admitido ({max_descomprimido // (1024 * 1024)} MB)."
        )
    if declarado > len(contenido) * MAX_RATIO_COMPRESION:
        raise ErrorValidacion(
            "El archivo se descomprime en una proporción impropia de un libro de Excel."
        )
