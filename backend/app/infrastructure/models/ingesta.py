"""Bitácora de las cargas de venta desde SIESA (§5).

«Cada corrida deja registro de filas leídas, aceptadas, rechazadas y el motivo
de cada rechazo.» Estas dos tablas son ese registro, y son lo que alimenta la
pantalla de Ingesta.

Los modelos están completos y estables **a propósito**: el agente de ingesta
construye su implementación encima de ellos sin tener que tocar el esquema.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.domain.enums import EstadoCorrida
from app.infrastructure.models.mixins import UtcDateTime, ahora_utc


class CorridaIngesta(Base):
    """Una ejecución de carga de venta, exitosa o no."""

    __tablename__ = "corridas_ingesta"
    __table_args__ = (Index("ix_corridas_cuando", "cuando"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    cuando: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    #: `siesa` o `excel`, según `app.domain.enums.FuenteIngesta`.
    fuente: Mapped[str] = mapped_column(String(20), nullable=False)
    desde: Mapped[date | None] = mapped_column()
    hasta: Mapped[date | None] = mapped_column()
    estado: Mapped[str] = mapped_column(
        String(30), nullable=False, default=EstadoCorrida.EN_CURSO.value
    )

    filas_leidas: Mapped[int] = mapped_column(default=0, nullable=False)
    aceptadas: Mapped[int] = mapped_column(default=0, nullable=False)
    rechazadas: Mapped[int] = mapped_column(default=0, nullable=False)
    duracion_ms: Mapped[int | None] = mapped_column()

    #: Nombre del archivo cargado o endpoint consultado. Ayuda a contestar «¿de
    #: dónde salió este número?» seis meses después.
    origen: Mapped[str | None] = mapped_column(String(300))
    mensaje: Mapped[str | None] = mapped_column(Text)

    rechazos: Mapped[list[RechazoIngesta]] = relationship(
        back_populates="corrida", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<CorridaIngesta {self.id} {self.estado}>"


class RechazoIngesta(Base):
    """Una fila que la ingesta no pudo aceptar, con su motivo.

    Rechazar en silencio es peor que fallar: el consolidado sale cuadrado y
    nadie se entera de que faltan tres días de un punto de venta.
    """

    __tablename__ = "rechazos_ingesta"
    __table_args__ = (Index("ix_rechazos_corrida", "corrida_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    corrida_id: Mapped[int] = mapped_column(
        ForeignKey("corridas_ingesta.id", ondelete="CASCADE"), nullable=False
    )
    #: Número de fila en el origen.
    fila: Mapped[int | None] = mapped_column()
    campo: Mapped[str | None] = mapped_column(String(60))
    #: Valor ofensivo, truncado. Se guarda como texto porque justamente el
    #: problema suele ser que no tenía el tipo que decía tener.
    valor: Mapped[str | None] = mapped_column(String(300))
    motivo: Mapped[str] = mapped_column(String(300), nullable=False)

    corrida: Mapped[CorridaIngesta] = relationship(back_populates="rechazos")
