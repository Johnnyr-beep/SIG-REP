"""Carga el libro mayor contable (`Consolidado.json`) a la base de la
instancia Grupo Santacruz.

Uso:

    python -m app.infrastructure.cargar_libro_mayor datos/Consolidado.json

Requiere `SIGREP_DB_URL_GRUPO_SANTACRUZ` configurada — es la única base donde
tiene sentido este dato (§ tablero financiero consolidado). Ejecutarlo contra
otra unidad fallaría igual que pedir `url_de_unidad("grupo-santacruz")` sin esa
variable: `ValueError` explícito, no una carga silenciosa en la base
equivocada.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.application.services.financiero_ingesta_service import cargar_libro_mayor
from app.core.config import obtener_settings
from app.core.db import sesion_ambito
from app.core.logging import configurar_logging, obtener_logger

logger = obtener_logger(__name__)


def main() -> None:  # pragma: no cover - utilidad de línea de comandos
    parser = argparse.ArgumentParser(
        description="Carga el libro mayor de SIESA (NDJSON) al tablero financiero."
    )
    parser.add_argument("archivo", help="ruta al archivo NDJSON (una fila JSON por línea)")
    argumentos = parser.parse_args()

    configurar_logging(obtener_settings().entorno)
    ruta = Path(argumentos.archivo)
    if not ruta.is_file():
        raise SystemExit(f"No existe el archivo: {ruta}")

    print(f"Cargando {ruta} en la base de grupo-santacruz…")
    with sesion_ambito("grupo-santacruz") as sesion:
        resumen = cargar_libro_mayor(sesion, ruta)

    print(f"Filas leídas:    {resumen.filas_leidas}")
    print(f"Aceptadas:       {resumen.aceptadas}")
    print(f"Rechazadas:      {resumen.rechazadas}")
    print(f"Compañías:       {sorted(resumen.cias)}")
    print(f"Períodos:        {sorted(resumen.periodos)}")
    if resumen.rechazos:
        print("\nPrimeros rechazos:")
        for rechazo in resumen.rechazos[:20]:
            print(f"  fila {rechazo.fila}: {rechazo.motivo}")


if __name__ == "__main__":  # pragma: no cover
    main()
