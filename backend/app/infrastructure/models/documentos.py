"""Número de documentos (facturas) por punto de venta y día.

Fuente: `GET /ventas/facturas-pdv-diario` de la API de SIESA. Antes de este
endpoint, §4.4 de la especificación documentaba el número de documentos como
un dato que **la fuente no entregaba** y que por eso no se publicaba —«Reservar
la columna, aunque fuera con un "—", sugeriría que el dato existe y está
fallando»—. Este endpoint lo entrega, un renglón por factura, y esta tabla
guarda el conteo ya agregado por (punto de venta, día): la venta en pesos y
kilos se persiste en detalle porque el reporte necesita reagruparla de muchas
formas (§3.4), pero un documento no se puede partir por categoría ni cliente,
así que no hay razón para guardar una fila por factura.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.infrastructure.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.infrastructure.models.organizacion import PuntoVenta


class NumeroDocumentosDiarios(Base, TimestampMixin):
    """Cuántas facturas distintas tuvo un punto de venta en un día."""

    __tablename__ = "numero_documentos_diarios"
    __table_args__ = (
        UniqueConstraint("punto_venta_id", "fecha", name="uq_documentos_pdv_fecha"),
        Index("ix_documentos_fecha", "fecha"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    punto_venta_id: Mapped[int] = mapped_column(
        ForeignKey("puntos_venta.id", ondelete="CASCADE"), nullable=False
    )
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    #: De dónde salió el conteo. Hoy siempre `siesa`; existe por si algún día
    #: hay que distinguir un conteo de otra procedencia, igual que `origen` en
    #: `MovimientoContable`.
    origen: Mapped[str] = mapped_column(String(20), nullable=False, default="siesa")

    punto_venta: Mapped[PuntoVenta] = relationship(lazy="joined")

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<NumeroDocumentosDiarios pdv={self.punto_venta_id} {self.fecha}={self.cantidad}>"
