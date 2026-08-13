"""Endpoints de presupuesto y períodos (`docs/API.md`, sección Presupuesto).

El alcance por punto de venta se aplica **aquí**, en la frontera, igual que en
`reportes.py`: la cifra de presupuesto de un punto es tan sensible entre
responsables como la de venta —es la vara con la que se les mide— y el rol
JEFE_PDV solo puede ver la de los suyos (§8.4).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Query, UploadFile

from app.api.v1 import AnalistaDep, GerenteDep, LecturaDep
from app.application.services.presupuesto_service import PresupuestoService
from app.core.deps import SesionDep, alcance_escritura, alcance_puntos_venta, leer_subida
from app.schemas.presupuesto import (
    HistorialSalida,
    PeriodoSalida,
    PresupuestoEntrada,
    PresupuestoSalida,
    ResultadoCargaMasiva,
)

router = APIRouter(prefix="/presupuesto", tags=["Presupuesto"])
periodos_router = APIRouter(prefix="/periodos", tags=["Presupuesto"])

PeriodoQuery = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", examples=["2026-08"])

#: Tope del archivo de carga masiva.
#:
#: El presupuesto de un mes son 128 filas, pero **no llega en un archivo de 128
#: filas**: el negocio sube el mismo libro que usa para todo, donde la hoja
#: `CUMPLIMIENTO PPTO` convive con las 131 819 filas de la hoja `VENTA`. Ese
#: libro pesa 18 MB, de modo que un tope de 5 MB rechazaba precisamente el
#: archivo real —comprobado contra la base: «El archivo supera el tamaño máximo
#: admitido (5 MB)»—. Se alinea con el de la ingesta de venta, que ya cubre este
#: caso.
MAX_BYTES_CARGA = 60 * 1024 * 1024

#: Tope de lo que ese archivo puede declarar al descomprimirse. Un `.xlsx` es
#: un ZIP: sin este límite, la subida admitida puede ser gigabytes en memoria.
MAX_DESCOMPRIMIDO_CARGA = 800 * 1024 * 1024

EXTENSIONES_CARGA = (".xlsx", ".xlsm", ".csv")


@router.get("", response_model=list[PresupuestoSalida], summary="Presupuesto del período")
def listar(
    usuario: LecturaDep,
    sesion: SesionDep,
    periodo: str = PeriodoQuery,
    punto_venta: str | None = None,
) -> list[PresupuestoSalida]:
    """RBAC: cualquier rol autenticado; JEFE_PDV solo ve sus puntos."""
    return PresupuestoService(sesion).listar(
        periodo, punto_venta, alcance=alcance_puntos_venta(usuario)
    )


@router.put("", response_model=PresupuestoSalida, summary="Fijar presupuesto de una celda")
def guardar(
    datos: PresupuestoEntrada, usuario: AnalistaDep, sesion: SesionDep
) -> PresupuestoSalida:
    """RBAC: ANALISTA (y GERENTE), y solo sobre los puntos de su alcance.

    Falla con 409 si el período está cerrado (§7). El `motivo` queda en el
    historial junto al autor y la fecha.
    """
    return PresupuestoService(sesion).guardar(
        codigo_periodo=datos.periodo,
        punto_venta_id=datos.punto_venta_id,
        categoria_id=datos.categoria_id,
        monto=datos.monto,
        kilos=datos.kilos,
        motivo=datos.motivo,
        usuario=usuario,
        alcance=alcance_escritura(usuario),
    )


@router.post(
    "/carga-masiva", response_model=ResultadoCargaMasiva, summary="Cargar presupuesto desde archivo"
)
async def carga_masiva(
    usuario: AnalistaDep,
    sesion: SesionDep,
    archivo: Annotated[UploadFile, File(description="Archivo .xlsx o .csv")],
    periodo: Annotated[str, Form(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")],
    motivo: Annotated[str, Form(min_length=5, max_length=400)] = "Carga masiva de presupuesto",
) -> ResultadoCargaMasiva:
    """RBAC: ANALISTA (y GERENTE), y solo sobre los puntos de su alcance.

    Devuelve lo aceptado y el detalle de lo rechazado con su número de fila.
    Una fila mala no aborta la carga; una fila fuera del alcance de quien carga
    tampoco, pero se rechaza con su motivo.

    El archivo se valida antes de abrirlo: extensión, tamaño mientras se lee y
    —por ser el `.xlsx` un ZIP— lo que declara al descomprimirse.
    """
    contenido = await leer_subida(
        archivo,
        extensiones=EXTENSIONES_CARGA,
        max_bytes=MAX_BYTES_CARGA,
        max_descomprimido=MAX_DESCOMPRIMIDO_CARGA,
    )

    return PresupuestoService(sesion).cargar_masivo(
        contenido,
        archivo.filename or "presupuesto.xlsx",
        codigo_periodo=periodo,
        motivo=motivo,
        usuario=usuario,
        alcance=alcance_escritura(usuario),
    )


@router.get("/historial", response_model=list[HistorialSalida], summary="Historial de cambios")
def historial(
    usuario: LecturaDep,
    sesion: SesionDep,
    periodo: str | None = None,
    punto_venta: str | None = None,
) -> list[HistorialSalida]:
    """RBAC: cualquier rol autenticado; JEFE_PDV solo ve sus puntos.

    El rastro de cambios es auditoría, pero lleva los mismos importes que el
    presupuesto —el anterior y el nuevo—, así que se filtra igual: dejarlo
    abierto sería reabrir por la puerta de al lado lo que se acaba de cerrar.
    """
    return PresupuestoService(sesion).historial(
        periodo, punto_venta, alcance=alcance_puntos_venta(usuario)
    )


@periodos_router.get("", response_model=list[PeriodoSalida], summary="Períodos y su estado")
def listar_periodos(_: LecturaDep, sesion: SesionDep) -> list[PeriodoSalida]:
    """RBAC: cualquier rol autenticado."""
    return PresupuestoService(sesion).listar_periodos()


@periodos_router.post(
    "/{periodo}/cerrar", response_model=PeriodoSalida, summary="Cerrar un período"
)
def cerrar_periodo(periodo: str, usuario: GerenteDep, sesion: SesionDep) -> PeriodoSalida:
    """RBAC: **solo GERENTE**.

    Cerrar congela el presupuesto del mes. Es una decisión de gerencia, no una
    tarea de operación, y por eso no la comparte con ANALISTA.
    """
    return PresupuestoService(sesion).cerrar_periodo(periodo, usuario)
