"""Presupuesto por (período, punto de venta, categoría) y su historial (§3.3)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.infrastructure.models.mixins import (
    Dinero,
    Kilos,
    TimestampMixin,
    UtcDateTime,
    ahora_utc,
)

if TYPE_CHECKING:
    from app.infrastructure.models.catalogo import Categoria
    from app.infrastructure.models.organizacion import PuntoVenta
    from app.infrastructure.models.periodo import Periodo


class Presupuesto(Base, TimestampMixin):
    """Presupuesto mensual de una categoría en un punto de venta.

    Se parametriza al grano más fino y **todo lo demás se calcula**: el
    presupuesto del punto de venta es la suma de sus categorías y el del grupo
    la suma de sus puntos. Capturarlo dos veces es garantizar que un día los dos
    números no coincidan.

    El presupuesto diario no se guarda: se deriva de los días hábiles de la zona
    (`presupuesto_mensual / dias_habiles`). Si se persistiera, cambiar el
    calendario dejaría el diario obsoleto sin que nadie se entere.
    """

    __tablename__ = "presupuestos"
    __table_args__ = (
        UniqueConstraint(
            "periodo_id", "punto_venta_id", "categoria_id", name="uq_presupuesto_pdv_categoria"
        ),
        CheckConstraint("monto >= 0", name="ck_presupuesto_monto_no_negativo"),
        CheckConstraint("kilos >= 0", name="ck_presupuesto_kilos_no_negativo"),
        # La consulta de reporte siempre entra por período y agrupa por punto de
        # venta; este índice cubre tanto el filtro como el orden de agregación.
        Index("ix_presupuesto_periodo_pdv", "periodo_id", "punto_venta_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey("periodos.id"), nullable=False, index=True)
    punto_venta_id: Mapped[int] = mapped_column(
        ForeignKey("puntos_venta.id"), nullable=False, index=True
    )
    categoria_id: Mapped[int] = mapped_column(
        ForeignKey("categorias.id"), nullable=False, index=True
    )

    monto: Mapped[Decimal] = mapped_column(Dinero, nullable=False, default=Decimal("0.00"))
    kilos: Mapped[Decimal] = mapped_column(Kilos, nullable=False, default=Decimal("0.000"))

    actualizado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))

    periodo: Mapped[Periodo] = relationship(lazy="joined")
    punto_venta: Mapped[PuntoVenta] = relationship(lazy="joined")
    categoria: Mapped[Categoria] = relationship(lazy="joined")

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<Presupuesto pdv={self.punto_venta_id} cat={self.categoria_id} {self.monto}>"


class PresupuestoHistorial(Base):
    """Rastro de cada cambio de presupuesto: quién, cuándo, qué y por qué.

    «Un presupuesto que cambia sin rastro no sirve para evaluar a nadie» (§3.3).
    Se registra una fila por **campo** modificado, con el valor anterior y el
    nuevo, para que el historial se pueda leer sin reconstruir estados.

    No se borra ni se actualiza nunca. Las claves apuntan al período, al punto
    de venta y a la categoría —no solo al presupuesto— para que el historial
    sobreviva si algún día se depura la tabla de presupuestos.

    `presupuesto_id` y `categoria_id` son **anulables**, y por el mismo motivo:
    el historial tiene que sobrevivir a lo que historia. El reparto de una
    categoría retirada borra la fila de presupuesto de origen (anula
    `presupuesto_id`) y la migración `0005` borra la categoría misma (anula
    `categoria_id`). Lo que queda —período, punto de venta, campo, valor
    anterior, valor nuevo, motivo, autor e instante— sigue contando la historia
    entera; lo único que se pierde es el vínculo con una fila que ya no existe.
    Ver `alembic/versions/0005_borrar_categoria_retirada.py`.
    """

    __tablename__ = "presupuesto_historial"
    __table_args__ = (Index("ix_historial_periodo_pdv", "periodo_id", "punto_venta_id", "cuando"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    presupuesto_id: Mapped[int | None] = mapped_column(ForeignKey("presupuestos.id"), index=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey("periodos.id"), nullable=False)
    punto_venta_id: Mapped[int] = mapped_column(ForeignKey("puntos_venta.id"), nullable=False)
    categoria_id: Mapped[int | None] = mapped_column(ForeignKey("categorias.id"))

    #: `monto` o `kilos`.
    campo: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Se guardan con la escala de los kilos (3 decimales) porque la columna
    #: sirve para ambos campos y así ningún valor pierde precisión al historiar.
    valor_anterior: Mapped[Decimal | None] = mapped_column(Kilos)
    valor_nuevo: Mapped[Decimal | None] = mapped_column(Kilos)

    motivo: Mapped[str] = mapped_column(String(400), nullable=False)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), index=True)
    cuando: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<PresupuestoHistorial {self.campo} {self.valor_anterior}→{self.valor_nuevo}>"
