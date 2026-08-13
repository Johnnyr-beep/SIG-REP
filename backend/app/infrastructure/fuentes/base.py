"""Piezas comunes a las fuentes de venta.

El puerto `FuenteVenta` (§5) devuelve `Iterable[LineaVenta]`, y eso deja una
pregunta abierta: **¿por dónde sale una fila que la fuente no pudo ni siquiera
formar?** Una fila cuya fecha es ilegible no cabe en un `LineaVenta` —el campo
está tipado `date`— y descartarla en silencio rompe la regla de §5: «cada
corrida deja registro de filas leídas, aceptadas, rechazadas y el motivo de cada
rechazo».

La solución es esta: la fuente sigue devolviendo el iterable que promete el
puerto y **acumula aparte** las filas que no pudo formar, en `rechazos`. La
ingesta las recoge al terminar de consumir el iterable y las vuelca en la
bitácora junto a los rechazos que detecta ella misma (punto de venta
desconocido, por ejemplo). El puerto no cambia y nada se pierde.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class RechazoFuente:
    """Una fila que la fuente no pudo convertir en `LineaVenta`."""

    fila: int | None
    campo: str | None
    valor: str | None
    motivo: str


@dataclass(frozen=True, slots=True)
class AnotacionFuente:
    """Algo que la fuente necesita contar y que **no** es un rechazo.

    La misma distinción que hace `BitacoraIngesta`, un piso más abajo: hay cosas
    que la fuente sabe y que nadie más puede saber —de qué `Origen` de SIESA
    vino cada fila, que PEREIRA no trae costo— y que no son filas perdidas.
    Meterlas por `rechazos` haría que `leidas = aceptadas + rechazadas` dejara de
    cuadrar y diría que se perdió venta que no se perdió.

    La ingesta las recoge junto a los rechazos y las manda a `bitacora.anotar`.
    """

    fila: int | None
    campo: str | None
    valor: str | None
    motivo: str


@dataclass(frozen=True, slots=True)
class ClienteFuente:
    """Un registro del catálogo de clientes (hoja `CLIENTES`, §3.4).

    Aporta el **canal** y el **vendedor asignado**, que es lo que habilita el
    reporte por vendedor. Los campos llegan crudos: el NIT viene como número en
    esta hoja y como texto rellenado en la de venta, y conciliarlos es trabajo
    de la ingesta, no de la fuente.
    """

    nit: object
    razon_social: object = None
    canal: object = None
    vendedor: object = None
    fila_origen: int | None = None


@runtime_checkable
class FuenteConClientes(Protocol):
    """Fuente que además del detalle de venta entrega el catálogo de clientes.

    No forma parte del puerto `FuenteVenta` a propósito: la venta la va a servir
    SIESA por API y el catálogo puede perfectamente seguir viniendo de otro
    lado. Quien lo tenga, lo declara implementando este protocolo.
    """

    def obtener_clientes(self) -> Iterable[ClienteFuente]:
        """Registros del catálogo de clientes disponibles en el origen."""
        ...
