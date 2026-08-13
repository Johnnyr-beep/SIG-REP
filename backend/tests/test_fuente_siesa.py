"""`FuenteVentaSiesa`: la venta leída de la API de consulta (§3.4, §5).

**Ninguna prueba de este archivo toca la red.** Todas las respuestas HTTP se
simulan con `httpx.MockTransport` sobre el CSV real —las once columnas, con sus
nombres exactos—. Una suite que depende de una API externa es una suite que
falla el día que no hay internet, y entonces nadie sabe si lo que se rompió fue
el código o la conexión.

Cada prueba corresponde a un hallazgo **medido** contra la API el 12–13 de
agosto de 2026, no a un caso imaginado. La que más vale es
`test_fecha_fin_es_inclusiva_y_no_se_le_suma_un_dia`: `poscarnes` documenta
`fecha_fin` como exclusiva y estos dos endpoints la tratan como inclusiva, así
que cualquiera que llegue de leer aquel contrato va a asumir lo contrario y
«arreglarlo» sumando un día. Ese arreglo mete el 1 de septiembre dentro de
agosto y esta prueba es lo único que lo frena.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services import ingesta_service
from app.application.services.ingesta_service import IngestaService
from app.domain.enums import EstadoCorrida, FuenteIngesta
from app.infrastructure.fuentes.siesa import (
    RUTA_POS_VENDEDOR_DETALLE,
    RUTA_VENDEDOR_ACUMULADA,
    ConfiguracionSiesa,
    ErrorFuenteSiesa,
    FuenteVentaSiesa,
    token_efectivo,
)
from app.infrastructure.models.catalogo import Categoria
from app.infrastructure.models.venta import VentaLinea
from tests.conftest import id_punto_venta

D = Decimal

#: El token de las pruebas. No es un secreto real; es la forma exacta en que la
#: API entrega el suyo: `1-` seguido de 64 hexadecimales.
TOKEN_CON_PREFIJO = "1-" + "a1b2c3d4" * 8
TOKEN_PELADO = "a1b2c3d4" * 8

#: `{descripcion_siesa: C.O.}` tal como lo siembra `app/infrastructure/semilla.py`.
#: Se repite aquí, y no se importa, a propósito: si alguien cambia la semilla,
#: quiero que falle una prueba de resolución, no que la prueba cambie con ella.
DESCRIPCIONES = {
    "PDV MALAMBO": "402",
    "CONCORD": "603",
    "PDV LA GRANJA": "403",
    "PDV BUCARMANGA": "412",  # la errata es de SIESA y se conserva
    "PDV PEREIRA": "409",
    "ALAMEDA 1": "605",
}

#: Encabezado exacto del CSV, en el orden en que lo devuelve la API.
ENCABEZADO = (
    "desc_co,codigo_vendedor,nombre_vendedor,referencia,desc_item,"
    "cantidad,costo_promedio,precio_unit,valor_subtotal,categoria,fecha"
)


def fila(
    desc_co: str = "PDV MALAMBO",
    *,
    fecha: str = "2026-08-01 00:00:00",
    cantidad: str = "19.9",
    costo: str = "76853.8",
    subtotal: str = "111440",
    categoria: str = "0001 - RES",
    vendedor: str = "V01",
    nombre_vendedor: str = "JOHANA MUÑOZ",
    referencia: str = "1039",
    desc_item: str = "HUESO SUSTANCIA CARNUDO",
    precio: str = "5600",
) -> str:
    """Una fila del CSV. Los valores por defecto son los de la fila real
    `1039 HUESO SUSTANCIA CARNUDO` verificada contra el Excel el 1-ago."""
    return (
        f"{desc_co},{vendedor},{nombre_vendedor},{referencia},{desc_item},"
        f"{cantidad},{costo},{precio},{subtotal},{categoria},{fecha}"
    )


def csv_ventas(*filas: str) -> str:
    return "\n".join((ENCABEZADO, *filas)) + "\n"


# ── La API simulada ───────────────────────────────────────────────────────────


class ApiFalsa:
    """La API de consulta, en memoria. Registra lo que se le pidió.

    Cada ruta lleva un guion de respuestas que se consume en orden; la última se
    repite. Eso es lo que permite probar «falla dos veces y a la tercera
    responde» sin inventarse un reloj ni esperar de verdad.
    """

    def __init__(self) -> None:
        self.peticiones: list[httpx.Request] = []
        self._guiones: dict[str, list[tuple[int, str] | Exception]] = {}

    def responder(self, ruta: str, *guion: tuple[int, str] | Exception) -> ApiFalsa:
        self._guiones[ruta] = list(guion)
        return self

    def ventas(self, *filas: str) -> ApiFalsa:
        """Atajo: `vendedor-acumulada` devuelve estas filas y PEREIRA, ninguna."""
        self.responder(RUTA_VENDEDOR_ACUMULADA, (200, csv_ventas(*filas)))
        self.responder(RUTA_POS_VENDEDOR_DETALLE, (200, csv_ventas()))
        return self

    def rutas_pedidas(self) -> list[str]:
        return [p.url.path for p in self.peticiones]

    def parametros(self, ruta: str) -> dict[str, str]:
        for peticion in self.peticiones:
            if peticion.url.path == ruta:
                return dict(peticion.url.params)
        raise AssertionError(f"Nunca se pidió {ruta}. Se pidió: {self.rutas_pedidas()}")

    def _manejar(self, peticion: httpx.Request) -> httpx.Response:
        self.peticiones.append(peticion)
        guion = self._guiones.get(peticion.url.path)
        if not guion:
            return httpx.Response(404, text="ruta no simulada en la prueba")
        paso = guion.pop(0) if len(guion) > 1 else guion[0]
        if isinstance(paso, Exception):
            raise paso
        estado, cuerpo = paso
        return httpx.Response(estado, text=cuerpo)

    def cliente(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self._manejar))


def configuracion(token: str = TOKEN_CON_PREFIJO, **extra: object) -> ConfiguracionSiesa:
    """Configuración de pruebas. `espera_reintento_seg=0`: nadie duerme aquí."""
    parametros: dict[str, object] = {
        "url_base": "https://apiconsulta.pruebas.local",
        "token": SecretStr(token),
        "espera_reintento_seg": 0.0,
    }
    parametros.update(extra)
    return ConfiguracionSiesa(**parametros)  # type: ignore[arg-type]


def montar(api: ApiFalsa, **extra: object) -> FuenteVentaSiesa:
    return FuenteVentaSiesa(
        DESCRIPCIONES, configuracion=configuracion(**extra), sesion_http=api.cliente()
    )


def leer(
    api: ApiFalsa,
    desde: date = date(2026, 8, 1),
    hasta: date = date(2026, 8, 1),
    **extra: object,
) -> tuple[FuenteVentaSiesa, list[object]]:
    fuente = montar(api, **extra)
    return fuente, list(fuente.obtener_ventas(desde, hasta))


# ── §5 · `fecha_fin` es INCLUSIVA ─────────────────────────────────────────────


def test_fecha_fin_es_inclusiva_y_no_se_le_suma_un_dia() -> None:
    """La trampa más peligrosa de esta integración, fijada por contrato.

    Medido el 13-ago-2026: `fecha_inicio=2026-08-01&fecha_fin=2026-08-02`
    devuelve los días 1 **y** 2. `/ventas/poscarnes` documenta lo contrario
    —«fecha final (exclusiva)»— y quien venga de leer aquel contrato va a
    «arreglar» esto sumando un día. Si lo hace, agosto cargará el 1 de
    septiembre y el cierre de mes saldrá largo justo cuando se mira.
    """
    api = ApiFalsa().ventas(fila(fecha="2026-08-02 00:00:00"))
    _, lineas = leer(api, date(2026, 8, 1), date(2026, 8, 2))

    parametros = api.parametros(RUTA_VENDEDOR_ACUMULADA)
    assert parametros["fecha_inicio"] == "2026-08-01"
    assert parametros["fecha_fin"] == "2026-08-02", (
        "`fecha_fin` es INCLUSIVA en este endpoint: se manda tal cual el «hasta» "
        "que pidió la ingesta, sin sumarle un día."
    )
    assert parametros["format"] == "csv"
    assert len(lineas) == 1, "el día 2 forma parte del rango 1–2 y tiene que entrar"


def test_el_ultimo_dia_del_rango_entra_en_la_carga() -> None:
    """La otra cara: pedir 1–2 y quedarse solo con el 1 sería perder un día."""
    api = ApiFalsa().ventas(
        fila(fecha="2026-08-01 00:00:00", subtotal="100"),
        fila(fecha="2026-08-02 00:00:00", subtotal="200"),
    )
    _, lineas = leer(api, date(2026, 8, 1), date(2026, 8, 2))

    assert [linea.fecha for linea in lineas] == [date(2026, 8, 1), date(2026, 8, 2)]  # type: ignore[attr-defined]


def test_una_fila_fuera_del_rango_no_se_carga_y_queda_anotada() -> None:
    """Si la API devolviera algo fuera del rango, su contrato habría cambiado."""
    api = ApiFalsa().ventas(fila(fecha="2026-09-01 00:00:00"))
    fuente, lineas = leer(api, date(2026, 8, 1), date(2026, 8, 31))

    assert lineas == []
    assert any("fuera del rango pedido" in a.motivo for a in fuente.anotaciones)


# ── §1 del documento de integración · El token ────────────────────────────────


@pytest.mark.parametrize("token", [TOKEN_CON_PREFIJO, TOKEN_PELADO])
def test_el_token_viaja_pelado_da_igual_como_lo_configuren(token: str) -> None:
    """El prefijo `1-` identifica la clave, no forma parte del secreto.

    Enviarlo completo devuelve `401 {"detail":"Token invalido."}`. Y va sin
    `Bearer`: `Authorization: Bearer <token>` también devuelve 401, pese a que
    el mensaje de error de la propia API lo sugiere.
    """
    api = ApiFalsa().ventas(fila())
    leer(api, **{"token": token})

    cabecera = api.peticiones[0].headers["authorization"]
    assert cabecera == TOKEN_PELADO
    assert not cabecera.lower().startswith(("bearer", "token ")), (
        "«Bearer» y «Token » devuelven 401 en esta API"
    )
    assert not cabecera.startswith("1-")


def test_token_efectivo_pela_el_prefijo_y_solo_el_prefijo() -> None:
    assert token_efectivo("1-abc") == "abc"
    assert token_efectivo("  1-abc  ") == "abc"
    assert token_efectivo("abc") == "abc"
    # `1-` solo se quita al principio: un token que lo contenga en medio no se toca.
    assert token_efectivo("ab1-c") == "ab1-c"


def test_el_token_no_aparece_en_el_mensaje_de_un_error_de_la_api() -> None:
    """Un secreto en un mensaje de error acaba en la bitácora y en un ticket."""
    api = ApiFalsa()
    api.responder(RUTA_VENDEDOR_ACUMULADA, (401, '{"detail":"Token invalido."}'))
    api.responder(RUTA_POS_VENDEDOR_DETALLE, (200, csv_ventas()))

    with pytest.raises(ErrorFuenteSiesa) as capturado:
        leer(api)

    mensaje = str(capturado.value)
    assert TOKEN_PELADO not in mensaje
    assert TOKEN_CON_PREFIJO not in mensaje
    assert "401" in mensaje and "SIGREP_SIESA_TOKEN" in mensaje


def test_la_configuracion_nunca_imprime_el_token() -> None:
    """`repr` de la configuración: es lo que sale en una traza de excepción."""
    texto = repr(configuracion())
    assert TOKEN_PELADO not in texto
    assert TOKEN_CON_PREFIJO not in texto


def test_el_nombre_del_origen_lleva_la_url_pero_no_el_token() -> None:
    """`corridas_ingesta.origen` se guarda y se muestra en pantalla."""
    nombre = montar(ApiFalsa().ventas()).nombre
    assert "apiconsulta.pruebas.local" in nombre
    assert TOKEN_PELADO not in nombre


# ── §3.1 · Resolución del punto de venta por `desc_co` ────────────────────────


@pytest.mark.parametrize(
    ("descripcion", "esperado"),
    [
        ("PDV MALAMBO", "402"),
        ("CONCORD", "603"),
        ("PDV BUCARMANGA", "412"),  # con la errata de SIESA
        ("ALAMEDA 1", "605"),
        ("  pdv   malambo  ", "402"),  # espacios de más y minúsculas
        ("PDV MALÁMBO", "402"),  # una tilde que alguien añadió en el ERP
    ],
)
def test_el_punto_de_venta_se_resuelve_por_la_descripcion_de_siesa(
    descripcion: str, esperado: str
) -> None:
    """Este endpoint **no trae el código de centro de operación**, solo `desc_co`.

    La resolución normaliza espacios, tildes y mayúsculas. Nada más: `PDV LA 43`
    y `PDV LA 93` se parecen demasiado como para permitir aproximaciones.
    """
    api = ApiFalsa().ventas(fila(descripcion))
    _, lineas = leer(api)

    assert len(lineas) == 1
    assert lineas[0].centro_operacion == esperado  # type: ignore[attr-defined]


def test_una_descripcion_desconocida_rechaza_la_fila_con_su_motivo() -> None:
    """Nunca se adivina el punto de venta y nunca se descarta en silencio (§5)."""
    api = ApiFalsa().ventas(fila("PDV MARTE"), fila("PDV MALAMBO"))
    fuente, lineas = leer(api)

    assert len(lineas) == 1, "la fila buena sigue entrando; una mala no tumba la carga"
    assert len(fuente.rechazos) == 1
    rechazo = fuente.rechazos[0]
    assert rechazo.campo == "desc_co"
    assert rechazo.valor == "PDV MARTE"
    assert "ningún punto de venta conocido" in rechazo.motivo
    assert RUTA_VENDEDOR_ACUMULADA in rechazo.motivo, "el motivo dice por qué endpoint vino"


def test_una_fila_sin_descripcion_de_centro_se_rechaza() -> None:
    api = ApiFalsa().ventas(fila(""))
    fuente, lineas = leer(api)

    assert lineas == []
    assert fuente.rechazos[0].campo == "desc_co"
    assert "no indica centro de operación" in fuente.rechazos[0].motivo


def test_sin_directorio_de_descripciones_la_fuente_dice_que_sembrar() -> None:
    """Sin `puntos_venta.descripcion_siesa` se rechazaría el 100 % de las filas.

    Más vale negarse a arrancar diciendo qué falta que producir una corrida con
    treinta mil rechazos idénticos.
    """
    from app.core.errors import ErrorValidacion

    with pytest.raises(ErrorValidacion, match="descripción"):
        FuenteVentaSiesa({}, configuracion=configuracion())


def test_sin_token_configurado_la_fuente_dice_que_configurar() -> None:
    from app.core.config import Settings
    from app.core.errors import ErrorValidacion

    settings = Settings(secret_key=SecretStr("c" * 40), siesa_token=SecretStr(""))
    with pytest.raises(ErrorValidacion, match="SIGREP_SIESA_TOKEN"):
        ConfiguracionSiesa.desde_settings(settings)


def test_filtra_por_los_centros_que_pide_la_ingesta() -> None:
    api = ApiFalsa().ventas(fila("PDV MALAMBO"), fila("CONCORD"))
    fuente = montar(api)
    lineas = list(fuente.obtener_ventas(date(2026, 8, 1), date(2026, 8, 1), centros=["603"]))

    assert [linea.centro_operacion for linea in lineas] == ["603"]


# ── §3.1 · La categoría llega en el formato del Excel ─────────────────────────


def test_la_categoria_llega_en_el_formato_del_excel_y_no_se_reescribe() -> None:
    """`categoria` viene como `'0001 - RES'`, idéntica a la del Excel.

    Por eso aquí **no hay ningún mapeo**: la tabla `mapeo_categorias` ya sembrada
    lo resuelve tal cual. Un `dict` paralelo en el código sería justo lo que §3.1
    prohíbe —el negocio reclasifica sin esperar un despliegue—.
    """
    api = ApiFalsa().ventas(
        fila(categoria="0001 - RES"),
        fila(categoria="0006 - QUESOS Y LACTEOS"),  # la variante con typo
    )
    _, lineas = leer(api)

    assert [linea.categoria_siesa for linea in lineas] == [  # type: ignore[attr-defined]
        "0001 - RES",
        "0006 - QUESOS Y LACTEOS",
    ]


# ── §3.4 · Importes: `Decimal` de extremo a extremo ───────────────────────────


def test_los_importes_son_decimal_exacto_ni_un_float_por_el_camino() -> None:
    """La fila `1039 HUESO SUSTANCIA CARNUDO`, verificada contra el Excel.

    `cantidad 19.9`, `costo 76853.8`, `subtotal 111440`: idénticos a la fila
    equivalente de la hoja `VENTA`. Se comparan con `Decimal` construido desde
    texto; pasar por `float` arrastraría el error binario y en un consolidado de
    veinte mil millones eso es un defecto, no un detalle.
    """
    _, lineas = leer(ApiFalsa().ventas(fila()))
    linea = lineas[0]

    assert linea.valor_subtotal == D("111440.00")  # type: ignore[attr-defined]
    assert linea.costo_promedio == D("76853.80")  # type: ignore[attr-defined]
    assert linea.cantidad_inv == D("19.900")  # type: ignore[attr-defined]
    assert all(
        isinstance(v, Decimal)
        for v in (linea.valor_subtotal, linea.costo_promedio, linea.cantidad_inv)  # type: ignore[attr-defined]
    )


def test_un_importe_que_no_es_un_numero_rechaza_la_fila() -> None:
    """Vacío vale cero —no hay nada que interpretar—; basura, no."""
    api = ApiFalsa().ventas(fila(subtotal="N/D"), fila(subtotal="100"))
    fuente, lineas = leer(api)

    assert len(lineas) == 1
    assert fuente.rechazos[0].campo == "valor_subtotal"
    assert "no es un número" in fuente.rechazos[0].motivo


def test_el_vendedor_viaja_en_la_linea() -> None:
    """`codigo_vendedor` y `nombre_vendedor` son lo que habilita el reporte por
    vendedor del POS, donde la venta es anónima y no hay cliente al que colgarla."""
    _, lineas = leer(ApiFalsa().ventas(fila()))

    assert lineas[0].codigo_vendedor == "V01"  # type: ignore[attr-defined]
    assert lineas[0].nombre_vendedor == "JOHANA MUÑOZ"  # type: ignore[attr-defined]


def test_los_campos_que_este_endpoint_no_trae_van_a_nulo() -> None:
    """NIT, condición de pago, domicilio y clase de cliente no vienen. No se inventan."""
    _, lineas = leer(ApiFalsa().ventas(fila()))
    linea = lineas[0]

    assert linea.nit_cliente is None  # type: ignore[attr-defined]
    assert linea.condicion_pago is None  # type: ignore[attr-defined]
    assert linea.domicilio is None  # type: ignore[attr-defined]
    assert linea.clase_cliente is None  # type: ignore[attr-defined]


# ── La unión de los dos endpoints ─────────────────────────────────────────────


def test_une_los_dos_endpoints_y_pereira_llega_por_el_suyo() -> None:
    """PEREIRA registra en otro módulo de POS (t9830/t9820) y solo está allí.

    Consultar un solo endpoint dejaría fuera un punto entero —101 millones el
    1-ago— sin que nadie se enterara.
    """
    api = ApiFalsa()
    api.responder(RUTA_VENDEDOR_ACUMULADA, (200, csv_ventas(fila("PDV MALAMBO", subtotal="100"))))
    api.responder(
        RUTA_POS_VENDEDOR_DETALLE,
        (200, csv_ventas(fila("PDV PEREIRA", costo="", subtotal="200"))),
    )
    _, lineas = leer(api)

    assert api.rutas_pedidas() == [RUTA_VENDEDOR_ACUMULADA, RUTA_POS_VENDEDOR_DETALLE]
    assert {linea.centro_operacion for linea in lineas} == {"402", "409"}  # type: ignore[attr-defined]


def test_el_reparto_entre_los_dos_endpoints_queda_en_la_bitacora() -> None:
    """Sin esta constancia, un endpoint que deja de responder se nota el día que
    alguien compara el total con el del mes pasado."""
    api = ApiFalsa()
    api.responder(RUTA_VENDEDOR_ACUMULADA, (200, csv_ventas(fila("PDV MALAMBO"), fila("CONCORD"))))
    api.responder(RUTA_POS_VENDEDOR_DETALLE, (200, csv_ventas(fila("PDV PEREIRA", costo=""))))
    fuente, _ = leer(api)

    reparto = {a.valor: a.motivo for a in fuente.anotaciones if a.campo == "Origen"}
    assert "2 filas leídas, 2 entregadas" in reparto[RUTA_VENDEDOR_ACUMULADA]
    assert "1 filas leídas, 1 entregadas" in reparto[RUTA_POS_VENDEDOR_DETALLE]


def test_pereira_por_el_endpoint_general_no_se_suma_dos_veces() -> None:
    """El reparto es excluyente: es lo único que garantiza que unir dos
    endpoints no pueda duplicar venta.

    Si la API empezara a servir PEREIRA también por `vendedor-acumulada`, sumar
    las dos daría el doble. La fila sobrante no se carga **y queda anotada**, que
    es la señal de que hay que vaciar `SIGREP_SIESA_CENTROS_POS_DETALLE`.
    """
    api = ApiFalsa()
    api.responder(
        RUTA_VENDEDOR_ACUMULADA,
        (200, csv_ventas(fila("PDV PEREIRA", subtotal="200"), fila("PDV MALAMBO"))),
    )
    api.responder(
        RUTA_POS_VENDEDOR_DETALLE,
        (200, csv_ventas(fila("PDV PEREIRA", costo="", subtotal="200"))),
    )
    fuente, lineas = leer(api)

    pereira = [linea for linea in lineas if linea.centro_operacion == "409"]  # type: ignore[attr-defined]
    assert len(pereira) == 1, "PEREIRA se toma de un solo endpoint, nunca de los dos"
    assert any("no duplicar venta" in a.motivo for a in fuente.anotaciones)


def test_un_centro_ajeno_en_el_endpoint_de_pereira_tampoco_se_cuela() -> None:
    """La guarda es simétrica: si `pos-vendedor-detalle` empieza a traer MALAMBO,
    esa fila ya vino por `vendedor-acumulada` y sumarla sería duplicarla."""
    api = ApiFalsa()
    api.responder(RUTA_VENDEDOR_ACUMULADA, (200, csv_ventas(fila("PDV MALAMBO", subtotal="100"))))
    api.responder(RUTA_POS_VENDEDOR_DETALLE, (200, csv_ventas(fila("PDV MALAMBO", subtotal="100"))))
    fuente, lineas = leer(api)

    assert len(lineas) == 1
    assert any("no duplicar venta" in a.motivo for a in fuente.anotaciones)


def test_pereira_sin_costo_entra_anotada_y_no_toca_el_margen_de_los_demas() -> None:
    """`costo_promedio` viene nulo en el 100 % de las filas de PEREIRA.

    No se inventa un costo y no se rechaza la venta: la línea viaja con
    `costo_promedio=None` —«no se sabe», que no es lo mismo que «costó cero»— y
    **queda anotada**. Con el cero que se ponía antes, §4.4 publicaba un 100 %
    de margen para PEREIRA. El costo de los demás puntos no se ve afectado.
    """
    api = ApiFalsa()
    api.responder(
        RUTA_VENDEDOR_ACUMULADA,
        (200, csv_ventas(fila("PDV MALAMBO", costo="76853.8", subtotal="111440"))),
    )
    api.responder(
        RUTA_POS_VENDEDOR_DETALLE,
        (200, csv_ventas(fila("PDV PEREIRA", costo="", subtotal="200"))),
    )
    fuente, lineas = leer(api)

    por_centro = {linea.centro_operacion: linea for linea in lineas}  # type: ignore[attr-defined]
    assert por_centro["402"].costo_promedio == D("76853.80"), "el margen de los demás intacto"
    assert por_centro["409"].costo_promedio is None, (
        "el costo que la API no manda no puede viajar como cero: eso publica 100 % de margen"
    )
    assert por_centro["409"].valor_subtotal == D("200.00"), "la venta de PEREIRA sí se carga"

    aviso = [a for a in fuente.anotaciones if a.campo == "costo_promedio"]
    assert len(aviso) == 1
    assert aviso[0].valor == "409"
    assert "no tiene margen calculable" in aviso[0].motivo


# ── §5 · Compañías y parámetros ───────────────────────────────────────────────


def test_sin_companias_configuradas_se_hace_una_sola_consulta() -> None:
    """Omitir `id_cia` devuelve las tres compañías de carnes (4, 6 y 7) de una vez."""
    api = ApiFalsa().ventas(fila())
    leer(api)

    assert "id_cia" not in api.parametros(RUTA_VENDEDOR_ACUMULADA)
    assert api.rutas_pedidas().count(RUTA_VENDEDOR_ACUMULADA) == 1


def test_con_companias_configuradas_se_pide_una_por_compania() -> None:
    """Partir la descarga sirve para acotar una incidencia sin desplegar."""
    api = ApiFalsa().ventas(fila())
    leer(api, **{"companias": (4, 6, 7)})

    pedidas = [
        p.url.params["id_cia"] for p in api.peticiones if p.url.path == RUTA_VENDEDOR_ACUMULADA
    ]
    assert pedidas == ["4", "6", "7"]


# ── Fallos de la API ──────────────────────────────────────────────────────────


def test_un_5xx_se_reintenta_y_a_la_tercera_carga() -> None:
    api = ApiFalsa()
    api.responder(
        RUTA_VENDEDOR_ACUMULADA,
        (503, "servicio no disponible"),
        (503, "servicio no disponible"),
        (200, csv_ventas(fila())),
    )
    api.responder(RUTA_POS_VENDEDOR_DETALLE, (200, csv_ventas()))
    _, lineas = leer(api)

    assert len(lineas) == 1
    assert api.rutas_pedidas().count(RUTA_VENDEDOR_ACUMULADA) == 3


def test_un_401_no_se_reintenta_porque_daria_el_mismo_401() -> None:
    api = ApiFalsa()
    api.responder(RUTA_VENDEDOR_ACUMULADA, (401, '{"detail":"Token invalido."}'))
    api.responder(RUTA_POS_VENDEDOR_DETALLE, (200, csv_ventas()))

    with pytest.raises(ErrorFuenteSiesa):
        leer(api)

    assert api.rutas_pedidas().count(RUTA_VENDEDOR_ACUMULADA) == 1


def test_una_descarga_cortada_a_la_mitad_no_se_reintenta() -> None:
    """Reintentar una descarga que ya entregó filas las volvería a mandar desde
    la primera, y en una fuente de un millón de filas eso es venta duplicada que
    nadie notaría: el total sube y todo el mundo se lo cree."""

    def cortada() -> Iterator[bytes]:
        yield csv_ventas(fila(), fila()).encode()
        raise httpx.ReadError("la conexión se cortó a mitad de la descarga")

    api = ApiFalsa()
    api._guiones[RUTA_POS_VENDEDOR_DETALLE] = [(200, csv_ventas())]

    def manejar(peticion: httpx.Request) -> httpx.Response:
        api.peticiones.append(peticion)
        if peticion.url.path == RUTA_VENDEDOR_ACUMULADA:
            return httpx.Response(200, content=cortada())
        return httpx.Response(200, text=csv_ventas())

    fuente = FuenteVentaSiesa(
        DESCRIPCIONES,
        configuracion=configuracion(),
        sesion_http=httpx.Client(transport=httpx.MockTransport(manejar)),
    )
    with pytest.raises(ErrorFuenteSiesa):
        list(fuente.obtener_ventas(date(2026, 8, 1), date(2026, 8, 1)))

    assert api.rutas_pedidas().count(RUTA_VENDEDOR_ACUMULADA) == 1


def test_un_csv_sin_las_columnas_obligatorias_es_un_cambio_de_contrato() -> None:
    api = ApiFalsa()
    api.responder(RUTA_VENDEDOR_ACUMULADA, (200, "referencia,desc_item\n1039,HUESO\n"))
    api.responder(RUTA_POS_VENDEDOR_DETALLE, (200, csv_ventas()))

    with pytest.raises(ErrorFuenteSiesa, match="columnas obligatorias"):
        leer(api)


def test_una_respuesta_vacia_no_sacrifica_el_otro_endpoint() -> None:
    """Si `vendedor-acumulada` devuelve un cuerpo vacío, PEREIRA sigue cargándose
    y la anomalía queda anotada. Perder los dos por culpa de uno sería peor."""
    api = ApiFalsa()
    api.responder(RUTA_VENDEDOR_ACUMULADA, (200, ""))
    api.responder(RUTA_POS_VENDEDOR_DETALLE, (200, csv_ventas(fila("PDV PEREIRA", costo=""))))
    fuente, lineas = leer(api)

    assert [linea.centro_operacion for linea in lineas] == ["409"]  # type: ignore[attr-defined]
    assert any("sin encabezado CSV" in a.motivo for a in fuente.anotaciones)


# ── Integración con la ingesta (§5, §7) ───────────────────────────────────────


@pytest.fixture
def ingesta_desde(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Enchufa una `FuenteVentaSiesa` con API simulada al servicio de ingesta."""

    def _montar(api: ApiFalsa, **extra: object) -> FuenteVentaSiesa:
        fuente = montar(api, **extra)
        monkeypatch.setattr(ingesta_service, "obtener_fuente", lambda *_a, **_k: fuente)
        return fuente

    return _montar


