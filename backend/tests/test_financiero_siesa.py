"""`saldos_por_clase_en_vivo`: el estado de resultados leído en vivo de SIESA.

Ninguna prueba de este archivo toca la red: la respuesta HTTP se simula con
`httpx.MockTransport` sobre el CSV real de `GET /ventas/estado-situacion-
financiera` — encabezado en minúsculas, columnas `S1`...`S12` con el
movimiento neto de cada mes (ver el docstring de
`app.infrastructure.fuentes.financiero_siesa`, que documenta cómo se midió que
`Sn` es movimiento y no saldo acumulado).
"""

from __future__ import annotations

from decimal import Decimal

import httpx
from pydantic import SecretStr

from app.domain.financiero import ClaseCuenta
from app.infrastructure.fuentes.financiero_siesa import (
    ConfiguracionFinancieroSiesa,
    saldos_por_clase_en_vivo,
    situacion_financiera_en_vivo,
)

ENCABEZADO = (
    "grupo,clase,cuenta,auxiliar,desc_auxiliar,desc_co,tercero,c_costo,co,un,nit,"
    + ",".join(f"S{m}" for m in range(1, 13))
)


def fila_mensual(
    auxiliar: str,
    valores_por_mes: dict[int, str],
    *,
    desc_auxiliar: str = "CUENTA DE PRUEBA",
    desc_co: str = "PRINCIPAL",
    tercero: str = "UN TERCERO",
    grupo: str = "GRUPO",
    subgrupo: str = "CLASE",
    cuenta: str = "CUENTA",
) -> str:
    """Una fila del CSV pivotado, con valor solo en los meses indicados."""
    columnas = [str(valores_por_mes.get(m, "0")) for m in range(1, 13)]
    return (
        f"{grupo},{subgrupo},{cuenta},{auxiliar},{desc_auxiliar},{desc_co},{tercero},,301,003,900000000,"
        + ",".join(columnas)
    )


def csv_estado_financiero(*filas: str) -> str:
    return "\n".join((ENCABEZADO, *filas)) + "\n"


def _configuracion() -> ConfiguracionFinancieroSiesa:
    return ConfiguracionFinancieroSiesa(
        url_base="https://apiconsulta.grupo-santacruz.com",
        token=SecretStr("1-" + "a1b2c3d4" * 8),
    )


def _cliente(cuerpo: str, *, estado: int = 200) -> httpx.Client:
    def _responder(peticion: httpx.Request) -> httpx.Response:
        return httpx.Response(estado, text=cuerpo, request=peticion)

    return httpx.Client(transport=httpx.MockTransport(_responder))


def test_suma_solo_la_columna_del_mes_pedido() -> None:
    """`S1` y `S2` son meses distintos: el de enero no debe colarse en febrero."""
    cuerpo = csv_estado_financiero(
        fila_mensual("4135010101", {1: "-500.00", 2: "-300.00"}),  # Ingreso, cred.
        fila_mensual("5105060101", {1: "200.00", 2: "150.00"}),  # Gasto, débito.
    )
    with _cliente(cuerpo) as cliente:
        saldos_enero = saldos_por_clase_en_vivo(
            4, 202601, configuracion=_configuracion(), cliente=cliente
        )
        saldos_febrero = saldos_por_clase_en_vivo(
            4, 202602, configuracion=_configuracion(), cliente=cliente
        )

    assert saldos_enero[ClaseCuenta.INGRESO] == Decimal("500.00")
    assert saldos_enero[ClaseCuenta.GASTO] == Decimal("200.00")
    assert saldos_febrero[ClaseCuenta.INGRESO] == Decimal("300.00")
    assert saldos_febrero[ClaseCuenta.GASTO] == Decimal("150.00")


def test_invierte_naturaleza_credito_igual_que_el_reporte_local() -> None:
    """Ingreso es naturaleza crédito: el crudo negativo se presenta positivo,

    igual que `app.domain.financiero.saldo_presentacion` y que
    `FinancieroReportesService._saldos_por_clase`.
    """
    cuerpo = csv_estado_financiero(fila_mensual("4135010101", {7: "-1000.00"}))
    with _cliente(cuerpo) as cliente:
        saldos = saldos_por_clase_en_vivo(
            3, 202607, configuracion=_configuracion(), cliente=cliente
        )

    assert saldos[ClaseCuenta.INGRESO] == Decimal("1000.00")


def test_filas_en_cero_no_ensucian_el_acumulado() -> None:
    """Una fila sin movimiento ese mes no debe aportar una clase con saldo cero

    de más: si la clase no tuvo ningún movimiento, no debe aparecer en el dict.
    """
    cuerpo = csv_estado_financiero(fila_mensual("1105050101", {1: "0"}))
    with _cliente(cuerpo) as cliente:
        saldos = saldos_por_clase_en_vivo(
            3, 202601, configuracion=_configuracion(), cliente=cliente
        )

    assert saldos == {}


def test_cuenta_sin_clasificar_se_ignora() -> None:
    """Un `auxiliar` vacío o fuera del PUC (1-9) no revienta la suma: se salta."""
    cuerpo = csv_estado_financiero(
        fila_mensual("", {1: "999.00"}),
        fila_mensual("0135010101", {1: "500.00"}),  # clase "0": no existe
        fila_mensual("4135010101", {1: "-100.00"}),
    )
    with _cliente(cuerpo) as cliente:
        saldos = saldos_por_clase_en_vivo(
            3, 202601, configuracion=_configuracion(), cliente=cliente
        )

    assert saldos == {ClaseCuenta.INGRESO: Decimal("100.00")}


def test_situacion_financiera_agrupa_por_clase_y_subgrupo() -> None:
    """Dos cuentas del mismo subgrupo se suman en un solo renglón; una de otro

    subgrupo queda aparte, igual que el reporte sumarizado nativo de SIESA.
    """
    cuerpo = csv_estado_financiero(
        fila_mensual(
            "5105060101", {1: "200.00"}, grupo="GASTOS", subgrupo="OPERACIONALES DE ADMON"
        ),
        fila_mensual("5105390101", {1: "50.00"}, grupo="GASTOS", subgrupo="OPERACIONALES DE ADMON"),
        fila_mensual("4135010101", {1: "-1000.00"}, grupo="INGRESOS", subgrupo="OPERACIONALES"),
    )
    with _cliente(cuerpo) as cliente:
        filas = situacion_financiera_en_vivo(
            3, 202601, configuracion=_configuracion(), cliente=cliente
        )

    por_subgrupo = {(f.clase, f.subgrupo): f.monto for f in filas}
    assert por_subgrupo[(ClaseCuenta.GASTO, "OPERACIONALES DE ADMON")] == Decimal("250.00")
    assert por_subgrupo[(ClaseCuenta.INGRESO, "OPERACIONALES")] == Decimal("1000.00")


def test_situacion_financiera_omite_filas_sin_movimiento_ese_mes() -> None:
    """Una cuenta con movimiento en otro mes no aparece en el renglón del mes pedido."""
    cuerpo = csv_estado_financiero(
        fila_mensual("5105060101", {2: "200.00"}, grupo="GASTOS", subgrupo="ADMON"),
    )
    with _cliente(cuerpo) as cliente:
        filas = situacion_financiera_en_vivo(
            3, 202601, configuracion=_configuracion(), cliente=cliente
        )

    assert filas == []
