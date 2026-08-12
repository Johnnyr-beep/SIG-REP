"""Jerarquía comercial: GRUPO → PUNTO DE VENTA, y las zonas de calendario (§3.1)."""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.infrastructure.models.mixins import TimestampMixin


class Grupo(Base, TimestampMixin):
    """Grupo comercial: la agrupación del reporte consolidado."""

    __tablename__ = "grupos"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(3), unique=True, nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(60), nullable=False)
    orden: Mapped[int] = mapped_column(default=0, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    puntos_venta: Mapped[list[PuntoVenta]] = relationship(
        back_populates="grupo", order_by="PuntoVenta.nombre"
    )

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<Grupo {self.codigo} {self.nombre}>"


class Zona(Base, TimestampMixin):
    """Zona de calendario: agrupa puntos de venta que abren los mismos días.

    No coincide con el grupo comercial y no tiene por qué: el grupo es para el
    reporte, la zona es para el calendario. BUCARAMANGA y CENTRO comparten
    calendario y están en grupos distintos.
    """

    __tablename__ = "zonas"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    activa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    puntos_venta: Mapped[list[PuntoVenta]] = relationship(
        back_populates="zona", order_by="PuntoVenta.nombre"
    )

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<Zona {self.nombre}>"


class PuntoVenta(Base, TimestampMixin):
    """Punto de venta. El código es el C.O. de SIESA y no se inventa.

    `codigo_co` es la llave de integración: viene de SIESA y llega tanto como
    texto con ceros a la izquierda como número (`'606'` y `606` conviven en el
    mismo archivo). Se persiste normalizado a texto de tres posiciones.
    """

    __tablename__ = "puntos_venta"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo_co: Mapped[str] = mapped_column(String(3), unique=True, nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(60), nullable=False)
    #: Descriptivo tal como lo entrega SIESA (`PDV BUCARMANGA`, con el typo de
    #: origen). No es llave; se guarda para conciliar a ojo con el ERP.
    descripcion_siesa: Mapped[str | None] = mapped_column(String(120))

    grupo_id: Mapped[int | None] = mapped_column(ForeignKey("grupos.id"), index=True)
    zona_id: Mapped[int | None] = mapped_column(ForeignKey("zonas.id"), index=True)

    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: Si el negocio le fija presupuesto. 432 EVENTOS BUCARAMANGA vende y no
    #: está presupuestado (§3.1): su venta se reporta aparte, nunca se descarta
    #: en silencio ni descuadra el consolidado.
    presupuestado: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    grupo: Mapped[Grupo | None] = relationship(back_populates="puntos_venta", lazy="joined")
    zona: Mapped[Zona | None] = relationship(back_populates="puntos_venta", lazy="joined")

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<PuntoVenta {self.codigo_co} {self.nombre}>"
