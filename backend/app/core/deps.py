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
from collections.abc import Callable, Generator
from typing import Annotated

from fastapi import Depends, Request, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import UNIDAD_POR_DEFECTO, UnidadDatos, obtener_sesion_de
from app.core.errors import ErrorAutenticacion, ErrorAutorizacion, ErrorValidacion
from app.core.security import TipoToken, decodificar_token
from app.domain.enums import Rol
from app.infrastructure.models.usuario import Usuario

PERMISO_VENTA_DIARIA_ASADERO = "PERMISO_VENTA_DIARIA_ASADERO"

# `auto_error=False` para devolver nuestro formato de error uniforme en lugar
# del que impone Starlette.
_esquema_bearer = HTTPBearer(auto_error=False, description="Token JWT de acceso")

#: Cabecera con la que el cliente declara a qué unidad quiere entrar. **Solo se
#: mira cuando no hay token**, que es el caso del inicio de sesión: ahí hace
#: falta saber contra qué base autenticar antes de que exista un token.
CABECERA_UNIDAD = "X-SIGREP-Unidad"

_UNIDADES: frozenset[str] = frozenset({"carnes", "agropecuaria", "carnes-frias"})


def unidad_de_peticion(peticion: Request) -> UnidadDatos:
    """A qué base va esta petición.

    El orden importa y es lo que sostiene la separación entre las dos compañías:

    **1. Si hay token, manda el token.** La unidad va firmada dentro, así que un
    cliente no puede cambiarla mandando otra cabecera. Sin esta precedencia, la
    cabecera sería una forma de leer la base de la otra compañía con un token
    legítimo, que es exactamente el agujero que este diseño evita.

    **2. Si no hay token, manda la cabecera.** Es el inicio de sesión, y ahí
    todavía no hay nada firmado: la unidad la eligió el usuario en el selector,
    antes de escribir sus credenciales, y viaja en la cabecera para que el propio
    acceso se valide contra la base correcta.

    **3. Si no hay ninguna de las dos, carnes.** Es la unidad de siempre y lo que
    responde a un cliente que no sabe de esto —una sonda, un balanceador—.

    Un token ilegible **no** se rechaza aquí: se cae al valor por defecto y quien
    lo rechaza, con su mensaje, es `obtener_usuario_actual`. Levantar el error de
    autenticación desde la dependencia de sesión lo haría aparecer en rutas
    públicas que no piden token para nada.
    """
    cabecera = peticion.headers.get("authorization", "")
    if cabecera.lower().startswith("bearer "):
        return _unidad_de_token(cabecera[7:].strip(), tipo="acceso")

    declarada = (peticion.headers.get(CABECERA_UNIDAD) or "").strip().lower()
    if declarada in _UNIDADES:
        return declarada  # type: ignore[return-value]
    return UNIDAD_POR_DEFECTO


def unidad_de_refresco(token_refresco: str) -> UnidadDatos:
    """A qué base va una renovación: a la que diga el **refresco presentado**.

    Hace falta porque el token de refresco viaja en el cuerpo y no en
    `Authorization`, así que `unidad_de_peticion` no puede verlo. Sin esto, la
    renovación de una sesión de agropecuaria resolvía por la cabecera —o por el
    valor por defecto— y abría la base de carnes: el usuario se buscaba por su
    `id` en la compañía equivocada, donde ese mismo `id` es otra persona, y la
    renovación devolvía un token a nombre de un desconocido después de comprobar
    «la cuenta sigue habilitada» sobre una cuenta ajena.

    Un refresco ilegible cae al valor por defecto, igual que en
    `unidad_de_peticion` y por el mismo motivo: quien lo rechaza con su mensaje
    es `AuthService.refrescar`, que es el que lo decodifica de verdad.
    """
    return _unidad_de_token(token_refresco, tipo="refresco")


