from collections import defaultdict
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field


def _fecha_siesa(valor: object) -> object:
    return valor.split("T", 1)[0] if isinstance(valor, str) else valor


class RegistroTpv(BaseModel):
    compania: int = Field(alias="Compania")
    codigo_co: str = Field(alias="CO")
    fecha: Annotated[date, BeforeValidator(_fecha_siesa)] = Field(alias="Fecha")
    tpv: str = Field(alias="TPV")
    estado: Literal["Abierto", "Cerrado"] = Field(alias="Estado")


class PuntoTpv(BaseModel):
    codigo_co: str
    nombre: str
    fecha_acumulada: date | None
    dias_acumulados: int
    dias_sin_acumulacion: int
    dias_sin_registros: int


class TpvAbierta(BaseModel):
    codigo_co: str
    punto_venta: str
    compania: int
    tpv: str
    fecha: date


class RespuestaTpv(BaseModel):
    fecha_corte: date
    puntos: list[PuntoTpv]
    abiertas: list[TpvAbierta]


def resumir_tpv(
    registros: list[RegistroTpv], nombres: dict[str, str], inicio: date, corte: date
) -> RespuestaTpv:
    dias: dict[str, dict[date, bool]] = defaultdict(dict)
    abiertas: dict[tuple[str, date, int, str], TpvAbierta] = {}
    for registro in registros:
        codigo = registro.codigo_co.strip().zfill(3)
        if codigo not in nombres or not inicio <= registro.fecha <= corte:
            continue
        fecha = registro.fecha
        dias[codigo][fecha] = dias[codigo].get(fecha, True) and registro.estado == "Cerrado"
        if registro.estado == "Abierto":
            abiertas[codigo, fecha, registro.compania, registro.tpv] = TpvAbierta(
                codigo_co=codigo,
                punto_venta=nombres[codigo],
                compania=registro.compania,
                tpv=registro.tpv,
                fecha=fecha,
            )

    total = (corte - inicio).days + 1
    puntos = []
    for codigo, estados in dias.items():
        cerrados = [fecha for fecha, cerrado in estados.items() if cerrado]
        puntos.append(PuntoTpv(
            codigo_co=codigo,
            nombre=nombres[codigo],
            fecha_acumulada=max(cerrados, default=None),
            dias_acumulados=len(cerrados),
            dias_sin_acumulacion=total - len(cerrados),
            dias_sin_registros=total - len(estados),
        ))

    return RespuestaTpv(
        fecha_corte=corte,
        puntos=sorted(puntos, key=lambda punto: (-punto.dias_acumulados, punto.nombre)),
        abiertas=sorted(abiertas.values(), key=lambda fila: (-fila.fecha.toordinal(),
                                                             fila.punto_venta, fila.tpv)),
    )