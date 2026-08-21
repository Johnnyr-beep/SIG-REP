"""`FuenteVentaAgropecuaria`: la venta del módulo agropecuario de SIESA.

Lee `GET /ventas/agropecuaria` de `https://apiconsulta.grupo-santacruz.com` con
**`id_cia=3`**, que es la compañía `AGROPECUARIA SANTACRUZ LTDA`.

── Por qué es un puerto nuevo y no `FuenteVenta` ─────────────────────────────

`app/domain/puertos.py` define `LineaVenta` con la forma de la venta de carnes:
centro de operación, categoría, NIT de cliente, condición de pago, domicilio.
La venta agropecuaria trae **28 campos y otras dimensiones**: vendedor, especie,
tipo comercial, tipo de ítem, grupo y producto, y no trae NIT, ni condición de
pago, ni domicilio. Forzarla dentro de `LineaVenta` significaría o ampliar el
contrato que carnes tiene en producción, o meter cinco dimensiones dentro de
campos que se llaman otra cosa. `LineaAgro` es el mismo patrón —una fila cruda
de la fuente, sin ORM— aplicado al negocio que le corresponde.

── Las trampas que hay que conocer antes de tocar este archivo ───────────────

**1. `fecha_fin` es INCLUSIVA.** `hasta` viaja tal cual, sin sumarle un día. Es
lo mismo que hace `costos-razon-social` —cuyo contrato lo declara— y lo
contrario de lo que documenta `/ventas/poscarnes`, así que cualquiera que llegue
de leer aquel contrato va a «arreglarlo». Ese arreglo mete el 1 de septiembre
dentro de agosto y el cierre sale largo. Lo fija
`test_fecha_fin_es_inclusiva_y_no_se_le_suma_un_dia`, que además comprueba que
una fila del propio `hasta` sí se carga.

Como comprobación adicional en ejecución: **una fila fuera del rango pedido no
se carga y queda anotada en la bitácora**. Si algún día la API cambiara de
criterio, la corrida lo dice en lugar de meter un día de más en silencio.

**2. `id_cia=3` y solo la 3.** La compañía 3 es la unidad agropecuaria. Las
compañías de carnes —4, 6 y 7— se reportan en la otra instancia y **no se
mezclan**: son negocios distintos, no dos mitades del mismo. El endpoint sirve
también a la 8, que tampoco es de aquí.

**3. `TipoItem = IMPUESTO` no se descarta en la fuente.** Se entrega marcado, y
es la ingesta la que lo persiste con su bandera. La tentación de filtrarlo aquí
—«total, no es venta»— dejaría un hueco entre lo que la API devuelve y lo que
SIGREP tiene, y la primera conciliación con el ERP no cuadraría sin que nadie
supiera por qué. Se guarda, se marca y se excluye **al reportar**.

**4. `LineasFacturadas` son líneas, no documentos.** La fuente lo transporta con
ese nombre y no lo convierte en nada más. Una venta de ocho productos son ocho
líneas y un documento; publicar este conteo como «documentos» daría una cifra
varias veces mayor que la real.

── El contrato, tal como se midió ────────────────────────────────────────────

Autenticación: **la misma que carnes**. Cabecera `Authorization` con el token
**pelado** —sin `Bearer` y sin el prefijo `1-`, que es un identificador de clave
y no parte del secreto—. Se reutiliza `SIGREP_SIESA_TOKEN` y su
`SIGREP_SIESA_URL_BASE`: es la misma API.

Parámetros: `fecha_inicio`, `fecha_fin`, `id_cia`, `limit`, `offset`,
`format=csv`. Se usa **CSV**: con `format=csv` la descarga es completa en
streaming, como en `costos-razon-social`, y no hay que encadenar páginas.

Sobre `limit`/`offset`: por defecto **no se envían**, porque en esta familia de
endpoints `format=csv` ignora la paginación y devuelve el rango entero —así está
medido y así carga carnes—. Queda `SIGREP_AGRO_LIMITE_PAGINA` para el día en que
eso deje de ser cierto: con un valor mayor que cero la fuente pagina de verdad,
pidiendo `limit` filas por vez y avanzando `offset` hasta que una página vuelve
corta. No se activa por si acaso: una paginación mal cerrada es venta duplicada,
y duplicada es peor que ausente porque el total sube y todo el mundo se lo cree.

Veintiocho columnas, con encabezado. Los nombres se comparan **plegados a
minúsculas** (`CO_Id` → `co_id`), así que un cambio de capitalización en la API
no rompe la carga; un cambio de nombre sí, y debe romperla.

Limitación conocida del lector CSV, heredada de `siesa.py`: se parte por líneas
físicas, así que un campo entrecomillado con un salto de línea dentro se leería
mal. No ocurre en el dato medido —las descripciones de ítem son de una línea— y
el día que ocurra la fila se rechaza con su motivo en lugar de colarse mal
formada.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from time import sleep
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import httpx
from pydantic import SecretStr

from app.core.errors import ErrorSigrep, ErrorValidacion
from app.domain.normalizacion import (
    ESCALA_DINERO,
    ESCALA_KILOS,
    a_decimal,
    a_fecha,
    normalizar_texto,
)
from app.infrastructure.fuentes.base import AnotacionFuente, RechazoFuente

if TYPE_CHECKING:  # pragma: no cover - solo para el tipado
    from app.core.config import Settings

#: El endpoint del módulo agropecuario. Detrás está la tabla `t470` de Siesa,
#: que es **facturación**: de ahí que traiga cliente, vendedor, especie y tipo
#: comercial, cosas que la venta de mostrador de carnes no tiene.
RUTA_AGROPECUARIA = "/ventas/agropecuaria"

#: La compañía de la unidad agropecuaria. **Solo la 3.** Ver la trampa 2.
COMPANIA_AGROPECUARIA = 3

#: Prefijo identificador de la clave. No forma parte del secreto y no se envía:
#: mandarlo completo devuelve `401 {"detail":"Token invalido."}`.
#: `noqa: S105` porque es lo contrario de un secreto embebido —es el trozo del
#: token que se descarta—, pero el nombre lleva la palabra «token».
PREFIJO_TOKEN = "1-"  # noqa: S105

# ── Columnas, plegadas a minúsculas ───────────────────────────────────────────

COL_FECHA = "fecha"
COL_CO_ID = "co_id"
COL_CENTRO = "centrooperacion"
COL_TIPO_ITEM_ID = "tipoitem_id"
COL_TIPO_ITEM = "tipoitem"
COL_ESPECIE_ID = "especie_id"
COL_ESPECIE = "especie"
COL_TIPO_COMERCIAL_ID = "tipocomercial_id"
COL_TIPO_COMERCIAL = "tipocomercial"
COL_GRUPO_ID = "grupo_id"
COL_GRUPO = "grupo"
COL_ITEM_REF = "item_ref"
COL_ITEM_DESC = "item_desc"
COL_CLIENTE = "cliente"
COL_CODIGO_VENDEDOR = "codigovendedor"
COL_NOMBRE_VENDEDOR = "nombrevendedor"
COL_CANTIDAD = "cantidadinv"
COL_KILOS = "kilostotal"
COL_VALOR_BRUTO = "valorbruto"
COL_DESCUENTOS = "descuentos"
COL_VALOR_SUBTOTAL = "valorsubtotal"
COL_TOTAL_NETO = "totalneto"
COL_TOTAL_COSTO = "totalcosto"
COL_UTILIDAD = "utilidadbruta"
COL_LINEAS = "lineasfacturadas"

#: Columnas sin las cuales no hay línea que valga.
#:
#: `tipoitem` está aquí y no es un capricho: es lo único que distingue una venta
#: de un recaudo de impuesto, y sin él las filas de IMPUESTO entrarían como
#: venta e inflarían todos los totales. Es el mismo papel que juega `Origen` en
#: `costos-razon-social`. Que falte esa columna es un cambio de contrato que
#: tiene que **parar la carga**, no degradarla.
COLUMNAS_OBLIGATORIAS = (COL_FECHA, COL_CO_ID, COL_TOTAL_NETO, COL_TIPO_ITEM)

#: Códigos de estado que merecen otro intento: la API está viva pero saturada o
#: caída un instante. Un 401 o un 422 no se reintentan —volver a pedir lo mismo
#: con el mismo token da exactamente el mismo 401— y un 404 tampoco.
ESTADOS_REINTENTABLES = frozenset({408, 429, 500, 502, 503, 504})

#: Tope de páginas cuando la paginación está activada. Es un cortacircuitos: si
#: la API dejara de respetar `offset`, el bucle pediría la misma página para
#: siempre y duplicaría la venta hasta llenar la base. Con el tope, la corrida
#: falla y lo dice.
MAX_PAGINAS = 2000

_CERO = Decimal("0")

#: `noqa: S105`: es el texto que se muestra cuando **falta** el token, no un
#: token. El nombre de la constante es lo único que dispara la regla.
MENSAJE_SIN_TOKEN = (
    "La fuente agropecuaria necesita credenciales. Es la misma API de consulta que usa "  # noqa: S105
    "carnes: configure `SIGREP_SIESA_TOKEN` con su token —el prefijo «1-» puede dejarse o "
    "quitarse, se pela solo— y `SIGREP_SIESA_URL_BASE` si la API no está en su dirección "
    "habitual."
)


@dataclass(frozen=True, slots=True)
class LineaAgro:
    """Una línea de factura agropecuaria tal como la entrega la fuente.

    Los campos llegan **crudos**: la normalización de las llaves de dimensión
    —mayúsculas, sin tildes, C.O. a tres posiciones— es responsabilidad de la
    ingesta, igual que en carnes, y vive en
    `app/infrastructure/models/agro_vocabulario.py` con pruebas propias.

    `total_costo` es opcional y los importes de venta no, y esa asimetría es
    §4.4 entera: un costo que no llega es `None` —«no se sabe»—, nunca un cero
    que afirmaría que vender no costó nada. Un agregado que contenga una sola
    línea sin costo publica el margen como «—».
    """

    fecha: date
    #: Llaves de dimensión, tal como vienen: `CO_Id`, `Especie_Id`, etc.
    co_id: str | None
    centro_operacion: str | None
    tipo_item_id: str | None
    tipo_item: str | None
    especie_id: str | None
    especie: str | None
    tipo_comercial_id: str | None
    tipo_comercial: str | None
    grupo_id: str | None
    grupo: str | None
    item_ref: str | None
    item_desc: str | None
    cliente: str | None
    codigo_vendedor: str | None
    nombre_vendedor: str | None

    #: Medidas.
    cantidad_inv: Decimal
    kilos_total: Decimal
    valor_bruto: Decimal
    descuentos: Decimal
    valor_subtotal: Decimal
    #: **La venta**: es la medida que se compara contra el presupuesto.
    total_neto: Decimal
    total_costo: Decimal | None
    utilidad_bruta: Decimal | None
    #: **Líneas, no documentos.** Ver la trampa 4 del encabezado.
    lineas_facturadas: int

    #: Número de fila en el origen. Es lo que hace útil un rechazo: sin él, el
    #: usuario sabe que algo falló pero no dónde mirar.
    fila_origen: int | None = None


@runtime_checkable
class FuenteVentaAgro(Protocol):
    """Origen de la venta agropecuaria.

    Puerto propio y no `FuenteVenta`: son 28 campos y otras dimensiones. La
    ingesta que lo consume es **idempotente**: reprocesar un día reemplaza ese
    día completo por centro de operación, no duplica (§5 y §7).
    """

    def obtener_ventas(self, desde: date, hasta: date) -> Iterator[LineaAgro]:
        """Líneas del rango, **ambos extremos incluidos**.

        Iterable perezoso a propósito: la respuesta se lee en streaming y no hay
        en ningún momento la descarga entera en memoria.
        """
        ...


class ErrorFuenteAgro(ErrorSigrep):
    """La API de consulta no respondió, o respondió algo que no es su contrato.

    Se distingue de `ErrorValidacion` a propósito: aquella dice «configure algo»
    y sale por 422 antes de abrir la corrida; esta dice «el origen falló» y la
    ingesta la recoge para cerrar la corrida como `FALLIDA` con su motivo, sin
    tumbar el proceso ni dejar medio día cargado.

    **Su mensaje nunca contiene el token.** Se construye a mano, con el estado,
    la ruta y como mucho un fragmento acotado del cuerpo de la respuesta.
    """

    codigo = "fuente_agropecuaria"
    http_status = 502

    def __init__(
        self, mensaje: str, *, reintentable: bool = False, detalles: dict[str, object] | None = None
    ) -> None:
        super().__init__(mensaje, detalles=detalles)
        self.reintentable = reintentable


def token_efectivo(valor: str) -> str:
    """El token tal como viaja en la cabecera: sin el prefijo `1-` y sin espacios.

    Se acepta el valor con prefijo y sin él para que nadie tenga que recordar
    cuál de las dos formas le pasaron por correo.
    """
    limpio = valor.strip()
    return limpio[len(PREFIJO_TOKEN) :] if limpio.startswith(PREFIJO_TOKEN) else limpio


@dataclass(frozen=True, slots=True)
class ConfiguracionAgro:
    """Todo lo que la fuente necesita saber del entorno, en un solo objeto.

    Existe para que las pruebas puedan montar la fuente sin fabricar un
    `Settings` completo —y por tanto sin depender de un `.env`—, y para que el
    token viva en un `SecretStr`: su `repr` es `**********`, así que ni un
    volcado de estado ni una traza de excepción pueden imprimirlo.
    """

    url_base: str
    token: SecretStr = field(repr=False)
    #: **Siempre la 3.** Es configurable para poder probar el recorrido, no para
    #: mezclar unidades de negocio: poner aquí una compañía de carnes cargaría
    #: en esta instancia venta que se reporta en la otra.
    compania: int = COMPANIA_AGROPECUARIA
    timeout_conexion_seg: float = 15.0
    timeout_lectura_seg: float = 600.0
    reintentos: int = 3
    espera_reintento_seg: float = 2.0
    #: `0` = no paginar, que es el comportamiento medido de `format=csv`. Ver el
    #: apartado del encabezado antes de subirlo de cero.
    limite_pagina: int = 0

    @classmethod
    def desde_settings(cls, settings: Settings) -> ConfiguracionAgro:
        """Lee `SIGREP_SIESA_*` y `SIGREP_AGRO_*`. Falla con instrucciones."""
        crudo = settings.siesa_token.get_secret_value().strip()
        url_base = (settings.siesa_url_base or "").strip().rstrip("/")
        if not crudo or not url_base:
            raise ErrorValidacion(MENSAJE_SIN_TOKEN)
        return cls(
            url_base=url_base,
            token=SecretStr(crudo),
            compania=settings.agro_compania,
            timeout_conexion_seg=settings.siesa_timeout_conexion_seg,
            timeout_lectura_seg=settings.siesa_timeout_lectura_seg,
            reintentos=settings.siesa_reintentos,
            espera_reintento_seg=settings.siesa_espera_reintento_seg,
            limite_pagina=settings.agro_limite_pagina,
        )

    def cabeceras(self) -> dict[str, str]:
        """`Authorization` con el token pelado. Sin `Bearer`: devuelve 401."""
        return {
            "Authorization": token_efectivo(self.token.get_secret_value()),
            "Accept": "text/csv",
        }


def _obligatoria(medidas: Mapping[str, Decimal | None], clave: str) -> Decimal:
    """Una medida de venta o cantidad, que nunca falta.

    `_medidas` documenta la regla: los importes de venta y las cantidades vacios
    valen cero, y solo **el costo** puede quedar en `None` —porque «no se sabe»
    y «costo cero» son afirmaciones distintas—. Esta funcion existe para que esa
    garantia quede escrita en el tipo y no solo en un comentario.
    """
    valor = medidas[clave]
    return valor if valor is not None else Decimal("0")


class FuenteVentaAgropecuaria:
    """Implementación del puerto `FuenteVentaAgro` contra la API de consulta.

    No consulta la base para nada: el centro de operación llega con su código
    (`CO_Id`), a diferencia de carnes, donde había que resolverlo por la
    descripción. Eso la hace probable entera sin montar un esquema.
    """

    def __init__(
        self,
        *,
        configuracion: ConfiguracionAgro | None = None,
        sesion_http: httpx.Client | None = None,
    ) -> None:
        if configuracion is None:
            from app.core.config import obtener_settings

            configuracion = ConfiguracionAgro.desde_settings(obtener_settings())
        self._configuracion = configuracion

        self._sesion_http = sesion_http
        self._propia = sesion_http is None

        #: Filas que no se pudieron convertir en `LineaAgro`. La ingesta las
        #: recoge al terminar y las vuelca en la bitácora de la corrida.
        self.rechazos: list[RechazoFuente] = []
        #: Constancia de lo que sí entró pero merece verse: las filas de
        #: impuesto, las que llegaron sin costo, las que llegaron fuera de rango.
        self.anotaciones: list[AnotacionFuente] = []

        self._numero = 0
        self._leidas = 0
        self._entregadas = 0
        self._sin_costo = 0

    # ── Identidad ─────────────────────────────────────────────────────────────

    @property
    def nombre(self) -> str:
        """Va a `agro_corridas_ingesta.origen`. Nunca lleva el token."""
        return (
            f"API SIESA {self._configuracion.url_base} "
            f"({RUTA_AGROPECUARIA}, id_cia={self._configuracion.compania})"
        )

    def cerrar(self) -> None:
        """Cierra el cliente HTTP si lo abrió esta fuente."""
        if self._propia and self._sesion_http is not None:
            self._sesion_http.close()
            self._sesion_http = None

    # ── Puerto `FuenteVentaAgro` ──────────────────────────────────────────────

    def obtener_ventas(self, desde: date, hasta: date) -> Iterator[LineaAgro]:
        """Líneas del rango, ambos extremos incluidos.

        `hasta` viaja tal cual a `fecha_fin`, **sin sumarle un día**: es
        inclusiva. Ver la trampa 1 del encabezado antes de tocar esta línea.

        Las filas de `TipoItem = IMPUESTO` **se entregan**: no es venta, pero se
        guarda marcada para poder conciliar con el origen. Filtrarla aquí dejaría
        un hueco entre lo que la API devuelve y lo que SIGREP tiene.
        """
        for texto in self._paginas(desde, hasta):
            lector = csv.DictReader(texto)
            for registro in self._registros(lector):
                self._numero += 1
                self._leidas += 1
                linea = self._formar_linea(registro, desde, hasta)
                if linea is not None:
                    self._entregadas += 1
                    yield linea

        self._anotar_resumen()

    # ── Lectura del CSV ───────────────────────────────────────────────────────

    def _registros(self, lector: csv.DictReader[str]) -> Iterator[dict[str, str]]:
        """Filas del CSV, tras comprobar que el encabezado es el del contrato."""
        try:
            columnas = lector.fieldnames
        except StopIteration:  # pragma: no cover - `DictReader` ya lo absorbe
            columnas = None

        if not columnas:
            # Cuerpo vacío con 200. No se lanza: una compañía sin venta ese día
            # es un caso legítimo. Queda en la bitácora y la corrida mostrará
            # las filas que no trajo.
            self._anotar(
                None,
                "Respuesta",
                RUTA_AGROPECUARIA,
                f"{RUTA_AGROPECUARIA} devolvió una respuesta sin encabezado CSV. Se leyeron "
                "cero filas de esa consulta.",
            )
            return

        presentes = {str(c).strip().lower() for c in columnas if c}
        faltantes = [c for c in COLUMNAS_OBLIGATORIAS if c not in presentes]
        if faltantes:
            raise ErrorFuenteAgro(
                f"El CSV de {RUTA_AGROPECUARIA} no trae las columnas obligatorias: "
                + ", ".join(faltantes)
                + f". Llegaron: {', '.join(sorted(presentes))}. "
                "El contrato de la API cambió; revise el mapeo antes de volver a cargar."
            )

        for registro in lector:
            yield {
                str(clave).strip().lower(): valor
                for clave, valor in registro.items()
                if clave is not None and isinstance(valor, str)
            }

    # ── Formación de la línea ─────────────────────────────────────────────────

    def _formar_linea(
        self, registro: Mapping[str, str], desde: date, hasta: date
    ) -> LineaAgro | None:
        """Un registro del CSV a `LineaAgro`, o `None` con su motivo apuntado."""
        numero = self._numero

        fecha = a_fecha(registro.get(COL_FECHA))
        if fecha is None:
            self._rechazar(numero, "Fecha", registro.get(COL_FECHA), "no es una fecha legible")
            return None
        if fecha < desde or fecha > hasta:
            # `fecha_fin` es inclusiva y la API respeta el rango, así que esto no
            # debería pasar. Si pasa, es que el contrato cambió y hay que verlo.
            self._anotar(
                numero,
                "Fecha",
                fecha.isoformat(),
                f"{RUTA_AGROPECUARIA} devolvió una fila fuera del rango pedido "
                f"({desde.isoformat()} a {hasta.isoformat()}, ambos incluidos); no se carga. "
                "Si se repite, el criterio de `fecha_fin` cambió en la API.",
            )
            return None

        if normalizar_texto(registro.get(COL_CO_ID)) is None:
            self._rechazar(
                numero,
                "CO_Id",
                registro.get(COL_CO_ID),
                "la fila no indica centro de operación, y sin él no se sabe de qué unidad "
                "es la venta ni qué calendario le corresponde",
            )
            return None

        medidas = self._medidas(registro, numero)
        if medidas is None:
            return None

        if medidas["total_costo"] is None:
            self._sin_costo += 1

        return LineaAgro(
            fecha=fecha,
            co_id=normalizar_texto(registro.get(COL_CO_ID), limite=60),
            centro_operacion=normalizar_texto(registro.get(COL_CENTRO), limite=200),
            tipo_item_id=normalizar_texto(registro.get(COL_TIPO_ITEM_ID), limite=60),
            tipo_item=normalizar_texto(registro.get(COL_TIPO_ITEM), limite=200),
            especie_id=normalizar_texto(registro.get(COL_ESPECIE_ID), limite=60),
            especie=normalizar_texto(registro.get(COL_ESPECIE), limite=200),
            tipo_comercial_id=normalizar_texto(registro.get(COL_TIPO_COMERCIAL_ID), limite=60),
            tipo_comercial=normalizar_texto(registro.get(COL_TIPO_COMERCIAL), limite=200),
            grupo_id=normalizar_texto(registro.get(COL_GRUPO_ID), limite=60),
            grupo=normalizar_texto(registro.get(COL_GRUPO), limite=200),
            item_ref=normalizar_texto(registro.get(COL_ITEM_REF), limite=60),
            item_desc=normalizar_texto(registro.get(COL_ITEM_DESC), limite=200),
            cliente=normalizar_texto(registro.get(COL_CLIENTE), limite=200),
            codigo_vendedor=normalizar_texto(registro.get(COL_CODIGO_VENDEDOR), limite=60),
            nombre_vendedor=normalizar_texto(registro.get(COL_NOMBRE_VENDEDOR), limite=200),
            cantidad_inv=_obligatoria(medidas, "cantidad_inv"),
            kilos_total=_obligatoria(medidas, "kilos_total"),
            valor_bruto=_obligatoria(medidas, "valor_bruto"),
            descuentos=_obligatoria(medidas, "descuentos"),
            valor_subtotal=_obligatoria(medidas, "valor_subtotal"),
            total_neto=_obligatoria(medidas, "total_neto"),
            total_costo=medidas["total_costo"],
            utilidad_bruta=medidas["utilidad_bruta"],
            lineas_facturadas=self._lineas(registro, numero),
            fila_origen=numero,
        )

    def _medidas(
        self, registro: Mapping[str, str], numero: int
    ) -> dict[str, Decimal | None] | None:
        """Los importes de la fila, o `None` si alguno no es un número.

        Tres reglas para tres clases de campo que no significan lo mismo:

        - **Los importes de venta y las cantidades vacíos valen cero.** Son
          medidas de lo que se vendió; una celda en blanco ahí es un cero que la
          API no molestó en escribir, y rechazar la fila costaría venta real.
        - **El costo vacío es `None`, no cero.** `NULL` dice «no se sabe» y `0`
          dice «costó cero»; de esa distinción depende que §4.4 publique el
          margen o pinte «—», y confundirla publica un 100 % que nadie ganó.
        - **Una celda con contenido que no es un número rechaza la fila**, sea
          cual sea el campo: ahí hay algo que alguien tiene que mirar, y
          convertirlo en cero o en nulo sería tapar el problema.
        """
        valores: dict[str, Decimal | None] = {}
        for campo, columna, etiqueta, escala in (
            ("cantidad_inv", COL_CANTIDAD, "CantidadInv", ESCALA_KILOS),
            ("kilos_total", COL_KILOS, "KilosTotal", ESCALA_KILOS),
            ("valor_bruto", COL_VALOR_BRUTO, "ValorBruto", ESCALA_DINERO),
            ("descuentos", COL_DESCUENTOS, "Descuentos", ESCALA_DINERO),
            ("valor_subtotal", COL_VALOR_SUBTOTAL, "ValorSubtotal", ESCALA_DINERO),
            ("total_neto", COL_TOTAL_NETO, "TotalNeto", ESCALA_DINERO),
        ):
            crudo = registro.get(columna)
            if normalizar_texto(crudo) is None:
                valores[campo] = _CERO.quantize(escala)
                continue
            numero_decimal = a_decimal(crudo, escala)
            if numero_decimal is None:
                self._rechazar(numero, etiqueta, crudo, "no es un número")
                return None
            valores[campo] = numero_decimal

        for campo, columna, etiqueta in (
            ("total_costo", COL_TOTAL_COSTO, "TotalCosto"),
            ("utilidad_bruta", COL_UTILIDAD, "UtilidadBruta"),
        ):
            crudo = registro.get(columna)
            if normalizar_texto(crudo) is None:
                valores[campo] = None
                continue
            numero_decimal = a_decimal(crudo, ESCALA_DINERO)
            if numero_decimal is None:
                self._rechazar(numero, etiqueta, crudo, "no es un número")
                return None
            valores[campo] = numero_decimal

        return valores

    def _lineas(self, registro: Mapping[str, str], numero: int) -> int:
        """`LineasFacturadas` a entero. **Líneas, no documentos.**

        Un valor ilegible se anota y entra como cero en lugar de rechazar la
        fila: es un conteo informativo y perder venta real por él sería el peor
        cambio posible, exactamente como con `margen_siesa` en carnes.
        """
        crudo = registro.get(COL_LINEAS)
        if normalizar_texto(crudo) is None:
            return 0
        valor = a_decimal(crudo)
        if valor is None:
            self._anotar(
                numero,
                "LineasFacturadas",
                crudo,
                "No es un número. La venta se carga igual —este conteo no alimenta ningún "
                "indicador— pero la fila entra con cero líneas facturadas.",
            )
            return 0
        return int(valor)

    # ── HTTP ──────────────────────────────────────────────────────────────────

    def _parametros(self, desde: date, hasta: date) -> dict[str, str]:
        """⚠️ `fecha_fin` es **INCLUSIVA**. `hasta` viaja tal cual.

        `fecha_inicio=2026-08-01&fecha_fin=2026-08-02` devuelve los días 1 y 2.
        No le sume un día «para arreglarlo»: agosto cargaría el 1 de septiembre.
        """
        return {
            "fecha_inicio": desde.isoformat(),
            "fecha_fin": hasta.isoformat(),
            "id_cia": str(self._configuracion.compania),
            "format": "csv",
        }

    def _paginas(self, desde: date, hasta: date) -> Iterator[list[str]]:
        """El CSV, entero o por páginas según `limite_pagina`.

        Con `limite_pagina = 0` —lo normal— hay **una sola** petición y su
        cuerpo se entrega en streaming. Con un límite mayor que cero se pagina
        de verdad: se piden `limit` filas por vez y se avanza `offset` hasta que
        una página vuelve corta, que es la señal de fin. El cortacircuitos de
        `MAX_PAGINAS` existe porque una API que dejara de respetar `offset`
        devolvería la misma página para siempre, y eso es venta duplicada.
        """
        base = self._parametros(desde, hasta)
        limite = self._configuracion.limite_pagina
        if limite <= 0:
            yield list(self._lineas_http(base))
            return

        offset = 0
        for pagina in range(MAX_PAGINAS):
            parametros = {**base, "limit": str(limite), "offset": str(offset)}
            texto = list(self._lineas_http(parametros))
            yield texto
            #: El encabezado no es una fila de datos y no cuenta para el fin de
            #: la paginación. Sin este `-1`, una página vacía —solo encabezado—
            #: parecería tener una fila y el bucle no terminaría nunca.
            filas = max(len(texto) - 1, 0)
            if filas < limite:
                return
            offset += limite
            if pagina == MAX_PAGINAS - 1:
                raise ErrorFuenteAgro(
                    f"{RUTA_AGROPECUARIA} superó las {MAX_PAGINAS} páginas de "
                    f"{limite} filas sin devolver una página corta. O el rango pedido es "
                    "desmedido, o la API dejó de respetar `offset` y estaría devolviendo "
                    "la misma página; en cualquiera de los dos casos la carga se detiene "
                    "antes de duplicar venta."
                )

    def _cliente(self) -> httpx.Client:
        if self._sesion_http is None:
            configuracion = self._configuracion
            self._sesion_http = httpx.Client(
                timeout=httpx.Timeout(
                    connect=configuracion.timeout_conexion_seg,
                    read=configuracion.timeout_lectura_seg,
                    write=configuracion.timeout_conexion_seg,
                    pool=configuracion.timeout_conexion_seg,
                ),
                follow_redirects=True,
            )
        return self._sesion_http

    def _lineas_http(self, parametros: Mapping[str, str]) -> Iterator[str]:
        """Las líneas del CSV en streaming, con reintentos acotados.

        **Solo se reintenta lo que todavía no entregó ninguna línea.** Reintentar
        una descarga cortada a la mitad volvería a mandar desde la primera fila
        lo que ya se leyó, y eso es venta duplicada que nadie notaría: el total
        sube y todo el mundo se lo cree. Si la conexión se cae con datos ya
        entregados, la corrida falla —y §5 garantiza que lo insertado se deshace
        entero, no a medias—.
        """
        configuracion = self._configuracion
        url = configuracion.url_base + RUTA_AGROPECUARIA

        for intento in range(1, max(configuracion.reintentos, 1) + 1):
            entregadas = 0
            ultimo = configuracion.reintentos <= intento
            try:
                with self._cliente().stream(
                    "GET", url, params=dict(parametros), headers=configuracion.cabeceras()
                ) as respuesta:
                    if respuesta.status_code >= 400:
                        respuesta.read()
                        raise self._error_http(respuesta)
                    for linea in respuesta.iter_lines():
                        entregadas += 1
                        yield linea
                    return
            except ErrorFuenteAgro as exc:
                if entregadas or ultimo or not exc.reintentable:
                    raise
            except httpx.HTTPError as exc:
                # `httpx` oculta la cabecera `Authorization` en sus `repr`, pero
                # aquí ni siquiera se reexpone la excepción original: se dice el
                # tipo y la ruta, que es lo que hace falta para diagnosticar.
                if entregadas or ultimo:
                    raise ErrorFuenteAgro(
                        f"No se pudo leer {RUTA_AGROPECUARIA} de la API de SIESA "
                        f"({type(exc).__name__}). Se agotaron los {configuracion.reintentos} "
                        "intentos configurados en `SIGREP_SIESA_REINTENTOS`."
                    ) from None
            if configuracion.espera_reintento_seg > 0:
                sleep(configuracion.espera_reintento_seg * intento)

    @staticmethod
    def _error_http(respuesta: httpx.Response) -> ErrorFuenteAgro:
        """Traduce una respuesta de error. **Nunca incluye el token.**

        El cuerpo se recorta a 200 caracteres: los mensajes útiles de esta API
        —«Falta el token», «Token invalido»— caben de sobra, y un volcado
        completo de una página de error solo llenaría la bitácora.
        """
        detalle = " ".join(respuesta.text.split())[:200]
        if respuesta.status_code == 401:
            pista = (
                "Revise `SIGREP_SIESA_TOKEN`: se envía en la cabecera `Authorization` con el "
                "valor pelado, sin «Bearer» y sin el prefijo «1-»."
            )
        elif respuesta.status_code in ESTADOS_REINTENTABLES:
            pista = "La API está saturada o no disponible; se reintentó y siguió fallando."
        else:
            pista = (
                "Revise el rango de fechas y los parámetros; `id_cia` es obligatorio y en "
                "esta instancia vale 3, la unidad agropecuaria."
            )
        return ErrorFuenteAgro(
            f"La API de SIESA respondió {respuesta.status_code} en {RUTA_AGROPECUARIA}. {pista}"
            + (f" Respuesta: {detalle}" if detalle else ""),
            reintentable=respuesta.status_code in ESTADOS_REINTENTABLES,
        )

    # ── Bitácora ──────────────────────────────────────────────────────────────

    def _rechazar(self, fila: int, campo: str, valor: object, motivo: str) -> None:
        self.rechazos.append(
            RechazoFuente(
                fila=fila,
                campo=campo,
                valor=normalizar_texto(valor, limite=300),
                motivo=f"{RUTA_AGROPECUARIA}: «{campo}» {motivo}.",
            )
        )

    def _anotar(self, fila: int | None, campo: str, valor: object, motivo: str) -> None:
        self.anotaciones.append(
            AnotacionFuente(
                fila=fila,
                campo=campo,
                valor=normalizar_texto(valor, limite=300),
                motivo=motivo,
            )
        )

    def _anotar_resumen(self) -> None:
        """Cuántas filas se leyeron, cuántas se entregaron y cuántas sin costo.

        Es la señal que avisa el día que la fuente cambie de comportamiento sin
        avisar: una caída de filas leídas es un rango que dejó de traer datos, y
        una subida de las filas sin costo es margen que va a desaparecer de la
        pantalla sin que nadie sepa por qué.
        """
        self._anotar(
            None,
            "Resumen",
            RUTA_AGROPECUARIA,
            f"{RUTA_AGROPECUARIA} (id_cia={self._configuracion.compania}): "
            f"{self._leidas} filas leídas, {self._entregadas} entregadas a la ingesta.",
        )
        if self._sin_costo:
            self._anotar(
                None,
                "TotalCosto",
                str(self._sin_costo),
                f"{self._sin_costo} filas llegaron **sin costo** —celda vacía, no cero—. "
                "Entran con NULL y **no tienen margen calculable**: ni ellas ni ningún "
                "agregado que las contenga publican margen, que se muestra «—» hasta que "
                "la fuente entregue el dato (§4.4).",
            )
