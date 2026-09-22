"""Endpoints del tablero financiero consolidado — instancia Grupo Santacruz.

Vive bajo su propio prefijo, con su propio servicio y su propio esquema,
igual que Agropecuaria (`app.api.v1.agro`): es un dominio distinto —libro
mayor contable, no venta comercial— y comparte solo el patrón de RBAC y de
"parametros_calculo" del resto de reportes, no las tablas ni las fórmulas.

El aislamiento por compañía **no lo hace este router**: lo hace la conexión.
`SesionDep` ya resuelve la base de la unidad que viaja en el token
(`app.core.db.obtener_sesion_de`), así que un token que no sea de
`grupo-santacruz` nunca llega a ver `movimientos_contables` porque no está
conectado a esa base.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.application.services.financiero_reportes_service import (
    FiltrosFinanciero,
    FinancieroReportesService,
    estado_resultados_en_vivo,
)
from app.core.deps import PERMISO_CONSULTAR_FINANCIERO, SesionDep, exigir_permiso_consulta
from app.core.errors import ErrorValidacion
from app.domain.financiero import etiqueta_clase
from app.infrastructure.fuentes.financiero_siesa import (
    detalle_cuentas_en_vivo,
    situacion_financiera_en_vivo,
)
from app.infrastructure.models.usuario import Usuario
from app.schemas.financiero import (
    FilaBalanceComprobacion,
    FilaCartera,
    FilaDetalleCuenta,
    FilaDetalleCuentaEnVivo,
    FilaSituacionFinancieraEnVivo,
    ParametrosCalculoEnVivo,
    ParametrosCalculoFinanciero,
    RespuestaBalanceComprobacion,
    RespuestaBalanceGeneral,
    RespuestaCartera,
    RespuestaDetalleCuentas,
    RespuestaDetalleCuentasEnVivo,
    RespuestaEstadoResultados,
    RespuestaEstadoResultadosEnVivo,
    RespuestaIndicadoresFinancieros,
    RespuestaSituacionFinancieraEnVivo,
)

router = APIRouter(prefix="/financiero", tags=["Financiero"])

#: Compañías con identidad confirmada para el estado de resultados en vivo.
#: Ver `docs/GRUPO_SANTACRUZ.md`: las seis unidades del grupo, de las cuales
#: estas cinco ya tienen movimientos en la API de consulta.
CIAS_EN_VIVO: dict[int, str] = {
    3: "Agropecuaria Santacruz",
    4: "Carnes Santacruz",
    6: "Cristian Serrano",
    7: "Serueda",
    8: "Inversiones Serrano Millán",
}

PeriodoQuery = Query(
    pattern=r"^\d{6}$",
    examples=["202607"],
    description="Año y mes contable AAAAMM, tal como lo entrega SIESA.",
)
CiaQuery = Query(default=None, description="Compañía; sin ella se suman todas las cargadas.")

#: Igual que el resto de reportes: RBAC declarado endpoint por endpoint,
#: nunca heredado por prefijo (ver `app.api.v1.__init__`).
UsuarioFinancieroDep = Annotated[
    Usuario, Depends(exigir_permiso_consulta(PERMISO_CONSULTAR_FINANCIERO))
]


def _parametros(periodo: str, cia: int | None) -> ParametrosCalculoFinanciero:
    return ParametrosCalculoFinanciero(periodo=periodo, cia=cia)


@router.get(
    "/balance-comprobacion",
    response_model=RespuestaBalanceComprobacion,
    summary="Balance de comprobación",
)
def balance_comprobacion(
    usuario: UsuarioFinancieroDep,
    sesion: SesionDep,
    periodo: str = PeriodoQuery,
    cia: int | None = CiaQuery,
) -> RespuestaBalanceComprobacion:
    del usuario  # exigido por la dependencia; el cuerpo no distingue por usuario
    servicio = FinancieroReportesService(sesion)
    filtros = FiltrosFinanciero(periodo=int(periodo), cia=cia)
    filas = [
        FilaBalanceComprobacion.model_validate(fila)
        for fila in servicio.balance_comprobacion(filtros)
    ]
    return RespuestaBalanceComprobacion(filas=filas, parametros_calculo=_parametros(periodo, cia))


@router.get("/balance-general", response_model=RespuestaBalanceGeneral, summary="Balance general")
def balance_general(
    usuario: UsuarioFinancieroDep,
    sesion: SesionDep,
    periodo: str = PeriodoQuery,
    cia: int | None = CiaQuery,
) -> RespuestaBalanceGeneral:
    del usuario
    servicio = FinancieroReportesService(sesion)
    resultado = servicio.balance_general(FiltrosFinanciero(periodo=int(periodo), cia=cia))
    return RespuestaBalanceGeneral(
        activo=resultado.activo,
        pasivo=resultado.pasivo,
        patrimonio=resultado.patrimonio,
        utilidad_del_ejercicio=resultado.utilidad_del_ejercicio,
        descuadre=resultado.descuadre,
        parametros_calculo=_parametros(periodo, cia),
    )


@router.get(
    "/estado-resultados",
    response_model=RespuestaEstadoResultados,
    summary="Estado de resultados",
)
def estado_resultados(
    usuario: UsuarioFinancieroDep,
    sesion: SesionDep,
    periodo: str = PeriodoQuery,
    cia: int | None = CiaQuery,
) -> RespuestaEstadoResultados:
    del usuario
    servicio = FinancieroReportesService(sesion)
    resultado = servicio.estado_resultados(FiltrosFinanciero(periodo=int(periodo), cia=cia))
    return RespuestaEstadoResultados(
        ingresos=resultado.ingresos,
        costos=resultado.costos,
        gastos=resultado.gastos,
        utilidad_neta=resultado.utilidad_neta,
        parametros_calculo=_parametros(periodo, cia),
    )


@router.get("/cartera", response_model=RespuestaCartera, summary="Cartera por cliente")
def cartera(
    usuario: UsuarioFinancieroDep,
    sesion: SesionDep,
    periodo: str = PeriodoQuery,
    cia: int | None = CiaQuery,
) -> RespuestaCartera:
    del usuario
    servicio = FinancieroReportesService(sesion)
    filas = [
        FilaCartera.model_validate(fila)
        for fila in servicio.cartera_por_cliente(FiltrosFinanciero(periodo=int(periodo), cia=cia))
    ]
    return RespuestaCartera(filas=filas, parametros_calculo=_parametros(periodo, cia))


@router.get(
    "/estado-resultados-vivo",
    response_model=RespuestaEstadoResultadosEnVivo,
    summary="Estado de resultados en vivo (SIESA)",
)
def estado_resultados_vivo(
    usuario: UsuarioFinancieroDep,
    periodo: str = PeriodoQuery,
    cia: int = Query(description="Compañía SIESA; debe ser una de las que ya tienen movimientos"),
) -> RespuestaEstadoResultadosEnVivo:
    del usuario
    if cia not in CIAS_EN_VIVO:
        raise ErrorValidacion(
            f"La compañía {cia} no tiene estado de resultados en vivo. Las disponibles son: "
            + ", ".join(f"{codigo} ({nombre})" for codigo, nombre in CIAS_EN_VIVO.items())
        )
    resultado = estado_resultados_en_vivo(cia, int(periodo))
    return RespuestaEstadoResultadosEnVivo(
        ingresos=resultado.ingresos,
        costos=resultado.costos,
        gastos=resultado.gastos,
        utilidad_neta=resultado.utilidad_neta,
        parametros_calculo=ParametrosCalculoEnVivo(periodo=periodo, cia=cia),
    )


@router.get(
    "/situacion-financiera-vivo",
    response_model=RespuestaSituacionFinancieraEnVivo,
    summary="Sumarizado de la situación financiera en vivo (SIESA)",
)
def situacion_financiera_vivo(
    usuario: UsuarioFinancieroDep,
    periodo: str = PeriodoQuery,
    cia: int = Query(description="Compañía SIESA; debe ser una de las que ya tienen movimientos"),
) -> RespuestaSituacionFinancieraEnVivo:
    """Un renglón por clase PUC × subgrupo, igual agrupación que el reporte
    nativo de SIESA («Consulta sumarizada estado de la situación financiera»).
    Es la base del gráfico de composición; el resumen de cuatro cifras sigue
    siendo `/estado-resultados-vivo`.
    """
    del usuario
    if cia not in CIAS_EN_VIVO:
        raise ErrorValidacion(
            f"La compañía {cia} no tiene situación financiera en vivo. Las disponibles son: "
            + ", ".join(f"{codigo} ({nombre})" for codigo, nombre in CIAS_EN_VIVO.items())
        )
    filas = [
        FilaSituacionFinancieraEnVivo(
            clase=etiqueta_clase(fila.clase),
            grupo=fila.grupo,
            subgrupo=fila.subgrupo,
            monto=fila.monto,
        )
        for fila in situacion_financiera_en_vivo(cia, int(periodo))
    ]
    return RespuestaSituacionFinancieraEnVivo(
        filas=filas, parametros_calculo=ParametrosCalculoEnVivo(periodo=periodo, cia=cia)
    )


@router.get(
    "/detalle-cuentas-vivo",
    response_model=RespuestaDetalleCuentasEnVivo,
    summary="Detalle por cuenta, tercero y centro de costo en vivo (SIESA)",
)
def detalle_cuentas_vivo(
    usuario: UsuarioFinancieroDep,
    periodo: str = PeriodoQuery,
    cia: int = Query(description="Compañía SIESA; debe ser una de las que ya tienen movimientos"),
) -> RespuestaDetalleCuentasEnVivo:
    """Un renglón por cuenta auxiliar × tercero × centro de costo, sin sumar:
    la base con la que se armó cada subgrupo de `/situacion-financiera-vivo`.
    """
    del usuario
    if cia not in CIAS_EN_VIVO:
        raise ErrorValidacion(
            f"La compañía {cia} no tiene detalle de cuentas en vivo. Las disponibles son: "
            + ", ".join(f"{codigo} ({nombre})" for codigo, nombre in CIAS_EN_VIVO.items())
        )
    filas = [
        FilaDetalleCuentaEnVivo(
            clase=etiqueta_clase(fila.clase),
            grupo=fila.grupo,
            subgrupo=fila.subgrupo,
            auxiliar=fila.auxiliar,
            cuenta=fila.cuenta,
            tercero=fila.tercero,
            centro_costo=fila.centro_costo,
            monto=fila.monto,
        )
        for fila in detalle_cuentas_en_vivo(cia, int(periodo))
    ]
    return RespuestaDetalleCuentasEnVivo(
        filas=filas, parametros_calculo=ParametrosCalculoEnVivo(periodo=periodo, cia=cia)
    )


@router.get(
    "/detalle-cuentas",
    response_model=RespuestaDetalleCuentas,
    summary="Detalle por cuenta, centro de costo y tercero",
)
def detalle_cuentas(
    usuario: UsuarioFinancieroDep,
    sesion: SesionDep,
    periodo: str = PeriodoQuery,
    cia: int | None = CiaQuery,
    centro_costo: str | None = Query(
        default=None, description="Filtra por un centro de costo exacto."
    ),
    mayor_iii: str | None = Query(
        default=None,
        pattern=r"^\d{4}$",
        description="Filtra por una cuenta PUC de 4 dígitos.",
    ),
) -> RespuestaDetalleCuentas:
    """Base de Balance/PyG «por tercero» y «por centro de costo»: un renglón
    por cuenta de 6 dígitos × centro de costo × tercero, sin agregar. La
    pantalla decide cómo agruparlo; el backend no supone cuál de los dos ejes
    importa más.
    """
    del usuario
    servicio = FinancieroReportesService(sesion)
    filas = [
        FilaDetalleCuenta.model_validate(fila)
        for fila in servicio.detalle_cuentas(
            FiltrosFinanciero(periodo=int(periodo), cia=cia),
            centro_costo=centro_costo,
            mayor_iii=mayor_iii,
        )
    ]
    return RespuestaDetalleCuentas(filas=filas, parametros_calculo=_parametros(periodo, cia))


@router.get(
    "/indicadores",
    response_model=RespuestaIndicadoresFinancieros,
    summary="Indicadores financieros",
)
def indicadores(
    usuario: UsuarioFinancieroDep,
    sesion: SesionDep,
    periodo: str = PeriodoQuery,
    cia: int | None = CiaQuery,
) -> RespuestaIndicadoresFinancieros:
    del usuario
    servicio = FinancieroReportesService(sesion)
    resultado = servicio.indicadores(FiltrosFinanciero(periodo=int(periodo), cia=cia))
    return RespuestaIndicadoresFinancieros(
        liquidez_corriente=resultado.liquidez_corriente,
        endeudamiento=resultado.endeudamiento,
        margen_neto=resultado.margen_neto,
        parametros_calculo=_parametros(periodo, cia),
    )
