"""Vocabulario del dominio SIGREP.

Los valores persistidos son cadenas explícitas y estables: cambiar el nombre de
un miembro de Python nunca debe corromper datos históricos.
"""

from __future__ import annotations

from enum import StrEnum


class Rol(StrEnum):
    """Roles del sistema (§8.4 de la especificación).

    SUPUESTO pendiente de confirmar con el usuario: GERENTE lo ve y lo cierra
    todo, ANALISTA parametriza, JEFE_PDV consulta solo sus puntos de venta y
    CONSULTA es lectura sin restricción de PDV.
    """

    GERENTE = "GERENTE"
    ANALISTA = "ANALISTA"
    JEFE_PDV = "JEFE_PDV"
    CONSULTA = "CONSULTA"

    @property
    def etiqueta(self) -> str:
        return _ETIQUETAS_ROL[self]


_ETIQUETAS_ROL: dict[Rol, str] = {
    Rol.GERENTE: "Gerencia",
    Rol.ANALISTA: "Analista",
    Rol.JEFE_PDV: "Jefe de punto de venta",
    Rol.CONSULTA: "Consulta",
}


class Semaforo(StrEnum):
    """Estado del cumplimiento contra el ideal (§4.1).

    `SIN_PRESUPUESTO` es el valor de «no evaluable»: cubre tanto el punto de
    venta que vende sin estar presupuestado (432 EVENTOS BUCARAMANGA) como el
    corte sin calendario cargado. En ambos casos no hay vara contra la cual
    medir y pintar verde o rojo sería inventar.
    """

    VERDE = "VERDE"
    AMARILLO = "AMARILLO"
    ROJO = "ROJO"
    SIN_PRESUPUESTO = "SIN_PRESUPUESTO"


class Medida(StrEnum):
    """Las dos varas del negocio: pesos y kilos (§4.5)."""

    VALOR = "valor"
    KILOS = "kilos"

    @property
    def decimales(self) -> int:
        """Escala de presentación: los importes llevan 2 y los kilos 3."""
        return 2 if self is Medida.VALOR else 3


class EstadoCorrida(StrEnum):
    """Ciclo de vida de una corrida de ingesta (§5)."""

    EN_CURSO = "EN_CURSO"
    COMPLETADA = "COMPLETADA"
    COMPLETADA_CON_RECHAZOS = "COMPLETADA_CON_RECHAZOS"
    FALLIDA = "FALLIDA"


class FuenteIngesta(StrEnum):
    """Origen de la venta ingerida."""

    SIESA = "siesa"
    EXCEL = "excel"


class AgrupacionClientes(StrEnum):
    """Ejes del reporte de clientes y vendedores."""

    CLIENTE = "cliente"
    VENDEDOR = "vendedor"
    CANAL = "canal"
    CONDICION_PAGO = "condicion_pago"
