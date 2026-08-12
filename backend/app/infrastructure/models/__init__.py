"""Modelos ORM.

Importar este paquete registra todas las tablas en `Base.metadata`, que es lo
que Alembic necesita para autogenerar migraciones completas y lo que resuelve
las relaciones declaradas por nombre entre módulos.
"""

from app.infrastructure.models.catalogo import Categoria, MapeoCategoria
from app.infrastructure.models.ingesta import CorridaIngesta, RechazoIngesta
from app.infrastructure.models.organizacion import Grupo, PuntoVenta, Zona
from app.infrastructure.models.periodo import CalendarioZona, Periodo
from app.infrastructure.models.presupuesto import Presupuesto, PresupuestoHistorial
from app.infrastructure.models.usuario import IntentoAcceso, Usuario, UsuarioPuntoVenta
from app.infrastructure.models.venta import Cliente, VentaLinea

__all__ = [
    "CalendarioZona",
    "Categoria",
    "Cliente",
    "CorridaIngesta",
    "Grupo",
    "IntentoAcceso",
    "MapeoCategoria",
    "Periodo",
    "Presupuesto",
    "PresupuestoHistorial",
    "PuntoVenta",
    "RechazoIngesta",
    "Usuario",
    "UsuarioPuntoVenta",
    "VentaLinea",
    "Zona",
]
