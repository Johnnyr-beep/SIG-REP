"""Esquemas del módulo de administración de usuarios (`docs/API.md`).

La regla que gobierna este archivo entero: **ningún esquema de salida tiene un
campo para el hash de la contraseña**. No se omite en el serializador ni se
excluye con `exclude`; sencillamente no existe, que es la única forma de que no
reaparezca el día que alguien construya la respuesta desde el modelo ORM.

La clave provisional viaja en exactamente dos esquemas —`UsuarioCreado` y
`ClaveProvisional`—, los dos de un único endpoint cada uno y ninguno reutilizado
en una consulta. Es lo que hace cumplible el «se muestra una sola vez».
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.domain.enums import AccionUsuario, Rol
from app.schemas.common import EsquemaBase

#: Nombre de acceso. Minúsculas, dígitos, punto, guion y guion bajo: es lo que
#: se teclea a diario y lo que aparece en el rastro de auditoría, así que no
#: admite espacios ni mayúsculas que después nadie recuerda si puso.
PATRON_USUARIO = r"^[a-z0-9][a-z0-9._-]{2,49}$"


class UsuarioSalida(EsquemaBase):
    """Una cuenta tal como la ve el administrador.

    `bloqueado` es derivado, no almacenado: dice si la cuenta está ahora mismo
    en el bloqueo temporal por intentos fallidos. Se expone porque la pregunta
    que llega a Sistemas nunca es «¿está activo?» sino «¿por qué no puede
    entrar?», y esas son dos cosas distintas.
    """

    id: int
    usuario: str
    nombre: str
    email: str | None = None
    rol: Rol
    activo: bool
    debe_cambiar_password: bool
    bloqueado: bool
    ultimo_acceso: datetime | None = None
    creado_en: datetime
    puntos_venta: list[str] = Field(
        default_factory=list,
        description="Códigos C.O. del alcance del usuario. Vacío = sin restricción de PDV.",
    )
    permisos: list[str] = Field(default_factory=list)


class PermisoSalida(EsquemaBase):
    usuario_id: int
    codigo: str


class UsuarioCreado(EsquemaBase):
    """Respuesta del alta. La única vez que la clave provisional sale del servidor."""

    usuario: UsuarioSalida
    clave_provisional: str = Field(
        description=(
            "Clave de un solo uso. No se almacena en claro ni se registra en ningún log, "
            "y no vuelve a viajar en ninguna respuesta posterior: si se pierde, se "
            "restablece."
        )
    )


class ClaveProvisional(EsquemaBase):
    """Respuesta del restablecimiento de clave."""

    id: int
    usuario: str
    clave_provisional: str


class UsuarioNuevo(BaseModel):
    """Alta de usuario. La clave **no** se envía: la genera el servidor."""

    usuario: str = Field(pattern=PATRON_USUARIO, max_length=50)
    nombre: str = Field(min_length=3, max_length=150)
    email: EmailStr | None = None
    rol: Rol
    puntos_venta: list[str] = Field(
        default_factory=list, description="Códigos C.O. del alcance inicial."
    )


class UsuarioModificacion(BaseModel):
    """Cambio de nombre, correo o rol. Parcial: lo que no se manda, no se toca.

    Que un campo ausente no sea lo mismo que un campo en `null` importa aquí:
    mandar `"email": null` **borra** el correo, y no mandarlo lo deja como
    estaba. La diferencia se resuelve con `model_fields_set`, no con un valor
    centinela.
    """

    nombre: str | None = Field(default=None, min_length=3, max_length=150)
    email: EmailStr | None = None
    rol: Rol | None = None

    @model_validator(mode="after")
    def _al_menos_un_campo(self) -> UsuarioModificacion:
        if not self.model_fields_set:
            raise ValueError("Indique al menos un campo a modificar.")
        return self


class AlcanceEntrada(BaseModel):
    """Alcance completo del usuario. **Reemplaza**, no acumula.

    Se eligió reemplazo y no `añadir`/`quitar` por una razón de seguridad, no de
    comodidad: con reemplazo, lo que la pantalla envía es exactamente lo que
    queda, y el rastro de auditoría guarda el conjunto anterior y el nuevo. Con
    operaciones incrementales, el alcance real de alguien solo se conoce
    reproduciendo la secuencia entera de altas y bajas.
    """

    puntos_venta: list[str] = Field(
        default_factory=list, description="Códigos C.O. Lista vacía = se le quita todo el alcance."
    )


class AuditoriaSalida(EsquemaBase):
    """Una línea del rastro de administración de cuentas."""

    cuando: datetime
    accion: AccionUsuario
    usuario: str = Field(description="Nombre de acceso de la cuenta administrada")
    actor: str = Field(description="Nombre de acceso de quien ejecutó la operación")
    campo: str | None = None
    valor_anterior: str | None = None
    valor_nuevo: str | None = None
    ip_origen: str | None = None
