from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

from app.api.v1 import AnalistaDep, LecturaDep
from app.application.services.agro_tat_service import AgroTatService
from app.core.deps import SesionDep
from app.schemas.agro_tat import AgroTatIngestaSalida, AgroTatResumen

router = APIRouter(prefix="/agro/tat", tags=["Ventas TAT Agropecuaria"])


@router.get("", response_model=AgroTatResumen, summary="Ventas TAT por factura")
def listar(
    _: LecturaDep,
    sesion: SesionDep,
    fecha_inicio: date,
    fecha_fin: date,
    limit: int = Query(100, ge=1, le=5000),
    offset: int = Query(0, ge=0),
) -> AgroTatResumen:
    return AgroTatService(sesion).listar(fecha_inicio, fecha_fin, limit, offset)


@router.post("/ingesta", response_model=AgroTatIngestaSalida, summary="Ingerir ventas TAT")
def ingesta(
    datos: dict[str, date],
    _: AnalistaDep,
    sesion: SesionDep,
) -> AgroTatIngestaSalida:
    return AgroTatService(sesion).ingerir(datos["fecha_inicio"], datos["fecha_fin"])
