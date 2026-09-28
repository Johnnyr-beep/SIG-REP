"""Contratos para consultas de inventario."""

from pydantic import Field

from app.schemas.common import DecimalStr, EsquemaBase


class FilaInventarioPdv(EsquemaBase):
    compania: int | None = None
    punto_venta: str | None = None
    codigo_producto: str | None = None
    referencia: str | None = None
    producto: str | None = None
    unidad: str | None = None
    existencia: DecimalStr | None = None
    comprometida: DecimalStr | None = None
    pendiente_entrada: DecimalStr | None = None
    pendiente_salida: DecimalStr | None = None
    datos: dict[str, str | None] = Field(default_factory=dict)


class RespuestaInventarioPdv(EsquemaBase):
    columnas: list[str]
    filas: list[FilaInventarioPdv]
    total: int = Field(ge=0)
