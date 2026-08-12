"""Punto de entrada de la API de SIGREP."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1 import auth as auth_api
from app.api.v1 import calendario as calendario_api
from app.api.v1 import catalogos as catalogos_api
from app.api.v1 import ingesta as ingesta_api
from app.api.v1 import presupuesto as presupuesto_api
from app.api.v1 import reportes as reportes_api
from app.api.v1 import salud as salud_api
from app.core.config import obtener_settings
from app.core.errors import registrar_manejadores
from app.core.logging import configurar_logging, obtener_logger
from app.schemas.common import DetalleError

settings = obtener_settings()
configurar_logging(settings.entorno)
logger = obtener_logger(__name__)


@asynccontextmanager
async def ciclo_vida(_: FastAPI) -> AsyncIterator[None]:
    """Arranque y apagado ordenado de la aplicación."""
    logger.info("aplicacion_iniciando", version=settings.version, entorno=settings.entorno)
    try:
        yield
    finally:
        logger.info("aplicacion_detenida")


DESCRIPCION = """
Sistema Gerencial de Reportes de Grupo Santa Cruz.

Reemplaza el libro de Excel de seguimiento de venta contra presupuesto por una
aplicación donde el presupuesto se parametriza una vez, la venta se ingiere
desde SIESA y el cumplimiento, la proyección y el semáforo se calculan solos,
**con las fórmulas escritas y visibles**.

**Frontera con SIESA**: SIESA es la fuente de verdad de la venta. SIGREP es la
capa de lectura gerencial: presupuesto, comparación y análisis.

Convenciones del contrato: los importes y cantidades viajan como `string`, los
porcentajes como fracción decimal (`"0.2885"` = 28.85 %) y todo indicador
indefinido viaja como `null` para pintarse «—», nunca como `0`.
"""

app = FastAPI(
    title=settings.nombre_app,
    version=settings.version,
    description=DESCRIPCION,
    lifespan=ciclo_vida,
    docs_url="/docs" if settings.docs_habilitados else None,
    redoc_url="/redoc" if settings.docs_habilitados else None,
    openapi_url="/openapi.json" if settings.docs_habilitados else None,
    responses={
        400: {"model": DetalleError},
        401: {"model": DetalleError},
        403: {"model": DetalleError},
        404: {"model": DetalleError},
        409: {"model": DetalleError},
        422: {"model": DetalleError},
        501: {"model": DetalleError},
    },
)

# ── Middleware ────────────────────────────────────────────────────────────────

if settings.es_produccion:
    # Evita Host header injection cuando hay un proxy inverso delante.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.hosts_efectivos)
    logger.info("hosts_permitidos", hosts=settings.hosts_efectivos)

# Un tablero con dieciséis puntos y ocho categorías son cientos de kilobytes de
# JSON; comprimirlo es la diferencia entre una pantalla que abre y una que se
# arrastra en la red de una sucursal.
app.add_middleware(GZipMiddleware, minimum_size=1024)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origenes,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)


@app.middleware("http")
async def contexto_peticion(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Correlaciona logs por petición y mide su duración."""
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(request_id=request_id, ruta=request.url.path)

    inicio = time.perf_counter()
    try:
        respuesta: Response = await call_next(request)
    finally:
        duracion_ms = (time.perf_counter() - inicio) * 1000
        structlog.contextvars.unbind_contextvars("request_id", "ruta")

    respuesta.headers["X-Request-ID"] = request_id
    respuesta.headers["X-Tiempo-Respuesta-ms"] = f"{duracion_ms:.1f}"

    # Cabeceras de endurecimiento (OWASP Secure Headers).
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    respuesta.headers["X-Frame-Options"] = "DENY"
    respuesta.headers["Referrer-Policy"] = "no-referrer"
    if settings.es_produccion:
        respuesta.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    logger.info(
        "peticion",
        metodo=request.method,
        ruta=request.url.path,
        estado=respuesta.status_code,
        duracion_ms=round(duracion_ms, 1),
    )
    return respuesta


registrar_manejadores(app)

# ── Rutas ─────────────────────────────────────────────────────────────────────

api = APIRouter(prefix=settings.api_prefix)
api.include_router(auth_api.router)
api.include_router(catalogos_api.router)
api.include_router(calendario_api.router)
api.include_router(presupuesto_api.router)
api.include_router(presupuesto_api.periodos_router)
api.include_router(reportes_api.router)
api.include_router(ingesta_api.router)
api.include_router(salud_api.router)

app.include_router(api)


@app.get("/listo", tags=["Sistema"], summary="Sonda de preparación")
def listo() -> dict[str, str]:
    """Sonda ligera para el balanceador, fuera del prefijo versionado."""
    return {"estado": "listo"}
