"""Implementaciones del puerto `FuenteVenta` (§5 de la especificación).

Dos, y cambiar de una a otra es la variable de entorno `SIGREP_FUENTE_VENTA`,
no un refactor:

- `FuenteVentaExcel` — lee el libro que hoy arma el negocio. Es la que permite
  tener el sistema funcionando y conciliado contra el Excel **antes** de que
  llegue la API de SIESA.
- `FuenteVentaSiesa` — esqueleto con la firma correcta. La API de SIESA no se ha
  entregado; inventarle un contrato sería trabajo que habría que tirar.
"""

from app.infrastructure.fuentes.base import ClienteFuente, FuenteConClientes, RechazoFuente
from app.infrastructure.fuentes.excel import FuenteVentaExcel
from app.infrastructure.fuentes.siesa import MENSAJE_SIESA_PENDIENTE, FuenteVentaSiesa

__all__ = [
    "MENSAJE_SIESA_PENDIENTE",
    "ClienteFuente",
    "FuenteConClientes",
    "FuenteVentaExcel",
    "FuenteVentaSiesa",
    "RechazoFuente",
]
