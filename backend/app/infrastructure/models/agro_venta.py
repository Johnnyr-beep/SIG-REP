"""Detalle de venta de la unidad Agropecuaria: la tabla caliente.

Grano de almacenamiento: **una fila por línea de factura**, tal como la entrega
`GET /ventas/agropecuaria`. Los agregados se calculan sobre ese detalle; guardar
totales impediría los dos cruces que el negocio pidió —vendedor × cliente y
vendedor × cliente × producto—, que solo existen si el detalle existe.

Dimensionamiento medido: 2120 filas en siete días, ~300 filas/día, ~9 000 al mes
y ~110 000 al año. Es **dos órdenes de magnitud menor** que carnes (5 millones
al año), y eso cambia una decisión de diseño: aquí los nombres de las
dimensiones se resuelven en memoria en lugar de con `JOIN`, porque el catálogo
entero cabe en un diccionario. La clave primaria sigue siendo `BigInteger` por
la misma razón que en carnes —migrarla en caliente no es algo que se quiera
descubrir un lunes—, pero el tamaño no obliga a nada más.

── Las tres columnas que no son obvias ───────────────────────────────────────

**1. `es_impuesto`.** `TipoItem = IMPUESTO` no es venta: es recaudo a nombre de
terceros. La decisión del negocio es que se **guarde marcado y se excluya al
reportar**, no que se descarte en la ingesta. Guardarlo permite conciliar fila a
fila con el origen y evita que nadie crea que se perdieron filas; excluirlo al
reportar es lo que hace que los totales, los porcentajes y la comparación contra
presupuesto digan la verdad.

Está desnormalizado en la línea, y no se resuelve con un `JOIN` a
`agro_dimensiones`, a propósito: **todas** las consultas del reporte lo filtran,
así que tiene que ser barato en todas. Con la bandera aquí, el filtro es una
columna del índice; con el `JOIN`, es una unión en cada una de las nueve
consultas del módulo, y la primera que se olvidara de ponerla publicaría el
impuesto como venta sin que nada fallara.

**2. `total_costo` es anulable.** `NULL` significa «la fuente no entregó el
costo» y `0` significa «costó cero». Son afirmaciones distintas y el reporte las
trata distinto: un agregado con una sola línea sin costo publica el margen como
«—», nunca un porcentaje calculado sobre una parte del conjunto. Es exactamente
la regla de §4.4, y quien la relaje «por limpieza» devuelve al tablero el 100 %
de margen inventado que costó una corrección entera en carnes.

**3. `lineas_facturadas` son LÍNEAS, no documentos.** Una venta de ocho
productos son ocho líneas y **un** documento. La fuente no entrega número ni
conteo de documentos, y esta columna no lo aproxima: se publica con su nombre y
nunca como «documentos» ni como «tickets». Publicar este conteo como documentos
daría, en el caso medido, una cifra varias veces mayor que la real.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.infrastructure.models.mixins import Dinero, Kilos, Porcentaje


class AgroVentaLinea(Base):
    """Una línea de factura del módulo agropecuario de SIESA (compañía 3).

    No hereda `TimestampMixin`: la trazabilidad temporal de la carga vive en
    `agro_corridas_ingesta`, y dos columnas de fecha por fila no aportarían nada
    que no esté ya en la corrida.
    """

    __tablename__ = "agro_venta_lineas"
    __table_args__ = (
        # ── La consulta caliente de todos los resúmenes ───────────────────────
        # `SELECT <dim>_id, SUM(...) FROM agro_venta_lineas
        #  WHERE periodo_id = ? AND fecha <= ? AND es_impuesto = 0 GROUP BY 1`
        # La columna de agrupación cambia con el eje pedido, así que no hay un
        # índice cubriente posible; lo que sí se puede cubrir —y es lo que
        # decide el coste— es el filtro completo, con la igualdad primero, el
        # rango después y la bandera del impuesto al final.
        Index("ix_agro_venta_periodo_fecha", "periodo_id", "fecha", "es_impuesto"),
        # Venta diaria y **borrado idempotente**: reprocesar un día reemplaza
        # ese día completo por centro de operación (§5).
        Index("ix_agro_venta_fecha_centro", "fecha", "centro_id"),
        # Los dos cruces que pidió el negocio entran los dos por aquí: el de dos
        # ejes usa el prefijo y el de tres añade el producto en Python.
        Index("ix_agro_venta_vendedor_cliente", "periodo_id", "vendedor_id", "cliente_id"),
        Index("ix_agro_venta_corrida", "corrida_id"),
    )

    #: `BigInteger` en los motores reales; `Integer` en SQLite, que solo
    #: autoincrementa sobre su `INTEGER PRIMARY KEY`. Mismo motivo que en
    #: `venta_lineas`: sin la variante la tabla es correcta en PostgreSQL y
    #: SQL Server e inservible en las pruebas.
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )

    #: Se reutiliza la tabla `periodos` de carnes, y es reutilización legítima y
    #: no un atajo: un período es un mes de operación con su bandera de cierre,
    #: no tiene nada de carnes dentro, y la regla de §7 —«un período cerrado no
    #: admite cambios de presupuesto»— es la misma para las dos unidades.
    periodo_id: Mapped[int] = mapped_column(ForeignKey("periodos.id"), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)

    # ── Las siete dimensiones, todas contra `agro_dimensiones` ────────────────
    #
    # `NOT NULL` en las siete, y no es rigidez: lo que llega vacío entra con su
    # miembro `SIN_DATO` y su etiqueta visible (`SIN GRUPO`, `SIN ESPECIE`…).
    # Una clave ajena anulable habría obligado a cada consulta a decidir por su
    # cuenta qué hacer con el nulo, y la primera que lo olvidara descartaría el
    # 22 % de las filas que no traen grupo.
    centro_id: Mapped[int] = mapped_column(ForeignKey("agro_dimensiones.id"), nullable=False)
    tipo_item_id: Mapped[int] = mapped_column(ForeignKey("agro_dimensiones.id"), nullable=False)
    especie_id: Mapped[int] = mapped_column(ForeignKey("agro_dimensiones.id"), nullable=False)
    tipo_comercial_id: Mapped[int] = mapped_column(
        ForeignKey("agro_dimensiones.id"), nullable=False
    )
    grupo_id: Mapped[int] = mapped_column(ForeignKey("agro_dimensiones.id"), nullable=False)
    vendedor_id: Mapped[int] = mapped_column(ForeignKey("agro_dimensiones.id"), nullable=False)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("agro_dimensiones.id"), nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("agro_dimensiones.id"), nullable=False)

    #: **La bandera del impuesto.** `True` = `TipoItem = IMPUESTO`: la fila se
    #: guarda para poder conciliar con el origen y **no suma en ningún reporte**.
    #: Ver el encabezado del módulo antes de quitarla o de convertirla en un
    #: `JOIN`.
    es_impuesto: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ── Medidas ───────────────────────────────────────────────────────────────

    #: `CantidadInv`: unidades del ítem. No son kilos; los kilos van aparte.
    cantidad_inv: Mapped[Decimal] = mapped_column(Kilos, nullable=False)
    #: `KilosTotal`. El negocio mide en pesos **y** en kilos (§4.5).
    kilos_total: Mapped[Decimal] = mapped_column(Kilos, nullable=False)

    #: `ValorBruto`, `Descuentos` y `ValorSubtotal` se guardan enteros para
    #: poder conciliar la cadena `bruto − descuentos = subtotal` con el origen,
    #: y para el análisis de descuento que el negocio va a pedir el día que vea
    #: la columna. **Ninguno de los tres es la venta del reporte**: ver
    #: `total_neto`.
    valor_bruto: Mapped[Decimal] = mapped_column(Dinero, nullable=False)
    descuentos: Mapped[Decimal] = mapped_column(Dinero, nullable=False)
    valor_subtotal: Mapped[Decimal] = mapped_column(Dinero, nullable=False)
    #: **La venta.** Es la medida que se compara contra el presupuesto y con la
    #: que se calculan el cumplimiento, la proyección y el margen.
    #: SUPUESTO MARCADO (`docs/ESPECIFICACION.md` §11): el negocio no precisó
    #: cuál de los cuatro importes es «la venta» y se eligió el **neto**, que es
    #: lo que la compañía factura y lo que hace que `UtilidadBruta` cuadre como
    #: `TotalNeto − TotalCosto`. Cambiarlo es cambiar `COLUMNA_VENTA` en
    #: `agro_reportes_service.py`; los otros tres importes ya están persistidos.
    total_neto: Mapped[Decimal] = mapped_column(Dinero, nullable=False)

    #: `TotalCosto`. **Anulable**: `NULL` es «la fuente no lo entregó» y `0` es
    #: «costó cero». Ver el punto 2 del encabezado.
    total_costo: Mapped[Decimal | None] = mapped_column(Dinero)
    #: `UtilidadBruta` tal como la envía SIESA. **Solo para conciliación**: el
    #: margen del reporte se recalcula ponderado sobre los totales y jamás sale
    #: de esta columna (§4.4).
    utilidad_bruta: Mapped[Decimal | None] = mapped_column(Dinero)
    #: `%` de rentabilidad si alguna vez llega. Hoy la fuente no lo trae y viaja
    #: nulo; existe para no tener que migrar la tabla el día que aparezca.
    margen_siesa: Mapped[Decimal | None] = mapped_column(Porcentaje)

    #: `LineasFacturadas`. **Líneas, no documentos.** Ver el punto 3.
    lineas_facturadas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    #: Texto crudo del tipo de ítem, conservado junto a la bandera ya resuelta.
    #: Sin él no se puede auditar por qué una fila quedó marcada como impuesto.
    tipo_item_siesa: Mapped[str | None] = mapped_column(String(60))

    corrida_id: Mapped[int | None] = mapped_column(ForeignKey("agro_corridas_ingesta.id"))

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<AgroVentaLinea {self.fecha} centro={self.centro_id} {self.total_neto}>"
