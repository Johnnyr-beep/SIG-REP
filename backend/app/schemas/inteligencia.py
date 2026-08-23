"""Contrato de inteligencia comercial de Agropecuaria."""

from __future__ import annotations

from app.schemas.common import DecimalStr, EsquemaBase


class AlertaComercial(EsquemaBase):
    tipo: str
    cliente: str
    producto: str | None = None
    venta_anterior: DecimalStr
    venta_actual: DecimalStr
    variacion: DecimalStr | None = None
    detalle: str


class OportunidadComercial(EsquemaBase):
    cliente: str
    producto: str
    venta_producto: DecimalStr
    detalle: str


class RecomendacionComercial(EsquemaBase):
    prioridad: str
    titulo: str
    detalle: str


class RespuestaInteligencia(EsquemaBase):
    periodo: str
    periodo_anterior: str
    disponible: bool
    mensaje: str | None = None
    alertas: list[AlertaComercial]
    productos_no_solicitados: list[AlertaComercial]
    oportunidades: list[OportunidadComercial]
    recomendaciones: list[RecomendacionComercial]
