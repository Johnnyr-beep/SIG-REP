"""Puertos del dominio: la frontera con los sistemas de afuera (§5).

**La API de SIESA todavía no se ha entregado.** Por eso SIGREP no se diseña
contra ella sino contra este puerto. Cambiar de la fuente Excel a la fuente
SIESA debe ser una variable de entorno (`SIGREP_FUENTE_VENTA`), no un refactor.

Este módulo es el contrato que el agente de ingesta implementa. Está pensado
para ser estable: si algo aquí cambia, cambia también el trabajo de todos los
que dependen de él, así que se añaden campos antes que renombrarlos.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class LineaVenta:
    """Una línea de detalle de venta tal como la entrega la fuente.

    Es el grano de almacenamiento que exige §3.4: detalle de transacción. Los
    agregados se calculan sobre él; guardar solo el total impediría el análisis
    por cliente y por categoría que el negocio ya hace.

    Los campos llegan **crudos**, tal como los da la fuente. La normalización
    documentada en §3.4 es responsabilidad de la ingesta, no de la fuente:

    - `centro_operacion` llega como `'606'` y como `606` según la fila; se
      normaliza a texto de tres posiciones con ceros a la izquierda.
    - `nit_cliente` llega con espacios de relleno a la derecha; se hace `strip`.
    - `clase_cliente` viene corrupta (95 907 filas vacías, nombres de persona y
      marcas de tiempo): solo se aceptan valores del catálogo y el resto se
      registra como `SIN CLASIFICAR` dejando constancia en la bitácora.
    - `categoria_siesa` se mapea contra la tabla `mapeo_categorias`, que incluye
      las dos variantes ortográficas de `0006`.

    `margen_siesa` se conserva **solo para conciliación** (§4.4): el margen del
    reporte se recalcula ponderado sobre los totales.
    """

    centro_operacion: str
    fecha: date
    valor_subtotal: Decimal
    #: `None` cuando **la fuente no entrega el costo**, que es el caso de
    #: `GET /ventas/pos-vendedor-detalle` —el endpoint de 409 PEREIRA— en el
    #: 100 % de sus filas. No es lo mismo que `Decimal("0")`: aquel afirma que
    #: vender no costó nada y este dice que nadie lo sabe. La distinción viaja
    #: intacta hasta `venta_lineas.costo_promedio`, que es anulable por eso, y
    #: decide si §4.4 publica el margen o pinta «—». Una fuente que rellene esto
    #: con cero devuelve el sistema al 100 % de margen inventado.
    costo_promedio: Decimal | None
    cantidad_inv: Decimal
    categoria_siesa: str | None = None
    nit_cliente: str | None = None
    razon_social: str | None = None
    margen_siesa: Decimal | None = None
    domicilio: str | None = None
    clase_cliente: str | None = None
    condicion_pago: str | None = None
    #: Vendedor de la línea, tal como lo entrega la API de SIESA
    #: (`codigo_vendedor` / `nombre_vendedor`). El libro de Excel no los trae y
    #: la API sí, en los dos endpoints; se transportan aquí para no perderlos en
    #: la frontera. **Todavía no se persisten**: `venta_lineas` no tiene columnas
    #: de vendedor y hoy el reporte por vendedor se resuelve por el catálogo de
    #: clientes. Guardarlos por línea es lo que permitirá el reporte por vendedor
    #: del POS, donde la venta es anónima y no hay cliente al que colgarla.
    codigo_vendedor: str | None = None
    nombre_vendedor: str | None = None
    #: Número de fila en el origen. Es lo que hace útil un rechazo: sin él, el
    #: usuario sabe que algo falló pero no dónde mirar.
    fila_origen: int | None = None


@runtime_checkable
class FuenteVenta(Protocol):
    """Origen de la venta. Implementaciones previstas en §5.

    1. `FuenteVentaExcel` — lee el libro actual. Permite tener el sistema
       funcionando y validado contra el Excel antes de que llegue la API.
    2. `FuenteVentaSiesa` — se implementa cuando llegue la especificación.

    La ingesta que consume este puerto es **idempotente**: reprocesar un día
    reemplaza ese día completo, no duplica (§5 y §7).
    """

    def obtener_ventas(
        self,
        desde: date,
        hasta: date,
        centros: Sequence[str] | None = None,
    ) -> Iterable[LineaVenta]:
        """Devuelve las líneas de venta del rango, ambos extremos incluidos.

        `centros` filtra por C.O.; `None` significa todos. El resultado se
        devuelve como iterable perezoso a propósito: son ~130 000 filas por cada
        nueve días y materializar un año entero en memoria no es una opción.
        """
        ...