def _unidad_de_token(token: str, *, tipo: TipoToken) -> UnidadDatos:
    """La unidad firmada dentro de un token, o la de por defecto si no se lee.

    Una unidad desconocida —un token de otra instalación, uno manipulado que no
    llega a verificar— también cae al valor por defecto: lo contrario sería
    abrir una conexión a partir de una cadena que llegó de fuera.
    """
    try:
        datos = decodificar_token(token, tipo_esperado=tipo)
    except Exception:
        return UNIDAD_POR_DEFECTO
    if datos.unidad in _UNIDADES:
        return datos.unidad  # type: ignore[return-value]
    return UNIDAD_POR_DEFECTO


def obtener_sesion_peticion(peticion: Request) -> Generator[Session, None, None]:
    """Dependencia de sesión: la base que le toca a **esta** petición."""
    yield from obtener_sesion_de(unidad_de_peticion(peticion))


SesionDep = Annotated[Session, Depends(obtener_sesion_peticion)]
UnidadDep = Annotated[UnidadDatos, Depends(unidad_de_peticion)]


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


def exigir_venta_diaria_asadero(usuario: UsuarioDep) -> Usuario:
    """Permite ADMIN o la capacidad de lectura estrictamente especializada."""
    if usuario.rol != Rol.ADMIN.value and not usuario.tiene_permiso(PERMISO_VENTA_DIARIA_ASADERO):
        raise ErrorAutorizacion("No tiene permiso para Venta Diaria Asadero.")
    if usuario.debe_cambiar_password:
        raise ErrorClavePendiente(
            "Debe cambiar la clave provisional antes de usar el sistema.",
            detalles={"debe_cambiar_password": True},
        )
    return usuario


def exigir_lectura_general(usuario: UsuarioDep) -> Usuario:
    """Lectura RBAC general; una cuenta granular queda fuera de este ámbito."""
    if usuario.rol == Rol.CONSULTA.value and usuario.tiene_permiso(PERMISO_VENTA_DIARIA_ASADERO):
        raise ErrorAutorizacion("Esta cuenta solo tiene acceso a Venta Diaria Asadero.")
    return usuario


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
    """Rechaza lo que no es un ZIP, lo que no es un libro y lo que se infla."""
    if not contenido.startswith(_FIRMA_ZIP):
        raise ErrorValidacion("El archivo no es un libro de Excel: no tiene formato ZIP.")

    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as libro:
            entradas = libro.infolist()
            declarado = sum(entrada.file_size for entrada in entradas)
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

    # Lo último, después de las dos guardas de tamaño: aquellas protegen el
    # servidor y esta protege al usuario, así que un archivo que sea las dos
    # cosas se rechaza primero por lo grave.
    _verificar_que_es_un_libro(entradas)


def _verificar_que_es_un_libro(entradas: list[zipfile.ZipInfo]) -> None:
    """Que dentro del ZIP haya un libro, y no un documento de otro programa.

    Un `.docx` y un `.pptx` **también** son ZIP y pasan la firma, así que hasta
    aquí llegaban intactos: `openpyxl` los abría, no encontraba las partes que
    esperaba y levantaba un `KeyError` crudo que salía por la API como un 500.
    Quien subió el archivo equivocado —que es lo que suele pasar: se adjunta el
    acta de la reunión en lugar del presupuesto— veía «error interno» y no tenía
    forma de saber que el problema era suyo y de un segundo.

    Se mira solo el listado de nombres, que ya está leído: ni se descomprime
    nada ni se hace una segunda pasada. La comprobación es deliberadamente laxa
    —basta con que exista la carpeta `xl/`— porque su trabajo es distinguir un
    libro de un documento de otra familia, no validar OOXML; un libro corrupto lo
    sigue detectando quien lo abre de verdad.
    """
    nombres = [entrada.filename for entrada in entradas]
    if not any(nombre.startswith("xl/") for nombre in nombres):
        raise ErrorValidacion(
            "El archivo es un ZIP válido pero no un libro de Excel: no contiene ninguna "
            "hoja de cálculo. Compruebe que está subiendo el libro y no otro documento."
        )
