"""Implementaciones del puerto `FuenteVenta` (§5 de la especificación).

Dos, y cambiar de una a otra es la variable de entorno `SIGREP_FUENTE_VENTA`,
no un refactor:

- `FuenteVentaExcel` — lee el libro que hoy arma el negocio. Es la que permite
  tener el sistema funcionando y conciliado contra el Excel, y la que sirve para
  cargar historia que la API no expone.
- `FuenteVentaSiesa` — consume la API de consulta de Grupo Santa Cruz por
  `/ventas/costos-razon-social`, que ya une los dos módulos de POS del lado de
  la API; ver el encabezado de `siesa.py`.
"""

from app.infrastructure.fuentes.base import (
    AnotacionFuente,
    ClienteFuente,
    FuenteConClientes,
    RechazoFuente,
)
from app.infrastructure.fuentes.excel import FuenteVentaExcel
from app.infrastructure.fuentes.siesa import (
    COMPANIAS_CARNES,
    MENSAJE_SIN_COMPANIAS,
    MENSAJE_SIN_DESCRIPCIONES,
    MENSAJE_SIN_TOKEN,
    ORIGEN_ACUMULADO,
    ORIGEN_SIN_ACUMULAR,
    ORIGENES_SIN_COSTO,
    RUTA_COSTOS_RAZON_SOCIAL,
    ConfiguracionSiesa,
    ErrorFuenteSiesa,
    FuenteVentaSiesa,
)

__all__ = [
    "COMPANIAS_CARNES",
    "MENSAJE_SIN_COMPANIAS",
    "MENSAJE_SIN_DESCRIPCIONES",
    "MENSAJE_SIN_TOKEN",
    "ORIGENES_SIN_COSTO",
    "ORIGEN_ACUMULADO",
    "ORIGEN_SIN_ACUMULAR",
    "RUTA_COSTOS_RAZON_SOCIAL",
    "AnotacionFuente",
    "ClienteFuente",
    "ConfiguracionSiesa",
    "ErrorFuenteSiesa",
    "FuenteConClientes",
    "FuenteVentaExcel",
    "FuenteVentaSiesa",
    "RechazoFuente",
]
