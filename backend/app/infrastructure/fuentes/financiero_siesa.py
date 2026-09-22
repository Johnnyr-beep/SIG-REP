"""Estado de resultados en vivo, leído de la API de consulta de SIESA.

Implementa un consumo de `GET /ventas/estado-situacion-financiera`, que trae
**el mismo libro mayor que `Consolidado.json`, pero pivotado por mes** en vez
de acumulado: cada fila es una cuenta auxiliar × tercero × centro, con doce
columnas `S1`...`S12`, una por mes del año pedido.

── Qué es cada columna `Sn`, medido ──────────────────────────────────────────

**Es el movimiento neto de ese mes para esa fila, no un saldo acumulado.**
Medido con cuentas de caja menuda de cia 4: una fila con `S1=8000000` y
`S2..S7=0` es un fondo que se creó en enero y no tuvo movimiento después —si
`Sn` fuera saldo acumulado, un fondo real de caja menuda no volvería a cero al
mes siguiente de crearse—. Confirmado también con una fila que vuelve a
moverse en junio (`S1=2000000, S2..S5=0, S6=2000000`): un aumento del fondo a
mitad de año, no una reapertura desde cero.

Por eso este módulo **no acumula entre meses**: para el estado de resultados
de un período puntual basta la columna `S{mes}` de cada fila, sumada por clase
PUC y con el mismo criterio de signo que `app.domain.financiero` (los ingresos
son de naturaleza crédito y se invierten para presentarse en positivo).

── Por qué esto sirve para el estado de resultados y no para el balance ──────

El estado de resultados de un mes puntual es exactamente la suma de `S{mes}`
por clase 4/5/6/7: no hace falta ningún saldo de apertura, el P&G nace en cero
cada mes de la petición. El balance general sí lo necesita —activo, pasivo y
patrimonio son saldos acumulados desde que existe la cuenta—, y esta fuente no
lo tiene: medido contra cia 4, sumar todos los meses disponibles (diciembre
2025 en adelante, que es donde empieza el historial que expone este endpoint)
da un activo muy distinto del que ya está cargado en la base local desde
`Consolidado.json`. Por eso el balance general de esta instancia sigue
viniendo de la base local, y esta fuente solo alimenta el estado de resultados.

── El contrato, tal como se midió ────────────────────────────────────────────

Autenticación y token: igual que `app.infrastructure.fuentes.siesa` —cabecera
`Authorization` con el token pelado, sin `Bearer`—.

Parámetros: `cia` (obligatorio), `periodo_inicio`, `periodo_fin` (ambos
`AAAAMM`, definen el año: solo importa el año, `S1`...`S12` cubre siempre los
doce meses), `format=csv`. Como en `costos-razon-social`, `format=csv` descarga
completo en streaming; `limit`/`offset` no aplican.

Columnas (minúsculas, con encabezado): `grupo`, `clase`, `cuenta`, `auxiliar`,
`desc_auxiliar`, `desc_co`, `tercero`, `c_costo`, `co`, `un`, `nit`, `S1`...`S12`.
`auxiliar` trae el código de cuenta completo (10 dígitos); sus primeros 4
dígitos son el `mayor_iii` que clasifica `app.domain.financiero.clasificar`.
"""

from __future__ import annotations

import csv
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

import httpx
from pydantic import SecretStr

from app.core.errors import ErrorSigrep, ErrorValidacion
from app.domain.financiero import ClaseCuenta, clasificar, es_naturaleza_credito
from app.infrastructure.fuentes.siesa import token_efectivo

if TYPE_CHECKING:  # pragma: no cover - solo para el tipado
    from app.core.config import Settings

RUTA_ESTADO_SITUACION_FINANCIERA = "/ventas/estado-situacion-financiera"

COL_AUXILIAR = "auxiliar"

MENSAJE_SIN_TOKEN = (
    "El estado de resultados en vivo necesita credenciales: configure "  # noqa: S105
    "`SIGREP_SIESA_TOKEN` y `SIGREP_SIESA_URL_BASE`."
)

_CERO = Decimal("0")


class ErrorFuenteFinancieroSiesa(ErrorSigrep):
    """La API de consulta respondió con un error al pedir el estado financiero."""

    codigo = "fuente_financiero_siesa"
    http_status = 502


@dataclass(frozen=True, slots=True)
class ConfiguracionFinancieroSiesa:
    """Lo mínimo que esta fuente necesita del entorno."""

    url_base: str
    token: SecretStr = field(repr=False)
    timeout_conexion_seg: float = 15.0
    timeout_lectura_seg: float = 600.0

    @classmethod
    def desde_settings(cls, settings: Settings) -> ConfiguracionFinancieroSiesa:
        crudo = settings.siesa_token.get_secret_value().strip()
        if not crudo:
            raise ErrorValidacion(MENSAJE_SIN_TOKEN)
        url_base = (settings.siesa_url_base or "").strip().rstrip("/")
        if not url_base:
            raise ErrorValidacion(MENSAJE_SIN_TOKEN)
        return cls(
            url_base=url_base,
            token=SecretStr(crudo),
            timeout_conexion_seg=settings.siesa_timeout_conexion_seg,
            timeout_lectura_seg=settings.siesa_timeout_lectura_seg,
        )

    def cabeceras(self) -> dict[str, str]:
        return {
            "Authorization": token_efectivo(self.token.get_secret_value()),
            "Accept": "text/csv",
        }


