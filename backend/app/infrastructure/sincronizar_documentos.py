"""Sincroniza el número de documentos diarios desde la API de SIESA.

Uso:

    python -m app.infrastructure.sincronizar_documentos --desde 2026-08-01 --hasta 2026-08-31

Requiere `SIGREP_SIESA_TOKEN` configurado (§ `FuenteFacturasSiesa`).
"""

from __future__ import annotations

import argparse
from datetime import date

from app.application.services.documentos_diarios_service import sincronizar_documentos_diarios
from app.core.config import obtener_settings
from app.core.db import sesion_ambito
from app.core.logging import configurar_logging, obtener_logger
from app.infrastructure.fuentes.facturas_siesa import FuenteFacturasSiesa

logger = obtener_logger(__name__)


def main() -> None:  # pragma: no cover - utilidad de línea de comandos
    parser = argparse.ArgumentParser(
        description="Sincroniza numero_documentos_diarios desde la API de SIESA."
    )
    parser.add_argument("--desde", required=True, help="AAAA-MM-DD, inclusive")
    parser.add_argument("--hasta", required=True, help="AAAA-MM-DD, inclusive")
    parser.add_argument(
        "--unidad",
        default="carnes",
        choices=["carnes", "carnes-frias"],
        help="unidad cuya base se actualiza",
    )
    argumentos = parser.parse_args()

    configurar_logging(obtener_settings().entorno)
    desde = date.fromisoformat(argumentos.desde)
    hasta = date.fromisoformat(argumentos.hasta)

    fuente = FuenteFacturasSiesa(unidad=argumentos.unidad)
    try:
        with sesion_ambito(argumentos.unidad) as sesion:
            resumen = sincronizar_documentos_diarios(sesion, fuente, desde, hasta)
    finally:
        fuente.cerrar()

    print(f"Rango:               {resumen.desde} a {resumen.hasta}")
    print(f"Puntos reconocidos:  {resumen.puntos_reconocidos}")
    print(f"Filas guardadas:     {resumen.filas_guardadas}")
    if resumen.puntos_desconocidos:
        print(f"Códigos sin PDV:     {sorted(resumen.puntos_desconocidos)}")


if __name__ == "__main__":  # pragma: no cover
    main()
