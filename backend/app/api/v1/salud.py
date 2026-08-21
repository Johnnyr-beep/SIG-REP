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
    #: Unidad que sirve esta instancia: `todas` —el caso de hoy, carnes y
    #: agropecuaria sobre la misma base— o una sola cuando se lleve a su propio
    #: despliegue. Va en un endpoint **publico** a proposito: la pantalla de
    #: acceso necesita saber que marcas ofrecer antes de que nadie entre.
    unidad: str
    #: Las que de verdad se pueden mirar. El selector desactiva las que no estan
    #: aqui en lugar de dejar entrar a una pantalla sin datos detras: elegir una
    #: marca no puede hacer aparecer una unidad que esta instancia no sirve.
    unidades: list[str]
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
        return EstadoSalud(
            estado="degradado",
            unidad=settings.unidad,
            unidades=settings.unidades_disponibles,
            version=settings.version,
            base_datos="no disponible",
        )

    corrida = IngestaService(sesion).ultima_corrida()
    return EstadoSalud(
        estado="operativo",
        unidad=settings.unidad,
        unidades=settings.unidades_disponibles,
        version=settings.version,
        base_datos=estado_bd,
        ultima_ingesta=corrida.cuando if corrida else None,
    )
