"""Implementaciones del puerto `FuenteVenta` (§5 de la especificación).

Dos, y cambiar de una a otra es la variable de entorno `SIGREP_FUENTE_VENTA`,
no un refactor:

- `FuenteVentaExcel` — lee el libro que hoy arma el negocio. Es la que permite
  tener el sistema funcionando y conciliado contra el Excel, y la que sirve para
  cargar historia que la API no expone.
- `FuenteVentaSiesa` — consume la API de consulta de Grupo Santa Cruz. Une
  `/ventas/vendedor-acumulada` y `/ventas/pos-vendedor-detalle` porque PEREIRA
  registra en otro módulo de POS; ver el encabezado de `siesa.py`.
"""

from app.infrastructure.fuentes.base import (
    AnotacionFuente,
    ClienteFuente,
    FuenteConClientes,
    RechazoFuente,
)
from app.infrastructure.fuentes.excel import FuenteVentaExcel
from app.infrastructure.fuentes.siesa import (
    MENSAJE_SIN_DESCRIPCIONES,
    MENSAJE_SIN_TOKEN,
    RUTA_POS_VENDEDOR_DETALLE,
    RUTA_VENDEDOR_ACUMULADA,
    ConfiguracionSiesa,
    ErrorFuenteSiesa,
    FuenteVentaSiesa,
)

__all__ = [
    "MENSAJE_SIN_DESCRIPCIONES",
    "MENSAJE_SIN_TOKEN",
    "RUTA_POS_VENDEDOR_DETALLE",
    "RUTA_VENDEDOR_ACUMULADA",
    "AnotacionFuente",
    "ClienteFuente",
    "ConfiguracionSiesa",
    "ErrorFuenteSiesa",
    "FuenteConClientes",
    "FuenteVentaExcel",
    "FuenteVentaSiesa",
    "RechazoFuente",
]
