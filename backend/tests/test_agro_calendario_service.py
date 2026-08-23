"""Calendario agropecuario visible desde la primera ingesta."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.application.services.agro_calendario_service import AgroCalendarioService
from app.application.services.periodos import obtener_o_crear_periodo
from app.infrastructure.models.agro_dimensiones import AgroDimension
from app.infrastructure.models.agro_vocabulario import TipoDimension


def test_listar_muestra_centros_sin_calendario_con_dias_por_defecto(
    sesion: Session,
) -> None:
    periodo = obtener_o_crear_periodo(sesion, "2026-08")
    sesion.add_all(
        [
            AgroDimension(
                tipo=TipoDimension.CENTRO_OPERACION.value,
                clave="301",
                nombre="AGROPECUARIA SANTACRUZ LTDA",
            ),
            AgroDimension(
                tipo=TipoDimension.CENTRO_OPERACION.value,
                clave="302",
                nombre="DISTRIBUCION SANTACRUZ MONTERIA",
            ),
        ]
    )
    sesion.flush()

    resultado = AgroCalendarioService(sesion).listar("2026-08")

    assert [fila.centro for fila in resultado] == ["301", "302"]
    assert [fila.dias_habiles for fila in resultado] == [Decimal("28"), Decimal("28")]
    assert all(fila.derivado for fila in resultado)
    assert sesion.query(AgroDimension).count() == 2
    assert periodo.id is not None
