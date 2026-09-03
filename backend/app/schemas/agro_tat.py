from __future__ import annotations

from datetime import date

from app.schemas.common import DecimalStr, EsquemaBase


class AgroTatVentaSalida(EsquemaBase):
    fecha_documento: date
    nro_documento: str
    tipo_comercial: str | None
    cliente_factura: str | None
    razon_social_cliente: str | None
    codigo_sucursal: str | None
    descripcion_sucursal: str | None
    direccion_sucursal: str | None
    cantidad_inv: DecimalStr
    valor_subtotal: DecimalStr


class AgroTatResumen(EsquemaBase):
    filas: list[AgroTatVentaSalida]
    total_cantidad: DecimalStr
    total_subtotal: DecimalStr


class AgroTatIngestaSalida(EsquemaBase):
    corrida_id: int
    filas_leidas: int
    filas_insertadas: int
