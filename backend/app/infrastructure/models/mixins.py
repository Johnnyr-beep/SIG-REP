"""Piezas reutilizables de los modelos ORM. Portado de GSC ONE."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Numeric
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator[datetime]):
    """Instante en UTC, siempre consciente de zona horaria.

    SQL Server devuelve `DATETIMEOFFSET` con zona y SQLite devuelve la fecha
    desnuda. Comparar ambos en el mismo código produce `TypeError: can't compare
    offset-naive and offset-aware datetimes`, un fallo que aparece en producción
    tras un cambio de motor o en pruebas y no en desarrollo. Este decorador
    normaliza en los dos sentidos para que el resto de la aplicación nunca
    tenga que preguntárselo.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError(
                "SIGREP solo persiste instantes con zona horaria explícita. "
                "Use `ahora_utc()` en lugar de `datetime.now()`."
            )
        return value.astimezone(UTC)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        instante: datetime = value
        if instante.tzinfo is None:
            # Lo escrito siempre fue UTC; el motor simplemente no guardó la zona.
            return instante.replace(tzinfo=UTC)
        return instante.astimezone(UTC)


#: Dinero: 18 dígitos, 2 decimales. Nunca `float` — el redondeo binario no es
#: admisible en un presupuesto de veinte mil millones.
Dinero = Numeric(18, 2)
#: Kilos: 18 dígitos, 3 decimales. `Cantidad inv.` de SIESA trae valores como
#: 370.83 y el negocio mide en kilos igual que en pesos (§4.5).
Kilos = Numeric(18, 3)
#: Días hábiles y trabajados: admiten media jornada (27.5, 28.5), así que son
#: `Numeric` y no `Integer`. Es el detalle que más veces se ha implementado mal.
Dias = Numeric(5, 2)
#: Porcentaje que envía SIESA línea a línea. Se guarda solo para conciliación.
Porcentaje = Numeric(9, 6)

CERO_DINERO = Decimal("0.00")
CERO_KILOS = Decimal("0.000")


def ahora_utc() -> datetime:
    """Instante actual con zona horaria explícita."""
    return datetime.now(UTC)


class TimestampMixin:
    """Marcas temporales de creación y última modificación."""

    creado_en: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(
        UtcDateTime, default=ahora_utc, onupdate=ahora_utc, nullable=False
    )