def _corrida(sesion: Session) -> object:
    return IngestaService(sesion).ejecutar(date(2026, 8, 1), date(2026, 8, 1), FuenteIngesta.SIESA)


def test_la_ingesta_carga_la_venta_de_los_dos_endpoints(
    sesion: Session,
    estructura: None,
    ingesta_desde,  # type: ignore[no-untyped-def]
) -> None:
    """De extremo a extremo: CSV simulado → `venta_lineas`, con la categoría ya
    resuelta por `mapeo_categorias` y sin ningún mapeo nuevo por el camino."""
    api = ApiFalsa()
    api.responder(
        RUTA_VENDEDOR_ACUMULADA,
        (200, csv_ventas(fila("PDV MALAMBO", subtotal="111440", categoria="0005 - EMBUTIDOS"))),
    )
    api.responder(
        RUTA_POS_VENDEDOR_DETALLE,
        (200, csv_ventas(fila("PDV PEREIRA", costo="", subtotal="200"))),
    )
    ingesta_desde(api)

    salida = _corrida(sesion)
    sesion.commit()

    assert salida.estado == EstadoCorrida.COMPLETADA  # type: ignore[attr-defined]
    assert salida.aceptadas == 2  # type: ignore[attr-defined]

    lineas = sesion.execute(select(VentaLinea).order_by(VentaLinea.punto_venta_id)).scalars().all()
    por_punto = {linea.punto_venta_id: linea for linea in lineas}

    malambo = por_punto[id_punto_venta(sesion, "402")]
    assert malambo.valor_subtotal == D("111440.00")
    assert malambo.costo_promedio == D("76853.80")
    assert malambo.cantidad_inv == D("19.900")
    embutidos = sesion.scalars(select(Categoria).where(Categoria.codigo == "EMBUTIDOS")).one()
    assert malambo.categoria_id == embutidos.id, "la resuelve `mapeo_categorias`, no el código"

    pereira = por_punto[id_punto_venta(sesion, "409")]
    assert pereira.valor_subtotal == D("200.00"), "la venta de PEREIRA se carga entera"
    assert pereira.costo_promedio is None, (
        "el nulo de la fuente se persiste como NULL; convertirlo en cero es lo que hacía "
        "que PEREIRA publicara 100 % de margen (§4.4)"
    )


