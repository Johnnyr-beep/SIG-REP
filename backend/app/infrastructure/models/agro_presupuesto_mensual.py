"""Presupuesto mensual configurable de la unidad Agropecuaria.

── Qué es y en qué se diferencia de `agro_presupuestos` ──────────────────────

`agro_presupuestos` es **una sola meta de la compañía descompuesta en cuatro
dimensiones** (vendedor, centro de operación, especie y tipo comercial). Sus
cuatro totales describen el mismo dinero y **no se suman**: sumarlos daría el
doble de la meta real. Ese modelo existe precisamente para hacer imposible la
suma, y no se toca.

Este módulo es **otra cosa**. Aquí el negocio fija **cuatro bloques
independientes** —comercial, agro distribución, servicio y nacional— y el
total mensual **es la suma de los cuatro**. Cada bloque tiene su propia lógica
de captura:

- **Comercial**: presupuestos por vendedor (incluido León) con categoría A–F
  asignada a cada vendedor en función de sus clientes.
- **Agro distribución**: los clientes pertenecen al vendedor `AGROPECUARIA`.
- **Nacional**: los clientes pertenecen a Juan Sierra, incluido Éxito.
- **Servicio**: un solo valor mensual; no depende de vendedor ni de cliente.

Los cuatro bloques se suman para dar el total mensual. Eso es justamente lo que
**no** se hace con `agro_presupuestos`, y por eso este módulo vive aparte, con
sus propias tablas y sus propias rutas bajo `/agro/presupuesto-mensual`.

── Las tablas ───────────────────────────────────────────────────────────────

Tres tablas:

1. `agro_ppto_mensual_mapeo` — configuración de asignaciones: a qué bloque,
   vendedor, cliente y categoría (A–F) pertenece cada combinación. Es
   configurable y activable/inactivable sin borrar.
2. `agro_ppto_mensual_detalle` — filas de presupuesto por período, bloque,
   cliente, vendedor y categoría, con monto y kilos. Las cuatro bloques
   compercial, agro distribución y nacional viven aquí; servicio también puede
   usar filas de detalle si se captura por cliente, pero su forma natural es
   la fila agregada.
3. `agro_ppto_mensual_servicio` — el bloque de servicio como un solo valor
   mensual, porque no depende de vendedor ni de cliente.

Las restricciones de unicidad impiden duplicados: no dos filas de detalle para
el mismo (período, bloque, cliente, vendedor, categoría), ni dos filas de
servicio para el mismo período.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
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
)

if TYPE_CHECKING:
    from app.infrastructure.models.periodo import Periodo

#: Los cuatro bloques del presupuesto mensual. Son independientes y se suman.
BLOQUES_PRESUPUESTO_MENSUAL: tuple[str, ...] = (
    "commercial",
    "agro_distribucion",
    "servicio",
    "nacional",
)

#: Categorías A–F que se asignan a los vendedores del bloque comercial.
CATEGORIAS_MENSUAL: tuple[str, ...] = ("A", "B", "C", "D", "E", "F")

_CHECK_BLOQUE = " OR ".join(f"bloque = '{b}'" for b in BLOQUES_PRESUPUESTO_MENSUAL)
_CHECK_CATEGORIA = " OR ".join(f"categoria = '{c}'" for c in CATEGORIAS_MENSUAL)


class AgroPptoMensualMapeo(Base, TimestampMixin):
    """Configuración de asignación: bloque → vendedor / cliente / categoría.

    Es la tabla que hace que la captura sea configurable en lugar de codificada:
    el negocio decide qué vendedor atiende a qué cliente, en qué bloque y con
    qué categoría (A–F), y lo activa o desactiva sin borrar el registro.

    `vendedor_clave`, `cliente_clave` y `categoria` son opcionales porque no
    todos los bloques los usan: el bloque de servicio no tiene vendedor ni
    cliente, y la categoría solo aplica al bloque comercial.

    Las claves no son claves ajenas a `agro_dimensiones` por la misma razón que
    en `agro_presupuestos`: el presupuesto se fija antes de que la ingesta
    pueble el catálogo, y exigir una FK obligaría a inventar miembros que el
    ERP todavía no conoce.
    """

    __tablename__ = "agro_ppto_mensual_mapeo"
    __table_args__ = (
        UniqueConstraint(
            "bloque",
            "vendedor_clave",
            "cliente_clave",
            "categoria",
            name="uq_agro_ppto_mensual_mapeo_bloque_asignacion",
        ),
        CheckConstraint(_CHECK_BLOQUE, name="ck_agro_ppto_mensual_mapeo_bloque"),
        CheckConstraint(
            "categoria IS NULL OR " + _CHECK_CATEGORIA,
            name="ck_agro_ppto_mensual_mapeo_categoria",
        ),
        Index(
            "ix_agro_ppto_mensual_mapeo_bloque",
            "bloque",
            "activo",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    #: Uno de los cuatro bloques. El `CHECK` impide un quinto por descuido.
    bloque: Mapped[str] = mapped_column(String(30), nullable=False)
    #: Clave del vendedor normalizada. Opcional: el bloque de servicio no la usa.
    vendedor_clave: Mapped[str | None] = mapped_column(String(60))
    #: Clave del cliente normalizada. Opcional por la misma razón.
    cliente_clave: Mapped[str | None] = mapped_column(String(60))
    #: Categoría A–F. Solo aplica al bloque comercial; `NULL` en los demás.
    categoria: Mapped[str | None] = mapped_column(String(1))
    #: `False` retira la asignación sin borrarla, para no perder la historia.
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<AgroPptoMensualMapeo {self.bloque} "
            f"v={self.vendedor_clave} c={self.cliente_clave} cat={self.categoria}>"
        )


class AgroPptoMensualDetalle(Base, TimestampMixin):
    """Fila de presupuesto mensual por bloque, cliente, vendedor y categoría.

    Cada fila es una meta de un bloque en un período, descompuesta por cliente,
    vendedor y categoría (esta última solo en el bloque comercial). El total
    mensual del bloque sale de sumar sus filas, y el total mensual de la
    compañía sale de sumar los cuatro bloques.

    `monto` y `kilos` no son negativos: un presupuesto negativo no tiene
    sentido de negocio y un `CHECK` lo impide en la base, igual que en
    `agro_presupuestos`.
    """

    __tablename__ = "agro_ppto_mensual_detalle"
    __table_args__ = (
        UniqueConstraint(
            "periodo_id",
            "bloque",
            "cliente_clave",
            "vendedor_clave",
            "categoria",
            name="uq_agro_ppto_mensual_detalle_periodo_bloque_asignacion",
        ),
        CheckConstraint(_CHECK_BLOQUE, name="ck_agro_ppto_mensual_detalle_bloque"),
        CheckConstraint(
            "categoria IS NULL OR " + _CHECK_CATEGORIA,
            name="ck_agro_ppto_mensual_detalle_categoria",
        ),
        CheckConstraint("monto >= 0", name="ck_agro_ppto_mensual_detalle_monto_no_negativo"),
        CheckConstraint("kilos >= 0", name="ck_agro_ppto_mensual_detalle_kilos_no_negativo"),
        Index(
            "ix_agro_ppto_mensual_detalle_periodo_bloque",
            "periodo_id",
            "bloque",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey("periodos.id"), nullable=False, index=True)
    bloque: Mapped[str] = mapped_column(String(30), nullable=False)
    #: Clave del cliente. Opcional: el bloque de servicio no la usa.
    cliente_clave: Mapped[str | None] = mapped_column(String(60))
    #: Clave del vendedor. Opcional: el bloque de servicio no la usa.
    vendedor_clave: Mapped[str | None] = mapped_column(String(60))
    #: Categoría A–F. Solo en el bloque comercial; `NULL` en los demás.
    categoria: Mapped[str | None] = mapped_column(String(1))
    #: Etiqueta legible del cliente, para mostrar algo cuando no hay catálogo.
    cliente_etiqueta: Mapped[str | None] = mapped_column(String(200))
    #: Etiqueta legible del vendedor.
    vendedor_etiqueta: Mapped[str | None] = mapped_column(String(200))

    monto: Mapped[Decimal] = mapped_column(Dinero, nullable=False, default=Decimal("0.00"))
    kilos: Mapped[Decimal] = mapped_column(Kilos, nullable=False, default=Decimal("0.000"))

    actualizado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))

    periodo: Mapped[Periodo] = relationship(lazy="joined")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<AgroPptoMensualDetalle {self.bloque} "
            f"v={self.vendedor_clave} c={self.cliente_clave} monto={self.monto}>"
        )


class AgroPptoMensualServicio(Base, TimestampMixin):
    """Presupuesto mensual del bloque de servicio: un solo valor por período.

    El bloque de servicio no se descompone por vendedor ni por cliente: es una
    sola meta mensual. Por eso vive en su propia tabla con una restricción de
    unicidad por período, y no en `agro_ppto_mensual_detalle` donde tendría que
    rellenar vendedor y cliente con `NULL` y competir con la restricción de
    unicidad.

    Su monto se suma al total mensual igual que los demás bloques.
    """

    __tablename__ = "agro_ppto_mensual_servicio"
    __table_args__ = (
        UniqueConstraint("periodo_id", name="uq_agro_ppto_mensual_servicio_periodo"),
        CheckConstraint("monto >= 0", name="ck_agro_ppto_mensual_servicio_monto_no_negativo"),
        CheckConstraint("kilos >= 0", name="ck_agro_ppto_mensual_servicio_kilos_no_negativo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey("periodos.id"), nullable=False, index=True)

    monto: Mapped[Decimal] = mapped_column(Dinero, nullable=False, default=Decimal("0.00"))
    kilos: Mapped[Decimal] = mapped_column(Kilos, nullable=False, default=Decimal("0.000"))

    actualizado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))

    periodo: Mapped[Periodo] = relationship(lazy="joined")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AgroPptoMensualServicio periodo={self.periodo_id} monto={self.monto}>"
