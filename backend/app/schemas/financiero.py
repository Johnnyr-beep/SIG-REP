"""Esquemas del tablero financiero consolidado — Grupo Santacruz.

Mismas reglas del contrato general: importes como `string` (`DecimalStr`) y
todo indicador indefinido viaja como `null`, nunca como `0` (`app.schemas.common`).
"""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import DecimalStr, EsquemaBase


class ParametrosCalculoFinanciero(EsquemaBase):
    """De dónde sale el número — igual que en `reportes.py`, para este módulo."""

    periodo: str = Field(description="AAAAMM tal como lo entrega SIESA", examples=["202607"])
    cia: int | None = Field(default=None, description="Compañía; ausente = todas las cargadas")


class FilaBalanceComprobacion(EsquemaBase):
    mayor_iii: str = Field(description="Cuenta PUC de 4 dígitos")
    descripcion: str | None = None
    clase: str = Field(description="Activo, Pasivo, Patrimonio, Ingresos, Gastos, Costos…")
    saldo_inicial: DecimalStr
    debitos: DecimalStr
    creditos: DecimalStr
    final: DecimalStr


class RespuestaBalanceComprobacion(EsquemaBase):
    filas: list[FilaBalanceComprobacion]
    parametros_calculo: ParametrosCalculoFinanciero


class RespuestaBalanceGeneral(EsquemaBase):
    activo: DecimalStr
    pasivo: DecimalStr
    patrimonio: DecimalStr
    descuadre: DecimalStr = Field(
        description="activo - pasivo - patrimonio. Debe ser 0; un valor distinto "
        "señala un descuadre en el origen, no un error de SIGREP."
    )
    parametros_calculo: ParametrosCalculoFinanciero


class RespuestaEstadoResultados(EsquemaBase):
    ingresos: DecimalStr
    costos: DecimalStr
    gastos: DecimalStr
    utilidad_neta: DecimalStr
    parametros_calculo: ParametrosCalculoFinanciero


class FilaCartera(EsquemaBase):
    id_tercero: str
    razon_social: str | None = None
    saldo: DecimalStr


class RespuestaCartera(EsquemaBase):
    filas: list[FilaCartera]
    parametros_calculo: ParametrosCalculoFinanciero


class RespuestaIndicadoresFinancieros(EsquemaBase):
    liquidez_corriente: DecimalStr | None = Field(
        default=None,
        description="Activo corriente / pasivo corriente. Clasificación por grupo "
        "de cuenta, pendiente de validar con contabilidad — ver docs.",
    )
    endeudamiento: DecimalStr | None = None
    margen_neto: DecimalStr | None = None
    parametros_calculo: ParametrosCalculoFinanciero
