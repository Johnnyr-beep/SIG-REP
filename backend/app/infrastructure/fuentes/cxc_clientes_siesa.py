"""Consulta de saldos de cuentas por cobrar a clientes en SIESA."""

from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import date
from time import sleep

import httpx

from app.core.config import obtener_settings
from app.infrastructure.fuentes.siesa import ConfiguracionSiesa, ErrorFuenteSiesa

RUTA_CXC_CLIENTES = "/ventas/saldos-cxc-clientes"
COMPANIAS_CXC_CLIENTES = (3, 4, 6, 7)


@dataclass(frozen=True, slots=True)
class CxcClientesCrudo:
    """Encabezados y filas tal como los entrega el CSV de SIESA."""

    columnas: tuple[str, ...]
    filas: tuple[dict[str, str | None], ...]


class FuenteCxcClientesSiesa:
    """Lee saldos y antigüedad de cartera por cliente para el Grupo Santacruz."""

    def __init__(
        self,
        *,
        configuracion: ConfiguracionSiesa | None = None,
        sesion_http: httpx.Client | None = None,
    ) -> None:
        if configuracion is None:
            base = ConfiguracionSiesa.desde_settings(obtener_settings(), unidad="carnes")
            configuracion = replace(base, companias=COMPANIAS_CXC_CLIENTES)
        self._configuracion = configuracion
        self._sesion_http = sesion_http
        self._propia = sesion_http is None

    def cerrar(self) -> None:
        if self._propia and self._sesion_http is not None:
            self._sesion_http.close()
            self._sesion_http = None

    def leer(self, fecha_corte: date | None = None) -> CxcClientesCrudo:
        configuracion = self._configuracion
        parametros: list[tuple[str, str | int | float | bool | None]] = [
            *(("compania", str(cia)) for cia in configuracion.companias),
        ]
        if fecha_corte is not None:
            parametros.append(("fecha_corte", fecha_corte.isoformat()))
        parametros.extend((("limit", "5000"), ("offset", "0"), ("format", "csv")))
        url = configuracion.url_base + RUTA_CXC_CLIENTES

        for intento in range(1, max(configuracion.reintentos, 1) + 1):
            ultimo = intento >= max(configuracion.reintentos, 1)
            try:
                with self._cliente().stream(
                    "GET",
                    url,
                    params=parametros,
                    headers=configuracion.cabeceras(),
                ) as respuesta:
                    if respuesta.status_code >= 400:
                        reintentable = respuesta.status_code in {408, 429, 500, 502, 503, 504}
                        estado = respuesta.status_code
                        respuesta.read()
                        if reintentable and not ultimo:
                            self._esperar(intento)
                            continue
                        raise ErrorFuenteSiesa(
                            f"La API de SIESA respondió {estado} en {RUTA_CXC_CLIENTES}.",
                            reintentable=reintentable,
                        )
                    return self._parsear(respuesta.iter_lines())
            except ErrorFuenteSiesa:
                raise
            except httpx.HTTPError as exc:
                if ultimo:
                    raise ErrorFuenteSiesa(
                        f"No se pudo leer {RUTA_CXC_CLIENTES} "
                        f"de la API de SIESA ({type(exc).__name__})."
                    ) from None
                self._esperar(intento)

        raise ErrorFuenteSiesa(f"No se pudo leer {RUTA_CXC_CLIENTES} de la API de SIESA.")

    def _parsear(self, lineas: Iterator[str]) -> CxcClientesCrudo:
        lector = csv.DictReader(lineas)
        encabezado = lector.fieldnames
        if not encabezado:
            raise ErrorFuenteSiesa(f"El CSV de {RUTA_CXC_CLIENTES} llegó vacío o sin encabezado.")

        columnas = tuple(str(columna).lstrip("\ufeff").strip() for columna in encabezado)
        filas = tuple(
            {
                columna: valor.strip() if valor and valor.strip() else None
                for original, columna in zip(encabezado, columnas, strict=True)
                if (valor := registro.get(original)) is not None
            }
            for registro in lector
        )
        return CxcClientesCrudo(columnas, filas)

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

    def _esperar(self, intento: int) -> None:
        espera = self._configuracion.espera_reintento_seg
        if espera > 0:
            sleep(espera * intento)