def test_la_ingesta_deja_en_la_bitacora_lo_que_trajo_cada_endpoint(
    sesion: Session,
    estructura: None,
    ingesta_desde,  # type: ignore[no-untyped-def]
) -> None:
    api = ApiFalsa()
    api.responder(RUTA_VENDEDOR_ACUMULADA, (200, csv_ventas(fila("PDV MALAMBO"))))
    api.responder(RUTA_POS_VENDEDOR_DETALLE, (200, csv_ventas(fila("PDV PEREIRA", costo=""))))
    ingesta_desde(api)

    salida = _corrida(sesion)
    sesion.commit()

    motivos = " · ".join(r.motivo for r in IngestaService(sesion).rechazos(salida.id))  # type: ignore[attr-defined]
    assert RUTA_VENDEDOR_ACUMULADA in motivos
    assert RUTA_POS_VENDEDOR_DETALLE in motivos
    assert "no tiene margen calculable" in motivos
    assert salida.rechazadas == 0, "las anotaciones no son rechazos: no se perdió venta"  # type: ignore[attr-defined]


def test_una_descripcion_desconocida_llega_a_la_bitacora_como_rechazo(
    sesion: Session,
    estructura: None,
    ingesta_desde,  # type: ignore[no-untyped-def]
) -> None:
    api = ApiFalsa().ventas(fila("PDV MARTE"), fila("PDV MALAMBO"))
    ingesta_desde(api)

    salida = _corrida(sesion)
    sesion.commit()

    assert salida.estado == EstadoCorrida.COMPLETADA_CON_RECHAZOS  # type: ignore[attr-defined]
    assert salida.aceptadas == 1 and salida.rechazadas == 1  # type: ignore[attr-defined]
    rechazos = IngestaService(sesion).rechazos(salida.id)  # type: ignore[attr-defined]
    assert any(r.valor == "PDV MARTE" for r in rechazos)


