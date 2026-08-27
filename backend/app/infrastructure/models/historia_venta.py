"""Historia manual de venta de carnes por período y punto de venta."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.infrastructure.models.mixins import Dinero, Kilos, TimestampMixin

if TYPE_CHECKING:
    from app.infrastructure.models.organizacion import PuntoVenta
    from app.infrastructure.models.periodo import Periodo


class HistoriaVentaManual(Base, TimestampMixin):
    """Total mensual histórico usado cuando SIESA no tiene detalle del período.

    El grano es período + PDV. Los reportes nunca suman esta fila con venta
    transaccional del mismo PDV: el detalle real siempre tiene precedencia.
    """

    __tablename__ = "historia_venta_manual"
    __table_args__ = (
        UniqueConstraint(
            "periodo_id", "punto_venta_id", name="uq_historia_venta_manual_periodo_pdv"
        ),
        CheckConstraint("monto >= 0", name="ck_historia_venta_manual_monto_no_negativo"),
        CheckConstraint("kilos >= 0", name="ck_historia_venta_manual_kilos_no_negativo"),
        Index("ix_historia_venta_manual_periodo_pdv", "periodo_id", "punto_venta_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    periodo_id: Mapped[int] = mapped_column(
        ForeignKey("periodos.id", ondelete="CASCADE"), nullable=False
    )
    punto_venta_id: Mapped[int] = mapped_column(ForeignKey("puntos_venta.id"), nullable=False)
    monto: Mapped[Decimal] = mapped_column(Dinero, nullable=False)
    kilos: Mapped[Decimal] = mapped_column(Kilos, nullable=False)
    motivo: Mapped[str] = mapped_column(String(400), nullable=False)
    actualizado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))

    periodo: Mapped[Periodo] = relationship(lazy="joined")
    punto_venta: Mapped[PuntoVenta] = relationship(lazy="joined")
