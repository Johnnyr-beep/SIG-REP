"""Detalle de venta y catálogo de clientes (§3.4).

`venta_lineas` es la tabla caliente del sistema y la que dicta el diseño de
índices de todo el esquema. Dimensionamiento real medido sobre el archivo de
SIESA: **131 819 filas para 9 días**, es decir ~14 600 filas/día,
~440 000 filas/mes y **más de 5 millones de filas al año**. Con la historia de
2025 cargada para el indicador de crecimiento, son diez millones largos.

De ahí tres decisiones:

1. `id` es `BigInteger`: un `Integer` de 32 bits se agota a los 2 100 millones y
   migrar la clave primaria de una tabla de ese tamaño en caliente no es algo
   que se quiera descubrir un lunes.
2. `periodo_id` está **desnormalizado** en la línea. Se podría derivar de
   `fecha`, pero la consulta caliente del reporte filtra por período y agrupa
   por (punto de venta, categoría); tenerlo como columna permite que un solo
   índice compuesto sirva el `WHERE` y el `GROUP BY` sin tocar la tabla.
3. Los índices están pensados para las tres consultas del reporte, no «por si
   acaso». Cada índice de más es escritura más lenta en una ingesta de medio
   millón de filas mensuales.

Sobre PostgreSQL, cuando la tabla supere unos pocos años, el paso natural es
particionar por rango de `fecha` (una partición por año o por trimestre). El
modelo no lo impone porque los tipos deben seguir siendo genéricos para SQL
Server, pero el esquema ya está listo: la clave de partición sería `fecha` y
ningún índice único la contradice.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.infrastructure.models.mixins import (
    Dinero,
    Kilos,
    Porcentaje,
    TimestampMixin,
)

if TYPE_CHECKING:
    from app.infrastructure.models.catalogo import Categoria
    from app.infrastructure.models.organizacion import PuntoVenta


class Cliente(Base, TimestampMixin):
    """Catálogo de clientes (hoja `CLIENTES`, 451 registros).

    Aporta el canal y el vendedor asignado, que es lo que habilita el reporte
    por vendedor —hoy inexistente en el Excel y claramente deseado por el
    negocio—.
    """

    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(primary_key=True)
    #: NIT. Llega de SIESA con espacios de relleno a la derecha; se persiste ya
    #: con `strip()` aplicado.
    nit: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    razon_social: Mapped[str | None] = mapped_column(String(200))
    canal: Mapped[str | None] = mapped_column(String(40), index=True)
    vendedor: Mapped[str | None] = mapped_column(String(120), index=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<Cliente {self.nit}>"


class VentaLinea(Base):
    """Una línea de venta de SIESA, en su grano original.

    No hereda `TimestampMixin`: dos columnas de fecha por fila, multiplicadas
    por millones de filas, son megabytes que no aportan nada —la trazabilidad
    temporal de la carga vive en `corridas_ingesta`—.
    """

    __tablename__ = "venta_lineas"
    __table_args__ = (
        # ── La consulta caliente ──────────────────────────────────────────────
        # `SELECT punto_venta_id, categoria_id, SUM(...) FROM venta_lineas
        #  WHERE periodo_id = ? AND fecha <= ? GROUP BY 1, 2`
        # El orden de las columnas es el que importa: primero la igualdad, luego
        # el rango, luego las claves de agrupación.
        Index(
            "ix_venta_periodo_pdv_categoria",
            "periodo_id",
            "fecha",
            "punto_venta_id",
            "categoria_id",
        ),
        # Reporte de venta diaria: detalle día por día del mes por punto.
        Index("ix_venta_fecha_pdv", "fecha", "punto_venta_id"),
        # Reporte de clientes y vendedores.
        Index("ix_venta_periodo_cliente", "periodo_id", "cliente_id"),
        # Borrado idempotente: reprocesar un día borra ese día completo por
        # (fecha, punto de venta) antes de insertar (§5).
        Index("ix_venta_corrida", "corrida_id"),
    )

    #: `BigInteger` en los motores reales; `Integer` en SQLite, que solo
    #: autoincrementa sobre su `INTEGER PRIMARY KEY` y con `BIGINT` deja el `id`
    #: en nulo. Sin la variante, la tabla es correcta en PostgreSQL y SQL Server
    #: pero inservible en las pruebas.
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )

    periodo_id: Mapped[int] = mapped_column(ForeignKey("periodos.id"), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    punto_venta_id: Mapped[int] = mapped_column(ForeignKey("puntos_venta.id"), nullable=False)
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"), nullable=False)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.id"))
    corrida_id: Mapped[int | None] = mapped_column(ForeignKey("corridas_ingesta.id"))

    #: `Valor subtotal` de SIESA. Es **la** medida contra presupuesto.
    valor_subtotal: Mapped[Decimal] = mapped_column(Dinero, nullable=False)
    #: `Costo promedio` de la línea. Insumo del margen ponderado (§4.4).
    #:
    #: **Anulable a propósito. No es una relajación de la integridad: es la
    #: única forma de no publicar un número falso.** `GET
    #: /ventas/pos-vendedor-detalle` —el único endpoint donde registra 409
    #: PEREIRA, el segundo punto de venta de la compañía— **no entrega el
    #: costo**: llega vacío en el 100 % de sus filas. Mientras esta columna fue
    #: `NOT NULL`, esas líneas entraban con costo cero y §4.4 calculaba
    #: `margen = (Σ subtotal − 0) / Σ subtotal` = **100 %** para PEREIRA. Un
    #: 100 % de margen no es una cifra alta: es una cifra falsa, y llega a la
    #: pantalla donde alguien decide.
    #:
    #: `NULL` significa «la fuente no entregó el costo» y `0` significa «costó
    #: cero», que son afirmaciones distintas y el reporte las trata distinto: un
    #: agregado que contenga una sola línea sin costo publica el margen como
    #: `None` —«—» en pantalla—, mientras que el resto de sus indicadores se
    #: calculan con toda normalidad (ver `app/domain/indicadores.py`).
    #:
    #: Quien vuelva a ponerla `NOT NULL` «por limpieza» reintroduce ese 100 %
    #: inventado en el consolidado de la compañía.
    costo_promedio: Mapped[Decimal | None] = mapped_column(Dinero)
    #: `Cantidad inv.` de SIESA: los kilos. Admite decimales (370.83).
    cantidad_inv: Mapped[Decimal] = mapped_column(Kilos, nullable=False)

    #: `MARGEN` tal como lo envía SIESA. **Solo para conciliación**: el margen
    #: del reporte se recalcula sobre los totales y jamás promediando esto.
    margen_siesa: Mapped[Decimal | None] = mapped_column(Porcentaje)

    #: Texto crudo de la categoría de SIESA, conservado junto a la clasificación
    #: ya resuelta. Sin él no se puede auditar un mapeo mal hecho.
    categoria_siesa: Mapped[str | None] = mapped_column(String(120))
    #: NIT tal como venía en la fila, incluso si no existe en el catálogo de
    #: clientes: la venta nunca se descarta por un cliente desconocido.
    nit_cliente: Mapped[str | None] = mapped_column(String(30))

    #: `Si`/`No` de SIESA, ya normalizado. `NULL` para las 28 filas en blanco
    #: del archivo actual: no se inventa un `False` que nadie afirmó.
    domicilio: Mapped[bool | None] = mapped_column(Boolean)
    #: Columna sucia en origen. Los valores fuera del catálogo entran como
    #: `SIN CLASIFICAR` y quedan registrados en la bitácora de ingesta (§3.4).
    clase_cliente: Mapped[str | None] = mapped_column(String(60))
    condicion_pago: Mapped[str | None] = mapped_column(String(10), index=True)

    punto_venta: Mapped[PuntoVenta] = relationship(lazy="raise")
    categoria: Mapped[Categoria] = relationship(lazy="raise")

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<VentaLinea {self.fecha} pdv={self.punto_venta_id} {self.valor_subtotal}>"
