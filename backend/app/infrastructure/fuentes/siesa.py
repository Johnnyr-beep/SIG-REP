"""`FuenteVentaSiesa`: la venta leída de la API de consulta de Grupo Santa Cruz.

Implementación del puerto `FuenteVenta` (§5) contra
`https://apiconsulta.grupo-santacruz.com`, validada el 12–13 de agosto de 2026
sumando la venta del 1-ago-2026 por punto de venta contra la hoja `VENTA` del
libro que el negocio usa hoy: **13 de los 15 puntos coinciden al peso exacto**.

── Por qué son DOS endpoints y no uno ────────────────────────────────────────

`GET /ventas/vendedor-acumulada` sirve **todos los puntos menos PEREIRA**.
`409 PEREIRA` registra en otro módulo de punto de venta (`t9830`/`t9820`) y solo
aparece en `GET /ventas/pos-vendedor-detalle`, que devuelve exactamente los
mismos once campos. No es una elección de diseño de SIGREP: es que en SIESA
conviven dos módulos de POS, y consultar uno solo dejaría fuera un punto entero
—101 millones de pesos el 1-ago— sin que nadie se enterara.

Por eso esta fuente consulta **los dos** y une los resultados. Para que la unión
no pueda duplicar nunca, el reparto es explícito y excluyente:

- los centros de `configuracion.centros_pos_detalle` (hoy `409`) **solo** se
  aceptan por `pos-vendedor-detalle`;
- cualquier otro centro **solo** se acepta por `vendedor-acumulada`.

Una fila que llega por el endpoint que no le toca no se suma ni se calla: se
anota en la bitácora diciendo por dónde vino. El día que la API unifique los dos
módulos, esa anotación es la señal de que hay que vaciar `centros_pos_detalle`.
Cada corrida deja además, por endpoint, cuántas filas leyó y cuántas entregó.

── Las dos trampas que hay que conocer antes de tocar este archivo ────────────

**1. `fecha_fin` es INCLUSIVA en estos endpoints.** Medido y confirmado:
`fecha_inicio=2026-08-01&fecha_fin=2026-08-02` devuelve los días 1 **y** 2. Es
lo contrario de lo que documenta `/ventas/poscarnes`, donde es exclusiva, y lo
contrario de lo que asume cualquiera que venga de leer aquel contrato. Si alguna
vez se «corrige» sumando un día al `hasta`, agosto cargará el 1 de septiembre
dentro de agosto y el cierre saldrá largo. Lo fija
`test_fecha_fin_es_inclusiva_y_no_se_le_suma_un_dia`.

**2. No viene el código de centro de operación, solo `desc_co`.** El punto de
venta se resuelve por la **descripción de SIESA** que la semilla ya guarda en
`puntos_venta.descripcion_siesa` (`PDV MALAMBO`, `CONCORD`, `PDV BUCARMANGA`
—con su errata de origen—, `ALAMEDA 1`…). La comparación normaliza espacios,
tildes y mayúsculas, y nada más: **una descripción que no se reconoce rechaza la
fila con su motivo**. No se adivina por parecido —`PDV LA 43` y `PDV LA 93` se
parecen demasiado— ni se descarta en silencio.

── Lo que esta fuente no puede arreglar ──────────────────────────────────────

- **PEREIRA no tiene costo.** `costo_promedio` viene nulo en el 100 % de las
  filas de `pos-vendedor-detalle`. Aquí no se inventa un costo y **tampoco se
  pone en cero**: la línea viaja con `costo_promedio=None` —«no se sabe», que es
  distinto de «costó cero»— y **queda anotado en la bitácora de cada corrida**.
  La venta sí se carga entera; lo único que se pierde es el margen.
  El resto de la regla vive fuera de este módulo, y conviene conocerla antes de
  «arreglar» este `None`: `venta_lineas.costo_promedio` es anulable (revisión
  `0003`) y §4.4 publica el margen como «—» en cualquier agregado que contenga
  una línea sin costo, PEREIRA y el consolidado de la compañía incluidos.
  Devolver un cero desde aquí volvería a publicar el 100 % de margen que esa
  cadena existe para evitar.
- **LA GRANJA (403) no cuadra con el Excel**: la API da 26 633 877 y el Excel
  21 413 829 el 1-ago. Los **dos** endpoints de la API coinciden entre sí, así
  que el que se desvía es el Excel. **No se compensa nada**: se carga lo que dice
  la API, que es la fuente de verdad de la venta (§1).
- **Campos que el Excel tiene y estos endpoints no**: NIT de cliente, condición
  de pago, domicilio y clase de cliente. Van a `NULL`. Inventarlos sería peor que
  no tenerlos.

── El contrato, tal como se midió ────────────────────────────────────────────

Autenticación: cabecera `Authorization` con el token **pelado**. Sin `Bearer` y
sin `Token ` —los dos devuelven 401 pese a que el mensaje de error de la propia
API sugiere `Bearer`—. El token se entrega con un prefijo `1-` que es un
identificador de clave, no parte del secreto, y **no se envía**.

Parámetros: `fecha_inicio`, `fecha_fin`, `id_cia`, `limit` (máx 5000), `offset`,
`format=csv`. Se usa **CSV**: con `format=csv` la descarga es completa en
streaming e ignora la paginación, y un día son ~31 000 filas —un mes, cerca de
un millón—. Con JSON habría que encadenar doscientas páginas por día.

`id_cia` se omite por defecto, que es lo que devuelve las tres compañías de
carnes (4, 6 y 7) en una sola consulta. Configurarlo parte la descarga en una
petición por compañía, que sirve para acotar una incidencia sin desplegar.

Once columnas, con encabezado: `desc_co`, `codigo_vendedor`, `nombre_vendedor`,
`referencia`, `desc_item`, `cantidad`, `costo_promedio`, `precio_unit`,
`valor_subtotal`, `categoria`, `fecha`.

Mapeo a `LineaVenta`: `valor_subtotal` → la venta contra presupuesto;
`costo_promedio` → el costo del margen; `cantidad` → kilos (`cantidad_inv`);
`categoria` → llega **en el formato exacto del Excel** (`'0001 - RES'`), así que
la tabla `mapeo_categorias` ya sembrada la resuelve tal cual y aquí no hay —ni
debe haber— un mapeo paralelo; `fecha` → `2026-08-01 00:00:00`.

Limitación conocida del lector CSV: se parte por líneas físicas, así que un
campo entrecomillado con un salto de línea dentro se leería mal. No ocurre en el
dato medido —las descripciones de ítem son de una línea— y el día que ocurra la
fila se rechaza con su motivo en lugar de colarse mal formada.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from time import sleep
from typing import TYPE_CHECKING

import httpx
from pydantic import SecretStr

from app.core.errors import ErrorSigrep, ErrorValidacion
from app.domain.normalizacion import (
    ESCALA_DINERO,
    ESCALA_KILOS,
    a_decimal,
    a_fecha,
    normalizar_texto,
    sin_acentos,
)
from app.domain.puertos import LineaVenta
from app.infrastructure.fuentes.base import AnotacionFuente, RechazoFuente

if TYPE_CHECKING:  # pragma: no cover - solo para el tipado
    from app.core.config import Settings

#: Endpoint que sirve todos los puntos de venta **menos** PEREIRA (t461/t470).
RUTA_VENDEDOR_ACUMULADA = "/ventas/vendedor-acumulada"

#: El otro módulo de POS (t9830/t9820). Hoy solo devuelve `409 PEREIRA`.
RUTA_POS_VENDEDOR_DETALLE = "/ventas/pos-vendedor-detalle"

#: Prefijo identificador de la clave. **No forma parte del secreto y no se
#: envía**: mandarlo completo devuelve `401 {"detail":"Token invalido."}`.
#: `noqa: S105` porque es justo lo contrario de un secreto embebido —es el
#: trozo del token que se descarta—, pero el nombre lleva la palabra «token».
PREFIJO_TOKEN = "1-"  # noqa: S105

#: Columnas sin las cuales no hay línea de venta que valga: el punto de venta,
#: el día y la medida contra la que se compara el presupuesto.
COLUMNAS_OBLIGATORIAS = ("desc_co", "fecha", "valor_subtotal")

#: Códigos de estado que merecen otro intento: la API está viva pero saturada o
#: caída un instante. Un 401 o un 422 no se reintentan —volver a pedir lo mismo
#: con el mismo token da exactamente el mismo 401— y un 404 tampoco.
ESTADOS_REINTENTABLES = frozenset({408, 429, 500, 502, 503, 504})

_CERO = Decimal("0")

#: `noqa: S105`: es el texto que se muestra cuando **falta** el token, no un
#: token. El nombre de la constante es lo único que dispara la regla.
MENSAJE_SIN_TOKEN = (
    "La fuente «siesa» necesita credenciales. Configure `SIGREP_SIESA_TOKEN` con el "  # noqa: S105
    "token de la API de consulta —el prefijo «1-» puede dejarse o quitarse, se pela "
    "solo— y `SIGREP_SIESA_URL_BASE` si la API no está en su dirección habitual."
)

MENSAJE_SIN_DESCRIPCIONES = (
    "La fuente «siesa» resuelve el punto de venta por la descripción que entrega "
    "SIESA (`desc_co`), y no hay ningún punto de venta con `descripcion_siesa` en la "
    "base. Siembre la estructura (§3.1) antes de ingerir: sin ese directorio, todas "
    "las filas se rechazarían por punto de venta desconocido."
)


@dataclass(frozen=True, slots=True)
class _Medidas:
    """Los tres importes de una fila del CSV, ya convertidos.

    `costo_promedio` es opcional y los otros dos no, y esa asimetría es el
    núcleo de la corrección de §4.4: la API no entrega el costo de PEREIRA, y un
    costo que no llega es `None` —«no se sabe»—, nunca un cero que afirmaría que
    vender no costó nada.
    """

    valor_subtotal: Decimal
    cantidad: Decimal
    costo_promedio: Decimal | None


class ErrorFuenteSiesa(ErrorSigrep):
    """La API de consulta no respondió, o respondió algo que no es su contrato.

    Se distingue de `ErrorValidacion` a propósito: aquella dice «configure algo»
    y sale por 422 antes de abrir la corrida; esta dice «el origen falló» y la
    ingesta la recoge para cerrar la corrida como `FALLIDA` con su motivo, sin
    tumbar el proceso ni dejar medio día cargado.

    **Su mensaje nunca contiene el token.** Se construye a mano, con el estado,
    la ruta y como mucho un fragmento acotado del cuerpo de la respuesta.
    """

    codigo = "fuente_siesa"
    http_status = 502

    def __init__(
        self, mensaje: str, *, reintentable: bool = False, detalles: dict[str, object] | None = None
    ) -> None:
        super().__init__(mensaje, detalles=detalles)
        self.reintentable = reintentable


def token_efectivo(valor: str) -> str:
    """El token tal como viaja en la cabecera: sin el prefijo `1-` y sin espacios.

    El prefijo es un identificador de clave, no parte del secreto. Se acepta el
    valor con prefijo y sin él para que nadie tenga que recordar cuál de las dos
    formas le pasaron por correo.
    """
    limpio = valor.strip()
    return limpio[len(PREFIJO_TOKEN) :] if limpio.startswith(PREFIJO_TOKEN) else limpio


@dataclass(frozen=True, slots=True)
class ConfiguracionSiesa:
    """Todo lo que la fuente necesita saber del entorno, en un solo objeto.

    Existe para que las pruebas puedan montar la fuente sin fabricar un
    `Settings` completo —y por tanto sin depender de un `.env`—, y para que el
    token viva en un `SecretStr`: su `repr` es `**********`, así que ni un
    volcado de estado ni una traza de excepción pueden imprimirlo.
    """

    url_base: str
    token: SecretStr = field(repr=False)
    #: Vacío = una sola consulta sin `id_cia`, que devuelve las tres compañías
    #: de carnes (4, 6 y 7). Con valores, una petición por compañía.
    companias: tuple[int, ...] = ()
    #: Centros que **solo** sirve `pos-vendedor-detalle`. Ver el encabezado.
    centros_pos_detalle: frozenset[str] = frozenset({"409"})
    timeout_conexion_seg: float = 15.0
    #: Un mes son ~1 000 000 de filas y la descarga tarda. Diez minutos de
    #: lectura no es generosidad: es el tiempo que cuesta el caso real.
    timeout_lectura_seg: float = 600.0
    reintentos: int = 3
    espera_reintento_seg: float = 2.0

    @classmethod
    def desde_settings(cls, settings: Settings) -> ConfiguracionSiesa:
        """Lee `SIGREP_SIESA_*`. Falla con instrucciones si falta el token."""
        crudo = settings.siesa_token.get_secret_value().strip()
        if not crudo:
            raise ErrorValidacion(MENSAJE_SIN_TOKEN)
        url_base = (settings.siesa_url_base or "").strip().rstrip("/")
        if not url_base:
            raise ErrorValidacion(MENSAJE_SIN_TOKEN)
        return cls(
            url_base=url_base,
            token=SecretStr(crudo),
            companias=tuple(settings.siesa_companias),
            centros_pos_detalle=frozenset(
                str(c).strip().zfill(3) for c in settings.siesa_centros_pos_detalle
            ),
            timeout_conexion_seg=settings.siesa_timeout_conexion_seg,
            timeout_lectura_seg=settings.siesa_timeout_lectura_seg,
            reintentos=settings.siesa_reintentos,
            espera_reintento_seg=settings.siesa_espera_reintento_seg,
        )

    def cabeceras(self) -> dict[str, str]:
        """`Authorization` con el token pelado. Sin `Bearer`: devuelve 401."""
        return {
            "Authorization": token_efectivo(self.token.get_secret_value()),
            "Accept": "text/csv",
        }


def clave_descripcion(valor: object) -> str:
    """Descripción de SIESA reducida a algo comparable.

    Mayúsculas, sin tildes y con los espacios colapsados. Nada más: `PDV LA 43`
    y `PDV LA 93` tienen que seguir siendo dos cosas distintas, así que aquí no
    hay parecidos ni distancias de edición.
    """
    crudo = normalizar_texto(valor)
    if crudo is None:
        return ""
    return " ".join(sin_acentos(crudo).upper().split())


def indexar_descripciones(descripciones: Mapping[str, str]) -> dict[str, str]:
    """`{descripción SIESA: C.O.}` a `{clave comparable: C.O.}`."""
    indice: dict[str, str] = {}
    for descripcion, codigo in descripciones.items():
        clave = clave_descripcion(descripcion)
        if clave:
            indice[clave] = str(codigo).strip().zfill(3)
    return indice


class FuenteVentaSiesa:
    """Implementación del puerto `FuenteVenta` contra la API de consulta.

    `descripciones` es `{descripcion_siesa: codigo_co}` tal como está sembrado en
    `puntos_venta`. Lo arma `obtener_fuente` desde la base: la fuente no consulta
    SQLAlchemy —no es su trabajo y la haría imposible de probar sin base—, pero
    tampoco se inventa el directorio.
    """

    def __init__(
        self,
        descripciones: Mapping[str, str] | None = None,
        *,
        configuracion: ConfiguracionSiesa | None = None,
        sesion_http: httpx.Client | None = None,
    ) -> None:
        if configuracion is None:
            from app.core.config import obtener_settings

            configuracion = ConfiguracionSiesa.desde_settings(obtener_settings())
        self._configuracion = configuracion

        self._puntos = indexar_descripciones(descripciones or {})
        if not self._puntos:
            raise ErrorValidacion(MENSAJE_SIN_DESCRIPCIONES)

        self._sesion_http = sesion_http
        self._propia = sesion_http is None

        #: Filas que no se pudieron convertir en `LineaVenta`. La ingesta las
        #: recoge al terminar y las vuelca en la bitácora de la corrida.
        self.rechazos: list[RechazoFuente] = []
        #: Constancia de lo que sí entró pero merece verse: el reparto entre los
        #: dos endpoints, PEREIRA sin costo, filas fuera del rango pedido.
        self.anotaciones: list[AnotacionFuente] = []

        self._numero = 0
        self._leidas: dict[str, int] = {}
        self._entregadas: dict[str, int] = {}

    # ── Identidad ─────────────────────────────────────────────────────────────

    @property
    def nombre(self) -> str:
        """Va a `corridas_ingesta.origen`. Nunca lleva el token, solo el host."""
        return (
            f"API SIESA {self._configuracion.url_base} "
            f"({RUTA_VENDEDOR_ACUMULADA} + {RUTA_POS_VENDEDOR_DETALLE})"
        )

    def cerrar(self) -> None:
        """Cierra el cliente HTTP si lo abrió esta fuente."""
        if self._propia and self._sesion_http is not None:
            self._sesion_http.close()
            self._sesion_http = None

    # ── Puerto `FuenteVenta` ──────────────────────────────────────────────────

    def obtener_ventas(
        self,
        desde: date,
        hasta: date,
        centros: Sequence[str] | None = None,
    ) -> Iterator[LineaVenta]:
        """Líneas de los **dos** endpoints del rango, ambos extremos incluidos.

        Es un generador: la respuesta se lee en streaming y no hay en ningún
        momento un millón de filas en memoria.

        `hasta` viaja tal cual a `fecha_fin`, **sin sumarle un día**, porque en
        estos endpoints `fecha_fin` es inclusiva. Ver la trampa 1 del encabezado
        del módulo antes de tocar esta línea.
        """
        pedidos = {str(c).strip().zfill(3) for c in centros} if centros else None

        for ruta in (RUTA_VENDEDOR_ACUMULADA, RUTA_POS_VENDEDOR_DETALLE):
            yield from self._leer_endpoint(ruta, desde, hasta, pedidos)
            self._anotar_reparto(ruta)

    # ── Lectura de un endpoint ────────────────────────────────────────────────

    def _leer_endpoint(
        self,
        ruta: str,
        desde: date,
        hasta: date,
        pedidos: set[str] | None,
    ) -> Iterator[LineaVenta]:
        self._leidas.setdefault(ruta, 0)
        self._entregadas.setdefault(ruta, 0)

        for parametros in self._peticiones(desde, hasta):
            lector = csv.DictReader(self._lineas(ruta, parametros))
            for registro in self._registros(lector, ruta):
                self._leidas[ruta] += 1
                self._numero += 1
                linea = self._formar_linea(registro, ruta, desde, hasta, pedidos)
                if linea is not None:
                    self._entregadas[ruta] += 1
                    yield linea

    def _registros(self, lector: csv.DictReader[str], ruta: str) -> Iterator[dict[str, str]]:
        """Filas del CSV, tras comprobar que el encabezado es el del contrato."""
        try:
            columnas = lector.fieldnames
        except StopIteration:  # pragma: no cover - `DictReader` ya lo absorbe
            columnas = None

        if not columnas:
            # Cuerpo vacío con 200. No se lanza: sacrificaría el otro endpoint
            # por una respuesta rara de este. Queda en la bitácora y la corrida
            # mostrará las filas que no trajo.
            self.anotaciones.append(
                AnotacionFuente(
                    fila=None,
                    campo="Respuesta",
                    valor=ruta,
                    motivo=(
                        f"{ruta} devolvió una respuesta sin encabezado CSV. "
                        "Se leyeron cero filas por ese endpoint."
                    ),
                )
            )
            return

        presentes = {str(c).strip().lower() for c in columnas if c}
        faltantes = [c for c in COLUMNAS_OBLIGATORIAS if c not in presentes]
        if faltantes:
            raise ErrorFuenteSiesa(
                f"El CSV de {ruta} no trae las columnas obligatorias: "
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
        self,
        registro: Mapping[str, str],
        ruta: str,
        desde: date,
        hasta: date,
        pedidos: set[str] | None,
    ) -> LineaVenta | None:
        """Un registro del CSV a `LineaVenta`, o `None` con su motivo apuntado."""
        numero = self._numero

        fecha = a_fecha(registro.get("fecha"))
        if fecha is None:
            self._rechazar(numero, "fecha", registro.get("fecha"), ruta, "no es una fecha legible")
            return None
        if fecha < desde or fecha > hasta:
            # `fecha_fin` es inclusiva y la API respeta el rango, así que esto no
            # debería pasar. Si pasa, es que el contrato cambió y hay que verlo.
            self._anotar(
                numero,
                "fecha",
                fecha.isoformat(),
                f"{ruta} devolvió una fila fuera del rango pedido "
                f"({desde.isoformat()} a {hasta.isoformat()}, ambos incluidos); no se carga.",
            )
            return None

        codigo = self._resolver_punto(registro.get("desc_co"), numero, ruta)
        if codigo is None:
            return None
        if not self._le_toca(codigo, ruta, numero, registro.get("desc_co")):
            return None
        if pedidos is not None and codigo not in pedidos:
            return None

        medidas = self._medidas(registro, numero, ruta)
        if medidas is None:
            return None
        if medidas.costo_promedio is None:
            self._anotar(
                numero,
                "costo_promedio",
                codigo,
                "Fila sin costo en el origen; entra como NULL —no como cero— y **no tiene "
                f"margen calculable**. {RUTA_POS_VENDEDOR_DETALLE} no expone el costo, así "
                "que ni este punto de venta ni ningún agregado que lo contenga publican "
                "margen: la pantalla muestra «—» hasta que la API entregue el dato.",
            )

        return LineaVenta(
            centro_operacion=codigo,
            fecha=fecha,
            valor_subtotal=medidas.valor_subtotal,
            costo_promedio=medidas.costo_promedio,
            cantidad_inv=medidas.cantidad,
            categoria_siesa=normalizar_texto(registro.get("categoria"), limite=120),
            # NIT, domicilio, clase de cliente y condición de pago no vienen en
            # estos endpoints. Van a `NULL`; no se inventan.
            codigo_vendedor=normalizar_texto(registro.get("codigo_vendedor"), limite=30),
            nombre_vendedor=normalizar_texto(registro.get("nombre_vendedor"), limite=120),
            fila_origen=numero,
        )

    def _resolver_punto(self, descripcion: object, numero: int, ruta: str) -> str | None:
        """El C.O. de la descripción de SIESA, o `None` tras rechazar la fila."""
        crudo = normalizar_texto(descripcion)
        if crudo is None:
            self._rechazar(
                numero, "desc_co", descripcion, ruta, "la fila no indica centro de operación"
            )
            return None

        codigo = self._puntos.get(clave_descripcion(crudo))
        if codigo is None:
            self._rechazar(
                numero,
                "desc_co",
                crudo,
                ruta,
                "esa descripción no corresponde a ningún punto de venta conocido. Añádala en "
                "`puntos_venta.descripcion_siesa` si es un punto nuevo; la venta no se adivina",
            )
            return None
        return codigo

    def _le_toca(self, codigo: str, ruta: str, numero: int, descripcion: object) -> bool:
        """¿Es este el endpoint del que debe salir este centro?

        El reparto es excluyente por diseño: es lo único que garantiza que unir
        dos endpoints no pueda duplicar venta. Ver el encabezado del módulo.
        """
        es_de_pos = codigo in self._configuracion.centros_pos_detalle
        if es_de_pos == (ruta == RUTA_POS_VENDEDOR_DETALLE):
            return True

        otro = RUTA_POS_VENDEDOR_DETALLE if es_de_pos else RUTA_VENDEDOR_ACUMULADA
        self._anotar(
            numero,
            "desc_co",
            normalizar_texto(descripcion),
            f"El centro {codigo} llegó por {ruta}, pero esta ingesta lo toma de {otro}. "
            "La fila no se carga para no duplicar venta. Si la API unificó los dos módulos "
            "de POS, ajuste `SIGREP_SIESA_CENTROS_POS_DETALLE`.",
        )
        return False

    def _medidas(self, registro: Mapping[str, str], numero: int, ruta: str) -> _Medidas | None:
        """Los tres importes de la fila, o `None` si alguno no es un número.

        Tres reglas distintas para tres campos que no significan lo mismo:

        - **La venta y los kilos vacíos valen cero.** Son medidas de lo que se
          vendió; una celda en blanco ahí es un cero que la API no molestó en
          escribir, y rechazar la fila costaría venta real.
        - **El costo vacío es `None`, no cero.** Es la diferencia entre «vender
          esto no costó nada» y «esta fuente no dice cuánto costó», y de ella
          depende que el margen se publique o se deje en «—» (§4.4). Llega así
          en el 100 % de las filas de PEREIRA, así que un cero aquí es un 100 %
          de margen en la pantalla de la gerencia.
        - **Una celda con contenido que no es un número rechaza la fila**, sea
          cual sea el campo: ahí hay algo que alguien tiene que mirar, y
          convertirlo en cero o en nulo sería tapar el problema.
        """
        obligatorias: dict[str, Decimal] = {}
        for campo, escala in (("valor_subtotal", ESCALA_DINERO), ("cantidad", ESCALA_KILOS)):
            crudo = registro.get(campo)
            if normalizar_texto(crudo) is None:
                obligatorias[campo] = _CERO
                continue
            numero_decimal = a_decimal(crudo, escala)
            if numero_decimal is None:
                self._rechazar(numero, campo, crudo, ruta, "no es un número")
                return None
            obligatorias[campo] = numero_decimal

        costo: Decimal | None = None
        crudo_costo = registro.get("costo_promedio")
        if normalizar_texto(crudo_costo) is not None:
            costo = a_decimal(crudo_costo, ESCALA_DINERO)
            if costo is None:
                self._rechazar(numero, "costo_promedio", crudo_costo, ruta, "no es un número")
                return None

        return _Medidas(
            valor_subtotal=obligatorias["valor_subtotal"],
            cantidad=obligatorias["cantidad"],
            costo_promedio=costo,
        )

    # ── HTTP ──────────────────────────────────────────────────────────────────

    def _peticiones(self, desde: date, hasta: date) -> Iterator[dict[str, str]]:
        """Los juegos de parámetros de un endpoint para el rango pedido.

        ⚠️ `fecha_fin` es **INCLUSIVA** en estos endpoints (medido el
        13-ago-2026): `fecha_inicio=2026-08-01&fecha_fin=2026-08-02` devuelve los
        días 1 y 2. `hasta` viaja tal cual. No le sume un día «para arreglarlo».
        """
        base = {
            "fecha_inicio": desde.isoformat(),
            "fecha_fin": hasta.isoformat(),
            "format": "csv",
        }
        if not self._configuracion.companias:
            yield dict(base)
            return
        for compania in self._configuracion.companias:
            yield {**base, "id_cia": str(compania)}

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

    def _lineas(self, ruta: str, parametros: Mapping[str, str]) -> Iterator[str]:
        """Las líneas del CSV en streaming, con reintentos acotados.

        **Solo se reintenta lo que todavía no entregó ninguna línea.** Reintentar
        una descarga cortada a la mitad volvería a mandar desde la primera fila
        lo que ya se leyó, y en una fuente de un millón de filas eso es venta
        duplicada que nadie notaría: el total sube y todo el mundo se lo cree.
        Si la conexión se cae con datos ya entregados, la corrida falla —y §5
        garantiza que lo insertado se deshace entero, no a medias—.
        """
        configuracion = self._configuracion
        url = configuracion.url_base + ruta

        for intento in range(1, max(configuracion.reintentos, 1) + 1):
            entregadas = 0
            ultimo = configuracion.reintentos <= intento
            try:
                with self._cliente().stream(
                    "GET", url, params=dict(parametros), headers=configuracion.cabeceras()
                ) as respuesta:
                    if respuesta.status_code >= 400:
                        respuesta.read()
                        raise self._error_http(ruta, respuesta)
                    for linea in respuesta.iter_lines():
                        entregadas += 1
                        yield linea
                    return
            except ErrorFuenteSiesa as exc:
                if entregadas or ultimo or not exc.reintentable:
                    raise
            except httpx.HTTPError as exc:
                # `httpx` oculta la cabecera `Authorization` en sus `repr`, pero
                # aquí ni siquiera se reexpone la excepción original al mensaje:
                # se dice el tipo y la ruta, que es lo que hace falta para
                # diagnosticar, y nada más.
                if entregadas or ultimo:
                    raise ErrorFuenteSiesa(
                        f"No se pudo leer {ruta} de la API de SIESA "
                        f"({type(exc).__name__}). Se agotaron los {configuracion.reintentos} "
                        "intentos configurados en `SIGREP_SIESA_REINTENTOS`."
                    ) from None
            if configuracion.espera_reintento_seg > 0:
                sleep(configuracion.espera_reintento_seg * intento)

    @staticmethod
    def _error_http(ruta: str, respuesta: httpx.Response) -> ErrorFuenteSiesa:
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
            pista = "Revise el rango de fechas y los parámetros de la consulta."
        return ErrorFuenteSiesa(
            f"La API de SIESA respondió {respuesta.status_code} en {ruta}. {pista}"
            + (f" Respuesta: {detalle}" if detalle else ""),
            reintentable=respuesta.status_code in ESTADOS_REINTENTABLES,
        )

    # ── Bitácora ──────────────────────────────────────────────────────────────

    def _rechazar(self, fila: int, campo: str, valor: object, ruta: str, motivo: str) -> None:
        self.rechazos.append(
            RechazoFuente(
                fila=fila,
                campo=campo,
                valor=normalizar_texto(valor, limite=300),
                motivo=f"{ruta}: «{campo}» {motivo}.",
            )
        )

    def _anotar(self, fila: int, campo: str, valor: object, motivo: str) -> None:
        self.anotaciones.append(
            AnotacionFuente(
                fila=fila,
                campo=campo,
                valor=normalizar_texto(valor, limite=300),
                motivo=motivo,
            )
        )

    def _anotar_reparto(self, ruta: str) -> None:
        """Cuántas filas trajo cada endpoint y cuántas entregó a la ingesta.

        Es la constancia de que la unión de los dos endpoints ocurrió y de en qué
        proporción: sin ella, un endpoint que empieza a devolver cero filas se
        nota el día que alguien compara el total con el mes pasado.
        """
        leidas = self._leidas.get(ruta, 0)
        self.anotaciones.append(
            AnotacionFuente(
                fila=None,
                campo="Origen",
                valor=ruta,
                motivo=(
                    f"{ruta}: {leidas} filas leídas, "
                    f"{self._entregadas.get(ruta, 0)} entregadas a la ingesta."
                ),
            )
        )
