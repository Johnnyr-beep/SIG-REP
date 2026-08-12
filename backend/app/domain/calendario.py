"""Derivación de días trabajados y presupuesto diario (§3.2 y §3.3).

Funciones puras: reciben fechas y decimales, devuelven decimales. El servicio de
calendario se encarga de ir a buscar los parámetros a la base.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal

from app.domain.indicadores import dividir

#: Los días hábiles admiten media jornada (27.5, 28.5): un domingo o festivo que
#: abre medio día cuenta 0.5. De ahí que se cuantice a un decimal y no a entero.
DECIMALES_DIAS = 1


def dias_del_mes(anio: int, mes: int) -> int:
    """Días calendario del mes indicado."""
    return monthrange(anio, mes)[1]


def dias_transcurridos(anio: int, mes: int, fecha_corte: date) -> int:
    """Días calendario del mes ya transcurridos a la fecha de corte, con el corte incluido.

    Fuera del mes se satura: antes del día 1 son 0 y después del último día es
    el mes completo. Así una fecha de corte heredada de otro período no produce
    un ideal absurdo.
    """
    total = dias_del_mes(anio, mes)
    if (fecha_corte.year, fecha_corte.month) < (anio, mes):
        return 0
    if (fecha_corte.year, fecha_corte.month) > (anio, mes):
        return total
    return min(fecha_corte.day, total)


def derivar_dias_trabajados(
    dias_habiles: Decimal | None,
    anio: int,
    mes: int,
    fecha_corte: date,
) -> Decimal | None:
    """Reparte los días hábiles del mes en proporción a los días transcurridos.

    SUPUESTO documentado (§8.1): SIGREP guarda el **total** de días hábiles por
    zona, no un calendario día a día, así que la única derivación honesta es la
    proporcional:

        dias_trabajados = dias_habiles × dias_transcurridos / dias_del_mes

    El usuario puede sobrescribir el resultado desde la pantalla de calendario,
    y esa sobreescritura manda: cuando el negocio sabe que el lunes festivo no
    se abrió, ese dato vale más que cualquier regla.
    """
    if dias_habiles is None:
        return None
    total = Decimal(dias_del_mes(anio, mes))
    transcurridos = Decimal(dias_transcurridos(anio, mes, fecha_corte))
    proporcion = dividir(transcurridos, total)
    if proporcion is None:  # pragma: no cover - un mes nunca tiene cero días
        return None
    return (dias_habiles * proporcion).quantize(Decimal(1).scaleb(-DECIMALES_DIAS))


def presupuesto_diario(
    presupuesto_mensual: Decimal | None, dias_habiles: Decimal | None
) -> Decimal | None:
    """`presupuesto_mensual / dias_habiles` (§3.3).

    `None` si la zona no tiene días hábiles parametrizados: es la línea de
    referencia del reporte de venta diaria y dibujarla en cero engañaría.
    """
    return dividir(presupuesto_mensual, dias_habiles)
