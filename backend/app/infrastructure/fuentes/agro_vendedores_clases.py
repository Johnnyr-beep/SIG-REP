"""Catálogo de clases asignadas a vendedores en SIESA."""

from __future__ import annotations

import csv
import io
import re
import unicodedata

import httpx

from app.infrastructure.fuentes.agropecuaria import (
    COMPANIA_AGROPECUARIA,
    ConfiguracionAgro,
    ErrorFuenteAgro,
)

RUTA_VENDEDORES_CLASES = "/ventas/vendedores-clases"
CLASES_RENTABILIDAD = ("CCT", "MAY", "MON", "OFI", "TAT")

_COLUMNAS_CODIGO = {"codigovendedor", "codvendedor", "idvendedor", "vendedorid"}
_COLUMNAS_CLASE = {"clase", "clasevendedor", "canal", "canalvendedor"}
_CODIGOS_CLASE = {
    "CCT": "CCT",
    "CALLCENTER": "CCT",
    "MAY": "MAY",
    "MAYORISTA": "MAY",
    "MON": "MON",
    "OFI": "OFI",
    "OFICINA": "OFI",
    "TAT": "TAT",
}


def _normalizar_columna(valor: str) -> str:
    plegado = unicodedata.normalize("NFKD", valor.strip().lower())
    sin_tildes = "".join(caracter for caracter in plegado if not unicodedata.combining(caracter))
    return re.sub(r"[^a-z0-9]", "", sin_tildes)


def _clase_corta(valor: str) -> str | None:
    clave = _normalizar_columna(valor).upper()
    return _CODIGOS_CLASE.get(clave)


def parsear_vendedores_clases(contenido: str) -> dict[str, str]:
    """Devuelve código de vendedor a una de las clases usadas en el reporte."""
    lector = csv.DictReader(io.StringIO(contenido))
    if not lector.fieldnames:
        return {}

    columnas = {_normalizar_columna(nombre): nombre for nombre in lector.fieldnames if nombre}
    columna_codigo = next(
        (columnas[nombre] for nombre in _COLUMNAS_CODIGO if nombre in columnas), None
    )
    columna_clase = next(
        (columnas[nombre] for nombre in _COLUMNAS_CLASE if nombre in columnas), None
    )
    if columna_codigo is None or columna_clase is None:
        recibidas = ", ".join(sorted(columnas))
        raise ErrorFuenteAgro(
            f"El CSV de {RUTA_VENDEDORES_CLASES} no contiene columnas reconocibles "
            f"de vendedor y clase. Llegaron: {recibidas}."
        )

    vendedores: dict[str, str] = {}
    for fila in lector:
        codigo = (fila.get(columna_codigo) or "").strip()
        clase = _clase_corta(fila.get(columna_clase) or "")
        if not codigo or clase is None:
            continue
        clase_anterior = vendedores.get(codigo)
        if clase_anterior is not None and clase_anterior != clase:
            raise ErrorFuenteAgro(
                f"El vendedor {codigo} tiene más de una clase en {RUTA_VENDEDORES_CLASES}."
            )
        vendedores[codigo] = clase
    return vendedores


def obtener_vendedores_clases(
    configuracion: ConfiguracionAgro,
    cliente: httpx.Client | None = None,
) -> dict[str, str]:
    """Consulta el catálogo de la compañía agropecuaria (cia 3)."""
    propio = cliente is None
    cliente_activo = cliente or httpx.Client(timeout=60, follow_redirects=True)
    try:
        respuesta = cliente_activo.get(
            configuracion.url_base + RUTA_VENDEDORES_CLASES,
            params={"cia": str(COMPANIA_AGROPECUARIA), "format": "csv"},
            headers=configuracion.cabeceras(),
        )
        if respuesta.status_code >= 400:
            raise ErrorFuenteAgro(
                f"La API de consulta respondió {respuesta.status_code} al pedir "
                f"{RUTA_VENDEDORES_CLASES}: {respuesta.text[:300]}"
            )
        return parsear_vendedores_clases(respuesta.text)
    except httpx.HTTPError as exc:
        raise ErrorFuenteAgro(
            f"No fue posible consultar {RUTA_VENDEDORES_CLASES}: {type(exc).__name__}."
        ) from exc
    finally:
        if propio:
            cliente_activo.close()
