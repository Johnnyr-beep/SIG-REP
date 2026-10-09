"""Precalentamiento periódico del snapshot de inventario por punto de venta."""

from __future__ import annotations

import asyncio
import threading

from app.core.config import obtener_settings
from app.core.logging import obtener_logger
from app.infrastructure.fuentes.inventario_siesa import (
    FuenteInventarioPdvSiesa,
    InventarioPdvCrudo,
)

logger = obtener_logger(__name__)

INTERVALO_MINUTOS = 5

_cache: InventarioPdvCrudo | None = None
_bloqueo_cache = threading.Lock()
_bloqueo_actualizacion = threading.Lock()


def _snapshot() -> InventarioPdvCrudo | None:
    with _bloqueo_cache:
        return _cache


def _descargar_y_guardar() -> InventarioPdvCrudo:
    global _cache
    with _bloqueo_actualizacion:
        fuente = FuenteInventarioPdvSiesa()
        try:
            inventario = fuente.leer()
        finally:
            fuente.cerrar()
        with _bloqueo_cache:
            _cache = inventario
        logger.info("inventario_pdv_precargado", filas=len(inventario.filas))
        return inventario


def obtener_inventario_pdv() -> InventarioPdvCrudo:
    """Devuelve el último snapshot; consulta SIESA solo si aún no hay uno."""
    inventario = _snapshot()
    if inventario is not None:
        return inventario
    return _descargar_y_guardar()


def limpiar_cache_inventario() -> None:
    """Vacía el snapshot en pruebas para aislar cada escenario."""
    global _cache
    with _bloqueo_cache:
        _cache = None


async def _precalentar_una_vez() -> None:
    try:
        await asyncio.to_thread(_descargar_y_guardar)
    except Exception:
        logger.exception("inventario_pdv_precarga_fallo")


async def _bucle() -> None:
    while True:
        await _precalentar_una_vez()
        await asyncio.sleep(INTERVALO_MINUTOS * 60)


def iniciar_precalentador_inventario() -> asyncio.Task[None] | None:
    """Arranca el refresco periódico solo si SIESA tiene credenciales."""
    if not obtener_settings().siesa_token.get_secret_value():
        logger.info("inventario_pdv_precargador_deshabilitado", motivo="sin_token_siesa")
        return None
    return asyncio.create_task(_bucle())
