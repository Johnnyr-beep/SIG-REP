"""`FuenteVentaSiesa`: la venta leída de la API de consulta de Grupo Santa Cruz.

Implementación del puerto `FuenteVenta` (§5) contra
`https://apiconsulta.grupo-santacruz.com`, sobre **un solo endpoint**:
`GET /ventas/costos-razon-social`.

── Por qué un endpoint y no dos, y qué error corrige el cambio ────────────────

Hasta el 13-ago-2026 esta fuente consultaba **dos** endpoints y los unía a mano:
`vendedor-acumulada` para catorce puntos de venta y `pos-vendedor-detalle` solo
para `409 PEREIRA`, repartidos con una lista de centros configurable. Aquello
tenía un defecto de importe que no era visible desde dentro:
**`pos-vendedor-detalle` daba PEREIRA a 135 201 210 el 1-ago-2026 y la cifra
correcta es 101 453 550** —33 747 660 de más, un 33 %, en el segundo punto de
venta más grande de la compañía—.

`costos-razon-social` hace esa misma unión, pero del lado de la API y bien.
Medido contra la hoja `VENTA` del libro que el negocio usa hoy, sumando el
1-ago-2026 por centro de operación:

- **catorce de los quince puntos cuadran al peso exacto**, PEREIRA incluida con
  sus 101 453 550, que es el número que confirma el libro;
- la única excepción es `403 LA GRANJA`: la API da 26 633 877 y el Excel
  21 413 829. Los tres endpoints de la API coinciden entre sí, así que el que se
  desvía es el Excel. **No se compensa nada**: se carga lo que dice la API, que
  es la fuente de verdad de la venta (§1).

Además trae el costo, que es lo que hace calculable el margen.

── `Origen`: dos valores complementarios que hay que SUMAR ────────────────────

La respuesta trae un campo `Origen` con dos valores, y la tentación de filtrar
por uno de ellos es el error que arruinaría la carga:

| `Origen` | Filas (1-ago) | Venta | Quién |
|---|---:|---:|---|
| `ACUMULADO` | 2289 | 765 177 470 | los catorce puntos; idéntico a `vendedor-acumulada` |
| `SIN ACUMULAR` | 203 | 101 453 550 | **solo PEREIRA** |

**No solapan: son complementarios y los dos se cargan.** Que la suma cuadre al
peso con el Excel en catorce de quince puntos es la demostración. Quedarse con
uno solo perdería un punto de venta entero —o los otros catorce—.

Cada corrida deja en la bitácora **cuántas filas vinieron de cada `Origen`**.
Esa es la señal que avisará el día que PEREIRA empiece a traer costo, cambie de
módulo o aparezca un tercer valor.

── Las tres trampas que hay que conocer antes de tocar este archivo ───────────

**1. `fecha_fin` es INCLUSIVA.** Aquí, a diferencia de los otros dos endpoints,
lo declara el propio contrato de la API —«Fecha final (inclusiva)»— y coincide
con el comportamiento medido de aquellos. Es lo contrario de lo que documenta
`/ventas/poscarnes`, donde es exclusiva, y lo contrario de lo que asume
cualquiera que venga de leer aquel contrato. Si alguna vez se «corrige» sumando
un día al `hasta`, agosto cargará el 1 de septiembre dentro de agosto y el
cierre saldrá largo. Lo fija `test_fecha_fin_es_inclusiva_y_no_se_le_suma_un_dia`.

**2. `id_cia` es OBLIGATORIO.** En `vendedor-acumulada` omitirlo devolvía las
tres compañías de carnes de una vez; aquí no. Hay que **recorrer 4, 6 y 7**, una
petición por compañía, y por eso `SIGREP_SIESA_COMPANIAS` deja de ser un ajuste
opcional para convertirse en parte del contrato: su valor por defecto es
`4,6,7` y dejarla vacía es un error de configuración, no «pedirlas todas».
Nunca la 3 ni la 8: la venta agropecuaria se reporta en otra instancia.

**3. No viene el código de centro de operación, solo `DescCO`.** El punto de
venta se resuelve por la **descripción de SIESA** que la semilla ya guarda en
`puntos_venta.descripcion_siesa` (`PDV MALAMBO`, `CONCORD`, `PDV BUCARMANGA`
—con su errata de origen—, `ALAMEDA 1`…). La comparación normaliza espacios,
tildes y mayúsculas, y nada más: **una descripción que no se reconoce rechaza la
fila con su motivo**. No se adivina por parecido —`PDV LA 43` y `PDV LA 93` se
parecen demasiado— ni se descarta en silencio.

── «Sin costo» no es «costo cero», y aquí la diferencia se afirma, no se infiere

**PEREIRA sigue sin costo.** Sus 203 filas traen `CostoPromedio`, pero en cero.
La regla de §4.4 sigue en pie y no se toca: una línea sin costo viaja con
`costo_promedio=None` —«no se sabe»— y cualquier agregado que la contenga
publica el margen como «—», porque `(venta − 0) / venta` sería un **100 % de
margen que nadie ha ganado** en la pantalla de la gerencia.

El matiz es que en este endpoint el costo **llega como `0`, no como celda
vacía**, y un cero es un valor legítimo: hay ítems que costaron cero. Inferir
«no hay dato» de un cero convertiría en `NULL` costos reales de los otros
catorce puntos y borraría margen verdadero.

Por eso el criterio **no mira el importe, mira el módulo**: se tratan como sin
costo las filas cuyo `Origen` es `SIN ACUMULAR`, que es la afirmación correcta
—ese módulo de POS no entrega costo, medido en el 100 % de sus filas— en lugar
de una deducción a partir de un número que podría ser cierto. En consecuencia:

- `Origen = SIN ACUMULAR` → `costo_promedio = None`, **cualquiera que sea el
  importe que traiga la columna**. El día que ese módulo empiece a entregar
  costo de verdad, hay que quitar su valor de `ORIGENES_SIN_COSTO`, y las
  cuentas por `Origen` de la bitácora son la señal de que ese día llegó.
- `Origen = ACUMULADO` con `CostoPromedio = 0` → `Decimal("0.00")`, **el cero se
  conserva**: ahí la fuente sí está afirmando un costo.
- Celda de costo vacía, venga de donde venga → `None` y anotada. Un blanco no
  es un cero en ninguno de los dos módulos.

── Lo que esta fuente no puede arreglar ──────────────────────────────────────

- **`costos-razon-social` no trae vendedor.** `vendedor-acumulada` entregaba
  `codigo_vendedor` y `nombre_vendedor`; este endpoint no expone ninguno de los
  dos, así que las líneas viajan con ambos en `None`. Hoy no se pierde nada
  persistido —`venta_lineas` todavía no tiene columnas de vendedor y el reporte
  por vendedor se resuelve por el catálogo de clientes—, pero el reporte por
  vendedor del POS que aquellos campos iban a habilitar queda a la espera de que
  la API los añada aquí o de cruzar con `/ventas/canales-vendedor`.
- **Campos que el Excel tiene y este endpoint no**: NIT de cliente, condición de
  pago, domicilio y clase de cliente. Van a `NULL`. Inventarlos sería peor que
  no tenerlos.

── El contrato, tal como se midió ────────────────────────────────────────────

Autenticación: cabecera `Authorization` con el token **pelado**. Sin `Bearer` y
sin `Token ` —los dos devuelven 401 pese a que el mensaje de error de la propia
API sugiere `Bearer`—. El token se entrega con un prefijo `1-` que es un
identificador de clave, no parte del secreto, y **no se envía**.

Parámetros: `fecha_inicio`, `fecha_fin`, `id_cia` (obligatorio), `limit`
(máx 5000), `offset`, `format=csv`. Se usa **CSV**: con `format=csv` la descarga
es completa en streaming e ignora la paginación. Con JSON habría que encadenar
doscientas páginas por día y compañía.

Catorce columnas, con encabezado y **en mayúsculas y minúsculas mezcladas**:
`Origen`, `DescCO`, `Referencia`, `DescItem`, `CantidadInv`, `PrecioVenta`,
`ValorSubtotal`, `PrecioCosto`, `CostoPromedio`, `UtilidadBruta`, `Categoria`,
`PorcCosto`, `PorcRentabilidad`, `FechaDocto`. Los nombres se comparan
plegados a minúsculas (`DescCO` → `descco`), así que un cambio de capitalización
en la API no rompe la carga; un cambio de nombre sí, y debe romperla.

Mapeo a `LineaVenta`: `ValorSubtotal` → la venta contra presupuesto;
`CostoPromedio` → el costo del margen; `CantidadInv` → kilos (`cantidad_inv`);
`Categoria` → llega **en el formato exacto del Excel** (`'0001 - RES'`),
incluidas las dos variantes ortográficas de `0006`, así que la tabla
`mapeo_categorias` ya sembrada la resuelve tal cual y aquí no hay —ni debe
haber— un mapeo paralelo; `PorcRentabilidad` → `margen_siesa`, que existe **solo
para conciliación** (§4.4) y nunca alimenta el margen del reporte, que se
recalcula ponderado sobre totales; `FechaDocto` → `2026-08-01T00:00:00`.

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
    ESCALA_PORCENTAJE,
    a_decimal,
    a_fecha,
    normalizar_texto,
    sin_acentos,
)
from app.domain.puertos import LineaVenta
from app.infrastructure.fuentes.base import AnotacionFuente, RechazoFuente

if TYPE_CHECKING:  # pragma: no cover - solo para el tipado
    from app.core.config import Settings

#: El endpoint. Une los dos módulos de POS del lado de la API —lo que antes se
#: hacía aquí a mano, y mal: `pos-vendedor-detalle` inflaba PEREIRA un 33 %—.
RUTA_COSTOS_RAZON_SOCIAL = "/ventas/costos-razon-social"

#: Compañías de carnes. `id_cia` es obligatorio en este endpoint, así que se
#: recorren una a una. Nunca la 3 ni la 8: esa venta es de la otra instancia.
COMPANIAS_CARNES = (4, 6, 7)

#: Los dos valores de `Origen`. **Complementarios, no alternativos**: se suman.
ORIGEN_ACUMULADO = "ACUMULADO"
ORIGEN_SIN_ACUMULAR = "SIN ACUMULAR"
ORIGENES_CONOCIDOS = frozenset({ORIGEN_ACUMULADO, ORIGEN_SIN_ACUMULAR})

#: Módulos que **no entregan costo**, medido en el 100 % de sus filas. Sus ceros
#: no son costos: son la ausencia del dato escrita como número. Ver el
#: encabezado: el criterio afirma qué módulo no lo entrega en lugar de deducirlo
#: de un cero que en `ACUMULADO` sí sería un costo real.
ORIGENES_SIN_COSTO = frozenset({ORIGEN_SIN_ACUMULAR})

#: Nombres de columna **plegados a minúsculas**, que es como los compara
#: `_registros`. El CSV los entrega en `CamelCase` (`DescCO`, `FechaDocto`).
COL_ORIGEN = "origen"
COL_DESC_CO = "descco"
COL_FECHA = "fechadocto"
COL_SUBTOTAL = "valorsubtotal"
COL_COSTO = "costopromedio"
COL_CANTIDAD = "cantidadinv"
COL_CATEGORIA = "categoria"
COL_RENTABILIDAD = "porcrentabilidad"

#: Prefijo identificador de la clave. **No forma parte del secreto y no se
#: envía**: mandarlo completo devuelve `401 {"detail":"Token invalido."}`.
#: `noqa: S105` porque es justo lo contrario de un secreto embebido —es el
#: trozo del token que se descarta—, pero el nombre lleva la palabra «token».
PREFIJO_TOKEN = "1-"  # noqa: S105

#: Columnas sin las cuales no hay línea de venta que valga: el punto de venta,
#: el día, la medida contra la que se compara el presupuesto y **el módulo del
#: que viene la fila**. `Origen` está aquí y no es un capricho: es lo único que
#: distingue «este costo es cero» de «este módulo no da costo», y sin él las
#: filas de PEREIRA entrarían con costo 0 y publicarían 100 % de margen. Que
#: falte esa columna es un cambio de contrato que tiene que parar la carga.
COLUMNAS_OBLIGATORIAS = (COL_ORIGEN, COL_DESC_CO, COL_FECHA, COL_SUBTOTAL)

#: Códigos de estado que merecen otro intento: la API está viva pero saturada o
#: caída un instante. Un 401 o un 422 no se reintentan —volver a pedir lo mismo
#: con el mismo token da exactamente el mismo 401— y un 404 tampoco.
ESTADOS_REINTENTABLES = frozenset({408, 429, 500, 502, 503, 504})

_CERO = Decimal("0")
#: `Numeric(12, 6)` admite seis enteros y seis decimales; el límite superior
#: es exclusivo porque `1_000_000.000000` ya requiere siete enteros.
_LIMITE_ABSOLUTO_MARGEN = Decimal("1000000")

#: `noqa: S105`: es el texto que se muestra cuando **falta** el token, no un
#: token. El nombre de la constante es lo único que dispara la regla.
MENSAJE_SIN_TOKEN = (
    "La fuente «siesa» necesita credenciales. Configure `SIGREP_SIESA_TOKEN` con el "  # noqa: S105
    "token de la API de consulta —el prefijo «1-» puede dejarse o quitarse, se pela "
    "solo— y `SIGREP_SIESA_URL_BASE` si la API no está en su dirección habitual."
)

MENSAJE_SIN_COMPANIAS = (
    "La fuente «siesa» necesita saber qué compañías consultar: `id_cia` es obligatorio "
    "en /ventas/costos-razon-social y una consulta sin él no devuelve «todas», falla. "
    "Configure `SIGREP_SIESA_COMPANIAS` con las compañías de carnes —"
    f"{','.join(str(c) for c in COMPANIAS_CARNES)}, su valor por defecto—. Dejarla "
    "vacía cargaría cero filas y la corrida parecería un día sin venta."
)

MENSAJE_SIN_DESCRIPCIONES = (
    "La fuente «siesa» resuelve el punto de venta por la descripción que entrega "
    "SIESA (`DescCO`), y no hay ningún punto de venta con `descripcion_siesa` en la "
    "base. Siembre la estructura (§3.1) antes de ingerir: sin ese directorio, todas "
    "las filas se rechazarían por punto de venta desconocido."
)


@dataclass(frozen=True, slots=True)
class _Medidas:
    """Los tres importes de una fila del CSV, ya convertidos.

    `costo_promedio` es opcional y los otros dos no, y esa asimetría es el
    núcleo de la corrección de §4.4: el módulo de POS de PEREIRA no entrega el
    costo, y un costo que no llega es `None` —«no se sabe»—, nunca un cero que
    afirmaría que vender no costó nada.
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


