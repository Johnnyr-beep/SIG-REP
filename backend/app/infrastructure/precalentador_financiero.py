"""Precalentamiento periódico de la caché de estado financiero en vivo.

Medido: descargar el CSV de `estado-situacion-financiera` para la cía 4
(Carnes Santacruz, ~226.000 filas, ~60 MB) tarda **~56 segundos solo en la
red**, antes de parsear una sola línea. Un usuario que elige esa compañía en
el selector de "Resumen financiero" espera esa descarga en vivo, dentro de la
misma petición HTTP — y algún proxy intermedio (Cloudflare delante de este
dominio) corta la respuesta con 504 bastante antes de que la descarga termine.

La caché de `app.infrastructure.fuentes.financiero_siesa` (10 minutos de TTL)
ya evita repetir la descarga si alguien vuelve a pedir la misma compañía y año
poco después. Este módulo la deja **tibia de antemano**: un bucle en segundo
plano, con el mismo patrón que `programador_documentos.py`, que la recarga
cada `INTERVALO_MINUTOS` para las compañías con estado de resultados en vivo
—antes de que el TTL expire—, así la primera persona del día no paga la
descarga completa dentro de su propia petición.

`SIGREP_WORKERS` puede ser mayor que 1: cada worker de Gunicorn arranca su
propio bucle y calienta su propia caché en memoria, que es exactamente lo que
hace falta —las peticiones reales se reparten entre los mismos workers—, sin
necesitar un candado ni una caché compartida entre procesos.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.core.logging import obtener_logger
from app.infrastructure.fuentes.financiero_siesa import (
    ConfiguracionFinancieroSiesa,
    _filas_del_anio,
)

logger = obtener_logger(__name__)

#: Las mismas cinco compañías que acepta `/financiero/estado-resultados-vivo`
#: (ver `CIAS_EN_VIVO` en `app.api.v1.financiero`). Se repite aquí, no se
#: importa: este módulo no debe depender de la capa de API para arrancar.
CIAS_EN_VIVO: tuple[int, ...] = (3, 4, 6, 7, 8)

#: Menos que el TTL de la caché (10 minutos): si se recalienta a los mismos
#: 10 minutos exactos, una carrera entre el vencimiento y este bucle deja una
#: ventana en la que la caché ya expiró y nadie la ha vuelto a llenar.
INTERVALO_MINUTOS = 8


async def _precalentar_una_vez() -> None:
    from app.core.config import obtener_settings

    configuracion = ConfiguracionFinancieroSiesa.desde_settings(obtener_settings())
    anio = datetime.now(UTC).year
    for cia in CIAS_EN_VIVO:
        try:
            filas = await asyncio.to_thread(_filas_del_anio, cia, anio, configuracion, None)
        except Exception:
            logger.exception("financiero_en_vivo_precalentamiento_fallo", cia=cia, anio=anio)
            continue
        logger.info("financiero_en_vivo_precalentado", cia=cia, anio=anio, filas=len(filas))


async def _bucle() -> None:
    """Corre de inmediato al arrancar y después cada `INTERVALO_MINUTOS` minutos."""
    while True:
        await _precalentar_una_vez()
        await asyncio.sleep(INTERVALO_MINUTOS * 60)


def iniciar_precalentador_financiero_en_vivo() -> asyncio.Task[None] | None:
    """Arranca el bucle periódico; `None` si no hay `SIGREP_SIESA_TOKEN` configurado.

    Sin token no hay con qué llamar a SIESA —el caso de un entorno local sin
    credenciales—, así que el bucle ni se crea en vez de fallar cada vez.
    """
    from app.core.config import obtener_settings

    settings = obtener_settings()
    if not settings.siesa_token.get_secret_value():
        logger.info("financiero_en_vivo_precalentador_deshabilitado", motivo="sin_token_siesa")
        return None
    return asyncio.create_task(_bucle())
