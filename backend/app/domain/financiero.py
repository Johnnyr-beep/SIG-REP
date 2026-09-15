"""Clasificación contable del libro mayor (PUC) para el tablero financiero
consolidado de la instancia Grupo Santacruz.

El libro mayor que entrega SIESA solo trae saldos ya sumados —`SALDOS_INICIAL
+ DEBITOS - CREDITOS = FINAL`— y esa aritmética no distingue la naturaleza de
la cuenta. Un pasivo con más débitos que créditos en el mes queda con `FINAL`
positivo aunque económicamente se redujo (medido: cuenta `2105`, un mes con
solo débitos, `FINAL` positivo). La presentación financiera sí necesita esa
distinción —un pasivo, un patrimonio y un ingreso son de naturaleza
crédito— y esa conversión vive aquí, no repartida en cada consulta.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum


class ClaseCuenta(StrEnum):
    """Clase del PUC colombiano: el primer dígito del código de cuenta."""

    ACTIVO = "1"
    PASIVO = "2"
    PATRIMONIO = "3"
    INGRESO = "4"
    GASTO = "5"
    COSTO_VENTA = "6"
    COSTO_PRODUCCION = "7"
    ORDEN_DEUDORA = "8"
    ORDEN_ACREEDORA = "9"


ETIQUETAS_CLASE: dict[ClaseCuenta, str] = {
    ClaseCuenta.ACTIVO: "Activo",
    ClaseCuenta.PASIVO: "Pasivo",
    ClaseCuenta.PATRIMONIO: "Patrimonio",
    ClaseCuenta.INGRESO: "Ingresos",
    ClaseCuenta.GASTO: "Gastos",
    ClaseCuenta.COSTO_VENTA: "Costo de ventas",
    ClaseCuenta.COSTO_PRODUCCION: "Costo de producción",
    ClaseCuenta.ORDEN_DEUDORA: "Cuentas de orden deudoras",
    ClaseCuenta.ORDEN_ACREEDORA: "Cuentas de orden acreedoras",
}

#: Naturaleza crédito: el saldo económico de estas clases crece con el
#: crédito, así que hay que invertir el signo de `FINAL` para presentarlas
#: como un saldo positivo normal.
_CLASES_NATURALEZA_CREDITO = frozenset(
    {
        ClaseCuenta.PASIVO,
        ClaseCuenta.PATRIMONIO,
        ClaseCuenta.INGRESO,
        ClaseCuenta.ORDEN_ACREEDORA,
    }
)

#: Grupos PUC (dos dígitos) que el estándar ubica como corto plazo.
#:
#: **Supuesto por grupo de cuenta, no por vencimiento real** — el libro mayor
#: no trae plazos de pago, así que esta es una aproximación estándar y debe
#: validarse con contabilidad antes de tratarse como definitiva.
#: PENDIENTE DE CONFIRMAR CON EL USUARIO.
GRUPOS_ACTIVO_CORRIENTE = frozenset({"11", "12", "13", "14"})
GRUPOS_PASIVO_CORRIENTE = frozenset({"21", "22", "23", "24", "25", "26", "27", "28"})

#: Grupo PUC de clientes (cartera). `13` completo, no solo `1305`: el negocio
#: también puede tener anticipos o cuentas por cobrar a empleados bajo el mismo
#: grupo de deudores.
GRUPO_CARTERA_CLIENTES = "13"


def clasificar(mayor_iii: str | None) -> ClaseCuenta | None:
    """La clase PUC de una cuenta, a partir de su código de 4 dígitos.

    `None` si el código viene vacío o con un primer dígito fuera del PUC
    estándar (1-9): mejor no clasificar que clasificar mal.
    """
    codigo = (mayor_iii or "").strip()
    if not codigo:
        return None
    try:
        return ClaseCuenta(codigo[0])
    except ValueError:
        return None


def etiqueta_clase(clase: ClaseCuenta) -> str:
    return ETIQUETAS_CLASE[clase]


def es_naturaleza_credito(clase: ClaseCuenta) -> bool:
    return clase in _CLASES_NATURALEZA_CREDITO


def saldo_presentacion(clase: ClaseCuenta | None, final: Decimal) -> Decimal:
    """`FINAL` reexpresado como saldo económico positivo normal de la cuenta."""
    if clase is not None and es_naturaleza_credito(clase):
        return -final
    return final


def es_corriente(mayor_iii: str | None) -> bool | None:
    """Corto plazo por grupo de cuenta (dos dígitos). Ver el supuesto arriba.

    `None` cuando la clase no es Activo ni Pasivo (Patrimonio, Ingreso, Gasto,
    Costos y cuentas de orden no se clasifican por plazo).
    """
    codigo = (mayor_iii or "").strip()
    if len(codigo) < 2:
        return None
    grupo = codigo[:2]
    clase = clasificar(mayor_iii)
    if clase == ClaseCuenta.ACTIVO:
        return grupo in GRUPOS_ACTIVO_CORRIENTE
    if clase == ClaseCuenta.PASIVO:
        return grupo in GRUPOS_PASIVO_CORRIENTE
    return None
