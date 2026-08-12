"""Sonda de salud (`GET /api/v1/salud`)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.application.services.ingesta_service import IngestaService
from app.core.config import obtener_settings
from app.core.deps import SesionDep

router = APIRouter(tags=["Sistema"])


class EstadoSalud(BaseModel):
    estado: str
    version: str
    base_datos: str
    ultima_ingesta: datetime | None = None


@router.get("/salud", response_model=EstadoSalud, summary="Estado del sistema")
def salud(sesion: SesionDep) -> EstadoSalud:
    """Público: es lo que consulta el balanceador y la pantalla de estado.

    Toca la base a propósito —una sonda que no la toca no dice nada útil— pero
    no revela ni el servidor ni el nombre de la base: un error de conexión
    responde «no disponible», no la cadena de conexión.
    """
    settings = obtener_settings()
    try:
        sesion.execute(text("SELECT 1"))
        estado_bd = "disponible"
    except Exception:
        return EstadoSalud(estado="degradado", version=settings.version, base_datos="no disponible")

    corrida = IngestaService(sesion).ultima_corrida()
    return EstadoSalud(
        estado="operativo",
        version=settings.version,
        base_datos=estado_bd,
        ultima_ingesta=corrida.cuando if corrida else None,
    )
