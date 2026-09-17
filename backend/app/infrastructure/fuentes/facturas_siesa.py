"""Conteo de documentos (facturas) por punto de venta y día.

`GET /ventas/facturas-pdv-diario` — un renglón por factura, no por línea de
producto. §4.4 documentaba el número de documentos como un dato que ningún
endpoint entregaba; este lo hace, y esta fuente lo reduce a lo único que hace
falta persistir: cuántas facturas **distintas** tuvo cada punto de venta cada
día.

── Dos diferencias con `FuenteVentaSiesa` que conviene tener presentes ────────

**1. El C.O. llega como código, no como descripción.** La columna es `id_co`
(`406`, `403`…), no `DescCO`. No hace falta el directorio de
`puntos_venta.descripcion_siesa` ni la comparación por texto: se normaliza
directo a tres cifras.

**2. `limit`/`offset` no aplican con `format=csv`.** Medido: pedir `limit=10`
sobre agosto-2026 (compañía 4) devolvió las **132 783** filas completas, igual
que sin `limit`. El CSV ignora la paginación y siempre trae el rango entero
por compañía, así que una petición por compañía basta.

Un `guid_factura` puede aparecer más de una vez si la fuente decidiera repetir
la fila (no se ha medido que ocurra, pero tampoco hay garantía de lo
contrario), así que se cuentan **valores distintos de `guid_factura`** por
`(id_co, fecha)`, nunca filas crudas.

── `facturas-pdv-resumen` como complemento, no como reemplazo ─────────────────

Medido (17-sep-2026): `facturas-pdv-resumen` **ignora** `fecha_inicio`/
`fecha_fin` —pedir 2026-09-01 a 2026-09-05 devolvió filas del 8 al 17—, así
que no sirve para el histórico y **nunca** reemplaza a `facturas-pdv-diario`.
Pero sí trae, en JSON y para su ventana reciente propia, los tres puntos que
`facturas-pdv-diario` no publica (605, 606, 415 — mismo hueco que el costo de
PEREIRA en §4.1). Por eso se usa **solo para rellenar** las combinaciones
`(id_co, fecha)` que `facturas-pdv-diario` no trajo, nunca para pisar un valor
ya contado por `guid_factura`. Si esta llamada falla, se ignora: el dato
principal ya quedó completo antes de intentarla.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator, Mapping
from datetime import date
from time import sleep

import httpx

from app.core.logging import obtener_logger
from app.domain.normalizacion import a_fecha
from app.infrastructure.fuentes.siesa import ConfiguracionSiesa, ErrorFuenteSiesa

logger = obtener_logger(__name__)

RUTA_FACTURAS_PDV_DIARIO = "/ventas/facturas-pdv-diario"
RUTA_FACTURAS_PDV_RESUMEN = "/ventas/facturas-pdv-resumen"

COL_ID_CO = "id_co"
COL_FECHA = "fecha"
COL_GUID = "guid_factura"
COLUMNAS_OBLIGATORIAS = (COL_ID_CO, COL_FECHA, COL_GUID)

#: Límite de página para `facturas-pdv-resumen`: la ventana que de verdad
#: devuelve es corta (días recientes), así que una sola página grande basta en
#: la práctica, pero se sigue `has_more` por si acaso.
LIMITE_PAGINA_RESUMEN = 1000


class FuenteFacturasSiesa:
    """Cuenta facturas distintas por `(codigo_co, fecha)` en un rango."""

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
        """`{(codigo_co, fecha): facturas distintas}` del rango, ambos incluidos.

        `facturas-pdv-diario` manda: es la que respeta el rango pedido. Encima
        se intenta rellenar con `facturas-pdv-resumen` lo que aquí faltó —hoy,
        los puntos 605, 606 y 415—, sin pisar nada de lo ya contado.
        """
        vistos: dict[tuple[str, date], set[str]] = {}
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
                    f"El CSV de {RUTA_FACTURAS_PDV_DIARIO} no trae las columnas obligatorias: "
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
                guid = (registro.get(COL_GUID) or "").strip()
                if not codigo or fecha is None or not guid:
                    continue
                clave_pdv = codigo.zfill(3)
                vistos.setdefault((clave_pdv, fecha), set()).add(guid)

        conteos = {clave: len(guids) for clave, guids in vistos.items()}

        try:
            for clave, cantidad in self._resumen_relleno(desde, hasta).items():
                conteos.setdefault(clave, cantidad)
        except Exception:
            logger.warning("facturas_pdv_resumen_fallo", exc_info=True)

        return conteos

    def _resumen_relleno(self, desde: date, hasta: date) -> dict[tuple[str, date], int]:
        """Lo que `facturas-pdv-resumen` traiga, tal cual, para rellenar huecos.

        No respeta `fecha_inicio`/`fecha_fin` —medido: devuelve su propia
        ventana reciente, no el rango pedido—, así que se le manda igual el
        rango por documentar la intención, pero no se confía en que lo honre.
        """
        relleno: dict[tuple[str, date], int] = {}
        offset = 0
        for _ in range(20):  # tope de seguridad: 20 000 filas, muy por encima de lo esperado
            parametros = {
                "fecha_inicio": desde.isoformat(),
                "fecha_fin": hasta.isoformat(),
                "limit": str(LIMITE_PAGINA_RESUMEN),
                "offset": str(offset),
            }
            cuerpo = self._cliente().get(
                self._configuracion.url_base + RUTA_FACTURAS_PDV_RESUMEN,
                params=parametros,
                headers=self._configuracion.cabeceras(),
                timeout=self._configuracion.timeout_lectura_seg,
            )
            if cuerpo.status_code >= 400:
                return relleno
            cuerpo_json = cuerpo.json()
            for fila in cuerpo_json.get("data", []):
                codigo = str(fila.get("id_co", "")).strip()
                fecha = a_fecha(fila.get("fecha"))
                cantidad = fila.get("num_facturas")
                if not codigo or fecha is None or not isinstance(cantidad, int):
                    continue
                relleno[(codigo.zfill(3), fecha)] = cantidad
            if not cuerpo_json.get("has_more"):
                return relleno
            offset = cuerpo_json.get("next_offset") or offset + LIMITE_PAGINA_RESUMEN
        return relleno

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
        url = configuracion.url_base + RUTA_FACTURAS_PDV_DIARIO

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
                            f"{RUTA_FACTURAS_PDV_DIARIO}: {detalle}",
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
                        f"No se pudo leer {RUTA_FACTURAS_PDV_DIARIO} de la API de SIESA "
                        f"({type(exc).__name__})."
                    ) from None
            if configuracion.espera_reintento_seg > 0:
                sleep(configuracion.espera_reintento_seg * intento)
