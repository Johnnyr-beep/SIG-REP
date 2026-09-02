"""`FuenteVentaSiesa`: la venta leída de la API de consulta (§3.4, §5).

**Ninguna prueba de este archivo toca la red.** Todas las respuestas HTTP se
simulan con `httpx.MockTransport` sobre el CSV real de
`GET /ventas/costos-razon-social` —las catorce columnas, con sus nombres exactos
y su capitalización exacta—. Una suite que depende de una API externa es una
suite que falla el día que no hay internet, y entonces nadie sabe si lo que se
rompió fue el código o la conexión.

── Qué cambió el 13-ago-2026 y por qué ───────────────────────────────────────

Hasta esa fecha este archivo fijaba el comportamiento de **dos** endpoints
unidos a mano: `vendedor-acumulada` para catorce puntos y `pos-vendedor-detalle`
solo para PEREIRA. Aquella unión tenía un error de importe que desde dentro no
se veía: `pos-vendedor-detalle` daba PEREIRA a 135 201 210 el 1-ago-2026 y la
cifra correcta es **101 453 550**, un 33 % de más en el segundo punto de venta
más grande de la compañía.

`costos-razon-social` hace esa misma unión del lado de la API y cuadra al peso
con el Excel en catorce de los quince puntos, PEREIRA incluida. Las pruebas que
afirmaban el reparto entre dos endpoints **no se borraron: se reescribieron**,
y cada una dice en su docstring qué afirmaba antes y qué afirma ahora.

Las tres que más valen:

- `test_fecha_fin_es_inclusiva_y_no_se_le_suma_un_dia`: `/ventas/poscarnes`
  documenta `fecha_fin` como exclusiva y este endpoint la declara inclusiva, así
  que cualquiera que llegue de leer aquel contrato va a «arreglarlo» sumando un
  día. Ese arreglo mete el 1 de septiembre dentro de agosto.
- `test_los_dos_origenes_se_suman_y_no_se_descarta_ninguno`: `ACUMULADO` y
  `SIN ACUMULAR` son complementarios. Filtrar por uno pierde un punto de venta
  entero o los otros catorce.
- `test_sin_acumular_no_tiene_costo_aunque_llegue_un_cero`: aquí el costo
  ausente llega **como `0`, no como celda vacía**, y un cero es un valor
  legítimo. El criterio mira el módulo (`Origen`), no el importe.
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
from app.core.config import Settings
from app.domain.enums import EstadoCorrida, FuenteIngesta
from app.infrastructure.fuentes.siesa import (
    COMPANIAS_CARNES,
    ORIGEN_ACUMULADO,
    ORIGEN_SIN_ACUMULAR,
    RUTA_COSTOS_RAZON_SOCIAL,
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

#: Encabezado exacto del CSV, en el orden y con la capitalización en que lo
#: devuelve la API. Se escribe en `CamelCase` a propósito: la fuente pliega los
#: nombres a minúsculas y esta constante es lo que comprueba que ese plegado
#: existe. Escribirla ya en minúsculas haría pasar la prueba sin él.
ENCABEZADO = (
    "Origen,DescCO,Referencia,DescItem,CantidadInv,PrecioVenta,ValorSubtotal,"
    "PrecioCosto,CostoPromedio,UtilidadBruta,Categoria,PorcCosto,PorcRentabilidad,FechaDocto"
)


def fila(
    desc_co: str = "PDV MALAMBO",
    *,
    origen: str = ORIGEN_ACUMULADO,
    fecha: str = "2026-08-01T00:00:00",
    cantidad: str = "19.9",
    costo: str = "76853.8",
    subtotal: str = "111440",
    categoria: str = "0001 - RES",
    referencia: str = "1039",
    desc_item: str = "HUESO SUSTANCIA CARNUDO",
    precio_venta: str = "5600",
    precio_costo: str = "3862.50",
    utilidad: str = "34586.20",
    porc_costo: str = "68.97",
    porc_rentabilidad: str = "31.03",
) -> str:
    """Una fila del CSV. Los valores por defecto son los de la fila real
    `1039 HUESO SUSTANCIA CARNUDO` verificada contra el Excel el 1-ago."""
    return (
        f"{origen},{desc_co},{referencia},{desc_item},{cantidad},{precio_venta},"
        f"{subtotal},{precio_costo},{costo},{utilidad},{categoria},{porc_costo},"
        f"{porc_rentabilidad},{fecha}"
    )


def fila_pereira(**extra: str) -> str:
    """La forma exacta en que llega PEREIRA: `SIN ACUMULAR` y **costo cero**.

    Ojo con el cero: no es una celda vacía. Ese módulo de POS no publica costo y
    lo escribe como `0`, que en cualquier otra fila sería un costo legítimo.
    """
    parametros: dict[str, str] = {"origen": ORIGEN_SIN_ACUMULAR, "costo": "0"}
    parametros.update(extra)
    return fila("PDV PEREIRA", **parametros)


def csv_ventas(*filas: str) -> str:
    return "\n".join((ENCABEZADO, *filas)) + "\n"


# ── La API simulada ───────────────────────────────────────────────────────────


class ApiFalsa:
    """La API de consulta, en memoria. Registra lo que se le pidió.

    El guion se escribe **por compañía**, porque `id_cia` es obligatorio en este
    endpoint y una corrida son tres peticiones (4, 6 y 7). Lo que no tenga guion
    propio cae en el global, y lo que tampoco lo tenga devuelve un CSV vacío
    —que es lo que hace una compañía sin venta ese día—.

    Cada guion se consume en orden y la última respuesta se repite. Eso es lo que
    permite probar «falla dos veces y a la tercera responde» sin inventarse un
    reloj ni esperar de verdad.
    """

    def __init__(self) -> None:
        self.peticiones: list[httpx.Request] = []
        self._por_compania: dict[str, list[tuple[int, str] | Exception]] = {}
        self._global: list[tuple[int, str] | Exception] | None = None

    def responder(self, *guion: tuple[int, str] | Exception, id_cia: str = "4") -> ApiFalsa:
        """Guion de una compañía concreta. Por defecto la 4."""
        self._por_compania[id_cia] = list(guion)
        return self

    def todas(self, *guion: tuple[int, str] | Exception) -> ApiFalsa:
        """Guion que sirve a cualquier compañía sin guion propio."""
        self._global = list(guion)
        return self

    def ventas(self, *filas: str) -> ApiFalsa:
        """Atajo: estas filas las trae la compañía 4 y las otras dos, ninguna."""
        return self.responder((200, csv_ventas(*filas)))

    def companias_pedidas(self) -> list[str]:
        return [p.url.params["id_cia"] for p in self.peticiones]

    def intentos(self, id_cia: str = "4") -> int:
        return self.companias_pedidas().count(id_cia)

    def parametros(self, id_cia: str = "4") -> dict[str, str]:
        for peticion in self.peticiones:
            if peticion.url.params.get("id_cia") == id_cia:
                return dict(peticion.url.params)
        raise AssertionError(
            f"Nunca se pidió id_cia={id_cia}. Se pidió: {self.companias_pedidas()}"
        )

    def _manejar(self, peticion: httpx.Request) -> httpx.Response:
        self.peticiones.append(peticion)
        if peticion.url.path != RUTA_COSTOS_RAZON_SOCIAL:
            return httpx.Response(404, text="ruta no simulada en la prueba")
        guion = self._por_compania.get(peticion.url.params["id_cia"]) or self._global
        if not guion:
            return httpx.Response(200, text=csv_ventas())
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


def test_carnes_frias_pide_solo_la_compania_ocho() -> None:
    """La compañía 8 no puede mezclarse con las compañías 4, 6 y 7 de Carnes."""
    settings = Settings(secret_key="c" * 40, siesa_token=TOKEN_PELADO)

    configuracion_frias = ConfiguracionSiesa.desde_settings(settings, unidad="carnes-frias")

    assert configuracion_frias.companias == (8,)


# ── `Origen`: los dos se suman, y solo uno carece de costo ────────────────────


def test_los_dos_origenes_se_suman_y_no_se_descarta_ninguno() -> None:
    """Reescrita. Antes: `test_une_los_dos_endpoints_y_pereira_llega_por_el_suyo`.

    Aquella afirmaba que PEREIRA venía de `pos-vendedor-detalle` y el resto de
    `vendedor-acumulada`, y que esta fuente unía las dos respuestas. La unión
    ahora la hace la API y llega marcada en `Origen`: `ACUMULADO` son los catorce
    puntos —2289 filas, 765 177 470 el 1-ago— y `SIN ACUMULAR` es **solo
    PEREIRA** —203 filas, 101 453 550—.

    Lo que hay que fijar es lo mismo que antes por otra vía: **no solapan y se
    suman**. Quedarse con `ACUMULADO` perdería un punto entero de 101 millones y
    quedarse con `SIN ACUMULAR` perdería los otros catorce.
    """
    api = ApiFalsa().ventas(
        fila("PDV MALAMBO", subtotal="100"),
        fila("CONCORD", subtotal="300"),
        fila_pereira(subtotal="200"),
    )
    _, lineas = leer(api)

    assert {linea.centro_operacion for linea in lineas} == {"402", "603", "409"}  # type: ignore[attr-defined]
    assert sum(linea.valor_subtotal for linea in lineas) == D("600.00")  # type: ignore[attr-defined]


def test_sin_acumular_no_tiene_costo_aunque_llegue_un_cero() -> None:
    """El matiz que decide si la gerencia ve un margen o ve «—».

    En este endpoint el costo que falta llega **como `0`, no como celda vacía**,
    y un cero es un valor legítimo: hay ítems que costaron cero. Deducir «no hay
    dato» de un cero convertiría en `NULL` costos reales de los otros catorce
    puntos y borraría margen verdadero.

    Por eso el criterio **mira el módulo, no el importe**: `Origen =
    SIN ACUMULAR` es la afirmación de que ese módulo de POS no publica costo
    —medido en el 100 % de sus filas—, y esa afirmación gana sobre lo que traiga
    la columna. En `ACUMULADO`, un cero es un costo y se conserva como cero.
    """
    api = ApiFalsa().ventas(
        fila("PDV MALAMBO", costo="0", subtotal="100"),
        fila_pereira(costo="0", subtotal="200"),
    )
    _, lineas = leer(api)

    por_centro = {linea.centro_operacion: linea for linea in lineas}  # type: ignore[attr-defined]
    assert por_centro["402"].costo_promedio == D("0.00"), (
        "en `ACUMULADO` el cero es un costo afirmado y se conserva: convertirlo en NULL "
        "borraría el margen de una venta que sí lo tiene"
    )
    assert por_centro["409"].costo_promedio is None, (
        "en `SIN ACUMULAR` el cero es la ausencia del dato escrita como número; dejarlo "
        "pasar publicaría un 100 % de margen que nadie ha ganado (§4.4)"
    )
    assert por_centro["409"].valor_subtotal == D("200.00"), "la venta de PEREIRA sí se carga"


def test_sin_acumular_ignora_el_costo_aunque_traiga_un_importe_de_verdad() -> None:
    """La regla es del módulo, no del número: mientras `SIN ACUMULAR` esté en
    `ORIGENES_SIN_COSTO`, lo que traiga su columna de costo no se cree.

    Si algún día ese módulo empieza a publicar costo de verdad, el arreglo es
    quitarlo de `ORIGENES_SIN_COSTO` —una decisión consciente, con su medición
    detrás— y no que un importe suelto lo decida por su cuenta.
    """
    _, lineas = leer(ApiFalsa().ventas(fila_pereira(costo="123456.78")))

    assert lineas[0].costo_promedio is None  # type: ignore[attr-defined]


def test_una_fila_sin_costo_entra_anotada_y_no_toca_el_margen_de_los_demas() -> None:
    """Reescrita. Antes: `test_pereira_sin_costo_entra_anotada_y_no_toca_el_margen_de_los_demas`.

    Lo que afirmaba sigue en pie palabra por palabra —la línea viaja con
    `costo_promedio=None`, «no se sabe», que no es lo mismo que «costó cero», y
    queda anotada—; lo único que cambió es de dónde se deduce el «no se sabe»:
    antes de una celda vacía de `pos-vendedor-detalle`, ahora del `Origen`.
    """
    api = ApiFalsa().ventas(
        fila("PDV MALAMBO", costo="76853.8", subtotal="111440"),
        fila_pereira(subtotal="200"),
    )
    fuente, lineas = leer(api)

    por_centro = {linea.centro_operacion: linea for linea in lineas}  # type: ignore[attr-defined]
    assert por_centro["402"].costo_promedio == D("76853.80"), "el margen de los demás intacto"
    assert por_centro["409"].costo_promedio is None

    aviso = [a for a in fuente.anotaciones if a.campo == "CostoPromedio"]
    assert len(aviso) == 1
    assert aviso[0].valor == "409"
    assert "no tiene margen calculable" in aviso[0].motivo


def test_una_celda_de_costo_vacia_sigue_siendo_nula_en_acumulado() -> None:
    """Un blanco no es un cero en ningún módulo. `ACUMULADO` llena el costo en
    el 100 % de sus filas, así que un hueco ahí es una anomalía que merece
    quedarse sin margen y anotada, no rellenarse con un cero inventado."""
    fuente, lineas = leer(ApiFalsa().ventas(fila("PDV MALAMBO", costo="")))

    assert lineas[0].costo_promedio is None  # type: ignore[attr-defined]
    assert any(a.campo == "CostoPromedio" for a in fuente.anotaciones)


def test_el_reparto_por_origen_queda_en_la_bitacora() -> None:
    """Reescrita. Antes: `test_el_reparto_entre_los_dos_endpoints_queda_en_la_bitacora`.

    Aquella contaba filas por endpoint; esta cuenta por `Origen`, que es la
    misma señal servida por la fuente correcta. Sin ella, el día que
    `SIN ACUMULAR` deje de aparecer —porque PEREIRA cambió de módulo o empezó a
    acumular— la venta caería 101 millones y nadie sabría por qué hasta comparar
    con el mes pasado.
    """
    api = ApiFalsa().ventas(fila("PDV MALAMBO"), fila("CONCORD"), fila_pereira())
    fuente, _ = leer(api)

    reparto = {a.valor: a.motivo for a in fuente.anotaciones if a.campo == "Origen"}
    assert "2 filas leídas, 2 entregadas" in reparto[ORIGEN_ACUMULADO]
    assert "1 filas leídas, 1 entregadas" in reparto[ORIGEN_SIN_ACUMULAR]


def test_un_origen_desconocido_se_carga_pero_queda_avisado() -> None:
    """Sustituye a `test_pereira_por_el_endpoint_general_no_se_suma_dos_veces` y a
    `test_un_centro_ajeno_en_el_endpoint_de_pereira_tampoco_se_cuela`.

    Aquellas dos guardaban contra la duplicación que podía producir unir dos
    endpoints a mano. Esa unión ya no existe —la hace la API— y con ella
    desaparece la clase entera de fallo: no hay dos respuestas que solapar.

    Lo que sí queda vivo del mismo miedo es un tercer `Origen` que aparezca sin
    avisar. Su venta se carga —es venta real y descartarla sería peor—, pero
    queda dicho en la bitácora, porque si ese módulo tampoco publica costo su
    cero se estaría creyendo como un 100 % de margen.
    """
    api = ApiFalsa().ventas(fila("PDV MALAMBO", origen="REMISIONES", subtotal="100"))
    fuente, lineas = leer(api)

    assert len(lineas) == 1, "la venta de un origen nuevo no se pierde"
    aviso = [a for a in fuente.anotaciones if a.campo == "Origen" and a.valor == "REMISIONES"]
    assert len(aviso) == 1
    assert "no es ninguno de los conocidos" in aviso[0].motivo
    assert "ORIGENES_SIN_COSTO" in aviso[0].motivo


def test_sin_la_columna_origen_la_carga_se_para() -> None:
    """`Origen` es lo único que distingue «costó cero» de «este módulo no da
    costo». Sin ella, las 203 filas de PEREIRA entrarían con costo 0 y
    publicarían un 100 % de margen. Que falte es un cambio de contrato que tiene
    que parar la carga, no degradarse en silencio."""
    sin_origen = ENCABEZADO.replace("Origen,", "", 1)
    api = ApiFalsa().todas((200, sin_origen + "\nPDV MALAMBO,1039,HUESO\n"))

    with pytest.raises(ErrorFuenteSiesa, match="columnas obligatorias"):
        leer(api)


# ── §5 · `fecha_fin` es INCLUSIVA ─────────────────────────────────────────────


def test_fecha_fin_es_inclusiva_y_no_se_le_suma_un_dia() -> None:
    """La trampa más peligrosa de esta integración, fijada por contrato.

    En `costos-razon-social` lo declara la propia API —«Fecha final
    (inclusiva)»— y coincide con el comportamiento medido de los otros dos
    endpoints. `/ventas/poscarnes` documenta lo contrario —«fecha final
    (exclusiva)»— y quien venga de leer aquel contrato va a «arreglar» esto
    sumando un día. Si lo hace, agosto cargará el 1 de septiembre y el cierre de
    mes saldrá largo justo cuando se mira.
    """
    api = ApiFalsa().ventas(fila(fecha="2026-08-02T00:00:00"))
    _, lineas = leer(api, date(2026, 8, 1), date(2026, 8, 2))

    parametros = api.parametros()
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
        fila(fecha="2026-08-01T00:00:00", subtotal="100"),
        fila(fecha="2026-08-02T00:00:00", subtotal="200"),
    )
    _, lineas = leer(api, date(2026, 8, 1), date(2026, 8, 2))

    assert [linea.fecha for linea in lineas] == [date(2026, 8, 1), date(2026, 8, 2)]  # type: ignore[attr-defined]


def test_una_fila_fuera_del_rango_no_se_carga_y_queda_anotada() -> None:
    """Si la API devolviera algo fuera del rango, su contrato habría cambiado."""
    api = ApiFalsa().ventas(fila(fecha="2026-09-01T00:00:00"))
    fuente, lineas = leer(api, date(2026, 8, 1), date(2026, 8, 31))

    assert lineas == []
    assert any("fuera del rango pedido" in a.motivo for a in fuente.anotaciones)


def test_una_fecha_ilegible_rechaza_la_fila_con_su_motivo() -> None:
    api = ApiFalsa().ventas(fila(fecha="ayer"), fila())
    fuente, lineas = leer(api)

    assert len(lineas) == 1
    assert fuente.rechazos[0].campo == "FechaDocto"
    assert "no es una fecha legible" in fuente.rechazos[0].motivo


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
    api = ApiFalsa().todas((401, '{"detail":"Token invalido."}'))

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


def test_el_nombre_del_origen_lleva_la_url_y_el_endpoint_pero_no_el_token() -> None:
    """`corridas_ingesta.origen` se guarda y se muestra en pantalla."""
    nombre = montar(ApiFalsa().ventas()).nombre
    assert "apiconsulta.pruebas.local" in nombre
    assert RUTA_COSTOS_RAZON_SOCIAL in nombre
    assert TOKEN_PELADO not in nombre


# ── §3.1 · Resolución del punto de venta por `DescCO` ─────────────────────────


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
    """Este endpoint **no trae el código de centro de operación**, solo `DescCO`.

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
    assert rechazo.campo == "DescCO"
    assert rechazo.valor == "PDV MARTE"
    assert "ningún punto de venta conocido" in rechazo.motivo
    assert RUTA_COSTOS_RAZON_SOCIAL in rechazo.motivo, "el motivo dice de dónde vino"


