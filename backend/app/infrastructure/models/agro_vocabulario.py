"""Vocabulario de la unidad Agropecuaria: dimensiones, ejes y llaves.

Módulo **puro**: sin SQLAlchemy, sin Pydantic, sin base de datos. Lo importan
los modelos, los servicios, los esquemas y el router, y por eso no puede
depender de ninguno de ellos.

── Por qué agropecuaria no reutiliza el modelo de carnes ─────────────────────

Carnes mide **punto de venta × categoría** contra presupuesto. Agropecuaria mide
**vendedor, cliente, especie, tipo comercial y centro de operación**. No son la
misma cosa con otros nombres: son dimensiones distintas, con cardinalidades
distintas (626 clientes y 21 vendedores frente a 16 puntos y 11 categorías) y
con un presupuesto que se fija por **varias** de ellas a la vez. Forzar el
esquema de carnes obligaría a llamar «punto de venta» a un vendedor y
«categoría» a una especie, y a partir de ahí ninguna consulta se lee.

── Las cuatro dimensiones del presupuesto, y la trampa que evitan ────────────

`DimensionPresupuesto` tiene exactamente cuatro miembros, y cada uno describe
**el mismo dinero repartido de otra forma**: la meta de la compañía vista por
vendedor, por centro de operación, por especie o por tipo comercial.

De ahí la regla que gobierna todo el módulo de presupuesto:

    **Dos presupuestos de dimensiones distintas NO se suman.**

Sumar el presupuesto por vendedor con el presupuesto por especie da el doble de
la meta real. El sistema no lo advierte: lo hace **imposible**. Ver
`app/application/services/agro_presupuesto_service.py`, donde el presupuesto
solo existe dentro de un `PlanPresupuesto` que lleva su dimensión pegada y se
niega a operar con un plan de otra.

── Los valores en blanco no se reparten y no se esconden ─────────────────────

El origen trae el grupo vacío en el 22 % de las filas, y la especie, el tipo
comercial y el tipo de ítem en un 1 %. Ninguno se descarta, ninguno se reparte
entre los demás y ninguno se adivina: entran con una etiqueta visible
(`SIN GRUPO`, `SIN ESPECIE`…) que aparece como una fila más del reporte. Es la
misma regla de §7: «nunca se descarta en silencio».
"""

from __future__ import annotations

import re
import unicodedata
from enum import StrEnum


#: Tipos de miembro de `agro_dimensiones`. Es una sola tabla con discriminador
#: en lugar de siete tablas casi idénticas: las siete tienen exactamente la
#: misma forma —llave del origen y nombre— y la que de verdad importa, la
#: dimensión, pasa a ser un dato de primera clase en vez de un nombre de tabla.
class TipoDimension(StrEnum):
    """Las siete dimensiones por las que se puede leer la venta agropecuaria."""

    CENTRO_OPERACION = "centro_operacion"
    TIPO_ITEM = "tipo_item"
    ESPECIE = "especie"
    TIPO_COMERCIAL = "tipo_comercial"
    GRUPO = "grupo"
    VENDEDOR = "vendedor"
    CLIENTE = "cliente"
    ITEM = "item"

    @property
    def etiqueta(self) -> str:
        return _ETIQUETAS_DIMENSION[self]


_ETIQUETAS_DIMENSION: dict[TipoDimension, str] = {
    TipoDimension.CENTRO_OPERACION: "Centro de operación",
    TipoDimension.TIPO_ITEM: "Tipo de ítem",
    TipoDimension.ESPECIE: "Especie",
    TipoDimension.TIPO_COMERCIAL: "Tipo comercial",
    TipoDimension.GRUPO: "Grupo",
    TipoDimension.VENDEDOR: "Vendedor",
    TipoDimension.CLIENTE: "Cliente",
    TipoDimension.ITEM: "Producto",
}


