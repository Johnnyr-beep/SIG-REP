"""Sincronización diaria de `numero_documentos_diarios`, en segundo plano.

Hasta ahora este dato solo se llenaba corriendo a mano
`python -m app.infrastructure.sincronizar_documentos` dentro del contenedor.
Este módulo hace lo mismo pero solo, arrancando un bucle en segundo plano
dentro del propio proceso de la API (`app/main.py` lo arranca en `ciclo_vida`):
sin cron del sistema operativo, sin acceso SSH al servidor —bloqueado desde el
incidente de seguridad— y sin secretos nuevos que configurar en Dokploy.

`SIGREP_WORKERS` puede ser mayor que 1: cada worker de Gunicorn arrancaría este
mismo bucle. Un advisory lock de Postgres (`pg_try_advisory_lock`) deja pasar
solo al primero que llega cada día; los demás se saltan ese turno sin error.
En SQLite (pruebas, desarrollo local sin Postgres) no hace falta el candado
porque ahí corre un único proceso.
"""

from __future__ import annotations

import asyncio
import zlib
from datetime import date, datetime, time, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.application.services.documentos_diarios_service import (
    ResumenDocumentos,
    sincronizar_documentos_diarios,
)
from app.core.config import obtener_settings
from app.core.db import UnidadDatos, sesion_ambito
from app.core.logging import obtener_logger
from app.infrastructure.fuentes.facturas_siesa import FuenteFacturasSiesa

logger = obtener_logger(__name__)

#: Número de documentos es un dato exclusivo de la instancia de Carnes: Carnes
#: Frías usa la pantalla de venta diaria de Agro (`VentaDiariaAgro`), que no
#: tiene esta columna, y Agropecuaria y Grupo Santacruz no traen esta fuente.
UNIDADES: tuple[UnidadDatos, ...] = ("carnes",)

#: Hoy y los 6 días anteriores: no solo "ayer", porque una factura corregida
#: o anulada un día después debe reflejarse sin esperar a que alguien vuelva a
#: correr el comando a mano.
DIAS_VENTANA = 7

#: Hora UTC a la que corre —el servidor no tiene zona horaria propia—.
HORA_EJECUCION = time(hour=7, minute=30)


def _segundos_hasta_proxima_ejecucion(ahora: datetime | None = None) -> float:
    ahora = ahora or datetime.utcnow()
    proxima = datetime.combine(ahora.date(), HORA_EJECUCION)
    if proxima <= ahora:
        proxima += timedelta(days=1)
    return (proxima - ahora).total_seconds()


def _tomar_turno(sesion: Session, unidad: UnidadDatos) -> bool:
    """`True` si a esta ejecución le toca sincronizar `unidad` hoy."""
    if sesion.get_bind().dialect.name != "postgresql":
        return True
    clave = zlib.crc32(f"sincronizar_documentos_diarios:{unidad}".encode())
    obtenido = sesion.execute(
        text("SELECT pg_try_advisory_lock(:clave)"), {"clave": clave}
    ).scalar()
    return bool(obtenido)


def _sincronizar_unidad(unidad: UnidadDatos, desde: date, hasta: date) -> ResumenDocumentos | None:
    fuente = FuenteFacturasSiesa(unidad=unidad)
    try:
        with sesion_ambito(unidad) as sesion:
            if not _tomar_turno(sesion, unidad):
                logger.info("documentos_diarios_turno_omitido", unidad=unidad)
                return None
            return sincronizar_documentos_diarios(sesion, fuente, desde, hasta)
    finally:
        fuente.cerrar()


async def _ejecutar_una_vez() -> None:
    hasta = date.today()
    desde = hasta - timedelta(days=DIAS_VENTANA - 1)
    for unidad in UNIDADES:
        try:
            resumen = await asyncio.to_thread(_sincronizar_unidad, unidad, desde, hasta)
        except Exception:
            logger.exception("documentos_diarios_fallo", unidad=unidad)
            continue
        if resumen is not None:
            logger.info(
                "documentos_diarios_sincronizados",
                unidad=unidad,
                desde=str(resumen.desde),
                hasta=str(resumen.hasta),
                filas_guardadas=resumen.filas_guardadas,
                puntos_desconocidos=sorted(resumen.puntos_desconocidos),
            )


async def _bucle() -> None:
    while True:
        await asyncio.sleep(_segundos_hasta_proxima_ejecucion())
        await _ejecutar_una_vez()


def iniciar_programador_documentos() -> asyncio.Task[None] | None:
    """Arranca el bucle diario; `None` si no hay `SIGREP_SIESA_TOKEN` configurado.

    Sin token no hay con qué llamar a SIESA —es el caso de un entorno local
    sin credenciales—, así que el bucle ni se crea en vez de fallar cada noche.
    """
    settings = obtener_settings()
    if not settings.siesa_token.get_secret_value():
        logger.info("documentos_diarios_programador_deshabilitado", motivo="sin_token_siesa")
        return None
    return asyncio.create_task(_bucle())
