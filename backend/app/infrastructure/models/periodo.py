"""Períodos mensuales y calendario de días hábiles por zona (§3.2)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.infrastructure.models.mixins import Dias, TimestampMixin, UtcDateTime

if TYPE_CHECKING:
    from app.infrastructure.models.organizacion import Zona


class Periodo(Base, TimestampMixin):
    """Un mes de operación. Se identifica hacia afuera como `YYYY-MM`.

    Se guarda como año y mes separados —y no como texto— para que ordenar y
    comparar períodos sea aritmética y no manipulación de cadenas.
    """

    __tablename__ = "periodos"
    __table_args__ = (
        UniqueConstraint("anio", "mes", name="uq_periodo_anio_mes"),
        CheckConstraint("mes >= 1 AND mes <= 12", name="ck_periodo_mes_valido"),
        Index("ix_periodo_orden", "anio", "mes"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    anio: Mapped[int] = mapped_column(nullable=False)
    mes: Mapped[int] = mapped_column(nullable=False)

    #: Un período cerrado no admite cambios de presupuesto (§7).
    cerrado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cerrado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    cerrado_en: Mapped[datetime | None] = mapped_column(UtcDateTime)

    calendarios: Mapped[list[CalendarioZona]] = relationship(
        back_populates="periodo", cascade="all, delete-orphan"
    )

    @property
    def codigo(self) -> str:
        """Representación `YYYY-MM` del contrato de API."""
        return f"{self.anio:04d}-{self.mes:02d}"

    @property
    def primer_dia(self) -> date:
        return date(self.anio, self.mes, 1)

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<Periodo {self.codigo}>"


class CalendarioZona(Base, TimestampMixin):
    """Días hábiles y trabajados de una zona en un período.

    El corazón de la parametrización: `ideal = dias_trabajados / dias_habiles`
    es la vara contra la que se mide todo el reporte.

    `dias_trabajados` en `NULL` significa **derivado** —lo calcula
    `app.domain.calendario.derivar_dias_trabajados` a partir de la fecha de
    corte—. Un valor explícito es una sobreescritura del usuario y manda sobre
    la derivación, porque el negocio sabe cosas que el calendario no.
    """

    __tablename__ = "calendario_zona"
    __table_args__ = (
        UniqueConstraint("periodo_id", "zona_id", name="uq_calendario_periodo_zona"),
        CheckConstraint("dias_habiles > 0", name="ck_calendario_habiles_positivos"),
        CheckConstraint(
            "dias_trabajados IS NULL OR dias_trabajados >= 0",
            name="ck_calendario_trabajados_no_negativos",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    periodo_id: Mapped[int] = mapped_column(
        ForeignKey("periodos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    zona_id: Mapped[int] = mapped_column(ForeignKey("zonas.id"), nullable=False, index=True)

    dias_habiles: Mapped[Decimal] = mapped_column(Dias, nullable=False)
    dias_trabajados: Mapped[Decimal | None] = mapped_column(Dias)
    #: Fecha de corte con la que el usuario fijó `dias_trabajados`. Sin ella,
    #: un número trabajado escrito a mano no se puede interpretar después.
    fecha_corte: Mapped[date | None] = mapped_column(Date)

    actualizado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))

    periodo: Mapped[Periodo] = relationship(back_populates="calendarios")
    zona: Mapped[Zona] = relationship(lazy="joined")

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<CalendarioZona zona={self.zona_id} habiles={self.dias_habiles}>"
