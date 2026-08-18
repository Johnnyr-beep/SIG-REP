"""Vocabulario del dominio SIGREP.

Los valores persistidos son cadenas explícitas y estables: cambiar el nombre de
un miembro de Python nunca debe corromper datos históricos.
"""

from __future__ import annotations

from enum import StrEnum


class Rol(StrEnum):
    """Roles del sistema (§8.4 de la especificación).

    GERENTE lo ve y lo cierra todo, ANALISTA parametriza, JEFE_PDV consulta
    solo sus puntos de venta y CONSULTA es lectura sin restricción de PDV.

    `ADMIN` es el rol de Sistemas y se añadió con el módulo de administración
    de usuarios. Es **superusuario**: puede todo lo que puede GERENTE —ver
    reportes, parametrizar presupuesto y calendario, ejecutar la ingesta,
    cerrar períodos— y además es el **único** que administra cuentas. La razón
    de que también vea el negocio es práctica: Sistemas necesita diagnosticar
    por sí mismo si un reporte muestra bien los datos sin pedir prestada una
    cuenta de gerencia.

    Que sea superusuario no relaja el resto: nadie se administra a sí mismo y
    siempre tiene que quedar un ADMIN activo. Ver
    `app.application.services.usuarios_service`.
    """

    ADMIN = "ADMIN"
    GERENTE = "GERENTE"
    ANALISTA = "ANALISTA"
    JEFE_PDV = "JEFE_PDV"
    CONSULTA = "CONSULTA"

    @property
    def etiqueta(self) -> str:
        return _ETIQUETAS_ROL[self]


_ETIQUETAS_ROL: dict[Rol, str] = {
    Rol.ADMIN: "Administrador de sistemas",
    Rol.GERENTE: "Gerencia",
    Rol.ANALISTA: "Analista",
    Rol.JEFE_PDV: "Jefe de punto de venta",
    Rol.CONSULTA: "Consulta",
}


class AccionUsuario(StrEnum):
    """Operaciones del módulo de administración de usuarios.

    Son el vocabulario de `usuario_auditoria`. Se guardan como cadenas
    explícitas por la misma razón que los roles: renombrar un miembro de Python
    no puede reescribir lo que ya pasó.
    """

    CREAR = "CREAR"
    MODIFICAR = "MODIFICAR"
    ASIGNAR_ALCANCE = "ASIGNAR_ALCANCE"
    ACTIVAR = "ACTIVAR"
    DESACTIVAR = "DESACTIVAR"
    RESTABLECER_CLAVE = "RESTABLECER_CLAVE"

    @property
    def etiqueta(self) -> str:
        return _ETIQUETAS_ACCION[self]


_ETIQUETAS_ACCION: dict[AccionUsuario, str] = {
    AccionUsuario.CREAR: "Alta de usuario",
    AccionUsuario.MODIFICAR: "Modificación de datos",
    AccionUsuario.ASIGNAR_ALCANCE: "Cambio de alcance",
    AccionUsuario.ACTIVAR: "Activación",
    AccionUsuario.DESACTIVAR: "Desactivación",
    AccionUsuario.RESTABLECER_CLAVE: "Restablecimiento de clave",
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
