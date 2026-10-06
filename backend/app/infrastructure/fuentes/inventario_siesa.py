"""Consulta del inventario actual por punto de venta en SIESA."""

from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import dataclass
from time import sleep

import httpx

from app.core.config import obtener_settings
from app.infrastructure.fuentes.siesa import ConfiguracionSiesa, ErrorFuenteSiesa

RUTA_INVENTARIO_BODEGA_COMPANIA = "/ventas/inventario-bodega-compania"
BODEGAS_INVENTARIO_PDV = (
    "40103",
    "40201",
    "40301",
    "40501",
    "40601",
    "40701",
    "40901",
    "41201",
    "41301",
    "41401",
    "41501",
    "42001",
    "42101",
)
PARAMETROS_INVENTARIO_BODEGA = {
    "bodega": ",".join(BODEGAS_INVENTARIO_PDV),
    "lista_precios": "999",
    "plan1": "001",
    "plan2": "002",
    "limit": "5000",
    "offset": "0",
    "format": "csv",
}


@dataclass(frozen=True, slots=True)
class InventarioPdvCrudo:
    """Encabezados y filas tal como los entrega el endpoint de SIESA."""

    columnas: tuple[str, ...]
    filas: tuple[dict[str, str | None], ...]


class FuenteInventarioPdvSiesa:
    """Lee la foto actual de inventario sin asumir nombres de columnas."""

    def __init__(
        self,
        *,
        configuracion: ConfiguracionSiesa | None = None,
        sesion_http: httpx.Client | None = None,
    ) -> None:
        if configuracion is None:
            configuracion = ConfiguracionSiesa.desde_settings(obtener_settings(), unidad="carnes")
        self._configuracion = configuracion
        self._sesion_http = sesion_http
        self._propia = sesion_http is None

    def cerrar(self) -> None:
        if self._propia and self._sesion_http is not None:
            self._sesion_http.close()
            self._sesion_http = None

    def leer(self) -> InventarioPdvCrudo:
        """Descarga el inventario CSV por bodega, una petición por compañía."""
        configuracion = self._configuracion
        url = configuracion.url_base + RUTA_INVENTARIO_BODEGA_COMPANIA
        columnas: list[str] = []
        filas: list[dict[str, str | None]] = []

        for compania in configuracion.companias:
            parametros = {**PARAMETROS_INVENTARIO_BODEGA, "compania": str(compania)}
            inventario = self._leer_compania(url, parametros)
            for columna in inventario.columnas:
                if columna not in columnas:
                    columnas.append(columna)
            filas.extend(inventario.filas)

        return InventarioPdvCrudo(
            columnas=tuple(columnas),
            filas=tuple({columna: fila.get(columna) for columna in columnas} for fila in filas),
        )

    def _leer_compania(self, url: str, parametros: dict[str, str]) -> InventarioPdvCrudo:
        configuracion = self._configuracion
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
                            f"La API de SIESA respondió {estado} en "
                            f"{RUTA_INVENTARIO_BODEGA_COMPANIA}.",
                            reintentable=reintentable,
                        )

                    return self._parsear(respuesta.iter_lines())
            except ErrorFuenteSiesa:
                raise
            except httpx.HTTPError as exc:
                if ultimo:
                    raise ErrorFuenteSiesa(
                        f"No se pudo leer {RUTA_INVENTARIO_BODEGA_COMPANIA} "
                        f"de la API de SIESA ({type(exc).__name__})."
                    ) from None
                self._esperar(intento)

        raise ErrorFuenteSiesa(
            f"No se pudo leer {RUTA_INVENTARIO_BODEGA_COMPANIA} de la API de SIESA."
        )

    def _parsear(self, lineas: Iterator[str]) -> InventarioPdvCrudo:
        lector = csv.DictReader(lineas)
        encabezado = lector.fieldnames
        if not encabezado:
            raise ErrorFuenteSiesa(
                f"El CSV de {RUTA_INVENTARIO_BODEGA_COMPANIA} llegó vacío o sin encabezado."
            )

        columnas = tuple(str(columna).lstrip("\ufeff").strip() for columna in encabezado)
        filas: list[dict[str, str | None]] = []
        for registro in lector:
            fila: dict[str, str | None] = {}
            for original, columna in zip(encabezado, columnas, strict=True):
                valor = registro.get(original)
                fila[columna] = valor.strip() if valor and valor.strip() else None
            filas.append(fila)
        return InventarioPdvCrudo(columnas=columnas, filas=tuple(filas))

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


__all__ = [
    "BODEGAS_INVENTARIO_PDV",
    "PARAMETROS_INVENTARIO_BODEGA",
    "RUTA_INVENTARIO_BODEGA_COMPANIA",
    "FuenteInventarioPdvSiesa",
    "InventarioPdvCrudo",
]
