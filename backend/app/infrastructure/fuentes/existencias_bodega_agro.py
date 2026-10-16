"""Consulta de existencias por bodega para Agropecuaria, compañía 3."""

from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import replace
from time import sleep

import httpx

from app.core.config import obtener_settings
from app.infrastructure.fuentes.inventario_siesa import InventarioPdvCrudo
from app.infrastructure.fuentes.siesa import ConfiguracionSiesa, ErrorFuenteSiesa, token_efectivo

RUTA_EXISTENCIAS_BODEGA = "/ventas/existencias-bodega"
PARAMETROS_EXISTENCIAS_BODEGA = {
    "cia": "3",
    "limit": "5000",
    "offset": "0",
    "format": "csv",
}


class FuenteExistenciasBodegaAgroSiesa:
    """Descarga la foto de inventario por bodega e ítem desde SIESA."""

    def __init__(
        self,
        *,
        configuracion: ConfiguracionSiesa | None = None,
        sesion_http: httpx.Client | None = None,
    ) -> None:
        if configuracion is None:
            settings = obtener_settings()
            base = ConfiguracionSiesa.desde_settings(settings, unidad="carnes")
            configuracion = replace(base, companias=(settings.agro_compania,))
        self._configuracion = configuracion
        self._sesion_http = sesion_http
        self._propia = sesion_http is None

    def cerrar(self) -> None:
        if self._propia and self._sesion_http is not None:
            self._sesion_http.close()
            self._sesion_http = None

    def leer(self) -> InventarioPdvCrudo:
        configuracion = self._configuracion
        url = configuracion.url_base + RUTA_EXISTENCIAS_BODEGA
        parametros = {
            **PARAMETROS_EXISTENCIAS_BODEGA,
            "cia": str(configuracion.companias[0]),
        }

        for intento in range(1, max(configuracion.reintentos, 1) + 1):
            ultimo = intento >= max(configuracion.reintentos, 1)
            try:
                with self._cliente().stream(
                    "GET",
                    url,
                    params=parametros,
                    headers={
                        "X-API-Key": token_efectivo(configuracion.token.get_secret_value()),
                        "Accept": "text/csv",
                    },
                ) as respuesta:
                    if respuesta.status_code >= 400:
                        reintentable = respuesta.status_code in {408, 429, 500, 502, 503, 504}
                        estado = respuesta.status_code
                        respuesta.read()
                        if reintentable and not ultimo:
                            self._esperar(intento)
                            continue
                        raise ErrorFuenteSiesa(
                            f"La API de SIESA respondió {estado} en {RUTA_EXISTENCIAS_BODEGA}.",
                            reintentable=reintentable,
                        )

                    return self._parsear(respuesta.iter_lines())
            except ErrorFuenteSiesa:
                raise
            except httpx.HTTPError as exc:
                if ultimo:
                    raise ErrorFuenteSiesa(
                        f"No se pudo leer {RUTA_EXISTENCIAS_BODEGA} "
                        f"de la API de SIESA ({type(exc).__name__})."
                    ) from None
                self._esperar(intento)

        raise ErrorFuenteSiesa(f"No se pudo leer {RUTA_EXISTENCIAS_BODEGA} de la API de SIESA.")

    def _parsear(self, lineas: Iterator[str]) -> InventarioPdvCrudo:
        lector = csv.DictReader(lineas)
        encabezado = lector.fieldnames
        if not encabezado:
            raise ErrorFuenteSiesa(
                f"El CSV de {RUTA_EXISTENCIAS_BODEGA} llegó vacío o sin encabezado."
            )

        columnas = tuple(str(columna).lstrip("\ufeff").strip() for columna in encabezado)
        filas: list[dict[str, str | None]] = []
        for registro in lector:
            filas.append(
                {
                    columna: valor.strip() if valor and valor.strip() else None
                    for original, columna in zip(encabezado, columnas, strict=True)
                    if (valor := registro.get(original)) is not None
                }
            )
        return InventarioPdvCrudo(columnas, tuple(filas))

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
