from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import StringIO

import httpx
from pydantic import SecretStr

from app.core.errors import ErrorSigrep, ErrorValidacion
from app.domain.normalizacion import a_decimal, a_fecha, normalizar_texto

RUTA_VENTAS_TAT = "/ventas/facturas-agropecuaria-tat"
COMPANIA_AGROPECUARIA = 3
COLUMNAS_TAT = (
    "fecha_documento",
    "nro_documento",
    "tipo_comercial",
    "cliente_factura",
    "razon_social_cliente",
    "codigo_sucursal",
    "descripcion_sucursal",
    "direccion_sucursal",
    "cantidad_inv",
    "valor_subtotal",
)


class ErrorFuenteTat(ErrorSigrep):
    codigo = "fuente_agro_tat"
    http_status = 502


@dataclass(frozen=True, slots=True)
class LineaTat:
    fecha_documento: date
    nro_documento: str
    tipo_comercial: str | None
    cliente_factura: str | None
    razon_social_cliente: str | None
    codigo_sucursal: str | None
    descripcion_sucursal: str | None
    direccion_sucursal: str | None
    cantidad_inv: Decimal
    valor_subtotal: Decimal


@dataclass(frozen=True, slots=True)
class ConfiguracionTat:
    url_base: str
    token: SecretStr
    cia: int = COMPANIA_AGROPECUARIA
    timeout_conexion_seg: float = 15.0
    timeout_lectura_seg: float = 600.0

    @classmethod
    def desde_settings(cls, settings: object) -> ConfiguracionTat:
        token = settings.siesa_token.get_secret_value().strip()  # type: ignore[attr-defined]
        url = settings.siesa_url_base.strip().rstrip("/")  # type: ignore[attr-defined]
        if not token or not url:
            raise ErrorValidacion("Configure SIGREP_SIESA_TOKEN y SIGREP_SIESA_URL_BASE.")
        return cls(url_base=url, token=SecretStr(token))


class FuenteVentasTat:
    def __init__(
        self,
        configuracion: ConfiguracionTat | None = None,
        cliente: httpx.Client | None = None,
    ) -> None:
        if configuracion is None:
            from app.core.config import obtener_settings

            configuracion = ConfiguracionTat.desde_settings(obtener_settings())
        self.configuracion = configuracion
        self._cliente = cliente or httpx.Client(
            timeout=httpx.Timeout(
                configuracion.timeout_lectura_seg,
                connect=configuracion.timeout_conexion_seg,
            )
        )
        self._propio = cliente is None

    def obtener_ventas(self, desde: date, hasta: date) -> Iterator[LineaTat]:
        respuesta = self._cliente.get(
            f"{self.configuracion.url_base}{RUTA_VENTAS_TAT}",
            headers={
                "Authorization": self.configuracion.token.get_secret_value().removeprefix("1-")
            },
            params={
                "fecha_inicio": desde.isoformat(),
                "fecha_fin": hasta.isoformat(),
                "cia": self.configuracion.cia,
                "limit": 0,
                "offset": 0,
                "format": "csv",
            },
        )
        if respuesta.is_error:
            raise ErrorFuenteTat(f"SIESA TAT respondió HTTP {respuesta.status_code}.")
        try:
            registros = csv.DictReader(StringIO(respuesta.text))
            encabezados = tuple(
                (campo or "").strip().lower() for campo in registros.fieldnames or ()
            )
            if encabezados != COLUMNAS_TAT:
                raise ErrorFuenteTat("El CSV TAT no coincide con las columnas esperadas.")
            for numero, fila in enumerate(registros, start=2):
                try:
                    fecha_documento = a_fecha(fila["fecha_documento"])
                    cantidad_inv = a_decimal(fila["cantidad_inv"])
                    valor_subtotal = a_decimal(fila["valor_subtotal"])
                    if fecha_documento is None or cantidad_inv is None or valor_subtotal is None:
                        raise ValueError("faltan fecha_documento, cantidad_inv o valor_subtotal")
                    yield LineaTat(
                        fecha_documento=fecha_documento,
                        nro_documento=normalizar_texto(fila["nro_documento"]) or "",
                        tipo_comercial=normalizar_texto(fila["tipo_comercial"]),
                        cliente_factura=normalizar_texto(fila["cliente_factura"]),
                        razon_social_cliente=normalizar_texto(fila["razon_social_cliente"]),
                        codigo_sucursal=normalizar_texto(fila["codigo_sucursal"]),
                        descripcion_sucursal=normalizar_texto(fila["descripcion_sucursal"]),
                        direccion_sucursal=normalizar_texto(fila["direccion_sucursal"]),
                        cantidad_inv=cantidad_inv,
                        valor_subtotal=valor_subtotal,
                    )
                except (KeyError, ValueError, TypeError) as exc:
                    raise ErrorFuenteTat(f"Fila TAT {numero} inválida: {exc}.") from exc
        except UnicodeDecodeError as exc:
            raise ErrorFuenteTat("La respuesta TAT no está codificada como texto válido.") from exc

    def cerrar(self) -> None:
        if self._propio:
            self._cliente.close()