class DimensionPresupuesto(StrEnum):
    """Las cuatro descomposiciones por las que el negocio fija presupuesto.

    **Son cuatro vistas del mismo total, no cuatro totales.** El presupuesto por
    vendedor y el presupuesto por especie describen el mismo dinero; sumarlos da
    el doble. El cumplimiento se calcula siempre *dentro* de una dimensión.

    Es un enum aparte de `TipoDimension` y no un subconjunto suyo por una razón
    concreta: `TipoDimension` dice «por aquí se puede leer la venta» y esto dice
    «por aquí se puede fijar la meta». Cliente, producto, grupo y tipo de ítem
    son buenos ejes de lectura y **no** son ejes de presupuesto —nadie
    presupuesta 626 clientes—, y tenerlos en el mismo enum invitaría a
    presupuestar por cualquiera de ellos con solo pasar el valor.
    """

    VENDEDOR = "vendedor"
    CENTRO_OPERACION = "centro_operacion"
    ESPECIE = "especie"
    TIPO_COMERCIAL = "tipo_comercial"

    @property
    def tipo(self) -> TipoDimension:
        """El eje de lectura equivalente, para cruzar meta con venta."""
        return TipoDimension(self.value)

    @property
    def etiqueta(self) -> str:
        return self.tipo.etiqueta


#: Los cuatro valores admitidos en `agro_presupuestos.dimension`, tal como los
#: fija el `CHECK` de la tabla. Se declara aquí para que la migración y el
#: modelo digan lo mismo sin copiarse a mano.
DIMENSIONES_PRESUPUESTO: tuple[str, ...] = tuple(d.value for d in DimensionPresupuesto)


class EjeResumen(StrEnum):
    """Ejes del reporte de resumen: los siete que pidió el negocio."""

    CENTRO_OPERACION = "centro_operacion"
    TIPO_ITEM = "tipo_item"
    ESPECIE = "especie"
    TIPO_COMERCIAL = "tipo_comercial"
    GRUPO = "grupo"
    VENDEDOR = "vendedor"
    CLIENTE = "cliente"

    @property
    def tipo(self) -> TipoDimension:
        return TipoDimension(self.value)

    @property
    def dimension_presupuesto(self) -> DimensionPresupuesto | None:
        """La dimensión de presupuesto de este eje, si la tiene.

        `None` en cliente, grupo y tipo de ítem: son ejes de lectura y no de
        meta. Sus filas publican venta, kilos y margen, y todo lo que dependa
        del presupuesto viaja vacío —«—»—, nunca en cero.
        """
        try:
            return DimensionPresupuesto(self.value)
        except ValueError:
            return None


class EjeCruce(StrEnum):
    """Los dos cruces que pidió el negocio, y solo esos dos.

    Es un enum cerrado y no una lista de ejes componibles a propósito: un cruce
    de tres dimensiones sobre 626 clientes y 252 productos ya es una tabla de
    decenas de miles de filas, y dejar que la petición componga cinco produciría
    una consulta que nadie quiso pedir.
    """

    VENDEDOR_CLIENTE = "vendedor-cliente"
    VENDEDOR_CLIENTE_PRODUCTO = "vendedor-cliente-producto"

    @property
    def tipos(self) -> tuple[TipoDimension, ...]:
        if self is EjeCruce.VENDEDOR_CLIENTE:
            return (TipoDimension.VENDEDOR, TipoDimension.CLIENTE)
        return (TipoDimension.VENDEDOR, TipoDimension.CLIENTE, TipoDimension.ITEM)


# ── Tipo de ítem: el impuesto se guarda y no se suma ──────────────────────────

#: Valor de `TipoItem` que **no es venta**: es recaudo a nombre de terceros.
#:
#: DECISIÓN DEL NEGOCIO. Las filas de impuesto se **ingieren y se guardan
#: marcadas** (`agro_venta_lineas.es_impuesto`), y se excluyen de todo total,
#: de todo porcentaje y de toda comparación contra presupuesto. Guardarlas es
#: lo que permite conciliar con el origen fila a fila; descartarlas en la
#: ingesta dejaría un hueco que parecería venta perdida.
TIPO_ITEM_IMPUESTO = "IMPUESTO"

# ── Etiquetas de lo que llega vacío ───────────────────────────────────────────

#: El grupo llega vacío en el **22 %** de las filas. Se reporta con esta
#: etiqueta, visible como una fila más, y nunca se reparte entre los grupos que
#: sí tienen valor: repartirlo movería una quinta parte de la venta a renglones
#: que no la hicieron.
SIN_GRUPO = "SIN GRUPO"
SIN_ESPECIE = "SIN ESPECIE"
SIN_TIPO_COMERCIAL = "SIN TIPO COMERCIAL"
SIN_TIPO_ITEM = "SIN TIPO DE ITEM"
SIN_VENDEDOR = "SIN VENDEDOR"
SIN_CLIENTE = "SIN CLIENTE"
SIN_ITEM = "SIN PRODUCTO"
SIN_CENTRO = "SIN CENTRO"

