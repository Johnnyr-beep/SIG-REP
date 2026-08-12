"""Logging estructurado (JSON en producción, legible en desarrollo).

Portado sin cambios desde GSC ONE: es código probado y el formato de log ya
está integrado con la operación.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

_CONFIGURADO = False


def configurar_logging(entorno: str = "local", nivel: str = "INFO") -> None:
    """Inicializa structlog. Idempotente."""
    global _CONFIGURADO
    if _CONFIGURADO:
        return

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=nivel)

    procesadores: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    procesadores.append(
        structlog.processors.JSONRenderer()
        if entorno == "produccion"
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=procesadores,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _CONFIGURADO = True


def obtener_logger(nombre: str) -> structlog.stdlib.BoundLogger:
    """Logger con nombre de módulo."""
    return structlog.get_logger(nombre)  # type: ignore[no-any-return]
