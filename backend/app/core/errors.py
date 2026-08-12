"""Excepciones de dominio y su traducción a respuestas HTTP.

El dominio no conoce HTTP: lanza errores con significado de negocio y la capa
API los traduce. Así las reglas se pueden probar sin levantar un servidor.

Portado de GSC ONE con una diferencia deliberada: el cuerpo del error sigue el
contrato de `docs/API.md` —`{"detalle": ..., "codigo": ...}`— en lugar del
`{"error": {...}}` de GSC ONE. Ver la nota al final de `docs/API.md`.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.config import obtener_settings
from app.core.logging import obtener_logger

logger = obtener_logger(__name__)

#: Starlette renombró la constante 422 entre versiones; se fija el literal para
#: no depender de cuál de los dos nombres exista en el entorno instalado.
HTTP_422_CONTENIDO_NO_PROCESABLE = 422


class ErrorSigrep(Exception):
    """Raíz de todos los errores esperados de la plataforma."""

    codigo: str = "error_interno"
    http_status: int = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(self, mensaje: str, *, detalles: dict[str, Any] | None = None) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.detalles = detalles or {}


class ErrorValidacion(ErrorSigrep):
    codigo = "validacion"
    http_status = HTTP_422_CONTENIDO_NO_PROCESABLE


class ErrorNoEncontrado(ErrorSigrep):
    codigo = "no_encontrado"
    http_status = status.HTTP_404_NOT_FOUND


class ErrorConflicto(ErrorSigrep):
    """El estado actual del recurso impide la operación."""

    codigo = "conflicto"
    http_status = status.HTTP_409_CONFLICT


class ErrorAutenticacion(ErrorSigrep):
    codigo = "no_autenticado"
    http_status = status.HTTP_401_UNAUTHORIZED


class ErrorAutorizacion(ErrorSigrep):
    codigo = "no_autorizado"
    http_status = status.HTTP_403_FORBIDDEN


class ErrorReglaNegocio(ErrorConflicto):
    """Una guarda de negocio bloqueó la operación.

    El caso emblemático en SIGREP: tocar el presupuesto de un período cerrado.
    """

    codigo = "regla_negocio"


class ErrorPeriodoCerrado(ErrorReglaNegocio):
    """Un período cerrado no admite cambios de presupuesto (§7)."""

    codigo = "periodo_cerrado"


def _cuerpo(codigo: str, detalle: str, detalles: dict[str, Any] | None = None) -> dict[str, Any]:
    """Cuerpo de error uniforme, según el contrato de `docs/API.md`."""
    return {"detalle": detalle, "codigo": codigo, "detalles": detalles or {}}


def registrar_manejadores(app: FastAPI) -> None:
    """Registra los manejadores de excepción de la aplicación."""

    @app.exception_handler(ErrorSigrep)
    async def _dominio(_: Request, exc: ErrorSigrep) -> JSONResponse:
        if exc.http_status >= 500:
            logger.error("error_dominio", codigo=exc.codigo, mensaje=exc.mensaje)
        else:
            logger.info("error_dominio", codigo=exc.codigo, mensaje=exc.mensaje)
        return JSONResponse(
            status_code=exc.http_status,
            content=_cuerpo(exc.codigo, exc.mensaje, exc.detalles),
        )

    @app.exception_handler(RequestValidationError)
    async def _validacion(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=HTTP_422_CONTENIDO_NO_PROCESABLE,
            content=_cuerpo(
                "validacion",
                "Los datos enviados no son válidos.",
                {"campos": _serializar_errores(exc)},
            ),
        )

    @app.exception_handler(IntegrityError)
    async def _integridad(_: Request, exc: IntegrityError) -> JSONResponse:
        logger.warning("violacion_integridad", detalle=str(exc.orig))
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_cuerpo(
                "conflicto",
                "La operación viola una restricción de integridad de datos.",
            ),
        )

    @app.exception_handler(SQLAlchemyError)
    async def _sql(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.exception("error_base_datos", tipo=type(exc).__name__)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=_cuerpo("base_datos", "Servicio de datos no disponible."),
        )

    @app.exception_handler(NotImplementedError)
    async def _no_implementado(_: Request, exc: NotImplementedError) -> JSONResponse:
        # La ingesta declara su contrato pero todavía no tiene implementación
        # (§5). Un 501 explícito es más honesto que un 500 anónimo.
        return JSONResponse(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            content=_cuerpo("no_implementado", str(exc) or "Funcionalidad no implementada."),
        )

    @app.exception_handler(Exception)
    async def _inesperado(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("error_no_controlado", tipo=type(exc).__name__)
        # Nunca se filtra la traza al cliente en producción (OWASP A09).
        detalle = (
            {"excepcion": f"{type(exc).__name__}: {exc}"}
            if not obtener_settings().es_produccion
            else {}
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_cuerpo("error_interno", "Ocurrió un error inesperado.", detalle),
        )


def _serializar_errores(exc: RequestValidationError) -> list[dict[str, Any]]:
    """Deja los errores de Pydantic en algo serializable a JSON.

    `errors()` puede incluir el valor de entrada tal cual (bytes de un archivo,
    por ejemplo), que `JSONResponse` no sabe codificar.
    """
    limpios: list[dict[str, Any]] = []
    for error in exc.errors():
        limpios.append(
            {
                "campo": ".".join(str(parte) for parte in error.get("loc", ())),
                "mensaje": error.get("msg", ""),
                "tipo": error.get("type", ""),
            }
        )
    return limpios
