"""Catálogo de dimensiones de la unidad Agropecuaria.

Una **sola** tabla con discriminador, `agro_dimensiones`, en lugar de ocho
tablas casi idénticas (`agro_vendedores`, `agro_especies`, `agro_clientes`…).
Las ocho tendrían exactamente la misma forma —llave del origen, nombre— y la
única diferencia sería el nombre de la tabla, que es justamente el dato que el
presupuesto necesita manipular como valor: `agro_presupuestos.dimension` es una
columna, no un nombre de tabla, y con ocho tablas habría que traducir de una a
otra en cada consulta.

Cardinalidad real medida sobre siete días (2120 filas):

| Dimensión | Distintos |
|---|---:|
| Centro de operación | 2 (301 Planta, 302 Montería) |
| Tipo de ítem | 4 (BIENES, SERVICIOS, IMPUESTO…) |
| Especie | 6 (RES, CERDO, CARNES FRIAS, VIVERES…) |
| Tipo comercial | 14 (CORTE, SUBPRODUCTO, SACRIFICIO, CANAL, DESPOSTE…) |
| Grupo | 9 (A–F, DESPOSTE, SACRIFICIO) **+ SIN GRUPO** |
| Vendedor | 21 |
| Cliente | 626 |
| Producto | 252 |

Poco más de novecientas filas en total. Eso permite algo que en carnes no se
puede hacer: **el reporte no une esta tabla con la venta**. La consulta caliente
agrupa por los `*_id` enteros de `agro_venta_lineas` y los nombres se resuelven
en memoria contra un diccionario cargado una vez. Un cruce de tres dimensiones
—vendedor × cliente × producto— necesitaría tres `JOIN` a la misma tabla, y
resolverlo en Python es más rápido y se lee mejor.

── Por qué el cliente se identifica por su nombre ────────────────────────────

`GET /ventas/agropecuaria` **no entrega el NIT del cliente**: la única columna
de cliente es `Cliente`, con la razón social. La llave es por tanto el nombre
normalizado, y eso tiene una consecuencia que hay que decir en voz alta: **dos
clientes distintos con la misma razón social en el origen son uno solo aquí.**
Es una limitación de la fuente, no una decisión de diseño, y se pide junto al
resto en `docs/API.md`. Inventar una llave sintética no arreglaría nada: al
reingerir el mismo día se generaría otra distinta para el mismo cliente.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.infrastructure.models.agro_vocabulario import TipoDimension
from app.infrastructure.models.mixins import TimestampMixin


class AgroDimension(Base, TimestampMixin):
    """Un miembro de cualquiera de las ocho dimensiones agropecuarias.

    `tipo` dice de qué dimensión es, `clave` es su identificador normalizado tal
    como viene del origen (`CO_Id`, `Especie_Id`, `CodigoVendedor`,
    `Item_Ref`…) y `nombre` es la etiqueta legible (`CentroOperacion`,
    `Especie`, `NombreVendedor`, `Item_Desc`).

    Los miembros se dan de alta **durante la ingesta**, no por una semilla: el
    catálogo de agropecuaria no lo fija el negocio de antemano —626 clientes y
    252 productos que cambian solos— y sembrarlo obligaría a mantener a mano una
    lista que el ERP ya mantiene.

    `nombre` no es único y no debe serlo: dos especies pueden llamarse igual en
    dos momentos distintos y la llave es `clave`. Lo que sí es único es el par
    `(tipo, clave)`, que es la identidad real de un miembro.
    """

    __tablename__ = "agro_dimensiones"
    __table_args__ = (
        UniqueConstraint("tipo", "clave", name="uq_agro_dimension_tipo_clave"),
        # Lista de un catálogo por pantalla: `WHERE tipo = ? ORDER BY nombre`.
        Index("ix_agro_dimension_tipo_nombre", "tipo", "nombre"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    #: Valor de `TipoDimension`. Cadena explícita y no `Enum` del motor: añadir
    #: una dimensión no puede exigir una migración de tipo en PostgreSQL.
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    #: Identificador normalizado (mayúsculas, sin tildes, espacios colapsados).
    #: `SIN_DATO` cuando la fuente no lo entrega; ver `normalizar_clave`.
    clave: Mapped[str] = mapped_column(String(60), nullable=False)
    #: Etiqueta legible. Es lo que pinta la pantalla; la `clave` es para cruzar.
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    #: Orden de presentación. Cero para todo lo que llega de la ingesta; el
    #: negocio puede fijarlo por catálogo cuando quiera un orden propio.
    orden: Mapped[int] = mapped_column(default=0, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    @property
    def dimension(self) -> TipoDimension:
        return TipoDimension(self.tipo)

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<AgroDimension {self.tipo}:{self.clave}>"
