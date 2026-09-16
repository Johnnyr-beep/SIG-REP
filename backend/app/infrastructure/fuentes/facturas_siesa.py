"""Conteo de documentos (facturas) por punto de venta y día.

`GET /ventas/facturas-pdv-resumen` — ya agregado del lado de SIESA: un renglón
por `(id_co, fecha)` —y bodega— con su propia columna `Documentos`, no uno por
factura. §4.4 documentaba el número de documentos como un dato que ningún
endpoint entregaba; primero se resolvió con `facturas-pdv-diario` contando
`guid_factura` distintos, y este endpoint hace la misma cuenta del lado de la
API, así que SIGREP ya no tiene que deduplicar nada.

── Lo que conviene tener presente ──────────────────────────────────────────

**1. El C.O. llega como código, no como descripción.** La columna es `id_co`
(`406`, `403`…), no `DescCO`. No hace falta el directorio de
`puntos_venta.descripcion_siesa` ni la comparación por texto: se normaliza
directo a tres cifras.

**2. Puede traer varias filas por `(id_co, fecha)`.** Si un punto de venta
factura desde más de una bodega el mismo día, cada bodega es su propia fila;
`Documentos` se **suma** por `(id_co, fecha)`, nunca se sobrescribe.

**3. `id_cia` es un entero, una petición por compañía.** Medido (16-sep-2026):
`id_cia=4,6,7` como lista separada por comas responde **422** ("Input should be
a valid integer"). Sigue el mismo patrón que `costos-razon-social`: hay que
pedir una vez por cada compañía de `SIGREP_SIESA_COMPANIAS`.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator, Mapping
from datetime import date
from time import sleep

import httpx

from app.domain.normalizacion import a_fecha
from app.infrastructure.fuentes.siesa import ConfiguracionSiesa, ErrorFuenteSiesa

RUTA_FACTURAS_PDV_RESUMEN = "/ventas/facturas-pdv-resumen"

COL_ID_CO = "id_co"
COL_FECHA = "fecha"
COL_DOCUMENTOS = "documentos"
COLUMNAS_OBLIGATORIAS = (COL_ID_CO, COL_FECHA, COL_DOCUMENTOS)


class FuenteFacturasSiesa:
    """Documentos por `(codigo_co, fecha)` en un rango, ya agregados por SIESA."""

    def __init__(
        self,
        *,
        unidad: str = "carnes",
        configuracion: ConfiguracionSiesa | None = None,
        sesion_http: httpx.Client | None = None,
    ) -> None:
        if configuracion is None:
            from app.core.config import obtener_settings

            configuracion = ConfiguracionSiesa.desde_settings(obtener_settings(), unidad=unidad)
        self._configuracion = configuracion
        self._sesion_http = sesion_http
        self._propia = sesion_http is None

    def cerrar(self) -> None:
        if self._propia and self._sesion_http is not None:
            self._sesion_http.close()
            self._sesion_http = None

    def contar_documentos(self, desde: date, hasta: date) -> dict[tuple[str, date], int]:
        """`{(codigo_co, fecha): documentos}` del rango, ambos incluidos.

        Una petición por compañía: medido (16-sep-2026) que `id_cia` aquí es un
        entero, no una lista —a diferencia de lo que parecía en una prueba
        manual, `id_cia=4,6,7` responde 422—. Se suma `Documentos` por
        `(id_co, fecha)` porque una misma fecha puede traer varias filas —una
        por bodega— para el mismo punto de venta.
        """
        conteos: dict[tuple[str, date], int] = {}
        for compania in self._configuracion.companias:
            parametros = {
                "fecha_inicio": desde.isoformat(),
                "fecha_fin": hasta.isoformat(),
                "id_cia": str(compania),
                "format": "csv",
            }
            lector = csv.DictReader(self._lineas(parametros))
            columnas = lector.fieldnames
            if not columnas:
                continue
            presentes = {str(c).strip().lower() for c in columnas if c}
            faltantes = [c for c in COLUMNAS_OBLIGATORIAS if c not in presentes]
            if faltantes:
                raise ErrorFuenteSiesa(
                    f"El CSV de {RUTA_FACTURAS_PDV_RESUMEN} no trae las columnas obligatorias: "
                    + ", ".join(faltantes)
                    + f". Llegaron: {', '.join(sorted(presentes))}."
                )
            for crudo in lector:
                registro = {
                    str(clave).strip().lower(): valor
                    for clave, valor in crudo.items()
                    if clave is not None
                }
                codigo = str(registro.get(COL_ID_CO, "")).strip()
                fecha = a_fecha(registro.get(COL_FECHA))
                crudo_documentos = str(registro.get(COL_DOCUMENTOS, "")).strip()
                if not codigo or fecha is None or not crudo_documentos:
                    continue
                try:
                    cantidad = int(crudo_documentos)
                except ValueError:
                    continue
                clave_pdv = codigo.zfill(3)
                conteos[(clave_pdv, fecha)] = conteos.get((clave_pdv, fecha), 0) + cantidad

        return conteos

    # ── HTTP ──────────────────────────────────────────────────────────────────

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

    def _lineas(self, parametros: Mapping[str, str]) -> Iterator[str]:
        """Streaming con reintentos acotados. Mismo criterio que `FuenteVentaSiesa`:

        solo se reintenta lo que todavía no entregó ninguna línea.
        """
        configuracion = self._configuracion
        url = configuracion.url_base + RUTA_FACTURAS_PDV_RESUMEN

        for intento in range(1, max(configuracion.reintentos, 1) + 1):
            entregadas = 0
            ultimo = configuracion.reintentos <= intento
            try:
                with self._cliente().stream(
                    "GET", url, params=dict(parametros), headers=configuracion.cabeceras()
                ) as respuesta:
                    if respuesta.status_code >= 400:
                        respuesta.read()
                        detalle = " ".join(respuesta.text.split())[:200]
                        raise ErrorFuenteSiesa(
                            f"La API de SIESA respondió {respuesta.status_code} en "
                            f"{RUTA_FACTURAS_PDV_RESUMEN}: {detalle}",
                            reintentable=respuesta.status_code in {408, 429, 500, 502, 503, 504},
                        )
                    for linea in respuesta.iter_lines():
                        entregadas += 1
                        yield linea
                    return
            except ErrorFuenteSiesa as exc:
                if entregadas or ultimo or not exc.reintentable:
                    raise
            except httpx.HTTPError as exc:
                if entregadas or ultimo:
                    raise ErrorFuenteSiesa(
                        f"No se pudo leer {RUTA_FACTURAS_PDV_RESUMEN} de la API de SIESA "
                        f"({type(exc).__name__})."
                    ) from None
            if configuracion.espera_reintento_seg > 0:
                sleep(configuracion.espera_reintento_seg * intento)
