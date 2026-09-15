"""Reportes del tablero financiero consolidado — Grupo Santacruz.

La agregación se hace **en la base**, con `GROUP BY` y `SUM`, nunca trayendo
1.27 millones de filas a Python: la misma razón que en
`app.application.services.reportes_service`.

Ningún reporte inventa una cifra que no esté en `movimientos_contables`: un
denominador en cero se devuelve como `None` (§ contrato: «un indicador
indefinido viaja como `null` y se pinta "—", nunca como `0`»), nunca se fuerza
a cero ni se omite la fila.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, DivisionByZero, InvalidOperation

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.domain.financiero import (
    ClaseCuenta,
    GRUPO_CARTERA_CLIENTES,
    GRUPOS_ACTIVO_CORRIENTE,
    GRUPOS_PASIVO_CORRIENTE,
    clasificar,
    es_naturaleza_credito,
    etiqueta_clase,
)
from app.infrastructure.models.financiero import MovimientoContable

CERO = Decimal("0.00")


def _dividir(numerador: Decimal, denominador: Decimal) -> Decimal | None:
    """`None` en vez de una `ZeroDivisionError` o un cero engañoso."""
    if denominador == 0:
        return None
    try:
        return numerador / denominador
    except (DivisionByZero, InvalidOperation):
        return None


@dataclass(frozen=True)
class FiltrosFinanciero:
    periodo: int  # AAAAMM
    cia: int | None = None

    def aplicar(self, consulta: Select[tuple]) -> Select[tuple]:
        consulta = consulta.where(MovimientoContable.periodo == self.periodo)
        if self.cia is not None:
            consulta = consulta.where(MovimientoContable.cia == self.cia)
        return consulta


@dataclass(frozen=True)
class FilaBalanceComprobacion:
    mayor_iii: str
    descripcion: str | None
    clase: str
    saldo_inicial: Decimal
    debitos: Decimal
    creditos: Decimal
    final: Decimal


@dataclass(frozen=True)
class FilaClaseCuenta:
    clase: str
    saldo: Decimal


@dataclass(frozen=True)
class BalanceGeneral:
    activo: Decimal
    pasivo: Decimal
    patrimonio: Decimal
    #: `activo - pasivo - patrimonio`. Debe dar `0` en una base bien cuadrada;
    #: se publica para que un descuadre del origen sea visible, no silencioso.
    descuadre: Decimal


@dataclass(frozen=True)
class EstadoResultados:
    ingresos: Decimal
    costos: Decimal
    gastos: Decimal
    utilidad_neta: Decimal


@dataclass(frozen=True)
class FilaCartera:
    id_tercero: str
    razon_social: str | None
    saldo: Decimal


@dataclass(frozen=True)
class IndicadoresFinancieros:
    liquidez_corriente: Decimal | None
    endeudamiento: Decimal | None
    margen_neto: Decimal | None


class FinancieroReportesService:
    def __init__(self, sesion: Session) -> None:
        self._sesion = sesion

    def _consulta_base(self, filtros: FiltrosFinanciero) -> Select[tuple]:
        return filtros.aplicar(select(MovimientoContable))

    def balance_comprobacion(self, filtros: FiltrosFinanciero) -> list[FilaBalanceComprobacion]:
        """Un renglón por cuenta (`mayor_iii`), sumado sobre CO y terceros."""
        consulta = filtros.aplicar(
            select(
                MovimientoContable.mayor_iii,
                func.max(MovimientoContable.descripcion).label("descripcion"),
                func.sum(MovimientoContable.saldo_inicial).label("saldo_inicial"),
                func.sum(MovimientoContable.debitos).label("debitos"),
                func.sum(MovimientoContable.creditos).label("creditos"),
                func.sum(MovimientoContable.final).label("final"),
            ).group_by(MovimientoContable.mayor_iii)
        ).order_by(MovimientoContable.mayor_iii)

        filas = []
        for mayor_iii, descripcion, saldo_inicial, debitos, creditos, final in self._sesion.execute(
            consulta
        ):
            clase = clasificar(mayor_iii)
            filas.append(
                FilaBalanceComprobacion(
                    mayor_iii=mayor_iii,
                    descripcion=descripcion,
                    clase=etiqueta_clase(clase) if clase else "Sin clasificar",
                    saldo_inicial=saldo_inicial or CERO,
                    debitos=debitos or CERO,
                    creditos=creditos or CERO,
                    final=final or CERO,
                )
            )
        return filas

    def _saldos_por_clase(self, filtros: FiltrosFinanciero) -> dict[ClaseCuenta, Decimal]:
        """Suma `FINAL` por clase, ya reexpresado como saldo económico

        (positivo para naturaleza débito, invertido para naturaleza crédito).
        `SUM` no puede aplicar esa inversión por fila con un simple `GROUP BY`
        en SQL portable, así que se agrupa por `mayor_iii` —ya viene agregado
        de `balance_comprobacion`— y se reduce en Python: son a lo sumo unos
        cientos de cuentas distintas, no millones de filas.
        """
        acumulado: dict[ClaseCuenta, Decimal] = {}
        for fila in self.balance_comprobacion(filtros):
            clase = clasificar(fila.mayor_iii)
            if clase is None:
                continue
            saldo = -fila.final if es_naturaleza_credito(clase) else fila.final
            acumulado[clase] = acumulado.get(clase, CERO) + saldo
        return acumulado

    def balance_general(self, filtros: FiltrosFinanciero) -> BalanceGeneral:
        saldos = self._saldos_por_clase(filtros)
        activo = saldos.get(ClaseCuenta.ACTIVO, CERO)
        pasivo = saldos.get(ClaseCuenta.PASIVO, CERO)
        patrimonio = saldos.get(ClaseCuenta.PATRIMONIO, CERO)
        return BalanceGeneral(
            activo=activo,
            pasivo=pasivo,
            patrimonio=patrimonio,
            descuadre=activo - pasivo - patrimonio,
        )

    def estado_resultados(self, filtros: FiltrosFinanciero) -> EstadoResultados:
        saldos = self._saldos_por_clase(filtros)
        ingresos = saldos.get(ClaseCuenta.INGRESO, CERO)
        costos = saldos.get(ClaseCuenta.COSTO_VENTA, CERO) + saldos.get(
            ClaseCuenta.COSTO_PRODUCCION, CERO
        )
        gastos = saldos.get(ClaseCuenta.GASTO, CERO)
        return EstadoResultados(
            ingresos=ingresos,
            costos=costos,
            gastos=gastos,
            utilidad_neta=ingresos - costos - gastos,
        )

    def cartera_por_cliente(self, filtros: FiltrosFinanciero) -> list[FilaCartera]:
        """Saldo final por tercero, cuentas del grupo `13` (deudores/cartera)."""
        consulta = filtros.aplicar(
            select(
                MovimientoContable.id_tercero,
                func.max(MovimientoContable.razon_social).label("razon_social"),
                func.sum(MovimientoContable.final).label("final"),
            )
            .where(
                MovimientoContable.mayor_iii.like(f"{GRUPO_CARTERA_CLIENTES}%"),
                MovimientoContable.id_tercero.is_not(None),
            )
            .group_by(MovimientoContable.id_tercero)
        ).order_by(func.sum(MovimientoContable.final).desc())

        return [
            FilaCartera(id_tercero=id_tercero, razon_social=razon_social, saldo=final or CERO)
            for id_tercero, razon_social, final in self._sesion.execute(consulta)
        ]

    def indicadores(self, filtros: FiltrosFinanciero) -> IndicadoresFinancieros:
        """Liquidez, endeudamiento y margen neto. Ver los supuestos de

        clasificación por plazo en `app.domain.financiero` — liquidez corriente
        depende de ellos y está pendiente de validar con contabilidad.
        """
        filas = self.balance_comprobacion(filtros)
        activo_corriente = CERO
        pasivo_corriente = CERO
        activo_total = CERO
        pasivo_total = CERO
        for fila in filas:
            clase = clasificar(fila.mayor_iii)
            if clase is None:
                continue
            saldo = -fila.final if es_naturaleza_credito(clase) else fila.final
            grupo = fila.mayor_iii[:2]
            if clase == ClaseCuenta.ACTIVO:
                activo_total += saldo
                if grupo in GRUPOS_ACTIVO_CORRIENTE:
                    activo_corriente += saldo
            elif clase == ClaseCuenta.PASIVO:
                pasivo_total += saldo
                if grupo in GRUPOS_PASIVO_CORRIENTE:
                    pasivo_corriente += saldo

        resultados = self.estado_resultados(filtros)
        return IndicadoresFinancieros(
            liquidez_corriente=_dividir(activo_corriente, pasivo_corriente),
            endeudamiento=_dividir(pasivo_total, activo_total),
            margen_neto=_dividir(resultados.utilidad_neta, resultados.ingresos),
        )
