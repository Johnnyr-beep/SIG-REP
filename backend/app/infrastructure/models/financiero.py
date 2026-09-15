"""Libro mayor contable — insumo del tablero financiero consolidado (§ Grupo
Santacruz). Vive únicamente en la base de esa instancia (`db_url_grupo_santacruz`);
las unidades operativas (Carnes, Agropecuaria, Carnes Frías) no la usan.

Grano de almacenamiento: **el detalle tal como lo entrega SIESA** — un
movimiento por compañía, centro de operación, período, cuenta auxiliar y
tercero. Guardar solo el agregado impediría reconstruir el balance por
tercero o por centro de costo, que es justo lo que pide el tablero.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.infrastructure.models.mixins import Dinero, TimestampMixin


class MovimientoContable(Base, TimestampMixin):
    """Un renglón del libro mayor: saldo inicial, movimiento y saldo final.

    `FINAL` viaja tal como lo calculó SIESA —`SALDOS_INICIAL + DEBITOS -
    CREDITOS`—, sin ajustar por naturaleza de la cuenta. Esa conversión es de
    presentación, no de almacenamiento, y vive en `app.domain.financiero`.
    """

    __tablename__ = "movimientos_contables"
    __table_args__ = (
        Index("ix_movcont_cia_periodo", "cia", "periodo"),
        Index("ix_movcont_mayor_iii", "mayor_iii"),
        Index("ix_movcont_tercero", "id_tercero"),
        Index("ix_movcont_co", "co"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    #: Compañía del grupo. El diseño admite varias a propósito: hoy solo hay
    #: datos de una, pero el tablero es "del grupo" y las demás llegarán en
    #: cargas separadas sin requerir otro esquema.
    cia: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Centro de operación contable. No es el mismo catálogo que el punto de
    #: venta comercial de `puntos_venta`: este módulo es independiente de esa
    #: jerarquía (decisión explícita, ver docs del módulo financiero).
    co: Mapped[str] = mapped_column(String(10), nullable=False)
    #: Año y mes contable, `YYYYMM` (`202603` = marzo de 2026), tal como lo
    #: entrega SIESA. Entero y no texto: comparar y ordenar es aritmética.
    periodo: Mapped[int] = mapped_column(Integer, nullable=False)

    auxiliar: Mapped[str] = mapped_column(String(30), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(200))
    id_tercero: Mapped[str | None] = mapped_column(String(30))
    razon_social: Mapped[str | None] = mapped_column(String(200))
    id_centro_costo: Mapped[str | None] = mapped_column(String(30))
    centro_costo: Mapped[str | None] = mapped_column(String(120))

    mayor: Mapped[str | None] = mapped_column(String(30))
    mayor_iv: Mapped[str | None] = mapped_column(String(30))
    #: Cuenta a nivel de clase (4 dígitos, `1305`). No admite nulo: es la
    #: llave con la que `app.domain.financiero.clasificar` decide si la fila
    #: es activo, pasivo, patrimonio, ingreso, gasto o costo.
    mayor_iii: Mapped[str] = mapped_column(String(10), nullable=False)

    saldo_inicial: Mapped[Decimal] = mapped_column(Dinero, nullable=False)
    debitos: Mapped[Decimal] = mapped_column(Dinero, nullable=False)
    creditos: Mapped[Decimal] = mapped_column(Dinero, nullable=False)
    final: Mapped[Decimal] = mapped_column(Dinero, nullable=False)

    #: Nombre del archivo origen de esta fila. Misma razón que en
    #: `RechazoIngesta`: seis meses después alguien pregunta de dónde salió el
    #: número y esta columna contesta sin tener que repetir la carga.
    origen: Mapped[str | None] = mapped_column(String(300))

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<MovimientoContable cia={self.cia} periodo={self.periodo} {self.auxiliar}>"
