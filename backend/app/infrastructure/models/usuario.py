"""Identidad y control de acceso. Portado de GSC ONE y simplificado.

Diferencia deliberada con GSC ONE: allí un usuario acumula varios roles; aquí
`docs/API.md` devuelve `rol` en singular en `/auth/yo`, así que el modelo es de
un rol por usuario. La otra diferencia es el alcance por punto de venta, que
GSC ONE no necesita: el rol JEFE_PDV consulta solo sus PDV (§8.4).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.domain.enums import Rol
from app.infrastructure.models.mixins import TimestampMixin, UtcDateTime, ahora_utc
from app.infrastructure.models.organizacion import PuntoVenta


class Usuario(Base, TimestampMixin):
    """Persona que consulta o parametriza el reporte."""

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    rol: Mapped[str] = mapped_column(String(20), nullable=False)

    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    debe_cambiar_password: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Defensa contra fuerza bruta: se bloquea la cuenta, no la IP, para no
    # castigar a toda la oficina que sale por la misma NAT.
    intentos_fallidos: Mapped[int] = mapped_column(default=0, nullable=False)
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(UtcDateTime)
    ultimo_acceso: Mapped[datetime | None] = mapped_column(UtcDateTime)

    alcances: Mapped[list[UsuarioPuntoVenta]] = relationship(
        back_populates="usuario",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    @property
    def esta_bloqueado(self) -> bool:
        return self.bloqueado_hasta is not None and self.bloqueado_hasta > ahora_utc()

    @property
    def puntos_venta_ids(self) -> list[int]:
        """Puntos de venta a los que el usuario tiene alcance.

        Vacío significa **sin restricción** para los roles que ven todo, y
        «todavía no le asignaron ninguno» para JEFE_PDV. La diferencia la
        resuelve `app.core.deps.alcance_puntos_venta`, que es donde vive la
        regla; el modelo solo guarda el dato.
        """
        return [alcance.punto_venta_id for alcance in self.alcances]

    def tiene_rol(self, *roles: Rol) -> bool:
        return any(self.rol == rol.value for rol in roles)

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<Usuario {self.usuario} ({self.rol})>"


class UsuarioPuntoVenta(Base):
    """Alcance de un usuario sobre un punto de venta (rol JEFE_PDV)."""

    __tablename__ = "usuario_puntos_venta"
    __table_args__ = (
        UniqueConstraint("usuario_id", "punto_venta_id", name="uq_usuario_punto_venta"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    punto_venta_id: Mapped[int] = mapped_column(
        ForeignKey("puntos_venta.id"), nullable=False, index=True
    )

    usuario: Mapped[Usuario] = relationship(back_populates="alcances")
    punto_venta: Mapped[PuntoVenta] = relationship(lazy="joined")


class UsuarioAuditoria(Base):
    """Rastro de la administración de cuentas: quién, sobre quién, qué y cuándo.

    Sigue el patrón de `presupuesto_historial` (§3.3) porque el problema es el
    mismo: «un permiso concedido sin rastro no se puede auditar», igual que un
    presupuesto que cambia sin rastro no sirve para evaluar a nadie. De ahí las
    tres decisiones que copia:

    1. **Una fila por campo modificado**, con el valor anterior y el nuevo, para
       poder leer el historial sin reconstruir estados intermedios.
    2. **No se borra ni se actualiza nunca.** No hay endpoint que lo toque.
    3. **Las claves ajenas son anulables** y el dato importante va además
       desnormalizado: `usuario` y `actor` guardan el nombre de acceso tal como
       era en ese momento. Así el rastro se lee entero aunque un día se depure
       la tabla de usuarios, y sigue diciendo la verdad aunque después alguien
       renombre la cuenta.

    Lo que **nunca** entra aquí es la clave. `RESTABLECER_CLAVE` deja constancia
    de que se restableció y de quién lo hizo; el valor no se guarda ni cifrado
    ni en claro, porque el rastro de auditoría lo lee más gente que la que puede
    entrar a la cuenta.
    """

    __tablename__ = "usuario_auditoria"
    __table_args__ = (Index("ix_auditoria_usuario_cuando", "usuario_id", "cuando"),)

    id: Mapped[int] = mapped_column(primary_key=True)

    #: Cuenta administrada.
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), index=True)
    usuario: Mapped[str] = mapped_column(String(50), nullable=False)

    #: Miembro de `app.domain.enums.AccionUsuario`.
    accion: Mapped[str] = mapped_column(String(30), nullable=False)
    #: Campo tocado (`rol`, `nombre`, `email`, `activo`, `alcance`) o nulo
    #: cuando la acción no modifica un campo concreto.
    campo: Mapped[str | None] = mapped_column(String(40))
    valor_anterior: Mapped[str | None] = mapped_column(String(200))
    valor_nuevo: Mapped[str | None] = mapped_column(String(200))

    #: Quién la ejecutó. Nulo solo si el rastro lo dejó la semilla.
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), index=True)
    actor: Mapped[str] = mapped_column(String(50), nullable=False)

    ip_origen: Mapped[str | None] = mapped_column(String(45))
    cuando: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<UsuarioAuditoria {self.accion} {self.usuario} por {self.actor}>"


class IntentoAcceso(Base):
    """Registro de intentos de autenticación para auditoría de seguridad."""

    __tablename__ = "intentos_acceso"
    __table_args__ = (Index("ix_intentos_usuario_fecha", "usuario", "fecha"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario: Mapped[str] = mapped_column(String(50), nullable=False)
    exitoso: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ip_origen: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    motivo: Mapped[str | None] = mapped_column(String(120))
    fecha: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)
