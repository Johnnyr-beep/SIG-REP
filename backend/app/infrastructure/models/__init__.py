"""Modelos ORM.

Importar este paquete registra todas las tablas en `Base.metadata`, que es lo
que Alembic necesita para autogenerar migraciones completas y lo que resuelve
las relaciones declaradas por nombre entre módulos.

Los modelos `Agro*` son los de la **unidad Agropecuaria** (compañía 3), que es
un negocio distinto del de carnes y no una variante suyo: mide vendedor,
cliente, especie, tipo comercial y centro de operación en lugar de punto de
venta y categoría. Tiene sus propias tablas —prefijo `agro_`— y sus propios
servicios; lo único que comparte es lo que de verdad es común: los períodos, los
usuarios y las fórmulas de `app/domain/indicadores.py`.
"""

from app.infrastructure.models.agro_dimensiones import AgroDimension
from app.infrastructure.models.agro_ingesta import AgroCorridaIngesta, AgroRechazoIngesta
from app.infrastructure.models.agro_presupuesto import (
    AgroCalendario,
    AgroPresupuesto,
    AgroPresupuestoHistorial,
)
from app.infrastructure.models.agro_presupuesto_mensual import (
    AgroPptoMensualCanalMapeo,
    AgroPptoMensualDetalle,
    AgroPptoMensualMapeo,
    AgroPptoMensualServicio,
)
from app.infrastructure.models.agro_tat import AgroTatCorrida, AgroTatVenta
from app.infrastructure.models.agro_venta import AgroVentaLinea
from app.infrastructure.models.catalogo import Categoria, MapeoCategoria
from app.infrastructure.models.historia_venta import HistoriaVentaManual
from app.infrastructure.models.ingesta import CorridaIngesta, RechazoIngesta
from app.infrastructure.models.organizacion import Grupo, PuntoVenta, Zona
from app.infrastructure.models.periodo import CalendarioZona, Periodo
from app.infrastructure.models.presupuesto import Presupuesto, PresupuestoHistorial
from app.infrastructure.models.usuario import (
    IntentoAcceso,
    Usuario,
    UsuarioAuditoria,
    UsuarioPuntoVenta,
)
from app.infrastructure.models.venta import Cliente, VentaLinea

__all__ = [
    "AgroCalendario",
    "AgroCorridaIngesta",
    "AgroDimension",
    "AgroPptoMensualCanalMapeo",
    "AgroPptoMensualDetalle",
    "AgroPptoMensualMapeo",
    "AgroPptoMensualServicio",
    "AgroPresupuesto",
    "AgroPresupuestoHistorial",
    "AgroRechazoIngesta",
    "AgroTatCorrida",
    "AgroTatVenta",
    "AgroVentaLinea",
    "CalendarioZona",
    "Categoria",
    "Cliente",
    "CorridaIngesta",
    "Grupo",
    "HistoriaVentaManual",
    "IntentoAcceso",
    "MapeoCategoria",
    "Periodo",
    "Presupuesto",
    "PresupuestoHistorial",
    "PuntoVenta",
    "RechazoIngesta",
    "Usuario",
    "UsuarioAuditoria",
    "UsuarioPuntoVenta",
    "VentaLinea",
    "Zona",
]
