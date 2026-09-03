from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict


class AgroTatVentaSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    fecha_documento: date
    nro_documento: str
    tipo_comercial: str | None
    cliente_factura: str | None
    razon_social_cliente: str | None
    codigo_sucursal: str | None
    descripcion_sucursal: str | None
    direccion_sucursal: str | None
    cantidad_inv: str
    valor_subtotal: str


class AgroTatResumen(BaseModel):
    filas: list[AgroTatVentaSalida]
    total_cantidad: str
    total_subtotal: str


class AgroTatIngestaSalida(BaseModel):
    corrida_id: int
    filas_leidas: int
    filas_insertadas: int