"""Lectura mensual de ventas facturadas por canal desde SIESA."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

import httpx
from pydantic import SecretStr

from app.core.config import obtener_settings
from app.core.errors import ErrorSigrep, ErrorValidacion
from app.infrastructure.fuentes.siesa import token_efectivo

if TYPE_CHECKING:
    from app.core.config import Settings

RUTA_VENTAS_POR_CANAL = "/ventas/ventas-por-canal"
LIMITE_PAGINA = 5000


class ErrorFuenteVentasCanal(ErrorSigrep):
    """La API SIESA no pudo entregar ventas facturadas por canal."""

    codigo = "fuente_ventas_canal"
    http_status = 502


@dataclass(frozen=True, slots=True)
class ConfiguracionVentasCanal:
    url_base: str
    token: SecretStr = field(repr=False)
    timeout_conexion_seg: float = 15.0
    timeout_lectura_seg: float = 600.0

    @classmethod
    def desde_settings(cls, settings: Settings) -> ConfiguracionVentasCanal:
        token = settings.siesa_token.get_secret_value().strip()
        url_base = (settings.siesa_url_base or "").strip().rstrip("/")
        if not token or not url_base:
            raise ErrorValidacion(
                "Las ventas facturadas por canal necesitan SIGREP_SIESA_TOKEN y "
                "SIGREP_SIESA_URL_BASE."
            )
        return cls(
            url_base=url_base,
            token=SecretStr(token),
            timeout_conexion_seg=settings.siesa_timeout_conexion_seg,
            timeout_lectura_seg=settings.siesa_timeout_lectura_seg,
        )

    def cabeceras(self) -> dict[str, str]:
        return {
            "Authorization": token_efectivo(self.token.get_secret_value()),
            "Accept": "application/json",
        }


@dataclass(frozen=True, slots=True)
class RegistroVentaCanal:
    canal: str
    venta_neta: Decimal


def _decimal_venta(valor: object) -> Decimal:
    try:
        return Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ErrorFuenteVentasCanal(
            "La API de consulta devolvió una Venta_Neta inválida para el reporte por canal."
        ) from exc


def consultar_ventas_por_canal(
    periodo: str,
    companias: tuple[int, ...],
    *,
    configuracion: ConfiguracionVentasCanal | None = None,
    cliente: httpx.Client | None = None,
) -> list[RegistroVentaCanal]:
    """Devuelve las filas facturadas de un mes completo, paginadas por SIESA."""
    if len(periodo) != 6 or not periodo.isdigit() or not 1 <= int(periodo[4:]) <= 12:
        raise ErrorValidacion("El período de ventas por canal debe tener formato AAAAMM.")
    if not companias:
        raise ErrorValidacion("No hay compañías SIESA configuradas para consultar canales.")

    if configuracion is None:
        configuracion = ConfiguracionVentasCanal.desde_settings(obtener_settings())

    propio = cliente is None
    if cliente is None:
        cliente = httpx.Client(
            timeout=httpx.Timeout(
                connect=configuracion.timeout_conexion_seg,
                read=configuracion.timeout_lectura_seg,
                write=configuracion.timeout_conexion_seg,
                pool=configuracion.timeout_conexion_seg,
            ),
            follow_redirects=True,
        )

    registros: list[RegistroVentaCanal] = []
    url = configuracion.url_base + RUTA_VENTAS_POR_CANAL
    try:
        for compania in companias:
            offset = 0
            while True:
                parametros: list[tuple[str, str | int | float | bool | None]] = [
                    ("periodo_inicio", periodo),
                    ("periodo_fin", periodo),
                    ("cia", str(compania)),
                    ("limit", str(LIMITE_PAGINA)),
                    ("offset", str(offset)),
                ]
                respuesta = cliente.get(url, params=parametros, headers=configuracion.cabeceras())
                if respuesta.status_code >= 400:
                    raise ErrorFuenteVentasCanal(
                        f"La API de consulta respondió {respuesta.status_code} al pedir "
                        f"ventas por canal de la compañía {compania}."
                    )
                pagina = respuesta.json()
                filas = pagina.get("data") if isinstance(pagina, Mapping) else None
                if not isinstance(filas, list):
                    raise ErrorFuenteVentasCanal(
                        "La API de consulta devolvió una página inválida de ventas por canal."
                    )
                for fila in filas:
                    if not isinstance(fila, Mapping):
                        raise ErrorFuenteVentasCanal(
                            "La API de consulta devolvió una fila inválida de ventas por canal."
                        )
                    canal = str(fila.get("Canal") or "").strip() or "SIN CLASE"
                    registros.append(
                        RegistroVentaCanal(
                            canal=canal,
                            venta_neta=_decimal_venta(fila.get("Venta_Neta")),
                        )
                    )

                if not pagina.get("has_more"):
                    break
                siguiente = pagina.get("next_offset")
                if not isinstance(siguiente, int) or siguiente <= offset:
                    raise ErrorFuenteVentasCanal(
                        "La API de consulta devolvió un desplazamiento de página inválido."
                    )
                offset = siguiente
    except ErrorFuenteVentasCanal:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise ErrorFuenteVentasCanal(
            "No fue posible consultar las ventas facturadas por canal en SIESA."
        ) from exc
    finally:
        if propio:
            cliente.close()

    return registros