def _a_decimal(crudo: str | None) -> Decimal:
    if crudo is None or crudo.strip() == "":
        return _CERO
    try:
        return Decimal(crudo.strip())
    except InvalidOperation:
        return _CERO


def _lineas(
    cia: int, anio: int, configuracion: ConfiguracionFinancieroSiesa, cliente: httpx.Client
) -> Iterator[str]:
    url = configuracion.url_base + RUTA_ESTADO_SITUACION_FINANCIERA
    parametros = {
        "cia": str(cia),
        "periodo_inicio": f"{anio}01",
        "periodo_fin": f"{anio}12",
        "format": "csv",
    }
    with cliente.stream(
        "GET", url, params=parametros, headers=configuracion.cabeceras()
    ) as respuesta:
        if respuesta.status_code >= 400:
            respuesta.read()
            raise ErrorFuenteFinancieroSiesa(
                f"La API de consulta respondió {respuesta.status_code} al pedir el "
                f"estado financiero de la cía {cia}: {respuesta.text[:300]}"
            )
        yield from respuesta.iter_lines()


@dataclass(frozen=True, slots=True)
class FilaAnualEnVivo:
    """Una fila del CSV, con sus doce meses ya resueltos y con el signo

    económico aplicado (naturaleza crédito invertida). `valores[0]` es enero,
    `valores[11]` diciembre. `grupo` y `subgrupo` son el texto tal como lo
    entrega SIESA (`GASTOS`, `OPERACIONALES DE ADMINISTRACION`...); no
    reemplazan a `clase`, que es la clasificación PUC por el primer dígito de
    `auxiliar` y la que decide el signo.
    """

    clase: ClaseCuenta
    grupo: str
    subgrupo: str
    cuenta: str
    valores: tuple[Decimal, ...]


def _cliente_http(configuracion: ConfiguracionFinancieroSiesa) -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(
            connect=configuracion.timeout_conexion_seg,
            read=configuracion.timeout_lectura_seg,
            write=configuracion.timeout_conexion_seg,
            pool=configuracion.timeout_conexion_seg,
        ),
        follow_redirects=True,
    )


#: `cia` 4 (Carnes Santacruz) trae ~226.000 filas por año contra ~32.000 de la
#: cía 3: sin memoria, cada cambio de mes o de reporte volvía a descargar y
#: parsear el año entero, y con dos reportes pidiéndolo casi a la vez
#: (`estado-resultados-vivo` y `situacion-financiera-vivo`) la carga se sentía
#: el doble de lenta de lo necesario. Se cachea el año completo —los doce
#: meses de una vez, no solo el mes pedido— para que cambiar de período o
#: pedir el otro reporte de la misma cía y año no vuelva a tocar la red.
_TTL_CACHE_SEG = 600.0
_cache: dict[tuple[int, int], tuple[float, list[FilaAnualEnVivo]]] = {}
_bloqueos: dict[tuple[int, int], threading.Lock] = {}
_bloqueo_registro = threading.Lock()


def _bloqueo_de(clave: tuple[int, int]) -> threading.Lock:
    with _bloqueo_registro:
        if clave not in _bloqueos:
            _bloqueos[clave] = threading.Lock()
        return _bloqueos[clave]


def limpiar_cache_en_vivo() -> None:
    """Vacía la caché de años descargados. Solo para pruebas: sin esto, una

    prueba que reutiliza (cia, año) de otra hereda su CSV simulado y afirma
    sobre datos que no son los suyos.
    """
    _cache.clear()


