"""Presupuesto agropecuario **por dimensión**, su historial y su calendario.

Es la pieza más delicada de la unidad, así que conviene leerla entera antes de
tocarla.

── El problema ───────────────────────────────────────────────────────────────

El negocio fija presupuesto por **vendedor**, por **centro de operación**, por
**especie** y por **tipo comercial**. No por uno de ellos: por los cuatro. Y no
son cuatro metas distintas: son **cuatro descomposiciones del mismo total**, la
misma meta de la compañía repartida de cuatro formas.

De ahí sale la trampa que este modelo tiene que hacer imposible:

    El presupuesto por vendedor y el presupuesto por especie describen **el
    mismo dinero** visto de dos maneras. Sumarlos da el doble de la meta.

── La forma de la tabla, y por qué esta y no otra ────────────────────────────

Una sola tabla, `(periodo, dimension, clave, monto, kilos)`. Las alternativas
que se descartaron, con su motivo:

- **Cuatro tablas** (`agro_ppto_vendedor`, `agro_ppto_especie`…). Cuatro tablas
  con la misma forma obligan a cuatro consultas, cuatro esquemas y cuatro rutas,
  y —lo que importa— hacen trivial escribir un `UNION ALL` de las cuatro y
  sumarlo. La suma prohibida quedaría a un `JOIN` de distancia.
- **Cuatro columnas de monto en una fila por período.** Impide que un vendedor
  tenga su propia fila y convierte cada alta en una migración.
- **Una fila por combinación (vendedor × especie × …).** Es lo que el negocio
  *no* pidió: obligaría a capturar el producto cartesiano —21 × 6 × 14 × 2 =
  3528 celdas— para poder fijar una meta por vendedor.

Con `(dimension, clave)` cada fila dice a qué descomposición pertenece, y el
`CHECK` de la columna impide que aparezca una quinta dimensión por descuido.

── Cómo se hace *imposible* sumar dos dimensiones, y no solo se advierte ─────

La tabla es la mitad de la respuesta; la otra mitad está en
`app/application/services/agro_presupuesto_service.py`. En resumen:

1. **No existe ninguna consulta de esta tabla sin `WHERE dimension = ?`.** El
   único método que la lee es `AgroPresupuestoService.plan(periodo, dimension)`,
   y `dimension` es un parámetro obligatorio y tipado.
2. **El presupuesto no sale del servicio como un número suelto.** Sale dentro de
   un `PlanPresupuesto`, que es inmutable, lleva su dimensión pegada y se
   **niega a sumarse** con un plan de otra dimensión: `__add__` lanza
   `ErrorDimensionesIncompatibles`. No hay forma de obtener «todos los
   presupuestos» como una lista sumable.
3. **La respuesta de la API tampoco lo permite.** `GET /agro/presupuesto`
   devuelve un mapa `{dimension: {total, filas}}`, con un total **por
   dimensión** y ninguno global. Una pantalla que quisiera el total de la
   compañía tiene que elegir una dimensión, que es exactamente la operación
   correcta.
4. **Y cuando las cuatro no cuadran, se dice.** `GET /agro/presupuesto/cuadre`
   compara los cuatro totales y publica la diferencia. No la corrige: un
   descuadre entre dimensiones es un error de captura y el sistema lo hace
   visible en lugar de repararlo por su cuenta.

── El calendario ─────────────────────────────────────────────────────────────

`AgroCalendario` es a agropecuaria lo que `calendario_zona` es a carnes, con una
diferencia: aquí la unidad de calendario es el **centro de operación** y no una
zona inventada. Son dos —Planta (301) y Montería (302)— y pueden tener días
hábiles distintos; el `ideal` de cada uno sale de los suyos.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.infrastructure.models.agro_vocabulario import (
    DIMENSIONES_PRESUPUESTO,
    DimensionPresupuesto,
)
from app.infrastructure.models.mixins import (
    Dias,
    Dinero,
    Kilos,
    TimestampMixin,
    UtcDateTime,
    ahora_utc,
)

if TYPE_CHECKING:
    from app.infrastructure.models.agro_dimensiones import AgroDimension
    from app.infrastructure.models.periodo import Periodo

#: `CHECK` de la columna `dimension`, construido desde el enum para que la
#: tabla y el vocabulario no puedan divergir. Una quinta dimensión escrita a
#: mano —o un typo, `'vendedores'`— no llega a persistirse.
_CHECK_DIMENSION = " OR ".join(f"dimension = '{valor}'" for valor in DIMENSIONES_PRESUPUESTO)


class AgroPresupuesto(Base, TimestampMixin):
    """Meta de un miembro de una dimensión en un período, en pesos y en kilos.

    `clave` **no** es una clave ajena a `agro_dimensiones`, y es deliberado: el
    presupuesto de un vendedor se fija en diciembre para enero, cuando ese
    vendedor todavía no ha facturado nada y por tanto no existe como miembro del
    catálogo —que lo puebla la ingesta—. Con una clave ajena habría que crear el
    miembro antes de poder presupuestarlo, es decir, inventar en el catálogo un
    vendedor que el ERP aún no conoce.

    El nombre se resuelve al leer, contra el catálogo, y cuando no hay miembro
    se publica la propia clave. Una meta para un vendedor que nunca facturó se
    ve en el reporte con cumplimiento cero, que es la verdad, en lugar de
    desaparecer.
    """

    __tablename__ = "agro_presupuestos"
    __table_args__ = (
        # Una sola meta por (período, dimensión, miembro). Sin esto, dos cargas
        # masivas del mismo archivo duplicarían la meta de la compañía.
        UniqueConstraint(
            "periodo_id", "dimension", "clave", name="uq_agro_presupuesto_dimension_clave"
        ),
        CheckConstraint(_CHECK_DIMENSION, name="ck_agro_presupuesto_dimension"),
        CheckConstraint("monto >= 0", name="ck_agro_presupuesto_monto_no_negativo"),
        CheckConstraint("kilos >= 0", name="ck_agro_presupuesto_kilos_no_negativo"),
        # **El índice empieza por la dimensión después del período**, y no es
        # una preferencia: es la forma del único acceso que existe a esta tabla,
        # `WHERE periodo_id = ? AND dimension = ?`. Un índice que no la
        # incluyera invitaría a escribir la consulta sin ella.
        Index("ix_agro_presupuesto_periodo_dimension", "periodo_id", "dimension", "clave"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey("periodos.id"), nullable=False, index=True)
    #: Una de las cuatro de `DimensionPresupuesto`. **Nunca se agrega sobre esta
    #: tabla sin filtrar por esta columna**: ver el encabezado del módulo.
    dimension: Mapped[str] = mapped_column(String(30), nullable=False)
    #: Miembro dentro de la dimensión, normalizado con `normalizar_clave`.
    clave: Mapped[str] = mapped_column(String(60), nullable=False)
    #: Etiqueta con la que se capturó, para poder mostrar algo legible cuando el
    #: miembro todavía no existe en el catálogo. La ingesta no la toca.
    etiqueta: Mapped[str | None] = mapped_column(String(200))

    monto: Mapped[Decimal] = mapped_column(Dinero, nullable=False, default=Decimal("0.00"))
    kilos: Mapped[Decimal] = mapped_column(Kilos, nullable=False, default=Decimal("0.000"))

    actualizado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))

    periodo: Mapped[Periodo] = relationship(lazy="joined")

    @property
    def dimension_enum(self) -> DimensionPresupuesto:
        return DimensionPresupuesto(self.dimension)

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<AgroPresupuesto {self.dimension}:{self.clave} {self.monto}>"


class AgroPresupuestoHistorial(Base):
    """Rastro de cada cambio de presupuesto agropecuario: quién, cuándo, qué y por qué.

    Misma regla que en carnes (§3.3): «un presupuesto que cambia sin rastro no
    sirve para evaluar a nadie». Una fila por **campo** modificado, con el valor
    anterior y el nuevo, para que el historial se lea sin reconstruir estados.

    No se borra ni se actualiza nunca. `presupuesto_id` es anulable por el mismo
    motivo que en carnes: el rastro tiene que sobrevivir a lo que historia. Lo
    que queda —período, dimensión, clave, campo, valores, motivo, autor e
    instante— sigue contando la historia entera.
    """

    __tablename__ = "agro_presupuesto_historial"
    __table_args__ = (
        Index("ix_agro_historial_periodo_dimension", "periodo_id", "dimension", "cuando"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    presupuesto_id: Mapped[int | None] = mapped_column(
        ForeignKey("agro_presupuestos.id"), index=True
    )
    periodo_id: Mapped[int] = mapped_column(ForeignKey("periodos.id"), nullable=False)
    dimension: Mapped[str] = mapped_column(String(30), nullable=False)
    clave: Mapped[str] = mapped_column(String(60), nullable=False)

    #: `monto` o `kilos`.
    campo: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Con la escala de los kilos (3 decimales) para los dos campos, igual que
    #: en carnes: una sola columna sirve a `monto` y a `kilos` y así ningún
    #: valor pierde precisión al historiar.
    valor_anterior: Mapped[Decimal | None] = mapped_column(Kilos)
    valor_nuevo: Mapped[Decimal | None] = mapped_column(Kilos)

    motivo: Mapped[str] = mapped_column(String(400), nullable=False)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), index=True)
    cuando: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<AgroPresupuestoHistorial {self.campo} {self.valor_anterior}→{self.valor_nuevo}>"


class AgroCalendario(Base, TimestampMixin):
    """Días hábiles y trabajados de un centro de operación en un período.

    La unidad de calendario de agropecuaria es el **centro de operación**, que
    son dos —301 Planta y 302 Montería—, y no una zona: aquí no hay dieciséis
    puntos repartidos en zonas, hay dos centros que pueden abrir días distintos.

    `dias_trabajados` en `NULL` significa **derivado**: lo calcula
    `app.domain.calendario.derivar_dias_trabajados` a partir de la fecha de
    corte. Un valor explícito es una sobreescritura del usuario y manda, porque
    el negocio sabe cosas que el calendario no.

    `centro_id` apunta a `agro_dimensiones`, donde el centro es un miembro más
    de la dimensión `centro_operacion`. No hay una tabla de centros aparte y no
    hace falta: son dos filas de un catálogo que la ingesta ya mantiene.
    """

    __tablename__ = "agro_calendario"
    __table_args__ = (
        UniqueConstraint("periodo_id", "centro_id", name="uq_agro_calendario_periodo_centro"),
        CheckConstraint("dias_habiles > 0", name="ck_agro_calendario_habiles_positivos"),
        CheckConstraint(
            "dias_trabajados IS NULL OR dias_trabajados >= 0",
            name="ck_agro_calendario_trabajados_no_negativos",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    periodo_id: Mapped[int] = mapped_column(
        ForeignKey("periodos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    centro_id: Mapped[int] = mapped_column(
        ForeignKey("agro_dimensiones.id"), nullable=False, index=True
    )

    dias_habiles: Mapped[Decimal] = mapped_column(Dias, nullable=False)
    dias_trabajados: Mapped[Decimal | None] = mapped_column(Dias)
    #: Fecha de corte con la que el usuario fijó `dias_trabajados`. Sin ella un
    #: número escrito a mano no se puede interpretar después.
    fecha_corte: Mapped[date | None] = mapped_column(Date)

    actualizado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))

    centro: Mapped[AgroDimension] = relationship(lazy="joined")

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<AgroCalendario centro={self.centro_id} habiles={self.dias_habiles}>"