def clave_origen(valor: object) -> str:
    """`Origen` reducido a algo comparable: mayúsculas, sin tildes, sin dobles espacios.

    `'sin  acumular'` y `'SIN ACUMULAR'` son el mismo módulo. Nada más que eso:
    un valor que no sea uno de los dos conocidos **no se asimila al que más se
    le parezca**, porque de esa comparación depende que un costo se publique o
    se deje en «—».
    """
    crudo = normalizar_texto(valor)
    if crudo is None:
        return ""
    return " ".join(sin_acentos(crudo).upper().split())


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
    #: Compañías a recorrer, una petición por cada una. **No puede estar vacío**:
    #: `id_cia` es obligatorio en este endpoint y omitirlo no devuelve «todas».
    companias: tuple[int, ...] = COMPANIAS_CARNES
    timeout_conexion_seg: float = 15.0
    #: Un mes son cientos de miles de filas y la descarga tarda. Diez minutos de
    #: lectura no es generosidad: es el tiempo que cuesta el caso real.
    timeout_lectura_seg: float = 600.0
    reintentos: int = 3
    espera_reintento_seg: float = 2.0

    def __post_init__(self) -> None:
        if not self.companias:
            raise ErrorValidacion(MENSAJE_SIN_COMPANIAS)

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
        #: Constancia de lo que sí entró pero merece verse: el reparto por
        #: `Origen`, las filas sin costo, las que llegaron fuera del rango.
        self.anotaciones: list[AnotacionFuente] = []

        self._numero = 0
        self._leidas: dict[str, int] = {}
        self._entregadas: dict[str, int] = {}

    # ── Identidad ─────────────────────────────────────────────────────────────

    @property
    def nombre(self) -> str:
        """Va a `corridas_ingesta.origen`. Nunca lleva el token, solo el host."""
        return f"API SIESA {self._configuracion.url_base} ({RUTA_COSTOS_RAZON_SOCIAL})"

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
        """Líneas del rango, ambos extremos incluidos, de las tres compañías.

        Es un generador: la respuesta se lee en streaming y no hay en ningún
        momento la descarga entera en memoria.

        `hasta` viaja tal cual a `fecha_fin`, **sin sumarle un día**, porque
        `fecha_fin` es inclusiva y aquí lo declara el propio contrato de la API.
        Ver la trampa 1 del encabezado del módulo antes de tocar esta línea.

        Los dos valores de `Origen` se cargan **los dos**: son complementarios y
        filtrar por uno perdería un punto de venta entero o los otros catorce.
        """
        pedidos = {str(c).strip().zfill(3) for c in centros} if centros else None

        for parametros in self._peticiones(desde, hasta):
            lector = csv.DictReader(self._lineas(parametros))
            for registro in self._registros(lector):
                self._numero += 1
                origen = clave_origen(registro.get(COL_ORIGEN))
                self._leidas[origen] = self._leidas.get(origen, 0) + 1
                linea = self._formar_linea(registro, origen, desde, hasta, pedidos)
                if linea is not None:
                    self._entregadas[origen] = self._entregadas.get(origen, 0) + 1
                    yield linea

        self._anotar_origenes()

    # ── Lectura del CSV ───────────────────────────────────────────────────────

    def _registros(self, lector: csv.DictReader[str]) -> Iterator[dict[str, str]]:
        """Filas del CSV, tras comprobar que el encabezado es el del contrato."""
        try:
            columnas = lector.fieldnames
        except StopIteration:  # pragma: no cover - `DictReader` ya lo absorbe
            columnas = None

        if not columnas:
            # Cuerpo vacío con 200. No se lanza: sacrificaría las otras dos
            # compañías por una respuesta rara de esta. Queda en la bitácora y
            # la corrida mostrará las filas que no trajo.
            self.anotaciones.append(
                AnotacionFuente(
                    fila=None,
                    campo="Respuesta",
                    valor=RUTA_COSTOS_RAZON_SOCIAL,
                    motivo=(
                        f"{RUTA_COSTOS_RAZON_SOCIAL} devolvió una respuesta sin encabezado "
                        "CSV para una de las compañías. Se leyeron cero filas de esa consulta."
                    ),
                )
            )
            return

        presentes = {str(c).strip().lower() for c in columnas if c}
        faltantes = [c for c in COLUMNAS_OBLIGATORIAS if c not in presentes]
        if faltantes:
            raise ErrorFuenteSiesa(
                f"El CSV de {RUTA_COSTOS_RAZON_SOCIAL} no trae las columnas obligatorias: "
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
        origen: str,
        desde: date,
        hasta: date,
        pedidos: set[str] | None,
    ) -> LineaVenta | None:
        """Un registro del CSV a `LineaVenta`, o `None` con su motivo apuntado."""
        numero = self._numero

        fecha = a_fecha(registro.get(COL_FECHA))
        if fecha is None:
            self._rechazar(numero, "FechaDocto", registro.get(COL_FECHA), "no es una fecha legible")
            return None
        if fecha < desde or fecha > hasta:
            # `fecha_fin` es inclusiva y la API respeta el rango, así que esto no
            # debería pasar. Si pasa, es que el contrato cambió y hay que verlo.
            self._anotar(
                numero,
                "FechaDocto",
                fecha.isoformat(),
                f"{RUTA_COSTOS_RAZON_SOCIAL} devolvió una fila fuera del rango pedido "
                f"({desde.isoformat()} a {hasta.isoformat()}, ambos incluidos); no se carga.",
            )
            return None

        codigo = self._resolver_punto(registro.get(COL_DESC_CO), numero)
        if codigo is None:
            return None
        if pedidos is not None and codigo not in pedidos:
            return None

        medidas = self._medidas(registro, origen, numero)
        if medidas is None:
            return None
        if medidas.costo_promedio is None:
            self._anotar(
                numero,
                "CostoPromedio",
                codigo,
                "Fila sin costo en el origen; entra como NULL —no como cero— y **no tiene "
                f"margen calculable**. El módulo «{origen or ORIGEN_SIN_ACUMULAR}» no expone "
                "el costo, así que ni este punto de venta ni ningún agregado que lo contenga "
                "publican margen: la pantalla muestra «—» hasta que la API entregue el dato.",
            )

        return LineaVenta(
            centro_operacion=codigo,
            fecha=fecha,
            valor_subtotal=medidas.valor_subtotal,
            costo_promedio=medidas.costo_promedio,
            cantidad_inv=medidas.cantidad,
            categoria_siesa=normalizar_texto(registro.get(COL_CATEGORIA), limite=120),
            # Solo para conciliación (§4.4): el margen del reporte se recalcula
            # ponderado sobre totales y nunca sale de esta columna.
            margen_siesa=self._margen(registro, numero),
            # NIT, domicilio, clase de cliente y condición de pago no vienen en
            # este endpoint, y tampoco el vendedor. Van a `NULL`; no se inventan.
            fila_origen=numero,
        )

    def _resolver_punto(self, descripcion: object, numero: int) -> str | None:
        """El C.O. de la descripción de SIESA, o `None` tras rechazar la fila."""
        crudo = normalizar_texto(descripcion)
        if crudo is None:
            self._rechazar(numero, "DescCO", descripcion, "la fila no indica centro de operación")
            return None

        codigo = self._puntos.get(clave_descripcion(crudo))
        if codigo is None:
            self._rechazar(
                numero,
                "DescCO",
                crudo,
                "esa descripción no corresponde a ningún punto de venta conocido. Añádala en "
                "`puntos_venta.descripcion_siesa` si es un punto nuevo; la venta no se adivina",
            )
            return None
        return codigo

    def _medidas(self, registro: Mapping[str, str], origen: str, numero: int) -> _Medidas | None:
        """Los tres importes de la fila, o `None` si alguno no es un número.

        Tres reglas distintas para tres campos que no significan lo mismo:

        - **La venta y los kilos vacíos valen cero.** Son medidas de lo que se
          vendió; una celda en blanco ahí es un cero que la API no molestó en
          escribir, y rechazar la fila costaría venta real.
        - **El costo depende del módulo, no del importe.** Si `Origen` está en
          `ORIGENES_SIN_COSTO` la fila entra con `None` *aunque traiga un cero*:
          ese módulo no publica costo y su cero es la ausencia del dato escrita
          como número. En cualquier otro módulo el cero **se conserva** —hay
          ítems que costaron cero— y solo la celda vacía es `None`. De esa
          distinción depende que §4.4 publique el margen o pinte «—», y
          confundirla en cualquiera de los dos sentidos hace daño: tratar el cero
          de `ACUMULADO` como «sin dato» borra margen real, y tratar el de
          `SIN ACUMULAR` como costo publica un 100 % que nadie ha ganado.
        - **Una celda con contenido que no es un número rechaza la fila**, sea
          cual sea el campo: ahí hay algo que alguien tiene que mirar, y
          convertirlo en cero o en nulo sería tapar el problema.
        """
        obligatorias: dict[str, Decimal] = {}
        for campo, etiqueta, escala in (
            (COL_SUBTOTAL, "ValorSubtotal", ESCALA_DINERO),
            (COL_CANTIDAD, "CantidadInv", ESCALA_KILOS),
        ):
            crudo = registro.get(campo)
            if normalizar_texto(crudo) is None:
                obligatorias[campo] = _CERO
                continue
            numero_decimal = a_decimal(crudo, escala)
            if numero_decimal is None:
                self._rechazar(numero, etiqueta, crudo, "no es un número")
                return None
            obligatorias[campo] = numero_decimal

        costo: Decimal | None = None
        crudo_costo = registro.get(COL_COSTO)
        if origen not in ORIGENES_SIN_COSTO and normalizar_texto(crudo_costo) is not None:
            costo = a_decimal(crudo_costo, ESCALA_DINERO)
            if costo is None:
                self._rechazar(numero, "CostoPromedio", crudo_costo, "no es un número")
                return None

        return _Medidas(
            valor_subtotal=obligatorias[COL_SUBTOTAL],
            cantidad=obligatorias[COL_CANTIDAD],
            costo_promedio=costo,
        )

    def _margen(self, registro: Mapping[str, str], numero: int) -> Decimal | None:
        """`PorcRentabilidad` a `margen_siesa`, sin que pueda costar una venta.

        Es un campo de **conciliación**: el margen del reporte se recalcula
        ponderado sobre totales y nunca sale de aquí. Por eso un valor ilegible
        se anota y se deja en `NULL` en vez de rechazar la fila: perder venta
        real por una columna que no alimenta ningún indicador sería el peor
        cambio posible.
        """
        crudo = registro.get(COL_RENTABILIDAD)
        if normalizar_texto(crudo) is None:
            return None
        margen = a_decimal(crudo, ESCALA_PORCENTAJE)
        if margen is None:
            self._anotar(
                numero,
                "PorcRentabilidad",
                crudo,
                "No es un número. La venta se carga igual —este campo solo sirve para "
                "conciliar (§4.4) y el margen del reporte se recalcula sobre totales—, "
                "pero `margen_siesa` queda en NULL para esta línea.",
            )
        elif abs(margen) >= _LIMITE_ABSOLUTO_MARGEN:
            self._anotar(
                numero,
                "PorcRentabilidad",
                crudo,
                "Excede el rango persistible de margen_siesa; la venta se carga igual —"
                "este campo solo sirve para conciliar (§4.4)—, pero queda en NULL para "
                "esta línea.",
            )
            return None
        return margen

    # ── HTTP ──────────────────────────────────────────────────────────────────

    def _peticiones(self, desde: date, hasta: date) -> Iterator[dict[str, str]]:
        """Un juego de parámetros por compañía. `id_cia` es **obligatorio** aquí.

        ⚠️ `fecha_fin` es **INCLUSIVA**: `fecha_inicio=2026-08-01&fecha_fin=
        2026-08-02` devuelve los días 1 y 2, y el propio contrato de la API lo
        declara. `hasta` viaja tal cual. No le sume un día «para arreglarlo».
        """
        base = {
            "fecha_inicio": desde.isoformat(),
            "fecha_fin": hasta.isoformat(),
            "format": "csv",
        }
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

    def _lineas(self, parametros: Mapping[str, str]) -> Iterator[str]:
        """Las líneas del CSV en streaming, con reintentos acotados.

        **Solo se reintenta lo que todavía no entregó ninguna línea.** Reintentar
        una descarga cortada a la mitad volvería a mandar desde la primera fila
        lo que ya se leyó, y en una fuente de cientos de miles de filas eso es
        venta duplicada que nadie notaría: el total sube y todo el mundo se lo
        cree. Si la conexión se cae con datos ya entregados, la corrida falla —y
        §5 garantiza que lo insertado se deshace entero, no a medias—.
        """
        configuracion = self._configuracion
        url = configuracion.url_base + RUTA_COSTOS_RAZON_SOCIAL

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
                        f"No se pudo leer {RUTA_COSTOS_RAZON_SOCIAL} de la API de SIESA "
                        f"({type(exc).__name__}). Se agotaron los {configuracion.reintentos} "
                        "intentos configurados en `SIGREP_SIESA_REINTENTOS`."
                    ) from None
            if configuracion.espera_reintento_seg > 0:
                sleep(configuracion.espera_reintento_seg * intento)

    @staticmethod
    def _error_http(respuesta: httpx.Response) -> ErrorFuenteSiesa:
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
                "Revise el rango de fechas y los parámetros de la consulta; `id_cia` es "
                "obligatorio en este endpoint."
            )
        return ErrorFuenteSiesa(
            f"La API de SIESA respondió {respuesta.status_code} en "
            f"{RUTA_COSTOS_RAZON_SOCIAL}. {pista}" + (f" Respuesta: {detalle}" if detalle else ""),
            reintentable=respuesta.status_code in ESTADOS_REINTENTABLES,
        )

    # ── Bitácora ──────────────────────────────────────────────────────────────

    def _rechazar(self, fila: int, campo: str, valor: object, motivo: str) -> None:
        self.rechazos.append(
            RechazoFuente(
                fila=fila,
                campo=campo,
                valor=normalizar_texto(valor, limite=300),
                motivo=f"{RUTA_COSTOS_RAZON_SOCIAL}: «{campo}» {motivo}.",
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

    def _anotar_origenes(self) -> None:
        """Cuántas filas trajo cada `Origen` y cuántas se entregaron a la ingesta.

        Es la señal que sustituye al reparto manual entre dos endpoints: sin
        ella, el día que `SIN ACUMULAR` deje de aparecer —porque PEREIRA cambió
        de módulo o empezó a acumular— la venta caería 101 millones y nadie
        sabría por qué hasta comparar con el mes pasado. Y si aparece un valor de
        `Origen` que esta ingesta no conoce, queda dicho aquí en lugar de
        colarse tratado como si trajera costo.
        """
        for origen in sorted(set(self._leidas) | set(self._entregadas)):
            etiqueta = origen or "(vacío)"
            aviso = (
                ""
                if origen in ORIGENES_CONOCIDOS
                else (
                    " ⚠️ Este valor de `Origen` no es ninguno de los conocidos "
                    f"({', '.join(sorted(ORIGENES_CONOCIDOS))}). Sus filas se cargaron con el "
                    "costo tal cual llegó; si ese módulo tampoco lo entrega, añádalo a "
                    "`ORIGENES_SIN_COSTO` antes de fiarse de su margen."
                )
            )
            self.anotaciones.append(
                AnotacionFuente(
                    fila=None,
                    campo="Origen",
                    valor=etiqueta,
                    motivo=(
                        f"Origen «{etiqueta}»: {self._leidas.get(origen, 0)} filas leídas, "
                        f"{self._entregadas.get(origen, 0)} entregadas a la ingesta.{aviso}"
                    ),
                )
            )
