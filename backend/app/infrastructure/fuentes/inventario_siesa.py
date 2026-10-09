"""Consulta del inventario actual por punto de venta en SIESA."""

from __future__ import annotations

import json
from dataclasses import dataclass
from time import sleep

import httpx

from app.core.config import obtener_settings
from app.infrastructure.fuentes.siesa import ConfiguracionSiesa, ErrorFuenteSiesa

RUTA_INVENTARIO_PDV = "/ventas/inventario-pdv"
PARAMETROS_INVENTARIO_PDV = {
    "limit": "5000",
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
        """Descarga todas las páginas JSON del inventario de puntos de venta."""
        configuracion = self._configuracion
        url = configuracion.url_base + RUTA_INVENTARIO_PDV
        columnas: list[str] = []
        filas: list[dict[str, str | None]] = []
        offset = 0
        while True:
            parametros = (*PARAMETROS_INVENTARIO_PDV.items(), ("offset", str(offset)))
            pagina, hay_mas, siguiente_offset = self._leer_pagina(url, parametros)
            for columna in pagina.columnas:
                if columna not in columnas:
                    columnas.append(columna)
            filas.extend(pagina.filas)
            if not hay_mas:
                return InventarioPdvCrudo(tuple(columnas), tuple(filas))
            if siguiente_offset is None or siguiente_offset <= offset:
                raise ErrorFuenteSiesa(
                    f"La paginación de {RUTA_INVENTARIO_PDV} no avanzó correctamente."
                )
            offset = siguiente_offset

    def _leer_pagina(
        self,
        url: str,
        parametros: tuple[tuple[str, str], ...],
    ) -> tuple[InventarioPdvCrudo, bool, int | None]:
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
                            f"La API de SIESA respondió {estado} en {RUTA_INVENTARIO_PDV}.",
                            reintentable=reintentable,
                        )

                    try:
                        contenido = respuesta.json()
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        raise ErrorFuenteSiesa(
                            f"La respuesta JSON de {RUTA_INVENTARIO_PDV} no es válida."
                        ) from None
                    return self._parsear(contenido)
            except ErrorFuenteSiesa:
                raise
            except httpx.HTTPError as exc:
                if ultimo:
                    raise ErrorFuenteSiesa(
                        f"No se pudo leer {RUTA_INVENTARIO_PDV} "
                        f"de la API de SIESA ({type(exc).__name__})."
                    ) from None
                self._esperar(intento)

        raise ErrorFuenteSiesa(f"No se pudo leer {RUTA_INVENTARIO_PDV} de la API de SIESA.")

    def _parsear(self, contenido: object) -> tuple[InventarioPdvCrudo, bool, int | None]:
        if not isinstance(contenido, dict):
            raise ErrorFuenteSiesa(f"La respuesta JSON de {RUTA_INVENTARIO_PDV} no es válida.")
        registros = contenido.get("data")
        if not isinstance(registros, list):
            raise ErrorFuenteSiesa(
                f"La respuesta JSON de {RUTA_INVENTARIO_PDV} no contiene una lista de filas."
            )

        columnas: list[str] = []
        filas: list[dict[str, str | None]] = []
        for registro in registros:
            if not isinstance(registro, dict):
                raise ErrorFuenteSiesa(
                    f"La respuesta JSON de {RUTA_INVENTARIO_PDV} contiene una fila inválida."
                )
            fila: dict[str, str | None] = {}
            for original, valor in registro.items():
                columna = str(original).strip()
                if columna not in columnas:
                    columnas.append(columna)
                fila[columna] = str(valor).strip() if valor is not None else None
            filas.append(fila)

        hay_mas = contenido.get("has_more", False)
        siguiente = contenido.get("next_offset")
        if not isinstance(hay_mas, bool) or (
            siguiente is not None
            and (not isinstance(siguiente, int) or isinstance(siguiente, bool))
        ):
            raise ErrorFuenteSiesa(
                f"La respuesta JSON de {RUTA_INVENTARIO_PDV} tiene datos de paginación inválidos."
            )
        return InventarioPdvCrudo(tuple(columnas), tuple(filas)), hay_mas, siguiente

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
    "PARAMETROS_INVENTARIO_PDV",
    "RUTA_INVENTARIO_PDV",
    "FuenteInventarioPdvSiesa",
    "InventarioPdvCrudo",
]
