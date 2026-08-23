"""Endpoints de la unidad **Agropecuaria**.

Es un negocio distinto del de carnes y por eso vive bajo su propio prefijo, con
sus propios servicios y su propio esquema. Lo que si comparte es el dominio de
indicadores: cumplimiento, ideal, proyeccion, semaforo y margen ponderado son
las mismas formulas de la seccion 4, ya probadas, y reescribirlas aqui seria
empezar a divergir desde el primer dia.

Sobre el presupuesto y su regla mas importante: se fija en **cuatro
descomposiciones del mismo total** —vendedor, centro, especie y tipo comercial—
y por eso **no existe ningun endpoint que devuelva «el presupuesto» sin decir de
que dimension**. Sumar dos de ellas daria el doble de la meta, asi que la API no
ofrece esa forma. Quien quiera el total de la compania elige una dimension, que
es justo la operacion correcta. El endpoint de cuadre compara las cuatro y
publica la diferencia cuando no coinciden: un descuadre entre dimensiones es un
error de captura y se hace visible en lugar de repararlo por cuenta propia.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile

from app.api.v1 import AnalistaDep, GerenteDep, LecturaDep
from app.application.services import agro_exportacion_service
from app.application.services.agro_calendario_service import AgroCalendarioService
from app.application.services.agro_ingesta_service import AgroIngestaService
from app.application.services.agro_presupuesto_service import AgroPresupuestoService
from app.application.services.agro_reportes_service import AgroReportesService, FiltrosAgro
from app.application.services.inteligencia_comercial_service import InteligenciaComercialService
from app.core.deps import SesionDep, leer_subida
from app.domain.enums import Medida
from app.infrastructure.models.agro_vocabulario import (
    DimensionPresupuesto,
    EjeCruce,
    EjeResumen,
    TipoDimension,
)
from app.schemas.agro import (
    CalendarioAgroEntrada,
    CalendarioAgroSalida,
    CorridaAgroSalida,
    CuadrePresupuestoSalida,
    HistorialAgroSalida,
    MiembroDimensionSalida,
    PresupuestoAgroEntrada,
    PresupuestoAgroSalida,
    PresupuestoDimensionSalida,
    RechazoAgroSalida,
    RespuestaCruceAgro,
    RespuestaResumenAgro,
    RespuestaVentaDiariaAgro,
    ResultadoCargaAgro,
)
from app.schemas.inteligencia import RespuestaInteligencia

TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

router = APIRouter(prefix="/agro", tags=["Agropecuaria"])

PeriodoQuery = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", examples=["2026-08"])

#: Mismos topes que la carga de presupuesto de carnes: el negocio sube el libro
#: entero, no una hoja recortada.
MAX_BYTES_CARGA = 60 * 1024 * 1024
MAX_DESCOMPRIMIDO_CARGA = 800 * 1024 * 1024
EXTENSIONES_CARGA = (".xlsx", ".xlsm", ".csv")


def _centros(valor: str | None) -> tuple[str, ...] | None:
    """Centros separados por coma. Igual que en carnes: estrecha, no ensancha.

    Vacio equivale a no filtrar: una barra que se limpia no pide el centro de
    codigo vacio.
    """
    if valor is None:
        return None
    codigos = tuple(dict.fromkeys(p.strip() for p in valor.split(",") if p.strip()))
    return codigos or None


def _eje[E: StrEnum](enumerado: type[E], valor: str | None, por_defecto: E) -> E:
    """Valida el eje contra **su** enumerado y da un 404 con su motivo si no es.

    Sin esto, pedir el cruce vendedor-cliente al resumen levantaria un
    `ValueError` dentro del servicio y saldria como 500: un error del
    servidor para lo que es un parametro mal escrito.
    """
    if valor is None:
        return por_defecto
    try:
        return enumerado(valor)
    except ValueError:
        from app.core.errors import ErrorNoEncontrado

        opciones = ", ".join(miembro.value for miembro in enumerado)
        raise ErrorNoEncontrado(f"Eje {valor!r} no valido. Opciones: {opciones}.") from None


def _filtros(
    periodo: str,
    hasta: date | None,
    desde: date | None,
    centro: str | None,
    medida: Medida,
) -> FiltrosAgro:
    return FiltrosAgro(
        periodo=periodo,
        hasta=hasta,
        desde=desde,
        centros=_centros(centro),
        medida=medida,
    )


# ── Reportes ──────────────────────────────────────────────────────────────────


@router.get("/resumen", response_model=RespuestaResumenAgro, summary="Venta por un eje")
def resumen(
    _: LecturaDep,
    sesion: SesionDep,
    por: EjeResumen,
    periodo: str = PeriodoQuery,
    hasta: date | None = None,
    desde: date | None = None,
    centro: str | None = None,
    medida: Medida = Medida.VALOR,
) -> RespuestaResumenAgro:
    """Venta, kilos y margen agrupados por centro, especie, vendedor, cliente...

    Cuando el eje coincide con una dimension presupuestada, la respuesta trae
    ademas cumplimiento, ideal, proyeccion y semaforo.
    """
    return AgroReportesService(sesion).resumen(_filtros(periodo, hasta, desde, centro, medida), por)


@router.get("/cruce", response_model=RespuestaCruceAgro, summary="Vendedor x cliente [x producto]")
def cruce(
    _: LecturaDep,
    sesion: SesionDep,
    por: EjeCruce,
    periodo: str = PeriodoQuery,
    hasta: date | None = None,
    desde: date | None = None,
    centro: str | None = None,
    medida: Medida = Medida.VALOR,
) -> RespuestaCruceAgro:
    return AgroReportesService(sesion).cruce(_filtros(periodo, hasta, desde, centro, medida), por)


@router.get("/venta-diaria", response_model=RespuestaVentaDiariaAgro, summary="Venta dia por dia")
def venta_diaria(
    _: LecturaDep,
    sesion: SesionDep,
    periodo: str = PeriodoQuery,
    hasta: date | None = None,
    desde: date | None = None,
    centro: str | None = None,
    medida: Medida = Medida.VALOR,
) -> RespuestaVentaDiariaAgro:
    return AgroReportesService(sesion).venta_diaria(_filtros(periodo, hasta, desde, centro, medida))


@router.get(
    "/exportar/{reporte}",
    summary="Exportar un reporte de agropecuaria a Excel",
    response_class=Response,
    responses={200: {"content": {TIPO_XLSX: {}}, "description": "Libro .xlsx"}},
)
def exportar(
    reporte: Annotated[str, "resumen | cruce | venta-diaria"],
    _: LecturaDep,
    sesion: SesionDep,
    periodo: str = PeriodoQuery,
    hasta: date | None = None,
    desde: date | None = None,
    centro: str | None = None,
    medida: Medida = Medida.VALOR,
    por: str | None = None,
) -> Response:
    """Exporta **lo mismo que muestra la pantalla**, con los mismos filtros.

    La ruta lleva el reporte al final —`/agro/exportar/resumen`— y no al
    principio como en carnes: un `/agro/{reporte}/exportar` capturaria tambien
    `/agro/presupuesto/cuadre` y `/agro/ingesta/corridas`, que ya existen y que
    FastAPI resolveria contra el comodin segun el orden de registro. Aqui el
    prefijo fijo no se puede confundir con nada.

    `por` es el eje —los valores de `EjeResumen` o de `EjeCruce` segun el
    reporte—. Se recibe como texto y se valida contra el enumerado que
    corresponde, para que un eje de cruce pedido al resumen sea un 404 con su
    motivo y no un 500.
    """
    from app.core.errors import ErrorNoEncontrado

    filtros = _filtros(periodo, hasta, desde, centro, medida)
    servicio = AgroReportesService(sesion)

    if reporte == "resumen":
        contenido = agro_exportacion_service.exportar_resumen(
            servicio.resumen(filtros, _eje(EjeResumen, por, EjeResumen.CENTRO_OPERACION))
        )
    elif reporte == "cruce":
        contenido = agro_exportacion_service.exportar_cruce(
            servicio.cruce(filtros, _eje(EjeCruce, por, EjeCruce.VENDEDOR_CLIENTE))
        )
    elif reporte == "venta-diaria":
        contenido = agro_exportacion_service.exportar_venta_diaria(servicio.venta_diaria(filtros))
    else:
        raise ErrorNoEncontrado(f"No existe el reporte {reporte!r} en agropecuaria.")

    sufijo = f"-{por}" if por else ""
    nombre = f"sigrep-agro-{reporte}{sufijo}-{periodo}.xlsx"
    return Response(
        content=contenido,
        media_type=TIPO_XLSX,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


# ── Presupuesto ───────────────────────────────────────────────────────────────


@router.get(
    "/presupuesto",
    response_model=list[PresupuestoDimensionSalida],
    summary="Presupuesto agrupado por dimension",
)
def presupuesto(
    _: LecturaDep,
    sesion: SesionDep,
    periodo: str = PeriodoQuery,
    dimension: DimensionPresupuesto | None = None,
) -> list[PresupuestoDimensionSalida]:
    """Devuelve **una entrada por dimension, cada una con su propio total**.

    Y no hay ningun total global, que es lo que impide el error de fondo: las
    cuatro descomposiciones describen el mismo dinero, asi que sumarlas daria
    cuatro veces la meta. Una pantalla que quiera el total de la compania elige
    una dimension, que es justo la operacion correcta.
    """
    return AgroPresupuestoService(sesion).listar(periodo, dimension)


@router.get(
    "/presupuesto/cuadre",
    response_model=CuadrePresupuestoSalida,
    summary="Cuadran las cuatro dimensiones entre si?",
)
def cuadre(
    _: LecturaDep, sesion: SesionDep, periodo: str = PeriodoQuery
) -> CuadrePresupuestoSalida:
    """Compara los cuatro totales y publica la diferencia. No la corrige."""
    return AgroPresupuestoService(sesion).cuadre_salida(periodo)


@router.put("/presupuesto", response_model=PresupuestoAgroSalida, summary="Fijar una meta")
def guardar_presupuesto(
    datos: PresupuestoAgroEntrada, usuario: AnalistaDep, sesion: SesionDep
) -> PresupuestoAgroSalida:
    return AgroPresupuestoService(sesion).guardar(
        codigo_periodo=datos.periodo,
        dimension=datos.dimension,
        clave=datos.clave,
        monto=datos.monto,
        kilos=datos.kilos,
        motivo=datos.motivo,
        usuario=usuario,
    )


@router.post(
    "/presupuesto/carga-masiva",
    response_model=ResultadoCargaAgro,
    summary="Carga masiva del presupuesto",
)
async def carga_masiva(
    usuario: AnalistaDep,
    sesion: SesionDep,
    archivo: Annotated[UploadFile, File(description="Archivo .xlsx o .csv")],
    periodo: Annotated[str, Form(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")],
    motivo: Annotated[str, Form(min_length=5, max_length=400)] = "Carga masiva de presupuesto",
) -> ResultadoCargaAgro:
    """El archivo trae una columna `dimension` por fila: las cuatro en una carga."""
    contenido = await leer_subida(
        archivo,
        extensiones=EXTENSIONES_CARGA,
        max_bytes=MAX_BYTES_CARGA,
        max_descomprimido=MAX_DESCOMPRIMIDO_CARGA,
    )
    return AgroPresupuestoService(sesion).cargar_masivo(
        contenido,
        archivo.filename or "presupuesto.xlsx",
        codigo_periodo=periodo,
        motivo=motivo,
        usuario=usuario,
    )


@router.get(
    "/presupuesto/historial",
    response_model=list[HistorialAgroSalida],
    summary="Historial de cambios",
)
def historial(
    _: LecturaDep,
    sesion: SesionDep,
    periodo: str | None = None,
    dimension: DimensionPresupuesto | None = None,
) -> list[HistorialAgroSalida]:
    return AgroPresupuestoService(sesion).historial(periodo, dimension)


# ── Catalogo ──────────────────────────────────────────────────────────────────


@router.get(
    "/dimensiones",
    response_model=list[MiembroDimensionSalida],
    summary="Miembros de una dimension",
)
def dimensiones(
    _: LecturaDep, sesion: SesionDep, tipo: TipoDimension
) -> list[MiembroDimensionSalida]:
    """Los miembros que existen en una dimension, para poder elegir uno.

    Lo consume la pantalla de presupuesto: fijar una meta a mano exige saber a
    quien, y la clave es la del origen —la cedula del vendedor, el `CO_Id` del
    centro—, no algo que se pueda teclear de memoria. Sin esta lista, la unica
    forma de capturar el presupuesto era subir un archivo.

    **El catalogo lo crea la ingesta**, no esta ruta. Si viene vacio no es un
    fallo: es que todavia no se ha cargado venta de la que deducirlo.
    """
    return AgroPresupuestoService(sesion).miembros(tipo)


# ── Calendario ────────────────────────────────────────────────────────────────


@router.get("/calendario", response_model=list[CalendarioAgroSalida], summary="Dias por centro")
def calendario(
    _: LecturaDep, sesion: SesionDep, periodo: str = PeriodoQuery, hasta: date | None = None
) -> list[CalendarioAgroSalida]:
    return AgroCalendarioService(sesion).listar(periodo, hasta)


@router.get(
    "/inteligencia",
    response_model=RespuestaInteligencia,
    summary="Alertas y oportunidades comerciales",
)
def inteligencia(
    _: LecturaDep, sesion: SesionDep, periodo: str = PeriodoQuery
) -> RespuestaInteligencia:
    return InteligenciaComercialService(sesion).analizar(periodo)


@router.put(
    "/calendario/{codigo_centro}", response_model=CalendarioAgroSalida, summary="Fijar dias"
)
def actualizar_calendario(
    codigo_centro: str,
    datos: CalendarioAgroEntrada,
    usuario: AnalistaDep,
    sesion: SesionDep,
    periodo: str = PeriodoQuery,
) -> CalendarioAgroSalida:
    return AgroCalendarioService(sesion).actualizar(
        codigo_centro,
        periodo,
        datos.dias_habiles,
        datos.dias_trabajados,
        usuario_id=usuario.id,
    )


# ── Ingesta ───────────────────────────────────────────────────────────────────


@router.post("/ingesta/ejecutar", response_model=CorridaAgroSalida, summary="Cargar desde SIESA")
def ingerir(usuario: AnalistaDep, sesion: SesionDep, desde: date, hasta: date) -> CorridaAgroSalida:
    """Reprocesar un rango lo reemplaza; no duplica."""
    return AgroIngestaService(sesion).ejecutar(desde, hasta, usuario=usuario)


@router.get("/ingesta/corridas", response_model=list[CorridaAgroSalida], summary="Corridas")
def corridas(_: LecturaDep, sesion: SesionDep, limite: int = 50) -> list[CorridaAgroSalida]:
    return AgroIngestaService(sesion).listar_corridas(limite)


@router.get(
    "/ingesta/corridas/{corrida_id}/rechazos",
    response_model=list[RechazoAgroSalida],
    summary="Filas rechazadas y su motivo",
)
def rechazos(usuario: GerenteDep, sesion: SesionDep, corrida_id: int) -> list[RechazoAgroSalida]:
    """Rol restringido: los rechazos llevan valores crudos de filas reales."""
    return AgroIngestaService(sesion).rechazos(corrida_id)
