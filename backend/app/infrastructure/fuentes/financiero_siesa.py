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
    # El encabezado se pliega a minúsculas más abajo (`s1`, no `S1`): la
    # columna tiene que buscarse con la misma forma o no encuentra nada.
    columna_mes = f"s{mes}"

    propio = cliente is None
    cliente = cliente or httpx.Client(
        timeout=httpx.Timeout(
            connect=configuracion.timeout_conexion_seg,
            read=configuracion.timeout_lectura_seg,
            write=configuracion.timeout_conexion_seg,
            pool=configuracion.timeout_conexion_seg,
        ),
        follow_redirects=True,
    )

    acumulado: dict[ClaseCuenta, Decimal] = {}
    try:
        encabezado: list[str] | None = None
        for linea in _lineas(cia, anio, configuracion, cliente):
            if not linea.strip():
                continue
            if encabezado is None:
                encabezado = [nombre.strip().lower() for nombre in next(csv.reader([linea]))]
                continue
            campos = next(csv.reader([linea]))
            fila = dict(zip(encabezado, campos, strict=False))
            auxiliar = (fila.get(COL_AUXILIAR) or "").strip()
            clase = clasificar(auxiliar[:4])
            if clase is None:
                continue
            valor = _a_decimal(fila.get(columna_mes))
            if valor == _CERO:
                continue
            saldo = -valor if es_naturaleza_credito(clase) else valor
            acumulado[clase] = acumulado.get(clase, _CERO) + saldo
    finally:
        if propio:
            cliente.close()

    return acumulado
