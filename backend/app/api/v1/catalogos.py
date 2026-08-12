"""Endpoints de catálogos (`docs/API.md`, sección Catálogos)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import AnalistaDep, LecturaDep
from app.application.services.catalogos_service import CatalogosService
from app.core.deps import SesionDep
from app.schemas.catalogos import (
    CategoriaSalida,
    GrupoSalida,
    MapeoCategoriaEntrada,
    MapeoCategoriaSalida,
    PuntoVentaSalida,
    ZonaSalida,
)

router = APIRouter(prefix="/catalogos", tags=["Catálogos"])


@router.get("/grupos", response_model=list[GrupoSalida], summary="Grupos comerciales")
def listar_grupos(_: LecturaDep, sesion: SesionDep) -> list[GrupoSalida]:
    """RBAC: cualquier rol autenticado."""
    return CatalogosService(sesion).listar_grupos()


@router.get("/puntos-venta", response_model=list[PuntoVentaSalida], summary="Puntos de venta")
def listar_puntos_venta(
    _: LecturaDep, sesion: SesionDep, incluir_inactivos: bool = False
) -> list[PuntoVentaSalida]:
    """RBAC: cualquier rol autenticado. **Sin filtrar por alcance, a propósito.**

    Decisión revisada en la auditoría de autorización, no heredada:

    1. La respuesta es `{id, codigo_co, nombre, grupo, zona, activo,
       presupuestado}`. Ni un importe, ni una venta, ni un presupuesto. Es el
       organigrama comercial, y los 16 puntos de Grupo Santa Cruz no son un
       secreto para un jefe de punto de venta: los conoce por el rótulo de la
       calle.
    2. El frontend necesita el catálogo entero para **etiquetar** —resolver
       `"402"` → `MALAMBO` en los desplegables y en las cabeceras— y para saber
       que un código que no le devuelve el reporte existe, en lugar de pintar
       un hueco sin explicación.
    3. Lo que sí protege el alcance es la **cifra**: qué vendió y cuánto tenía
       presupuestado cada punto. Eso vive en `/reportes` y en `/presupuesto`, y
       los dos filtran.

    La regla que deja esta decisión válida hacia el futuro: si algún día este
    esquema crece con un dato de negocio —una meta, un responsable, una venta
    del mes—, deja de ser catálogo y pasa a filtrarse por alcance como el
    resto.
    """
    return CatalogosService(sesion).listar_puntos_venta(incluir_inactivos=incluir_inactivos)


@router.get("/categorias", response_model=list[CategoriaSalida], summary="Categorías")
def listar_categorias(_: LecturaDep, sesion: SesionDep) -> list[CategoriaSalida]:
    """RBAC: cualquier rol autenticado."""
    return CatalogosService(sesion).listar_categorias()


@router.get("/zonas", response_model=list[ZonaSalida], summary="Zonas de calendario")
def listar_zonas(_: LecturaDep, sesion: SesionDep) -> list[ZonaSalida]:
    """RBAC: cualquier rol autenticado."""
    return CatalogosService(sesion).listar_zonas()


@router.get(
    "/mapeo-categorias",
    response_model=list[MapeoCategoriaSalida],
    summary="Mapeo de categorías de SIESA",
)
def listar_mapeo(_: LecturaDep, sesion: SesionDep) -> list[MapeoCategoriaSalida]:
    """RBAC: cualquier rol autenticado."""
    return CatalogosService(sesion).listar_mapeo_categorias()


@router.post(
    "/mapeo-categorias",
    response_model=MapeoCategoriaSalida,
    summary="Crear o reclasificar un mapeo",
)
def guardar_mapeo(
    datos: MapeoCategoriaEntrada, _: AnalistaDep, sesion: SesionDep
) -> MapeoCategoriaSalida:
    """RBAC: ANALISTA (y GERENTE).

    Es el mecanismo por el que el negocio reclasifica una categoría nueva de
    SIESA sin esperar un despliegue (§3.1).
    """
    return CatalogosService(sesion).guardar_mapeo(datos.texto_siesa, datos.categoria)
