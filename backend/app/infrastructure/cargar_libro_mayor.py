"""Carga el libro mayor contable (NDJSON, formato `Consolidado.json`) a la base
de una instancia financiera (Grupo Santacruz, Agroporcicola o Transantacruz).

Uso:

    python -m app.infrastructure.cargar_libro_mayor datos/Consolidado.json --unidad grupo-santacruz

Requiere `SIGREP_DB_URL_<UNIDAD>` configurada para la unidad elegida. Ejecutarlo
sin esa variable falla igual que pedir `url_de_unidad(unidad)` sin ella:
`ValueError` explícito, no una carga silenciosa en la base equivocada.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import cast

from app.application.services.financiero_ingesta_service import cargar_libro_mayor
from app.core.config import obtener_settings
from app.core.db import UnidadDatos, sesion_ambito
from app.core.logging import configurar_logging, obtener_logger

logger = obtener_logger(__name__)


def main() -> None:  # pragma: no cover - utilidad de línea de comandos
    parser = argparse.ArgumentParser(
        description="Carga el libro mayor de SIESA (NDJSON) al tablero financiero."
    )
    parser.add_argument("archivo", help="ruta al archivo NDJSON (una fila JSON por línea)")
    parser.add_argument(
        "--unidad",
        choices=["grupo-santacruz", "agroporcicola", "transantacruz"],
        default="grupo-santacruz",
        help="unidad financiera cuya base recibe la carga",
    )
    argumentos = parser.parse_args()

    configurar_logging(obtener_settings().entorno)
    ruta = Path(argumentos.archivo)
    if not ruta.is_file():
        raise SystemExit(f"No existe el archivo: {ruta}")

    print(f"Cargando {ruta} en la base de {argumentos.unidad}…")
    unidad = cast(UnidadDatos, argumentos.unidad)
    with sesion_ambito(unidad) as sesion:
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