def test_una_fila_sin_descripcion_de_centro_se_rechaza() -> None:
    api = ApiFalsa().ventas(fila(""))
    fuente, lineas = leer(api)

    assert lineas == []
    assert fuente.rechazos[0].campo == "DescCO"
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
    """`Categoria` viene como `'0001 - RES'`, idéntica a la del Excel.

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

    `CantidadInv 19.9`, `CostoPromedio 76853.8`, `ValorSubtotal 111440`:
    idénticos a la fila equivalente de la hoja `VENTA`. Se comparan con `Decimal`
    construido desde texto; pasar por `float` arrastraría el error binario y en
    un consolidado de veinte mil millones eso es un defecto, no un detalle.
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
    assert fuente.rechazos[0].campo == "ValorSubtotal"
    assert "no es un número" in fuente.rechazos[0].motivo


def test_la_rentabilidad_viaja_como_margen_de_conciliacion() -> None:
    """`PorcRentabilidad` → `margen_siesa`, que existe **solo para conciliar**.

    El margen del reporte se recalcula ponderado sobre totales (§4.4) y nunca
    sale de esta columna; guardarla sirve para cuadrar contra SIESA cuando algo
    no encaja.
    """
    _, lineas = leer(ApiFalsa().ventas(fila(porc_rentabilidad="31.03")))

    assert lineas[0].margen_siesa == D("31.030000")  # type: ignore[attr-defined]


def test_una_rentabilidad_ilegible_no_cuesta_la_venta() -> None:
    """Rechazar una fila por un campo que no alimenta ningún indicador sería el
    peor cambio posible: se pierde venta real por una columna de conciliación."""
    fuente, lineas = leer(ApiFalsa().ventas(fila(porc_rentabilidad="N/D", subtotal="100")))

    assert len(lineas) == 1
    assert lineas[0].valor_subtotal == D("100.00")  # type: ignore[attr-defined]
    assert lineas[0].margen_siesa is None  # type: ignore[attr-defined]
    assert any(a.campo == "PorcRentabilidad" for a in fuente.anotaciones)


def test_una_rentabilidad_fuera_del_rango_persistible_no_cuesta_la_venta() -> None:
    """`Numeric(12, 6)` no admite un séptimo dígito entero.

    Es una columna de conciliación: el valor corrupto queda anotado y en NULL,
    pero no puede revertir el lote completo de ventas válidas.
    """
    fuente, lineas = leer(ApiFalsa().ventas(fila(porc_rentabilidad="1000000", subtotal="100")))

    assert len(lineas) == 1
    assert lineas[0].valor_subtotal == D("100.00")  # type: ignore[attr-defined]
    assert lineas[0].margen_siesa is None  # type: ignore[attr-defined]
    assert any(
        anotacion.campo == "PorcRentabilidad" and "rango persistible" in anotacion.motivo
        for anotacion in fuente.anotaciones
    )


def test_los_campos_que_este_endpoint_no_trae_van_a_nulo() -> None:
    """Reescrita. Antes: mismo nombre, pero `vendedor` sí venía.

    `vendedor-acumulada` entregaba `codigo_vendedor` y `nombre_vendedor` y había
    una prueba —`test_el_vendedor_viaja_en_la_linea`— que lo fijaba.
    `costos-razon-social` **no expone ninguno de los dos**, así que aquella
    prueba se convierte en esta afirmación: van a `NULL` como el NIT, la
    condición de pago, el domicilio y la clase de cliente. No se inventan, y el
    reporte por vendedor del POS queda a la espera de que la API los añada.
    """
    _, lineas = leer(ApiFalsa().ventas(fila()))
    linea = lineas[0]

    assert linea.nit_cliente is None  # type: ignore[attr-defined]
    assert linea.condicion_pago is None  # type: ignore[attr-defined]
    assert linea.domicilio is None  # type: ignore[attr-defined]
    assert linea.clase_cliente is None  # type: ignore[attr-defined]
    assert linea.codigo_vendedor is None  # type: ignore[attr-defined]
    assert linea.nombre_vendedor is None  # type: ignore[attr-defined]


# ── §5 · Compañías: `id_cia` es obligatorio ───────────────────────────────────


def test_se_recorren_las_tres_companias_de_carnes() -> None:
    """Reescrita. Antes: `test_sin_companias_configuradas_se_hace_una_sola_consulta`.

    Aquella afirmaba lo correcto para `vendedor-acumulada`, donde omitir
    `id_cia` devolvía las tres compañías de una vez. **Aquí `id_cia` es
    obligatorio**, así que se hace una petición por compañía y se recorren la 4,
    la 6 y la 7. Nunca la 3 ni la 8: esa venta agropecuaria se reporta en otra
    instancia y sumarla aquí inflaría el consolidado en cientos de millones.
    """
    api = ApiFalsa().ventas(fila())
    leer(api)

    assert api.companias_pedidas() == ["4", "6", "7"]
    assert [str(c) for c in COMPANIAS_CARNES] == ["4", "6", "7"]


def test_cada_compania_aporta_sus_filas_y_ninguna_se_pisa() -> None:
    """Tres respuestas distintas, una carga. El C.O. lleva la compañía en el
    primer dígito (`4xx`, `6xx`, `7xx`) y no hay solapamiento, así que la unión
    de las tres es una suma limpia."""
    api = ApiFalsa()
    api.responder((200, csv_ventas(fila("PDV MALAMBO", subtotal="100"))), id_cia="4")
    api.responder((200, csv_ventas(fila("CONCORD", subtotal="200"))), id_cia="6")
    api.responder((200, csv_ventas(fila("ALAMEDA 1", subtotal="300"))), id_cia="7")
    _, lineas = leer(api)

    assert [linea.centro_operacion for linea in lineas] == ["402", "603", "605"]  # type: ignore[attr-defined]
    assert sum(linea.valor_subtotal for linea in lineas) == D("600.00")  # type: ignore[attr-defined]


def test_una_lista_de_companias_vacia_es_un_error_de_configuracion() -> None:
    """Antes vacío significaba «todas». Aquí significaría **cero filas**, y una
    corrida vacía se parece demasiado a un día sin venta como para dejarla
    pasar en silencio."""
    from app.core.errors import ErrorValidacion

    with pytest.raises(ErrorValidacion, match="SIGREP_SIESA_COMPANIAS"):
        configuracion(companias=())


def test_las_companias_por_defecto_son_las_de_carnes() -> None:
    """`SIGREP_SIESA_COMPANIAS` deja de ser un ajuste opcional y pasa a ser parte
    del contrato, así que su valor por defecto tiene que ser el correcto."""
    from app.core.config import Settings

    settings = Settings(secret_key=SecretStr("c" * 40), siesa_token=SecretStr(TOKEN_CON_PREFIJO))
    assert settings.siesa_companias == [4, 6, 7]
    assert ConfiguracionSiesa.desde_settings(settings).companias == COMPANIAS_CARNES


# ── Fallos de la API ──────────────────────────────────────────────────────────


def test_un_5xx_se_reintenta_y_a_la_tercera_carga() -> None:
    api = ApiFalsa()
    api.responder(
        (503, "servicio no disponible"),
        (503, "servicio no disponible"),
        (200, csv_ventas(fila())),
        id_cia="4",
    )
    _, lineas = leer(api)

    assert len(lineas) == 1
    assert api.intentos("4") == 3
    assert api.intentos("6") == 1, "las otras compañías no pagan el reintento de la primera"


def test_un_401_no_se_reintenta_porque_daria_el_mismo_401() -> None:
    api = ApiFalsa().todas((401, '{"detail":"Token invalido."}'))

    with pytest.raises(ErrorFuenteSiesa):
        leer(api)

    assert api.intentos("4") == 1


def test_una_descarga_cortada_a_la_mitad_no_se_reintenta() -> None:
    """Reintentar una descarga que ya entregó filas las volvería a mandar desde
    la primera, y en una fuente de cientos de miles de filas eso es venta
    duplicada que nadie notaría: el total sube y todo el mundo se lo cree."""

    def cortada() -> Iterator[bytes]:
        yield csv_ventas(fila(), fila()).encode()
        raise httpx.ReadError("la conexión se cortó a mitad de la descarga")

    api = ApiFalsa()

    def manejar(peticion: httpx.Request) -> httpx.Response:
        api.peticiones.append(peticion)
        if peticion.url.params["id_cia"] == "4":
            return httpx.Response(200, content=cortada())
        return httpx.Response(200, text=csv_ventas())

    fuente = FuenteVentaSiesa(
        DESCRIPCIONES,
        configuracion=configuracion(),
        sesion_http=httpx.Client(transport=httpx.MockTransport(manejar)),
    )
    with pytest.raises(ErrorFuenteSiesa):
        list(fuente.obtener_ventas(date(2026, 8, 1), date(2026, 8, 1)))

    assert api.intentos("4") == 1


def test_un_csv_sin_las_columnas_obligatorias_es_un_cambio_de_contrato() -> None:
    api = ApiFalsa().todas((200, "Referencia,DescItem\n1039,HUESO\n"))

    with pytest.raises(ErrorFuenteSiesa, match="columnas obligatorias"):
        leer(api)


def test_una_respuesta_vacia_no_sacrifica_a_las_demas_companias() -> None:
    """Reescrita. Antes: `test_una_respuesta_vacia_no_sacrifica_el_otro_endpoint`.

    El razonamiento es idéntico y solo cambia el eje: antes eran dos endpoints y
    ahora son tres compañías. Si la consulta de una devuelve un cuerpo vacío, las
    otras dos siguen cargándose y la anomalía queda anotada. Perder las tres por
    culpa de una sería peor.
    """
    api = ApiFalsa()
    api.responder((200, ""), id_cia="4")
    api.responder((200, csv_ventas(fila("CONCORD"))), id_cia="6")
    fuente, lineas = leer(api)

    assert [linea.centro_operacion for linea in lineas] == ["603"]  # type: ignore[attr-defined]
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


def test_la_ingesta_carga_la_venta_de_los_dos_origenes(
    sesion: Session,
    estructura: None,
    ingesta_desde,  # type: ignore[no-untyped-def]
) -> None:
    """De extremo a extremo: CSV simulado → `venta_lineas`, con la categoría ya
    resuelta por `mapeo_categorias` y sin ningún mapeo nuevo por el camino."""
    api = ApiFalsa().ventas(
        fila("PDV MALAMBO", subtotal="111440", categoria="0005 - EMBUTIDOS"),
        fila_pereira(subtotal="200"),
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
        "el cero de `SIN ACUMULAR` se persiste como NULL; guardarlo como cero es lo que "
        "hacía que PEREIRA publicara 100 % de margen (§4.4)"
    )


def test_la_ingesta_deja_en_la_bitacora_lo_que_trajo_cada_origen(
    sesion: Session,
    estructura: None,
    ingesta_desde,  # type: ignore[no-untyped-def]
) -> None:
    api = ApiFalsa().ventas(fila("PDV MALAMBO"), fila_pereira())
    ingesta_desde(api)

    salida = _corrida(sesion)
    sesion.commit()

    motivos = " · ".join(r.motivo for r in IngestaService(sesion).rechazos(salida.id))  # type: ignore[attr-defined]
    assert f"Origen «{ORIGEN_ACUMULADO}»" in motivos
    assert f"Origen «{ORIGEN_SIN_ACUMULAR}»" in motivos
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
    api = ApiFalsa().todas((500, "boom"))
    ingesta_desde(api)

    salida = _corrida(sesion)
    sesion.commit()

    assert salida.estado == EstadoCorrida.FALLIDA  # type: ignore[attr-defined]
    assert salida.aceptadas == 0  # type: ignore[attr-defined]
    assert sesion.scalars(select(VentaLinea)).all() == []

    corrida = IngestaService(sesion).ultima_corrida()
    assert corrida is not None and corrida.mensaje is not None
    assert "500" in corrida.mensaje
    assert RUTA_COSTOS_RAZON_SOCIAL in corrida.mensaje
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