def _filas_del_anio(
    cia: int,
    anio: int,
    configuracion: ConfiguracionFinancieroSiesa,
    cliente: httpx.Client | None,
    *,
    usar_cache: bool = True,
) -> list[FilaAnualEnVivo]:
    clave = (cia, anio)
    if usar_cache:
        entrada = _cache.get(clave)
        if entrada is not None and time.monotonic() - entrada[0] < _TTL_CACHE_SEG:
            return entrada[1]

    with _bloqueo_de(clave) if usar_cache else _NULO:
        if usar_cache:
            entrada = _cache.get(clave)
            if entrada is not None and time.monotonic() - entrada[0] < _TTL_CACHE_SEG:
                return entrada[1]

        propio = cliente is None
        cliente_activo = cliente or _cliente_http(configuracion)
        filas: list[FilaAnualEnVivo] = []
        try:
            # `csv.reader` una sola vez sobre todo el flujo, no una instancia
            # nueva por línea: con ~226.000 filas (cia 4) esa asignación de
            # más era una parte medible del tiempo de análisis. Los índices de
            # columna se calculan una sola vez, al leer el encabezado; nada de
            # armar un diccionario por fila para leer cinco campos.
            lector = csv.reader(_lineas(cia, anio, configuracion, cliente_activo))
            encabezado: list[str] | None = None
            i_auxiliar = i_grupo = i_subgrupo = i_cuenta = i_desc_auxiliar = -1
            indices_meses: list[int] = []
            largo_minimo = 0
            for campos in lector:
                if not campos:
                    continue
                if encabezado is None:
                    encabezado = [nombre.strip().lower() for nombre in campos]
                    indice = {nombre: posicion for posicion, nombre in enumerate(encabezado)}
                    i_auxiliar = indice.get(COL_AUXILIAR, -1)
                    i_grupo = indice.get("grupo", -1)
                    i_subgrupo = indice.get("clase", -1)
                    i_cuenta = indice.get("cuenta", -1)
                    i_desc_auxiliar = indice.get("desc_auxiliar", -1)
                    indices_meses = [indice.get(f"s{mes}", -1) for mes in range(1, 13)]
                    largo_minimo = max([i_auxiliar, *indices_meses]) + 1
                    continue
                if len(campos) < largo_minimo:
                    continue

                auxiliar = campos[i_auxiliar].strip() if i_auxiliar >= 0 else ""
                clase = clasificar(auxiliar[:4])
                if clase is None:
                    continue
                signo = -1 if es_naturaleza_credito(clase) else 1
                valores = tuple(
                    _a_decimal(campos[posicion]) * signo if posicion >= 0 else _CERO
                    for posicion in indices_meses
                )
                if all(valor == _CERO for valor in valores):
                    continue
                cuenta = (campos[i_cuenta].strip() if i_cuenta >= 0 else "") or (
                    campos[i_desc_auxiliar].strip() if i_desc_auxiliar >= 0 else ""
                )
                filas.append(
                    FilaAnualEnVivo(
                        clase=clase,
                        grupo=campos[i_grupo].strip() if i_grupo >= 0 else "",
                        subgrupo=campos[i_subgrupo].strip() if i_subgrupo >= 0 else "",
                        cuenta=cuenta,
                        valores=valores,
                    )
                )
        finally:
            if propio:
                cliente_activo.close()

        if usar_cache:
            _cache[clave] = (time.monotonic(), filas)
        return filas


class _ContextoNulo:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_: object) -> None:
        return None


_NULO = _ContextoNulo()


def saldos_por_clase_en_vivo(
    cia: int,
    periodo: int,
    *,
    configuracion: ConfiguracionFinancieroSiesa | None = None,
    cliente: httpx.Client | None = None,
) -> dict[ClaseCuenta, Decimal]:
    """Suma, por clase PUC, el movimiento del mes `periodo` (AAAAMM) para `cia`.

    Ya reexpresado como saldo económico positivo (naturaleza crédito
    invertida), igual que `FinancieroReportesService._saldos_por_clase`.
    """
    if configuracion is None:
        from app.core.config import obtener_settings

        configuracion = ConfiguracionFinancieroSiesa.desde_settings(obtener_settings())

    anio = periodo // 100
    mes = periodo % 100
    # Sin caché cuando la prueba trae su propio cliente simulado: cada prueba
    # arma un CSV distinto para la misma (cia, año) y no debe heredar la
    # respuesta de la anterior.
    filas = _filas_del_anio(cia, anio, configuracion, cliente, usar_cache=cliente is None)

    acumulado: dict[ClaseCuenta, Decimal] = {}
    for fila in filas:
        valor = fila.valores[mes - 1]
        if valor == _CERO:
            continue
        acumulado[fila.clase] = acumulado.get(fila.clase, _CERO) + valor
    return acumulado


@dataclass(frozen=True, slots=True)
class FilaSituacionFinanciera:
    """Un renglón sumarizado: clase PUC × subgrupo, con su monto del mes."""

    clase: ClaseCuenta
    grupo: str
    subgrupo: str
    monto: Decimal


def situacion_financiera_en_vivo(
    cia: int,
    periodo: int,
    *,
    configuracion: ConfiguracionFinancieroSiesa | None = None,
    cliente: httpx.Client | None = None,
) -> list[FilaSituacionFinanciera]:
    """El sumarizado de la situación financiera del mes: una fila por

    (clase PUC, subgrupo), la misma agrupación que muestra el reporte nativo
    de SIESA («Consulta sumarizada estado de la situación financiera»), en vez
    del detalle cuenta por cuenta × tercero × centro.
    """
    if configuracion is None:
        from app.core.config import obtener_settings

        configuracion = ConfiguracionFinancieroSiesa.desde_settings(obtener_settings())

    anio = periodo // 100
    mes = periodo % 100
    filas = _filas_del_anio(cia, anio, configuracion, cliente, usar_cache=cliente is None)

    acumulado: dict[tuple[ClaseCuenta, str, str], Decimal] = {}
    for fila in filas:
        valor = fila.valores[mes - 1]
        if valor == _CERO:
            continue
        clave = (fila.clase, fila.grupo, fila.subgrupo)
        acumulado[clave] = acumulado.get(clave, _CERO) + valor

    return [
        FilaSituacionFinanciera(clase=clase, grupo=grupo, subgrupo=subgrupo, monto=monto)
        for (clase, grupo, subgrupo), monto in acumulado.items()
    ]