def test_un_error_de_la_api_deja_la_corrida_fallida_con_su_motivo(
    sesion: Session,
    estructura: None,
    ingesta_desde,  # type: ignore[no-untyped-def]
) -> None:
    """La API falla y el proceso no se cae: la corrida queda `FALLIDA` con su
    motivo en la bitácora, y sin medio día cargado (§5)."""
    api = ApiFalsa()
    api.responder(RUTA_VENDEDOR_ACUMULADA, (500, "boom"))
    api.responder(RUTA_POS_VENDEDOR_DETALLE, (200, csv_ventas()))
    ingesta_desde(api)

    salida = _corrida(sesion)
    sesion.commit()

    assert salida.estado == EstadoCorrida.FALLIDA  # type: ignore[attr-defined]
    assert salida.aceptadas == 0  # type: ignore[attr-defined]
    assert sesion.scalars(select(VentaLinea)).all() == []

    corrida = IngestaService(sesion).ultima_corrida()
    assert corrida is not None and corrida.mensaje is not None
    assert "500" in corrida.mensaje
    assert TOKEN_PELADO not in corrida.mensaje


def test_recargar_el_mismo_dia_desde_la_api_reemplaza_y_no_duplica(
    sesion: Session,
    estructura: None,
    ingesta_desde,  # type: ignore[no-untyped-def]
) -> None:
    """La idempotencia de §5 vale igual con la fuente SIESA que con el Excel."""
    ingesta_desde(ApiFalsa().ventas(fila("PDV MALAMBO", subtotal="100")))
    _corrida(sesion)
    sesion.commit()

    ingesta_desde(ApiFalsa().ventas(fila("PDV MALAMBO", subtotal="999")))
    _corrida(sesion)
    sesion.commit()

    lineas = sesion.scalars(select(VentaLinea)).all()
    assert len(lineas) == 1
    assert lineas[0].valor_subtotal == D("999.00")
