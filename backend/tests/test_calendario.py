"""Derivación de días trabajados y presupuesto diario (§3.2 y §3.3)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domain.calendario import (
    derivar_dias_trabajados,
    dias_transcurridos,
    presupuesto_diario,
)

D = Decimal


def test_dias_transcurridos_incluye_el_dia_de_corte() -> None:
    """Al corte del 9 de agosto se han trabajado 9 días, no 8."""
    assert dias_transcurridos(2026, 8, date(2026, 8, 9)) == 9


def test_dias_transcurridos_se_satura_fuera_del_mes() -> None:
    """Una fecha de corte heredada de otro período no produce un ideal absurdo."""
    assert dias_transcurridos(2026, 8, date(2026, 7, 15)) == 0
    assert dias_transcurridos(2026, 8, date(2026, 9, 15)) == 31


def test_derivar_dias_trabajados_es_proporcional() -> None:
    """27.5 hábiles × 9/31 días transcurridos = 8.0 días trabajados."""
    assert derivar_dias_trabajados(D("27.5"), 2026, 8, date(2026, 8, 9)) == D("8.0")


def test_derivar_dias_trabajados_al_cierre_del_mes_da_el_mes_completo() -> None:
    assert derivar_dias_trabajados(D("27.5"), 2026, 8, date(2026, 8, 31)) == D("27.5")


def test_derivar_dias_trabajados_sin_calendario_es_none() -> None:
    assert derivar_dias_trabajados(None, 2026, 8, date(2026, 8, 9)) is None


def test_presupuesto_diario_deriva_de_los_dias_habiles() -> None:
    """618 882 592 / 27.5 = 22 504 821.53 diarios para MALAMBO."""
    resultado = presupuesto_diario(D("618882592"), D("27.5"))
    assert resultado is not None
    assert resultado.quantize(D("0.01")) == D("22504821.53")


@pytest.mark.parametrize(("mensual", "habiles"), [(D("100"), None), (None, D("27.5"))])
def test_presupuesto_diario_es_none_sin_parametros(
    mensual: Decimal | None, habiles: Decimal | None
) -> None:
    """Es la línea de referencia del reporte diario: dibujarla en cero engaña."""
    assert presupuesto_diario(mensual, habiles) is None
