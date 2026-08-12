"""Endpoints de ingesta (`docs/API.md`, sección Ingesta).

El router y los esquemas están completos; la ejecución responde **501 Not
Implemented** hasta que el agente de ingesta construya la implementación sobre
el puerto `FuenteVenta` (§5). Las consultas de corridas y rechazos sí funcionan:
son lectura sobre modelos que ya existen.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile

from app.api.v1 import AnalistaDep, LecturaDep
from app.application.services.ingesta_service import IngestaService
from app.core.deps import SesionDep, leer_subida
from app.schemas.ingesta import CorridaSalida, RechazoSalida, SolicitudIngesta

router = APIRouter(prefix="/ingesta", tags=["Ingesta"])

#: El archivo de venta de nueve días pesa 18 MB; se admite hasta 60 MB para
#: cubrir un mes completo sin dejar la puerta abierta a una carga arbitraria.
MAX_BYTES_ARCHIVO = 60 * 1024 * 1024

#: Y hasta 800 MB una vez descomprimido: el XML de un libro de este tamaño se
#: expande mucho, pero no mil veces. Por encima de ahí no es un libro de venta,
#: es una bomba de descompresión.
MAX_DESCOMPRIMIDO_ARCHIVO = 800 * 1024 * 1024

EXTENSIONES_ARCHIVO = (".xlsx", ".xlsm")


@router.post("/ejecutar", response_model=CorridaSalida, summary="Ejecutar una carga de venta")
def ejecutar(datos: SolicitudIngesta, usuario: AnalistaDep, sesion: SesionDep) -> CorridaSalida:
    """RBAC: ANALISTA (y GERENTE). Pendiente de implementación (501)."""
    return IngestaService(sesion).ejecutar(datos.desde, datos.hasta, datos.fuente, usuario)


@router.post("/archivo", response_model=CorridaSalida, summary="Cargar venta desde archivo")
async def cargar_archivo(
    usuario: AnalistaDep,
    sesion: SesionDep,
    archivo: Annotated[UploadFile, File(description="Libro .xlsx con la hoja VENTA")],
) -> CorridaSalida:
    """RBAC: ANALISTA (y GERENTE).

    El archivo se valida antes de abrirlo: extensión, tamaño mientras se lee y
    lo que el ZIP declara al descomprimirse. `openpyxl` no ve un solo byte que
    no haya pasado por las tres.
    """
    contenido = await leer_subida(
        archivo,
        extensiones=EXTENSIONES_ARCHIVO,
        max_bytes=MAX_BYTES_ARCHIVO,
        max_descomprimido=MAX_DESCOMPRIMIDO_ARCHIVO,
    )
    return IngestaService(sesion).ingerir_archivo(
        contenido, archivo.filename or "venta.xlsx", usuario
    )


@router.get("/corridas", response_model=list[CorridaSalida], summary="Historial de corridas")
def listar_corridas(
    _: LecturaDep, sesion: SesionDep, limite: int = Query(default=50, ge=1, le=200)
) -> list[CorridaSalida]:
    """RBAC: cualquier rol autenticado.

    La corrida son contadores —leídas, aceptadas, rechazadas— y no lleva ni un
    dato de punto de venta, cliente o importe: responde «¿está cargado el mes?»,
    que es una pregunta legítima de cualquiera que consulte el reporte. No hay
    nada que filtrar por alcance aquí.
    """
    return IngestaService(sesion).listar_corridas(limite)


@router.get(
    "/corridas/{corrida_id}/rechazos",
    response_model=list[RechazoSalida],
    summary="Filas rechazadas de una corrida",
)
def listar_rechazos(corrida_id: int, _: AnalistaDep, sesion: SesionDep) -> list[RechazoSalida]:
    """RBAC: **ANALISTA (y GERENTE)**, no cualquier rol autenticado.

    Es la pantalla que responde «¿por qué no cuadra?» sin abrir la base, y para
    responderlo devuelve el **valor crudo de la fila rechazada**: NIT de
    cliente, importes, C.O., tal como venían en el archivo de SIESA.

    Esos valores no se pueden filtrar por alcance —`rechazos_ingesta` no tiene
    punto de venta, y no puede tenerlo: buena parte de los rechazos son
    justamente filas cuyo C.O. no se reconoció—. Sin filtro posible, el control
    que queda es el rol: lo ve quien opera la carga y tiene que corregirla, no
    quien consulta el reporte. Un JEFE_PDV que pidiera esta lista se llevaría
    filas de venta de puntos ajenos con su NIT y su importe.
    """
    return IngestaService(sesion).rechazos(corrida_id)