ETIQUETA_VACIA: dict[TipoDimension, str] = {
    TipoDimension.CENTRO_OPERACION: SIN_CENTRO,
    TipoDimension.TIPO_ITEM: SIN_TIPO_ITEM,
    TipoDimension.ESPECIE: SIN_ESPECIE,
    TipoDimension.TIPO_COMERCIAL: SIN_TIPO_COMERCIAL,
    TipoDimension.GRUPO: SIN_GRUPO,
    TipoDimension.VENDEDOR: SIN_VENDEDOR,
    TipoDimension.CLIENTE: SIN_CLIENTE,
    TipoDimension.ITEM: SIN_ITEM,
}

#: Llave con la que entra un miembro sin identificador en el origen. Es la misma
#: para las ocho dimensiones y es un texto reconocible a simple vista: quien vea
#: `SIN_DATO` en una respuesta sabe que la fuente no dijo nada, no que alguien
#: bautizó así a un vendedor.
CLAVE_VACIA = "SIN_DATO"

#: `AGROPECUARIA SANTACRUZ LTDA` factura como vendedor y concentra el 58 % de la
#: venta. **Es un vendedor legítimo**: no es «sin asignar», no se excluye de los
#: totales y no se reparte entre los otros veinte. Se nombra aquí para que quede
#: dicho por escrito y para que la prueba que lo fija tenga de dónde importarlo.
VENDEDOR_CASA = "AGROPECUARIA SANTACRUZ LTDA"

#: Espacios que hay que recortar, incluidos el no separable (U+00A0) y el de
#: ancho cero (U+200B), que llegan pegados a los textos que alguien pegó desde
#: una hoja de cálculo y que no se ven al mirar la celda. Se escriben escapados
#: justamente porque son invisibles.
_ESPACIOS = " \t\r\n\xa0\u200b"
_MULTIESPACIO = re.compile(r"\s+")


def sin_acentos(texto: str) -> str:
    """Quita las tildes conservando el resto."""
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(caracter for caracter in descompuesto if not unicodedata.combining(caracter))


def normalizar_etiqueta(valor: object, limite: int = 200) -> str | None:
    """Nombre legible saneado: sin espacios de relleno ni dobles espacios.

    `None` cuando no queda nada. Un `'   '` de relleno del ERP está tan vacío
    como un `None` y se trata igual.
    """
    if valor is None:
        return None
    crudo = _a_texto(valor).strip(_ESPACIOS)
    if not crudo:
        return None
    return _MULTIESPACIO.sub(" ", crudo)[:limite]


def normalizar_clave(tipo: TipoDimension, valor: object, limite: int = 60) -> str:
    """Llave comparable de un miembro de dimensión.

    Mayúsculas, sin tildes y con los espacios colapsados, y para el centro de
    operación además rellenada a tres posiciones: `301` y `'301'` conviven en el
    origen igual que en carnes, y sin normalizar Planta aparecería dos veces.

    Devuelve `CLAVE_VACIA` cuando no hay identificador, en lugar de `None`: es
    una llave real, con su etiqueta visible, y así el resto del código nunca
    tiene que preguntarse si la dimensión de una fila existe.

    **Nada de parecidos.** No hay distancia de edición ni prefijos: dos códigos
    que se parecen son dos miembros distintos, y asimilarlos movería venta de un
    vendedor a otro sin que nadie lo notara.
    """
    crudo = normalizar_etiqueta(valor, limite=limite)
    if crudo is None:
        return CLAVE_VACIA
    if crudo.endswith(".0") and crudo[:-2].isdigit():
        crudo = crudo[:-2]
    clave = sin_acentos(crudo).upper()
    if tipo is TipoDimension.CENTRO_OPERACION and clave.isdigit():
        clave = clave.zfill(3)
    return clave[:limite]


def es_impuesto(tipo_item: object) -> bool:
    """¿Esta fila es recaudo de impuesto y no venta?

    Se compara contra el valor **afirmado** por la fuente, no contra un parecido
    ni contra la ausencia de dato: una fila sin `TipoItem` no es un impuesto,
    es una fila sin tipo, y excluirla de la venta por si acaso costaría venta
    real.
    """
    return normalizar_clave(TipoDimension.TIPO_ITEM, tipo_item) == TIPO_ITEM_IMPUESTO


def _a_texto(valor: object) -> str:
    """`301.0` → `'301'`; el resto, `str()` a secas."""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor)
