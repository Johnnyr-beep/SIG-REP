from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, Date, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AgroTatCorrida(Base):
    __tablename__ = "agro_tat_corridas"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    desde: Mapped[date] = mapped_column(Date, nullable=False)
    hasta: Mapped[date] = mapped_column(Date, nullable=False)
    filas_leidas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    filas_insertadas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class AgroTatVenta(Base):
    __tablename__ = "agro_tat_ventas"
    __table_args__ = (
        Index("ix_agro_tat_fecha_sucursal", "fecha_documento", "codigo_sucursal"),
        Index("ix_agro_tat_documento", "nro_documento"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    corrida_id: Mapped[int] = mapped_column(ForeignKey("agro_tat_corridas.id"), nullable=False)
    fecha_documento: Mapped[date] = mapped_column(Date, nullable=False)
    nro_documento: Mapped[str] = mapped_column(String(80), nullable=False)
    tipo_comercial: Mapped[str | None] = mapped_column(String(120))
    cliente_factura: Mapped[str | None] = mapped_column(String(80))
    razon_social_cliente: Mapped[str | None] = mapped_column(String(240))
    codigo_sucursal: Mapped[str | None] = mapped_column(String(80))
    descripcion_sucursal: Mapped[str | None] = mapped_column(String(240))
    direccion_sucursal: Mapped[str | None] = mapped_column(String(300))
    cantidad_inv: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    valor_subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
